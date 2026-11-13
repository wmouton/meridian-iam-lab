"""Shared helpers for the Meridian IAM lab tooling (standard library only)."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "data" / "role_catalog.json"
DEFAULT_SOD = ROOT / "data" / "sod_rules.json"

HR_FIELDS = [
    "employee_id",
    "first_name",
    "last_name",
    "upn",
    "department",
    "job_title",
    "manager_id",
    "location",
    "employment_type",
    "status",
    "start_date",
    "end_date",
]


def parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD. Blank returns None; anything else invalid raises ValueError."""
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_json(path: Path | str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_catalog(path: Path | str = DEFAULT_CATALOG) -> dict:
    return load_json(path)


def load_sod_rules(path: Path | str = DEFAULT_SOD) -> list[dict]:
    return load_json(path)["rules"]


def read_csv(path: Path | str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path | str, rows: Iterable[dict], fields: list[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sod_conflicts(entitlements: Iterable[str], rules: list[dict]) -> list[dict]:
    """Return every SoD rule whose two entitlements are both held."""
    held = set(entitlements)
    return [r for r in rules if r["entitlement_a"] in held and r["entitlement_b"] in held]


def baseline_entitlements(title: str, catalog: dict, include_birthright: bool = True) -> set[str]:
    spec = catalog["titles"][title]
    ents = set(spec["entitlements"])
    if include_birthright:
        ents |= set(catalog["birthright_entitlements"])
    return ents


def is_privileged(entitlement: str, catalog: dict) -> bool:
    return entitlement in set(catalog["privileged_entitlements"])


def group_names(department: str, business_role: str, entitlements: Iterable[str]) -> list[str]:
    """Deterministic group naming: birthright, department, business role, one group per entitlement."""
    groups = {
        "grp-bir-all-staff",
        f"grp-dept-{department.lower()}",
        f"grp-role-{business_role.lower()}",
    }
    groups |= {"grp-app-" + e.lower().replace(":", "-").replace("_", "-") for e in entitlements}
    return sorted(groups)
