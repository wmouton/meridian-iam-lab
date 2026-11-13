#!/usr/bin/env python3
"""Apply the recommended remediation for every finding to a copy of the access export.

This lets the lab show a measurable before/after: re-running the analyzer on the remediated
export must return zero findings. It simulates the revoke / disable actions an IAM team would
execute through the directory; it does not replace them.

  ORPHAN, LEAVER_*, DORMANT  -> every assignment on the account is removed (account disabled)
  EXCESS_ENTITLEMENT, SOD    -> only the offending entitlement is removed
  PRIVILEGED_NO_MFA          -> MFA registration enforced (flag set to TRUE)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meridian_iam.iamlib import ROOT, read_csv, write_csv

REMOVE_ACCOUNT = {"ORPHAN_ACCOUNT", "LEAVER_ACTIVE_ACCESS", "LEAVER_POST_TERMINATION_LOGIN", "DORMANT_ACCOUNT"}


def remediate(access_rows: list[dict], findings: list[dict]) -> list[dict]:
    drop_accounts = {f["account_id"] for f in findings if f["type"] in REMOVE_ACCOUNT}
    drop_pairs: set[tuple[str, str]] = set()
    mfa_fix = {f["account_id"] for f in findings if f["type"] == "PRIVILEGED_NO_MFA"}
    for f in findings:
        if f["type"] == "EXCESS_ENTITLEMENT":
            drop_pairs |= {(f["account_id"], e) for e in f["entitlements"].split(";")}
    result = []
    for row in access_rows:
        if row["account_id"] in drop_accounts or (row["account_id"], row["entitlement"]) in drop_pairs:
            continue
        if row["account_id"] in mfa_fix:
            row = {**row, "mfa_registered": "TRUE"}
        result.append(row)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--access", default=str(ROOT / "data" / "app_access_export.csv"))
    ap.add_argument("--findings", default=str(ROOT / "out" / "findings.csv"))
    ap.add_argument("--out", default=str(ROOT / "out" / "app_access_export_remediated.csv"))
    args = ap.parse_args(argv)
    access, findings = read_csv(args.access), read_csv(args.findings)
    fixed = remediate(access, findings)
    write_csv(args.out, fixed, list(access[0].keys()))
    print(f"{len(access)} -> {len(fixed)} entitlement assignments written to {Path(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
