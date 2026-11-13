"""Role design must itself be free of SoD conflicts and internally consistent."""

from meridian_iam.iamlib import baseline_entitlements, is_privileged, load_catalog, load_sod_rules, sod_conflicts


def test_headcount_is_200():
    assert sum(t["headcount"] for t in load_catalog()["titles"].values()) == 200


def test_no_business_role_contains_an_sod_conflict():
    catalog, rules = load_catalog(), load_sod_rules()
    for title in catalog["titles"]:
        assert not sod_conflicts(baseline_entitlements(title, catalog), rules), f"{title} violates SoD"


def test_business_role_ids_are_unique():
    ids = [t["business_role"] for t in load_catalog()["titles"].values()]
    assert len(ids) == len(set(ids))


def test_every_sod_entitlement_exists_in_catalog():
    catalog = load_catalog()
    known = {e for t in catalog["titles"].values() for e in t["entitlements"]} | set(catalog["birthright_entitlements"])
    for rule in load_sod_rules():
        assert rule["entitlement_a"] in known and rule["entitlement_b"] in known


def test_privileged_entitlements_are_assigned_somewhere():
    catalog = load_catalog()
    assigned = {e for t in catalog["titles"].values() for e in t["entitlements"]}
    assert all(p in assigned for p in catalog["privileged_entitlements"])
    assert is_privileged("ITSM:Admin", catalog) and not is_privileged("CRM:Rep", catalog)
