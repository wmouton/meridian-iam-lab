#!/usr/bin/env python3
"""Deterministic synthetic data generator for the Meridian IAM lab.

Produces (in --out, default ./data):
  hr_feed_day0.csv          Baseline HR feed: 200 active + 9 historical leavers
  hr_feed_day30.csv         Thirty days later: joiners, movers, leavers, bad rows
  app_access_export.csv     Application access export seeded with known defects
  ground_truth.json         The answer key used by the automated tests
  role_matrix.csv           Role -> entitlement matrix generated from the catalog

Everything is seeded, so every run produces identical files.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from meridian_iam.iamlib import (
    HR_FIELDS,
    ROOT,
    baseline_entitlements,
    is_privileged,
    load_catalog,
    load_sod_rules,
    sod_conflicts,
    write_csv,
)

SEED = 20261109
DAY0 = date(2026, 9, 30)
DAY30 = date(2026, 10, 30)

FIRST = [
    "Thabo",
    "Ayesha",
    "Liam",
    "Naledi",
    "Oliver",
    "Zanele",
    "Sipho",
    "Emma",
    "Kagiso",
    "Priya",
    "Daniel",
    "Lerato",
    "Michael",
    "Fatima",
    "Johan",
    "Chloe",
    "Themba",
    "Sarah",
    "Pieter",
    "Nomsa",
    "Ethan",
    "Amara",
    "Riaan",
    "Megan",
    "Bongani",
    "Hannah",
    "Tariq",
    "Lindiwe",
    "Ruan",
    "Olivia",
    "Kabelo",
    "Isabella",
    "Mpho",
    "Nathan",
    "Palesa",
    "Jacob",
    "Ntombi",
    "Samuel",
    "Thandi",
    "Ryan",
]
LAST = [
    "Nkosi",
    "Patel",
    "Smith",
    "Dlamini",
    "van der Merwe",
    "Mokoena",
    "Naidoo",
    "Jones",
    "Khumalo",
    "Botha",
    "Williams",
    "Sithole",
    "Pretorius",
    "Moyo",
    "Brown",
    "Mahlangu",
    "Govender",
    "Taylor",
    "Molefe",
    "Du Plessis",
    "Ndlovu",
    "Fourie",
    "Mthembu",
    "Evans",
    "Zulu",
    "Coetzee",
    "Singh",
    "Radebe",
    "Jansen",
    "Mabaso",
    "Wilson",
    "Ferreira",
    "Tshabalala",
    "Adams",
    "Ngubane",
    "Roberts",
    "Cele",
    "Venter",
    "Maseko",
    "Clarke",
]
LOCATIONS = ["Johannesburg", "Cape Town", "Durban", "London", "Remote"]
SAFE_EXCESS = ["CRM:Rep", "ATS:Recruiter", "CLM:Contributor", "WMS:Read", "ITSM:Agent"]


def _slug(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _new_person(rng, catalog, used_upn, emp_no, title, status="Active"):
    spec = catalog["titles"][title]
    while True:
        first, last = rng.choice(FIRST), rng.choice(LAST)
        upn = f"{_slug(first)}.{_slug(last)}@{catalog['company']['domain']}"
        if upn not in used_upn:
            used_upn.add(upn)
            break
    contractor = rng.random() < 0.08 and not spec["is_manager"]
    return {
        "employee_id": f"E{emp_no}",
        "first_name": first,
        "last_name": last,
        "upn": upn,
        "department": spec["department"],
        "job_title": title,
        "manager_id": "",
        "location": rng.choice(LOCATIONS),
        "employment_type": "Contractor" if contractor else "Employee",
        "status": status,
        "start_date": (DAY0 - timedelta(days=rng.randint(60, 3000))).isoformat(),
        "end_date": (DAY0 + timedelta(days=rng.randint(90, 365))).isoformat() if contractor else "",
    }


def _assign_managers(rng, catalog, people):
    ceo = next(p for p in people if p["job_title"] == "Executive Leader")
    managers_by_dept: dict[str, list[dict]] = {}
    for p in people:
        if catalog["titles"][p["job_title"]]["is_manager"] and p["status"] == "Active":
            managers_by_dept.setdefault(p["department"], []).append(p)
    for p in people:
        if p is ceo:
            p["manager_id"] = ""
        elif catalog["titles"][p["job_title"]]["is_manager"]:
            p["manager_id"] = ceo["employee_id"]
        else:
            pool = managers_by_dept[p["department"]]
            p["manager_id"] = rng.choice(pool)["employee_id"]


MANAGER_TITLES: set[str] = set()


def build_hr_feeds(rng, catalog):
    MANAGER_TITLES.clear()
    MANAGER_TITLES.update(t for t, s in catalog["titles"].items() if s["is_manager"])
    used_upn: set[str] = set()
    people, n = [], 10001
    for title, spec in catalog["titles"].items():
        for _ in range(spec["headcount"]):
            people.append(_new_person(rng, catalog, used_upn, n, title))
            n += 1
    # Historical leavers (already terminated before day 0)
    leaver_titles = [t for t, s in catalog["titles"].items() if not s["is_manager"]]
    historical = []
    for i in range(9):
        p = _new_person(rng, catalog, used_upn, 10201 + i, rng.choice(leaver_titles), status="Terminated")
        p["employment_type"] = "Employee"
        p["end_date"] = (DAY0 - timedelta(days=rng.randint(20, 200))).isoformat()
        p["start_date"] = (DAY0 - timedelta(days=rng.randint(400, 3000))).isoformat()
        historical.append(p)
    people_all = people + historical
    _assign_managers(rng, catalog, people_all)
    day0 = sorted(people_all, key=lambda r: r["employee_id"])
    return day0, people, historical, used_upn


def build_day30(rng, catalog, day0, active, used_upn):
    rows = [dict(r) for r in day0]
    by_id = {r["employee_id"]: r for r in rows}
    changes = {"joiners": [], "movers": [], "leavers": [], "scheduled_leavers": [], "bad_rows": [], "sod_prevented_movers": []}
    taken: set[str] = set()

    def pick(pred):
        cands = [
            r
            for r in sorted(by_id.values(), key=lambda r: r["employee_id"])
            if r["status"] == "Active" and r["employee_id"] not in taken and pred(r)
        ]
        choice = rng.choice(cands)
        taken.add(choice["employee_id"])
        return choice

    non_mgr = lambda r: r["job_title"] not in MANAGER_TITLES  # noqa: E731

    # Leavers: 3 terminated, 1 contractor reaching end date today, 1 scheduled (future) notice
    for _ in range(3):
        r = pick(non_mgr)
        r["status"] = "Terminated"
        r["end_date"] = (DAY30 - timedelta(days=rng.randint(0, 2))).isoformat()
        changes["leavers"].append(r["employee_id"])
    r = pick(lambda x: non_mgr(x) and x["employment_type"] == "Contractor")
    r["end_date"] = DAY30.isoformat()
    changes["leavers"].append(r["employee_id"])
    r = pick(non_mgr)
    r["end_date"] = (DAY30 + timedelta(days=14)).isoformat()
    changes["scheduled_leavers"].append(r["employee_id"])

    # Scripted movers that would create an SoD conflict if old access were retained
    def move(rec, new_title):
        spec = catalog["titles"][new_title]
        rec["job_title"], rec["department"] = new_title, spec["department"]
        pool = [
            p
            for p in rows
            if p["department"] == spec["department"]
            and p["status"] == "Active"
            and p["job_title"] in MANAGER_TITLES
            and p["employee_id"] != rec["employee_id"]
        ]
        rec["manager_id"] = rng.choice(pool)["employee_id"]
        changes["movers"].append(rec["employee_id"])

    ap = pick(lambda r: r["job_title"] == "AP Specialist")
    move(ap, "Finance Manager")
    changes["sod_prevented_movers"].append(ap["employee_id"])
    pay = pick(lambda r: r["job_title"] == "Payroll Specialist")
    move(pay, "HR Manager")
    changes["sod_prevented_movers"].append(pay["employee_id"])
    # 2 promotions + 4 cross-department transfers
    for _ in range(2):
        r = pick(lambda x: x["job_title"] in ("Account Executive", "Helpdesk Analyst", "Operations Analyst"))
        move(
            r,
            {"Account Executive": "Sales Manager", "Helpdesk Analyst": "IT Manager", "Operations Analyst": "Operations Manager"}[
                r["job_title"]
            ],
        )
    for new_title in ("Recruiter", "Security Analyst", "Paralegal", "Sales Ops Analyst"):
        src = pick(
            lambda x, new_title=new_title: (
                non_mgr(x)
                and x["job_title"] != new_title
                and x["department"] != catalog["titles"][new_title]["department"]
                and x["job_title"] not in ("AP Specialist", "Payroll Specialist")
            )
        )
        move(src, new_title)

    # Joiners: three start now or earlier (enabled), three within the pre-boarding window (disabled)
    join_titles = ["Accountant", "Account Executive", "Helpdesk Analyst", "Logistics Coordinator", "Recruiter", "Security Analyst"]
    for i, (offset, title) in enumerate(zip([-3, -1, 0, 2, 4, 6], join_titles, strict=True)):
        p = _new_person(rng, catalog, used_upn, 10301 + i, title)
        p["employment_type"] = "Employee"
        p["end_date"] = ""
        p["start_date"] = (DAY30 + timedelta(days=offset)).isoformat()
        pool = [
            x
            for x in rows
            if x["department"] == p["department"]
            and x["status"] == "Active"
            and x["job_title"] in MANAGER_TITLES
            and x["employee_id"] not in changes["leavers"]
        ]
        p["manager_id"] = rng.choice(pool)["employee_id"]
        rows.append(p)
        changes["joiners"].append(p["employee_id"])

    # Bad rows: a duplicate employee id (ambiguous -> quarantined) and a malformed date
    dup_src = pick(non_mgr)
    dup = dict(dup_src)
    dup["department"], dup["job_title"] = "Finance", "Accountant"
    rows.append(dup)
    changes["bad_rows"].append(dup_src["employee_id"])
    bad = _new_person(rng, catalog, used_upn, 10399, "Paralegal")
    bad["start_date"] = "31/13/2026"
    bad["manager_id"] = rng.choice([x for x in rows if x["department"] == "Legal" and x["job_title"] in MANAGER_TITLES])["employee_id"]
    rows.append(bad)
    changes["bad_rows"].append(bad["employee_id"])
    return rows, changes


ACCESS_FIELDS = [
    "account_id",
    "employee_id",
    "display_name",
    "app",
    "entitlement",
    "account_type",
    "owner",
    "granted_date",
    "last_login",
    "mfa_registered",
]


def build_access_export(rng, catalog, rules, day0, historical):
    active = [p for p in day0 if p["status"] == "Active"]
    ents_by_emp = {p["employee_id"]: sorted(baseline_entitlements(p["job_title"], catalog, False)) for p in active}
    mfa = {p["employee_id"]: "TRUE" for p in active}
    last_login = {p["employee_id"]: DAY0 - timedelta(days=rng.randint(0, 30)) for p in active}
    truth = {
        "as_of": DAY0.isoformat(),
        "orphan": [],
        "leaver_active": [],
        "leaver_post_termination_login": [],
        "sod": {},
        "dormant": [],
        "excess_entitlement": [],
        "privileged_no_mfa": [],
        "service_accounts_clean": [],
    }
    used: set[str] = set()

    def choose(title, n):
        cands = [p for p in active if p["job_title"] == title and p["employee_id"] not in used]
        out = rng.sample(cands, n)
        used.update(p["employee_id"] for p in out)
        return out

    sod_plan = [
        ("AP Specialist", "ERP:AP_Approve", "SOD-001", 6),
        ("Payroll Specialist", "HRIS:HR_Admin", "SOD-003", 3),
        ("Logistics Coordinator", "WMS:Approver", "SOD-005", 2),
    ]
    for title, ent, rule_id, n in sod_plan:
        for p in choose(title, n):
            ents_by_emp[p["employee_id"]].append(ent)
            truth["sod"].setdefault(rule_id, []).append(p["upn"])
            truth["excess_entitlement"].append(p["upn"])

    priv_titles = [t for t, s in catalog["titles"].items() if any(is_privileged(e, catalog) for e in s["entitlements"])]
    cands = [p for p in active if p["job_title"] in priv_titles and p["employee_id"] not in used]
    for p in rng.sample(cands, 5):
        used.add(p["employee_id"])
        mfa[p["employee_id"]] = "FALSE"
        truth["privileged_no_mfa"].append(p["upn"])

    rest = [p for p in active if p["employee_id"] not in used]
    for p in rng.sample(rest, 23):
        used.add(p["employee_id"])
        last_login[p["employee_id"]] = DAY0 - timedelta(days=rng.randint(100, 300))
        truth["dormant"].append(p["upn"])

    rest = [p for p in active if p["employee_id"] not in used]
    for p in rng.sample(rest, 17):
        used.add(p["employee_id"])
        options = [
            e
            for e in SAFE_EXCESS
            if e not in ents_by_emp[p["employee_id"]] and not sod_conflicts(ents_by_emp[p["employee_id"]] + [e], rules)
        ]
        ents_by_emp[p["employee_id"]].append(rng.choice(options))
        truth["excess_entitlement"].append(p["upn"])

    rows = []
    for p in active:
        for ent in ents_by_emp[p["employee_id"]]:
            rows.append(
                {
                    "account_id": p["upn"],
                    "employee_id": p["employee_id"],
                    "display_name": f"{p['first_name']} {p['last_name']}",
                    "app": ent.split(":")[0],
                    "entitlement": ent,
                    "account_type": "user",
                    "owner": p["manager_id"],
                    "granted_date": (DAY0 - timedelta(days=rng.randint(10, 1500))).isoformat(),
                    "last_login": last_login[p["employee_id"]].isoformat(),
                    "mfa_registered": mfa[p["employee_id"]],
                }
            )

    # Leavers who still hold access; three of them logged in AFTER termination
    post_login = {p["employee_id"] for p in rng.sample(historical, 3)}
    for p in historical:
        end = date.fromisoformat(p["end_date"])
        login = end + timedelta(days=rng.randint(3, 15)) if p["employee_id"] in post_login else end - timedelta(days=rng.randint(1, 10))
        for ent in sorted(baseline_entitlements(p["job_title"], catalog, False)):
            rows.append(
                {
                    "account_id": p["upn"],
                    "employee_id": p["employee_id"],
                    "display_name": f"{p['first_name']} {p['last_name']}",
                    "app": ent.split(":")[0],
                    "entitlement": ent,
                    "account_type": "user",
                    "owner": p["manager_id"],
                    "granted_date": p["start_date"],
                    "last_login": login.isoformat(),
                    "mfa_registered": "TRUE",
                }
            )
        truth["leaver_active"].append(p["upn"])
        if p["employee_id"] in post_login:
            truth["leaver_post_termination_login"].append(p["upn"])

    # Orphans: no HR record, no owner
    orphan_names = (
        [f"ctr-{n}" for n in ("kwezi", "bluepeak", "ironvale", "tidewater", "northgate", "lumen")]
        + [f"test.user{n}" for n in range(1, 5)]
        + [f"former-vendor-{n}" for n in ("audit", "print", "cleaning", "travel")]
    )
    pool = ["ERP:GL_Read", "CRM:Rep", "WMS:Read", "ITSM:Agent", "CLM:Contributor", "ITSM:Admin", "CRM:Admin", "HRIS:HR_Read"]
    for i, name in enumerate(orphan_names):
        acct = f"{name}@{catalog['company']['domain']}"
        for ent in rng.sample(pool, 2 if i % 3 else 3):
            rows.append(
                {
                    "account_id": acct,
                    "employee_id": "",
                    "display_name": name,
                    "app": ent.split(":")[0],
                    "entitlement": ent,
                    "account_type": "user",
                    "owner": "",
                    "granted_date": (DAY0 - timedelta(days=rng.randint(200, 1800))).isoformat(),
                    "last_login": (DAY0 - timedelta(days=rng.randint(2, 400))).isoformat(),
                    "mfa_registered": "TRUE",
                }
            )
        truth["orphan"].append(acct)

    # Legitimate service accounts (owned) - must NOT be flagged
    it_mgr = next(p for p in active if p["job_title"] == "IT Manager")
    for svc, ent in (
        ("svc-backup", "INFRA:Backup_Operator"),
        ("svc-erp-integration", "ERP:API_Integration"),
        ("svc-crm-sync", "CRM:API_Integration"),
    ):
        acct = f"{svc}@{catalog['company']['domain']}"
        rows.append(
            {
                "account_id": acct,
                "employee_id": "",
                "display_name": svc,
                "app": ent.split(":")[0],
                "entitlement": ent,
                "account_type": "service",
                "owner": it_mgr["employee_id"],
                "granted_date": "2024-01-15",
                "last_login": DAY0.isoformat(),
                "mfa_registered": "N/A",
            }
        )
        truth["service_accounts_clean"].append(acct)

    rng.shuffle(rows)
    for key in (
        "orphan",
        "leaver_active",
        "leaver_post_termination_login",
        "dormant",
        "excess_entitlement",
        "privileged_no_mfa",
        "service_accounts_clean",
    ):
        truth[key] = sorted(set(truth[key]))
    truth["sod"] = {k: sorted(v) for k, v in truth["sod"].items()}
    return rows, truth


def write_role_matrix(path, catalog):
    ents = sorted({e for s in catalog["titles"].values() for e in s["entitlements"]} | set(catalog["birthright_entitlements"]))
    rows = []
    for title, spec in catalog["titles"].items():
        base = baseline_entitlements(title, catalog)
        row = {"business_role": spec["business_role"], "job_title": title, "department": spec["department"]}
        row.update({e: ("X" if e in base else "") for e in ents})
        rows.append(row)
    write_csv(path, rows, ["business_role", "job_title", "department"] + ents)


def main(out_dir: Path | str | None = None) -> dict:
    out = Path(out_dir) if out_dir else ROOT / "data"
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    catalog, rules = load_catalog(), load_sod_rules()
    day0, active, historical, used_upn = build_hr_feeds(rng, catalog)
    write_csv(out / "hr_feed_day0.csv", day0, HR_FIELDS)
    day30, changes = build_day30(rng, catalog, day0, active, used_upn)
    write_csv(out / "hr_feed_day30.csv", sorted(day30, key=lambda r: (r["employee_id"], r["job_title"])), HR_FIELDS)
    access, truth = build_access_export(rng, catalog, rules, day0, historical)
    write_csv(out / "app_access_export.csv", access, ACCESS_FIELDS)
    truth["day30_changes"] = changes
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    write_role_matrix(out / "role_matrix.csv", catalog)
    return truth


def cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="Output directory (default: ./data)")
    args = ap.parse_args()
    t = main(args.out)
    print(f"Generated data in {args.out or ROOT / 'data'}")
    for k in ("orphan", "leaver_active", "dormant", "excess_entitlement", "privileged_no_mfa"):
        print(f"  seeded {k}: {len(t[k])}")


if __name__ == "__main__":
    cli()
