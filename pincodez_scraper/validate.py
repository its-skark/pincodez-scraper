from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import digipin
from .storage import read_jsonl, write_jsonl

DIGIPIN_RE = re.compile(r"^[0-9A-Z]{10}$")

EXPECTED_STATES = 36
EXPECTED_DISTRICTS = 737
EXPECTED_PINCODES = 19300
EXPECTED_POST_OFFICES = 157126

COMPARE_FIELDS = (
    "name",
    "pincode",
    "office_type",
    "delivery_status",
    "state_name",
    "district_name",
    "circle_name",
    "region_name",
    "division_name",
    "latitude",
    "longitude",
    "digipin",
)


@dataclass
class Report:
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str, data: dict[str, Any] | None = None) -> None:
        self.checks.append({"check": name, "passed": passed, "detail": detail, "data": data or {}})

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [check for check in self.checks if not check["passed"]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": not self.failures,
            "total_checks": len(self.checks),
            "failed_checks": len(self.failures),
            "checks": self.checks,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_database(db_path: Path, jsonl_dir: Path, conflicts_path: Path) -> Report:
    report = Report()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("states", "districts", "subdistricts", "pincodes", "post_offices")
    }
    report.add(
        "row_counts",
        counts["states"] == EXPECTED_STATES
        and counts["districts"] == EXPECTED_DISTRICTS
        and counts["pincodes"] == EXPECTED_PINCODES
        and counts["post_offices"] == EXPECTED_POST_OFFICES,
        ", ".join(f"{key}={value}" for key, value in counts.items()),
        counts,
    )

    orphans = conn.execute(
        "SELECT COUNT(*) FROM post_offices p LEFT JOIN pincodes c ON c.pincode = p.pincode "
        "WHERE c.pincode IS NULL"
    ).fetchone()[0]
    report.add("post_office_pincode_fk", orphans == 0, f"{orphans} orphan post offices", {"orphans": orphans})

    orphan_pins = conn.execute(
        "SELECT COUNT(*) FROM pincodes p LEFT JOIN districts d ON d.id = p.district_id "
        "WHERE p.district_id IS NOT NULL AND d.id IS NULL"
    ).fetchone()[0]
    report.add("pincode_district_fk", orphan_pins == 0, f"{orphan_pins} orphan pincodes", {"orphans": orphan_pins})

    orphan_districts = conn.execute(
        "SELECT COUNT(*) FROM districts d LEFT JOIN states s ON s.id = d.state_id WHERE s.id IS NULL"
    ).fetchone()[0]
    report.add("district_state_fk", orphan_districts == 0, f"{orphan_districts} orphan districts")

    dup_po = conn.execute(
        "SELECT COUNT(*) FROM (SELECT id FROM post_offices GROUP BY id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    dup_pin = conn.execute(
        "SELECT COUNT(*) FROM (SELECT id FROM pincodes GROUP BY id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    report.add("unique_ids", dup_po == 0 and dup_pin == 0, f"dup_post_offices={dup_po}, dup_pincodes={dup_pin}")

    malformed_pin = conn.execute(
        "SELECT COUNT(*) FROM pincodes WHERE digipin IS NOT NULL AND digipin NOT GLOB '[0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z]'"
    ).fetchone()[0]
    malformed_po = conn.execute(
        "SELECT COUNT(*) FROM post_offices WHERE digipin IS NOT NULL AND digipin NOT GLOB '[0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z][0-9A-Z]'"
    ).fetchone()[0]
    report.add(
        "digipin_format",
        malformed_pin == 0 and malformed_po == 0,
        f"malformed pincode digipins={malformed_pin}, post office digipins={malformed_po}",
    )

    out_of_bounds = conn.execute(
        "SELECT COUNT(*) FROM pincodes WHERE latitude IS NOT NULL AND "
        "(latitude < 2.5 OR latitude > 38.5 OR longitude < 63.5 OR longitude > 99.5)"
    ).fetchone()[0] + conn.execute(
        "SELECT COUNT(*) FROM post_offices WHERE latitude IS NOT NULL AND "
        "(latitude < 2.5 OR latitude > 38.5 OR longitude < 63.5 OR longitude > 99.5)"
    ).fetchone()[0]
    report.add("coordinate_envelope", out_of_bounds == 0, f"{out_of_bounds} records outside India's envelope")

    pin_mismatch = 0
    pin_checked = 0
    for row in conn.execute(
        "SELECT latitude, longitude, digipin FROM pincodes WHERE latitude IS NOT NULL AND digipin IS NOT NULL"
    ):
        pin_checked += 1
        if digipin.encode(row["latitude"], row["longitude"]) != row["digipin"]:
            pin_mismatch += 1
    report.add(
        "digipin_reencode_pincodes",
        pin_mismatch == 0,
        f"{pin_checked - pin_mismatch}/{pin_checked} pincodes re-encode exactly",
        {"checked": pin_checked, "mismatched": pin_mismatch},
    )

    po_mismatch = 0
    po_checked = 0
    for row in conn.execute(
        "SELECT latitude, longitude, digipin FROM post_offices WHERE latitude IS NOT NULL AND digipin IS NOT NULL"
    ):
        po_checked += 1
        if digipin.encode(row["latitude"], row["longitude"]) != row["digipin"]:
            po_mismatch += 1
    report.add(
        "digipin_reencode_post_offices",
        po_mismatch == 0,
        f"{po_checked - po_mismatch}/{po_checked} post offices re-encode exactly",
        {"checked": po_checked, "mismatched": po_mismatch},
    )

    null_pins = conn.execute(
        "SELECT COUNT(*) FROM pincodes WHERE latitude IS NULL OR digipin IS NULL"
    ).fetchone()[0]
    null_pos = conn.execute(
        "SELECT COUNT(*) FROM post_offices WHERE latitude IS NULL OR digipin IS NULL"
    ).fetchone()[0]
    report.add(
        "null_coordinates_census",
        True,
        f"pincodes with unknown centroid={null_pins}, post offices with unknown coordinates={null_pos}",
        {"pincodes": null_pins, "post_offices": null_pos},
    )

    taluk_filled = conn.execute(
        "SELECT COUNT(*) FROM post_offices WHERE taluk IS NOT NULL AND taluk != ''"
    ).fetchone()[0]
    report.add(
        "taluk_coverage",
        True,
        f"{taluk_filled} post offices carry a taluk value (source dataset has this column empty)",
        {"filled": taluk_filled},
    )

    stated = conn.execute("SELECT SUM(total_pincodes) FROM states").fetchone()[0] or 0
    actual = counts["pincodes"]
    delta = stated - actual
    variance_pct = (abs(delta) / actual * 100) if actual else 0.0
    report.add(
        "upstream_state_count_variance",
        variance_pct <= 1.0,
        f"sum(state.total_pincodes)={stated}, actual pincodes={actual}, delta={delta} "
        f"({variance_pct:.2f}%) - the source site double-counts PIN codes across state boundaries",
        {"stated": stated, "actual": actual, "delta": delta, "variance_pct": round(variance_pct, 4)},
    )

    per_district = conn.execute(
        "SELECT COUNT(*) FROM pincodes WHERE district_id IS NULL"
    ).fetchone()[0]
    report.add("pincode_district_resolution", per_district == 0, f"{per_district} pincodes without district")

    membership_rows = conn.execute("SELECT COUNT(*) FROM district_pincodes").fetchone()[0]
    membership_distinct = conn.execute(
        "SELECT COUNT(DISTINCT pincode) FROM district_pincodes"
    ).fetchone()[0]
    multi_district = conn.execute(
        "SELECT COUNT(*) FROM (SELECT pincode FROM district_pincodes GROUP BY pincode HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    report.add(
        "district_membership_integrity",
        membership_rows == membership_distinct and multi_district == 0,
        f"{membership_rows} memberships across {membership_distinct} distinct PIN codes, "
        f"{multi_district} PIN codes listed under more than one district",
        {"memberships": membership_rows, "distinct": membership_distinct, "multi": multi_district},
    )

    counter_sum = conn.execute("SELECT SUM(total_pincodes) FROM districts").fetchone()[0] or 0
    report.add(
        "district_counter_variance",
        True,
        f"sum(district.total_pincodes)={counter_sum} vs {membership_rows} actual memberships - "
        "the source site's per-district counters are inflated; the membership map is authoritative",
        {"counter_sum": counter_sum, "actual": membership_rows},
    )

    bulk_po = {r["id"]: r for r in read_jsonl(jsonl_dir / "bulk_post_offices.jsonl") if r.get("id")}
    detail_po = {r["id"]: r for r in read_jsonl(jsonl_dir / "post_offices.jsonl") if r.get("id")}
    conflicts: list[dict[str, Any]] = []
    field_mismatches: Counter[str] = Counter()
    for identifier, detail in detail_po.items():
        bulk = bulk_po.get(identifier)
        if not bulk:
            continue
        for name in COMPARE_FIELDS:
            bulk_value = bulk.get(name)
            detail_value = detail.get(name)
            if name == "name":
                bulk_value = bulk.get("canonical_name")
            if name in ("latitude", "longitude"):
                if bulk_value is None or detail_value is None:
                    continue
                if abs(float(bulk_value) - float(detail_value)) > 1e-6:
                    field_mismatches[name] += 1
                    conflicts.append(
                        {"id": identifier, "field": name, "bulk": bulk_value, "detail": detail_value}
                    )
                continue
            if (bulk_value or None) != (detail_value or None):
                field_mismatches[name] += 1
                conflicts.append({"id": identifier, "field": name, "bulk": bulk_value, "detail": detail_value})
    missing_from_bulk = len(set(detail_po) - set(bulk_po))
    missing_from_detail = len(set(bulk_po) - set(detail_po))
    write_jsonl(conflicts_path, conflicts)
    report.add(
        "bulk_vs_detail_diff",
        not conflicts,
        f"field mismatches={len(conflicts)}, only_in_detail={missing_from_bulk}, only_in_bulk={missing_from_detail}",
        {
            "mismatches": len(conflicts),
            "only_in_detail": missing_from_bulk,
            "only_in_bulk": missing_from_detail,
            "by_field": dict(field_mismatches),
        },
    )

    digests = {}
    for path in sorted(jsonl_dir.glob("*.jsonl")):
        digests[path.name] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    report.add("artifact_digests", True, f"{len(digests)} artifact digests recorded", {"digests": digests})

    conn.close()
    return report


def write_report(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2))
