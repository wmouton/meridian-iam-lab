#!/usr/bin/env python3
"""Joiner / Mover / Leaver (JML) lifecycle engine, offline version.

Reads an HR feed (the source of truth), compares it with a directory snapshot and produces an
ordered action plan. Dry-run by default; --apply commits the plan to the snapshot and appends
to an audit log. The PowerShell script Invoke-JmlSync.ps1 implements the same rules against
Microsoft Entra ID through Microsoft Graph.

Design rules (see docs/02-identity-lifecycle.md):
  * HR is authoritative; the directory never writes back to HR.
  * Fail safe: malformed or ambiguous rows are quarantined and produce NO action.
  * Circuit breaker: abort if a run would disable an abnormal share of accounts, or if the feed
    looks truncated compared with the previous run (override with --force).
  * Idempotent: running the same feed twice produces zero actions the second time.
  * Movers lose entitlements of the old role (no privilege creep) and the engine reports any
    segregation-of-duties conflict that would have existed had the old access been kept.

Exit codes: 0 ok | 2 circuit breaker tripped | 3 feed invalid
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from meridian_iam.iamlib import (
    DEFAULT_CATALOG,
    DEFAULT_SOD,
    ROOT,
    group_names,
    is_privileged,
    load_catalog,
    load_sod_rules,
    parse_date,
    sod_conflicts,
)

LOG = logging.getLogger("jml")

PREBOARD_DAYS = 7  # accounts are created disabled this many days before start date
RETENTION_DAYS = 30  # disabled accounts are deleted after this many days
CIRCUIT_BREAKER_PCT = 5.0  # max % of enabled accounts one run may disable/delete
FEED_TRUNCATION_RATIO = 0.90
REQUIRED_COLUMNS = ["employee_id", "upn", "department", "job_title", "manager_id", "employment_type", "status", "start_date", "end_date"]


class FeedError(Exception):
    """The HR feed cannot be processed at all (missing columns, unreadable)."""


class CircuitBreakerTripped(Exception):
    """The plan looks dangerous and needs a human decision."""


@dataclass
class Action:
    type: str
    employee_id: str
    upn: str
    detail: dict = field(default_factory=dict)
    severity: str = "info"
    target: dict | None = None  # desired state; used by apply(), not written to the audit detail

    def to_log(self) -> dict:
        return {"action": self.type, "employee_id": self.employee_id, "upn": self.upn, "severity": self.severity, "detail": self.detail}


# ----------------------------------------------------------------------------- feed loading
def validate_row(row: dict, catalog: dict) -> str | None:
    """Return a quarantine reason or None if the row is valid."""
    if (row.get("status") or "").strip() not in ("Active", "Terminated"):
        return "status must be Active or Terminated"
    if "@" not in (row.get("upn") or ""):
        return "invalid upn"
    for col in ("start_date", "end_date"):
        try:
            parse_date(row.get(col))
        except ValueError:
            return f"invalid {col}: {row.get(col)!r}"
    if not parse_date(row.get("start_date")):
        return "start_date is required"
    title = (row.get("job_title") or "").strip()
    spec = catalog["titles"].get(title)
    if spec is None:
        return f"unknown job_title: {title!r}"
    if spec["department"] != (row.get("department") or "").strip():
        return f"department {row.get('department')!r} does not match job_title {title!r}"
    return None


def load_hr_feed(path: Path | str, catalog: dict) -> tuple[dict[str, dict], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise FeedError(f"HR feed is missing required columns: {missing}")
        rows = list(reader)
    by_id: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for line_no, row in enumerate(rows, start=2):
        by_id[(row.get("employee_id") or "").strip()].append((line_no, row))
    records: dict[str, dict] = {}
    quarantine: list[dict] = []
    for eid, items in by_id.items():
        if not eid:
            quarantine += [{"line": ln, "employee_id": "", "reason": "missing employee_id", "row": r} for ln, r in items]
        elif len(items) > 1:
            quarantine += [{"line": ln, "employee_id": eid, "reason": "duplicate employee_id", "row": r} for ln, r in items]
        else:
            ln, row = items[0]
            reason = validate_row(row, catalog)
            if reason:
                quarantine.append({"line": ln, "employee_id": eid, "reason": reason, "row": row})
                continue
            rec = {k: (v or "").strip() for k, v in row.items() if k is not None}
            rec["start_date"] = parse_date(rec["start_date"])
            rec["end_date"] = parse_date(rec["end_date"])
            records[eid] = rec
    return records, sorted(quarantine, key=lambda q: q["line"])


# ----------------------------------------------------------------------------- desired state
def desired_state(rec: dict, catalog: dict, as_of: date) -> dict | None:
    """What the directory should look like for this HR record. None = no account yet."""
    spec = catalog["titles"][rec["job_title"]]
    base = {
        "department": rec["department"],
        "job_title": rec["job_title"],
        "manager_id": rec["manager_id"],
        "business_role": spec["business_role"],
    }
    is_leaver = rec["status"] == "Terminated" or (rec["end_date"] is not None and rec["end_date"] <= as_of)
    if is_leaver:
        return {**base, "lifecycle": "leaver", "enabled": False, "entitlements": [], "groups": []}
    days_to_start = (rec["start_date"] - as_of).days
    if days_to_start > PREBOARD_DAYS:
        return None
    ents = sorted(set(catalog["birthright_entitlements"]) | set(spec["entitlements"]))
    return {
        **base,
        "lifecycle": "preboard" if days_to_start > 0 else "active",
        "enabled": days_to_start <= 0,
        "entitlements": ents,
        "groups": group_names(rec["department"], spec["business_role"], ents),
    }


# ----------------------------------------------------------------------------- planning
def plan(
    records: dict[str, dict], directory: dict, catalog: dict, rules: list[dict], as_of: date, quarantined_ids: frozenset[str] = frozenset()
) -> list[Action]:
    accounts = directory["accounts"]
    actions: list[Action] = []

    def manager_departed(want: dict) -> bool:
        mgr = records.get(want["manager_id"])
        if not mgr:
            return False
        state = desired_state(mgr, catalog, as_of)
        return bool(state and state["lifecycle"] == "leaver")

    for eid in sorted(records):
        rec = records[eid]
        want = desired_state(rec, catalog, as_of)
        acct = accounts.get(eid)
        if want is None:
            continue

        if acct is None:
            if want["lifecycle"] == "leaver":
                continue  # never had an account: nothing to do
            actions.append(
                Action(
                    "CREATE",
                    eid,
                    rec["upn"],
                    {
                        "enabled": want["enabled"],
                        "lifecycle": want["lifecycle"],
                        "job_title": want["job_title"],
                        "department": want["department"],
                        "business_role": want["business_role"],
                        "entitlements": want["entitlements"],
                    },
                    target=want,
                )
            )
            for r in sod_conflicts(want["entitlements"], rules):
                actions.append(Action("FLAG_SOD", eid, rec["upn"], {"rule": r["id"], "context": "role design"}, "high"))
            if manager_departed(want):
                actions.append(Action("FLAG_MANAGER", eid, rec["upn"], {"manager_id": want["manager_id"]}, "medium"))
            continue

        if want["lifecycle"] == "leaver":
            if acct["enabled"] or acct["entitlements"] or acct["groups"]:
                sev = "high" if any(is_privileged(e, catalog) for e in acct["entitlements"]) else "medium"
                actions.append(
                    Action(
                        "DISABLE",
                        eid,
                        rec["upn"],
                        {
                            "revoke_sessions": True,
                            "removed_entitlements": sorted(acct["entitlements"]),
                            "removed_groups": sorted(acct["groups"]),
                            "retention_days": RETENTION_DAYS,
                            "end_date": rec["end_date"].isoformat() if rec["end_date"] else None,
                        },
                        sev,
                        target=want,
                    )
                )
            elif acct.get("disabled_on") and (as_of - parse_date(acct["disabled_on"])).days >= RETENTION_DAYS:
                actions.append(Action("DELETE", eid, rec["upn"], {"disabled_on": acct["disabled_on"]}))
            continue

        if acct.get("lifecycle") == "leaver":
            actions.append(
                Action("FLAG_REHIRE", eid, rec["upn"], {"note": "Account previously offboarded; manual re-enable required"}, "medium")
            )
            continue

        org_changed = acct["department"] != want["department"] or acct["job_title"] != want["job_title"]
        added = sorted(set(want["entitlements"]) - set(acct["entitlements"]))
        removed = sorted(set(acct["entitlements"]) - set(want["entitlements"]))
        if org_changed:
            retained_conflicts = {r["id"] for r in sod_conflicts(set(acct["entitlements"]) | set(want["entitlements"]), rules)}
            target_conflicts = {r["id"] for r in sod_conflicts(want["entitlements"], rules)}
            prevented = sorted(retained_conflicts - target_conflicts)
            actions.append(
                Action(
                    "MOVER",
                    eid,
                    rec["upn"],
                    {
                        "from": {"department": acct["department"], "job_title": acct["job_title"]},
                        "to": {"department": want["department"], "job_title": want["job_title"]},
                        "added_entitlements": added,
                        "removed_entitlements": removed,
                        "manager_id": want["manager_id"],
                        "sod_conflicts_prevented": prevented,
                    },
                    "high" if prevented else "info",
                    target=want,
                )
            )
            if manager_departed(want):
                actions.append(Action("FLAG_MANAGER", eid, rec["upn"], {"manager_id": want["manager_id"]}, "medium"))
        elif added or removed:
            actions.append(
                Action("DRIFT", eid, rec["upn"], {"added_entitlements": added, "removed_entitlements": removed}, "medium", target=want)
            )
        elif acct["manager_id"] != want["manager_id"]:
            actions.append(Action("UPDATE", eid, rec["upn"], {"manager_id": want["manager_id"]}, target=want))
        if want["enabled"] and not acct["enabled"]:
            actions.append(Action("ENABLE", eid, rec["upn"], {"reason": "start date reached"}, target=want))

    known = set(records) | set(quarantined_ids)
    for eid, acct in sorted(accounts.items()):
        if acct.get("type", "user") != "service" and eid not in known:
            actions.append(Action("FLAG_ORPHAN", eid, acct["upn"], {"enabled": acct["enabled"]}, "high"))
    return actions


def check_safety(actions: list[Action], directory: dict, feed_rows: int, pct: float = CIRCUIT_BREAKER_PCT) -> list[str]:
    problems = []
    enabled = sum(1 for a in directory["accounts"].values() if a["enabled"])
    destructive = sum(1 for a in actions if a.type in ("DISABLE", "DELETE"))
    if enabled >= 20 and destructive * 100.0 / enabled > pct:
        problems.append(
            f"{destructive} disable/delete actions is {destructive * 100.0 / enabled:.1f}% of {enabled} enabled accounts (limit {pct}%)"
        )
    previous = directory.get("meta", {}).get("last_feed_rows")
    if previous and feed_rows < previous * FEED_TRUNCATION_RATIO:
        problems.append(f"HR feed has {feed_rows} rows versus {previous} on the previous run - possible truncation")
    return problems


# ----------------------------------------------------------------------------- apply
def apply_actions(actions: list[Action], directory: dict, as_of: date, feed_rows: int) -> None:
    accounts = directory["accounts"]
    for a in actions:
        t, eid, want = a.type, a.employee_id, a.target
        if t == "CREATE":
            accounts[eid] = {
                "employee_id": eid,
                "upn": a.upn,
                "type": "user",
                "enabled": want["enabled"],
                "lifecycle": want["lifecycle"],
                "department": want["department"],
                "job_title": want["job_title"],
                "manager_id": want["manager_id"],
                "business_role": want["business_role"],
                "entitlements": want["entitlements"],
                "groups": want["groups"],
                "created_on": as_of.isoformat(),
                "disabled_on": None,
            }
        elif t in ("MOVER", "DRIFT", "UPDATE"):
            accounts[eid].update({k: want[k] for k in ("department", "job_title", "manager_id", "business_role", "entitlements", "groups")})
        elif t == "ENABLE":
            accounts[eid].update({"enabled": True, "lifecycle": "active"})
        elif t == "DISABLE":
            accounts[eid].update(
                {
                    "enabled": False,
                    "lifecycle": "leaver",
                    "entitlements": [],
                    "groups": [],
                    "disabled_on": accounts[eid].get("disabled_on") or as_of.isoformat(),
                }
            )
        elif t == "DELETE":
            del accounts[eid]
    directory.setdefault("meta", {}).update({"last_feed_rows": feed_rows, "last_run_as_of": as_of.isoformat()})


# ----------------------------------------------------------------------------- I/O + CLI
def load_directory(path: Path) -> dict:
    if not path.exists():
        return {"meta": {}, "accounts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_directory(path: Path, directory: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(directory, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX and Windows


def summarise(actions: list[Action], quarantine: list[dict], records: dict, as_of: date) -> dict:
    counts = Counter(a.type for a in actions)
    upcoming = sorted(
        r["employee_id"] for r in records.values() if r["status"] == "Active" and r["end_date"] and 0 < (r["end_date"] - as_of).days <= 14
    )
    return {
        "as_of": as_of.isoformat(),
        "actions": dict(sorted(counts.items())),
        "total_actions": len(actions),
        "quarantined_rows": len(quarantine),
        "sod_conflicts_prevented_on_movers": sum(len(a.detail.get("sod_conflicts_prevented", [])) for a in actions if a.type == "MOVER"),
        "upcoming_leavers_14d": upcoming,
    }


def run(
    hr_feed,
    directory_path,
    catalog_path=DEFAULT_CATALOG,
    sod_path=DEFAULT_SOD,
    as_of: date | None = None,
    apply: bool = False,
    force: bool = False,
    out_dir: Path | str | None = None,
) -> dict:
    as_of = as_of or date.today()
    catalog, rules = load_catalog(catalog_path), load_sod_rules(sod_path)
    records, quarantine = load_hr_feed(hr_feed, catalog)
    directory_path = Path(directory_path)
    directory = load_directory(directory_path)
    actions = plan(records, directory, catalog, rules, as_of, frozenset(q["employee_id"] for q in quarantine if q["employee_id"]))
    feed_rows = len(records) + len(quarantine)
    problems = check_safety(actions, directory, feed_rows)
    summary = summarise(actions, quarantine, records, as_of)
    summary["mode"] = "apply" if apply else "dry-run"
    summary["safety_problems"] = problems

    out = Path(out_dir) if out_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "jml_actions.json").write_text(json.dumps([a.to_log() for a in actions], indent=2), encoding="utf-8")
        (out / "jml_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        with open(out / "quarantine.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["line", "employee_id", "reason"])
            w.writerows([[q["line"], q["employee_id"], q["reason"]] for q in quarantine])

    if problems and not force:
        raise CircuitBreakerTripped("; ".join(problems))
    if problems:
        LOG.warning("Safety checks overridden with --force: %s", "; ".join(problems))

    if apply:
        apply_actions(actions, directory, as_of, feed_rows)
        save_directory(directory_path, directory)
        if out:
            run_id = uuid.uuid4().hex[:8]
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with open(out / "audit.jsonl", "a", encoding="utf-8") as fh:
                for a in actions:
                    fh.write(json.dumps({"ts": ts, "run_id": run_id, "as_of": as_of.isoformat(), **a.to_log()}) + "\n")
    summary["_actions"] = actions
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hr-feed", required=True)
    ap.add_argument("--directory", default=str(ROOT / "state" / "directory.json"))
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    ap.add_argument("--sod-rules", default=str(DEFAULT_SOD))
    ap.add_argument("--as-of", type=parse_date, default=None, help="Processing date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--apply", action="store_true", help="Commit changes (default is dry-run)")
    ap.add_argument("--force", action="store_true", help="Override circuit breaker")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    try:
        summary = run(args.hr_feed, args.directory, args.catalog, args.sod_rules, args.as_of, args.apply, args.force, args.out)
    except FeedError as exc:
        LOG.error("Feed invalid: %s", exc)
        return 3
    except CircuitBreakerTripped as exc:
        LOG.error("CIRCUIT BREAKER: %s. Nothing was changed. Review the feed or re-run with --force.", exc)
        return 2
    summary.pop("_actions", None)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
