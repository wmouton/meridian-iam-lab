"""The analyzer must find exactly the defects the generator seeded - no misses, no false positives."""

from collections import defaultdict
from datetime import date

import pytest

from meridian_iam.access_review_analyzer import analyze, load_hr
from meridian_iam.iamlib import load_catalog, load_sod_rules, read_csv
from meridian_iam.simulate_remediation import remediate

AS_OF = date(2026, 9, 30)


@pytest.fixture(scope="module")
def result(dataset):
    data, truth = dataset
    access = read_csv(data / "app_access_export.csv")
    hr = load_hr(data / "hr_feed_day0.csv")
    findings = analyze(access, hr, load_catalog(), load_sod_rules(), AS_OF)
    grouped = defaultdict(set)
    for f in findings:
        grouped[f["type"]].add(f["account_id"])
    return access, hr, findings, grouped, truth


@pytest.mark.parametrize(
    "ftype,key",
    [
        ("ORPHAN_ACCOUNT", "orphan"),
        ("LEAVER_ACTIVE_ACCESS", "leaver_active"),
        ("LEAVER_POST_TERMINATION_LOGIN", "leaver_post_termination_login"),
        ("DORMANT_ACCOUNT", "dormant"),
        ("EXCESS_ENTITLEMENT", "excess_entitlement"),
        ("PRIVILEGED_NO_MFA", "privileged_no_mfa"),
    ],
)
def test_detection_matches_ground_truth_exactly(result, ftype, key):
    *_, grouped, truth = result
    assert grouped[ftype] == set(truth[key])


def test_sod_findings_match_per_rule(result):
    _, _, findings, _, truth = result
    for rule_id, accounts in truth["sod"].items():
        found = {f["account_id"] for f in findings if f["type"] == "SOD_VIOLATION" and f["detail"].startswith(rule_id)}
        assert found == set(accounts)


def test_owned_service_accounts_are_not_flagged(result):
    _, _, findings, _, truth = result
    flagged = {f["account_id"] for f in findings}
    assert not flagged & set(truth["service_accounts_clean"])


def test_post_termination_logins_are_critical(result):
    _, _, findings, _, _ = result
    assert all(f["severity"] == "Critical" for f in findings if f["type"] == "LEAVER_POST_TERMINATION_LOGIN")


def test_remediation_clears_every_finding(result):
    access, hr, findings, _, _ = result
    fixed = remediate(access, findings)
    assert analyze(fixed, hr, load_catalog(), load_sod_rules(), AS_OF) == []


def test_account_with_no_login_history_is_reported_not_a_crash(result):
    _, hr, *_ = result
    eid = next(e for e, r in hr.items() if r["status"] == "Active" and not r["end_date"])
    row = {
        "account_id": hr[eid]["upn"],
        "employee_id": eid,
        "display_name": "No Login",
        "app": "M365",
        "entitlement": "M365:E3",
        "account_type": "user",
        "owner": "",
        "granted_date": "2026-01-01",
        "last_login": "",
        "mfa_registered": "TRUE",
    }
    findings = analyze([row], hr, load_catalog(), load_sod_rules(), AS_OF)
    assert [f["type"] for f in findings] == ["DORMANT_ACCOUNT"]
