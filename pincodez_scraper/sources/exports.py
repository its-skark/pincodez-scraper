from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterator

from ..http import Client
from ..util import to_float, to_int

DOWNLOAD_PATH = "/download/dataset"

POST_OFFICE_COLUMNS = (
    "Post Office Name",
    "Pincode",
    "Office Type",
    "Delivery Status",
    "Division",
    "Region",
    "Circle",
    "District",
    "State",
    "Latitude",
    "Longitude",
    "DIGIPIN",
    "Pincodez ID",
)

PINCODE_COLUMNS = (
    "Pincode",
    "District",
    "State",
    "Circle",
    "Region",
    "Division",
    "Latitude",
    "Longitude",
    "DIGIPIN",
    "Post Office Count",
    "Delivery Offices Count",
    "Office Types",
    "Pincodez ID",
)


async def download_dataset(
    client: Client,
    entity_type: str,
    destination: Path,
    state: str = "",
    district: str = "",
) -> bool:
    params = {"state": state, "district": district, "type": entity_type, "format": "csv"}
    result = await client.download(DOWNLOAD_PATH, params, destination)
    return result.ok


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def parse_post_offices(path: Path) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        pincode = (row.get("Pincode") or "").strip()
        if not pincode:
            continue
        yield {
            "id": (row.get("Pincodez ID") or "").strip() or None,
            "slug": None,
            "name": (row.get("Post Office Name") or "").strip(),
            "canonical_name": (row.get("Post Office Name") or "").strip(),
            "pincode": pincode,
            "office_type": (row.get("Office Type") or "").strip() or None,
            "delivery_status": (row.get("Delivery Status") or "").strip() or None,
            "state_id": None,
            "state_name": (row.get("State") or "").strip(),
            "district_id": None,
            "district_name": (row.get("District") or "").strip(),
            "circle_name": (row.get("Circle") or "").strip() or None,
            "region_name": (row.get("Region") or "").strip() or None,
            "division_name": (row.get("Division") or "").strip() or None,
            "latitude": to_float(row.get("Latitude")),
            "longitude": to_float(row.get("Longitude")),
            "digipin": (row.get("DIGIPIN") or "").strip() or None,
            "taluk": None,
            "confidence": None,
            "source_id": None,
            "release_id": None,
        }


def parse_pincodes(path: Path) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        pincode = (row.get("Pincode") or "").strip()
        if not pincode:
            continue
        yield {
            "id": (row.get("Pincodez ID") or "").strip() or None,
            "pincode": pincode,
            "state_id": None,
            "state_name": (row.get("State") or "").strip(),
            "district_id": None,
            "district_name": (row.get("District") or "").strip(),
            "circle_name": (row.get("Circle") or "").strip() or None,
            "region_name": (row.get("Region") or "").strip() or None,
            "division_name": (row.get("Division") or "").strip() or None,
            "latitude": to_float(row.get("Latitude")),
            "longitude": to_float(row.get("Longitude")),
            "digipin": (row.get("DIGIPIN") or "").strip() or None,
            "post_office_count": to_int(row.get("Post Office Count")),
            "delivery_offices_count": to_int(row.get("Delivery Offices Count")),
            "office_types": (row.get("Office Types") or "").strip() or None,
            "confidence": None,
            "source_id": None,
            "release_id": None,
        }


def parse_json_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
