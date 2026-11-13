import json
from datetime import date, timedelta

import pytest

from meridian_iam.iamlib import HR_FIELDS, read_csv, write_csv
from meridian_iam.jml_engine import CircuitBreakerTripped, FeedError, run

DAY0, DAY30 = date(2026, 9, 30), date(2026, 10, 30)


def _run(dataset, tmp_path, feed, as_of, apply=True, force=False):
    data, _ = dataset
    return run(data / feed, tmp_path / "directory.json", as_of=as_of, apply=apply, force=force, out_dir=tmp_path / "out")


def test_day0_creates_only_active_employees(dataset, tmp_path):
    s = _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    assert s["actions"] == {"CREATE": 200}  # 9 historical leavers never get accounts
    assert s["quarantined_rows"] == 0


def test_second_run_is_idempotent(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    again = _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    assert again["total_actions"] == 0


def test_dry_run_does_not_write_state(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0, apply=False)
    assert not (tmp_path / "directory.json").exists()


def test_day30_joiners_movers_leavers(dataset, tmp_path):
    _, truth = dataset
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    s = _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30)
    assert s["actions"] == {"CREATE": 6, "DISABLE": 4, "MOVER": 8}
    assert s["quarantined_rows"] == 3
    assert s["sod_conflicts_prevented_on_movers"] == 2
    assert s["upcoming_leavers_14d"] == truth["day30_changes"]["scheduled_leavers"]


def test_ambiguous_and_malformed_rows_produce_no_action(dataset, tmp_path):
    _, truth = dataset
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    s = _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30)
    touched = {a.employee_id for a in s["_actions"]}
    for eid in truth["day30_changes"]["bad_rows"]:
        assert eid not in touched


def test_preboarding_accounts_are_created_disabled(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30)
    accounts = json.loads((tmp_path / "directory.json").read_text())["accounts"]
    states = [(accounts[e]["enabled"], accounts[e]["lifecycle"]) for e in ("E10301", "E10302", "E10303", "E10304", "E10305", "E10306")]
    assert states == [(True, "active")] * 3 + [(False, "preboard")] * 3


def test_preboard_account_is_enabled_on_start_date(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30)
    s = _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30 + timedelta(days=7))
    assert s["actions"].get("ENABLE") == 3


def test_leaver_is_fully_stripped_then_deleted_after_retention(dataset, tmp_path):
    _, truth = dataset
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30)
    accounts = json.loads((tmp_path / "directory.json").read_text())["accounts"]
    for eid in truth["day30_changes"]["leavers"]:
        a = accounts[eid]
        assert (a["enabled"], a["entitlements"], a["groups"], a["lifecycle"]) == (False, [], [], "leaver")
    s = _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30 + timedelta(days=31))
    assert s["actions"].get("DELETE") == 4


def test_mover_loses_old_access(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    _run(dataset, tmp_path, "hr_feed_day30.csv", DAY30)
    accounts = json.loads((tmp_path / "directory.json").read_text())["accounts"]
    ap_to_mgr = accounts["E10030"]  # AP Specialist -> Finance Manager
    assert "ERP:AP_Entry" not in ap_to_mgr["entitlements"] and "ERP:AP_Approve" in ap_to_mgr["entitlements"]


def test_manual_entitlement_drift_is_corrected(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    path = tmp_path / "directory.json"
    state = json.loads(path.read_text())
    state["accounts"]["E10001"]["entitlements"].append("ITSM:Admin")
    path.write_text(json.dumps(state))
    s = _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    assert s["actions"] == {"DRIFT": 1}


def test_unknown_account_is_flagged_as_orphan_not_deleted(dataset, tmp_path):
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    path = tmp_path / "directory.json"
    state = json.loads(path.read_text())
    state["accounts"]["E99999"] = {**state["accounts"]["E10001"], "employee_id": "E99999", "upn": "ghost@meridian-lab.example"}
    path.write_text(json.dumps(state))
    s = _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    assert s["actions"] == {"FLAG_ORPHAN": 1}


def test_circuit_breaker_blocks_mass_termination(dataset, tmp_path):
    data, _ = dataset
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    rows = read_csv(data / "hr_feed_day0.csv")
    for r in rows[:30]:
        r["status"], r["end_date"] = "Terminated", "2026-09-29"
    bad = tmp_path / "mass.csv"
    write_csv(bad, rows, HR_FIELDS)
    with pytest.raises(CircuitBreakerTripped):
        run(bad, tmp_path / "directory.json", as_of=DAY0, apply=True, out_dir=tmp_path / "o2")
    # nothing changed
    assert run(data / "hr_feed_day0.csv", tmp_path / "directory.json", as_of=DAY0)["total_actions"] == 0
    # explicit override works
    assert run(bad, tmp_path / "directory.json", as_of=DAY0, apply=False, force=True)["actions"]["DISABLE"] == 30


def test_truncated_feed_is_rejected(dataset, tmp_path):
    data, _ = dataset
    _run(dataset, tmp_path, "hr_feed_day0.csv", DAY0)
    rows = read_csv(data / "hr_feed_day0.csv")[:100]
    short = tmp_path / "short.csv"
    write_csv(short, rows, HR_FIELDS)
    with pytest.raises(CircuitBreakerTripped):
        run(short, tmp_path / "directory.json", as_of=DAY0)


def test_missing_columns_raise_feed_error(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("employee_id,upn\nE1,a@b.c\n")
    with pytest.raises(FeedError):
        run(bad, tmp_path / "d.json", as_of=DAY0)
