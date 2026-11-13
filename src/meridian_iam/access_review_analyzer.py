#!/usr/bin/env python3
"""Access review analyzer: finds the defects a recertification campaign is supposed to catch.

Inputs : application access export (CSV), HR feed (CSV), role catalog, SoD rules.
Outputs: findings.csv  (doubles as the reviewer worksheet: decision / reviewer columns are blank)
         findings_summary.json, access_review_report.md

Finding types
  ORPHAN_ACCOUNT                  no HR record and no owner
  LEAVER_ACTIVE_ACCESS            HR says terminated; access still present
  LEAVER_POST_TERMINATION_LOGIN   ...and the account was used after the end date (treat as incident)
  DORMANT_ACCOUNT                 active employee, no sign-in for more than --dormant-days
  EXCESS_ENTITLEMENT              entitlement outside the role baseline (privilege creep)
  SOD_VIOLATION                   toxic combination defined in sod_rules.json
  PRIVILEGED_NO_MFA               privileged entitlement on an account without MFA
  SERVICE_ACCOUNT_NO_OWNER        non-human account without an accountable owner
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from meridian_iam.iamlib import (
    DEFAULT_CATALOG,
    DEFAULT_SOD,
    ROOT,
    baseline_entitlements,
    is_privileged,
    load_catalog,
    load_sod_rules,
    parse_date,
    read_csv,
    sod_conflicts,
    write_csv,
)

RECOMMENDED = {
    "ORPHAN_ACCOUNT": "Disable immediately; identify owner or delete after retention period",
    "LEAVER_ACTIVE_ACCESS": "Revoke all access; run leaver checklist; confirm HR end date",
    "LEAVER_POST_TERMINATION_LOGIN": "Open security incident; revoke access; review activity since end date",
    "DORMANT_ACCOUNT": "Disable; remove access if no business justification within 14 days",
    "EXCESS_ENTITLEMENT": "Revoke entitlement unless manager provides documented exception",
    "SOD_VIOLATION": "Remove one side of the conflict or record an approved compensating control",
    "PRIVILEGED_NO_MFA": "Require MFA registration within 24h or suspend privileged access",
    "SERVICE_ACCOUNT_NO_OWNER": "Assign an accountable owner or decommission",
}
CONTROLS = {
    "ORPHAN_ACCOUNT": "NIST AC-2, AC-2(3); ISO 27001 A.5.16, A.5.18; SOC 2 CC6.2",
    "LEAVER_ACTIVE_ACCESS": "NIST PS-4, AC-2; ISO 27001 A.6.5; SOC 2 CC6.2",
    "LEAVER_POST_TERMINATION_LOGIN": "NIST PS-4, IR-4; ISO 27001 A.6.5, A.5.25; SOC 2 CC7.3",
    "DORMANT_ACCOUNT": "NIST AC-2(3); ISO 27001 A.5.18; SOC 2 CC6.2",
    "EXCESS_ENTITLEMENT": "NIST AC-6, AC-2; ISO 27001 A.5.15, A.5.18; SOC 2 CC6.3",
    "SOD_VIOLATION": "NIST AC-5; ISO 27001 A.5.3; SOC 2 CC6.3; SOX ITGC access / SoD",
    "PRIVILEGED_NO_MFA": "NIST IA-2(1), AC-6(5); ISO 27001 A.8.2, A.8.5; SOC 2 CC6.1",
    "SERVICE_ACCOUNT_NO_OWNER": "NIST AC-2, IA-4; ISO 27001 A.5.16; SOC 2 CC6.2",
}
FINDING_FIELDS = [
    "finding_id",
    "severity",
    "type",
    "account_id",
    "employee_id",
    "entitlements",
    "detail",
    "recommended_action",
    "control_refs",
    "decision",
    "reviewer",
    "decision_date",
]
SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def load_hr(path) -> dict[str, dict]:
    return {r["employee_id"].strip(): r for r in read_csv(path)}


def analyze(
    access_rows: list[dict], hr: dict[str, dict], catalog: dict, rules: list[dict], as_of: date, dormant_days: int = 90
) -> list[dict]:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for row in access_rows:
        by_account[row["account_id"]].append(row)
    findings: list[dict] = []

    def add(ftype, sev, acct, eid, ents, detail):
        findings.append(
            {
                "type": ftype,
                "severity": sev,
                "account_id": acct,
                "employee_id": eid,
                "entitlements": ";".join(sorted(ents)),
                "detail": detail,
                "recommended_action": RECOMMENDED[ftype],
                "control_refs": CONTROLS[ftype],
                "decision": "",
                "reviewer": "",
                "decision_date": "",
            }
        )

    for acct, rows in sorted(by_account.items()):
        first = rows[0]
        eid = (first["employee_id"] or "").strip()
        ents = sorted({r["entitlement"] for r in rows})
        priv = [e for e in ents if is_privileged(e, catalog)]
        logins = [parse_date(r["last_login"]) for r in rows if (r["last_login"] or "").strip()]
        last_login = max(logins) if logins else None  # no recorded login at all is possible in a real export

        if first["account_type"] == "service":
            if not (first["owner"] or "").strip():
                add("SERVICE_ACCOUNT_NO_OWNER", "High", acct, eid, ents, "Service account has no owner")
            continue

        hr_rec = hr.get(eid) if eid else None
        if hr_rec is None:
            add(
                "ORPHAN_ACCOUNT",
                "Critical" if priv else "High",
                acct,
                eid,
                ents,
                f"No HR record, no owner; last login {last_login or 'never'}" + (f"; privileged: {', '.join(priv)}" if priv else ""),
            )
            continue

        end = parse_date(hr_rec.get("end_date"))
        if hr_rec["status"] == "Terminated" or (end and end <= as_of):
            add("LEAVER_ACTIVE_ACCESS", "Critical", acct, eid, ents, f"Terminated {end}; {len(ents)} entitlement(s) still active")
            if end and last_login and last_login > end:
                add(
                    "LEAVER_POST_TERMINATION_LOGIN",
                    "Critical",
                    acct,
                    eid,
                    ents,
                    f"Last login {last_login} is {(last_login - end).days} day(s) after termination",
                )
            continue

        if last_login is None:
            add("DORMANT_ACCOUNT", "High" if priv else "Medium", acct, eid, ents, "No login on record")
        elif (idle := (as_of - last_login).days) > dormant_days:
            add("DORMANT_ACCOUNT", "High" if priv else "Medium", acct, eid, ents, f"No login for {idle} days (threshold {dormant_days})")

        allowed = baseline_entitlements(hr_rec["job_title"], catalog)
        extra = [e for e in ents if e not in allowed]
        if extra:
            add(
                "EXCESS_ENTITLEMENT",
                "High" if any(is_privileged(e, catalog) for e in extra) else "Medium",
                acct,
                eid,
                extra,
                f"Outside baseline for {hr_rec['job_title']}",
            )

        for rule in sod_conflicts(ents, rules):
            add(
                "SOD_VIOLATION",
                rule["severity"],
                acct,
                eid,
                [rule["entitlement_a"], rule["entitlement_b"]],
                f"{rule['id']}: {rule['rationale']}",
            )

        if priv and any(r["mfa_registered"].upper() == "FALSE" for r in rows):
            add("PRIVILEGED_NO_MFA", "Critical", acct, eid, priv, "Privileged entitlement without MFA registration")

    findings.sort(key=lambda f: (SEV_ORDER[f["severity"]], f["type"], f["account_id"]))
    for i, f in enumerate(findings, start=1):
        f["finding_id"] = f"F-{i:04d}"
    return findings


def summarise(findings: list[dict], access_rows: list[dict]) -> dict:
    accounts = {r["account_id"] for r in access_rows}
    by_type = Counter(f["type"] for f in findings)
    return {
        "accounts_reviewed": len(accounts),
        "entitlement_rows_reviewed": len(access_rows),
        "total_findings": len(findings),
        "accounts_with_findings": len({f["account_id"] for f in findings}),
        "by_severity": dict(sorted(Counter(f["severity"] for f in findings).items(), key=lambda kv: SEV_ORDER[kv[0]])),
        "by_type": dict(sorted(by_type.items())),
    }


def write_report(path: Path, summary: dict, findings: list[dict], as_of: date) -> None:
    lines = [
        f"# Access Review Report - as of {as_of}",
        "",
        f"Reviewed **{summary['accounts_reviewed']}** accounts / **{summary['entitlement_rows_reviewed']}** entitlement assignments. "
        f"Found **{summary['total_findings']}** findings across **{summary['accounts_with_findings']}** accounts.",
        "",
        "## Findings by type",
        "",
        "| Type | Count | Recommended action |",
        "|---|---:|---|",
    ]
    for t, n in summary["by_type"].items():
        lines.append(f"| {t} | {n} | {RECOMMENDED[t]} |")
    lines += ["", "## Findings by severity", "", "| Severity | Count |", "|---|---:|"]
    lines += [f"| {s} | {n} |" for s, n in summary["by_severity"].items()]
    lines += ["", "## Critical findings", "", "| ID | Type | Account | Detail |", "|---|---|---|---|"]
    lines += [f"| {f['finding_id']} | {f['type']} | {f['account_id']} | {f['detail']} |" for f in findings if f["severity"] == "Critical"]
    lines += ["", "_Produced by access_review_analyzer.py. Reviewer decisions go in findings.csv._", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--access", default=str(ROOT / "data" / "app_access_export.csv"))
    ap.add_argument("--hr-feed", default=str(ROOT / "data" / "hr_feed_day0.csv"))
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    ap.add_argument("--sod-rules", default=str(DEFAULT_SOD))
    ap.add_argument("--as-of", type=parse_date, default=date(2026, 9, 30))
    ap.add_argument("--dormant-days", type=int, default=90)
    ap.add_argument("--out", default=str(ROOT / "out"))
    args = ap.parse_args(argv)

    access = read_csv(args.access)
    findings = analyze(
        access, load_hr(args.hr_feed), load_catalog(args.catalog), load_sod_rules(args.sod_rules), args.as_of, args.dormant_days
    )
    summary = summarise(findings, access)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "findings.csv", findings, FINDING_FIELDS)
    (out / "findings_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(out / "access_review_report.md", summary, findings, args.as_of)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
