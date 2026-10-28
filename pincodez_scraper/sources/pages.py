from __future__ import annotations

import json
import re
from typing import Any

_SUBDISTRICTS_RE = re.compile(r"subdistrictsData\s*=\s*(\[.*?\])\s*;", re.DOTALL)
_SUBDISTRICT_HEADING_RE = re.compile(
    r"Sub-Districts\s*/\s*Tehsils in [^<]{1,80}?</h[23][^>]*>(.*?)</h[23]>", re.DOTALL | re.IGNORECASE
)
_TALUK_CELL_RE = re.compile(
    r'<a href="/post-offices/[^"]+">\s*(?:<strong>)?(?P<name>[^<]+?)(?:</strong>)?\s*</a>.*?'
    r'data-label="Sub-District / Taluk">\s*(?P<taluk>[^<]*)</td>',
    re.DOTALL,
)


def parse_subdistricts(html: str) -> list[str]:
    match = _SUBDISTRICTS_RE.search(html)
    if match:
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            payload = []
        names: list[str] = []
        for item in payload:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = str(item).strip()
            if name:
                names.append(name)
        if names:
            return names
        if isinstance(payload, list):
            return []
    heading = _SUBDISTRICT_HEADING_RE.search(html)
    if heading:
        text = re.sub(r"<[^>]+>", " ", heading.group(1))
        return [part.strip() for part in re.split(r"\s{2,}|[,|]", text) if part.strip()]
    return []


def parse_pin_taluk_column(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in _TALUK_CELL_RE.finditer(html):
        name = match.group("name").strip()
        taluk = match.group("taluk").strip()
        if name:
            rows.append({"name": name, "taluk": taluk or None})
    return rows


def parse_pin_office_rows(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<tr>\s*<td class="primary-cell" data-label="Office Name">(.*?)</tr>',
        re.DOTALL,
    )
    for block in pattern.findall(html):
        name_match = re.search(r"<strong>([^<]+)</strong>", block)
        type_match = re.search(r'data-label="Type">.*?>([A-Z]{2})<', block, re.DOTALL)
        delivery_match = re.search(r'data-label="Delivery">.*?>([^<]+)<', block, re.DOTALL)
        taluk_match = re.search(r'data-label="Sub-District / Taluk">\s*([^<]*)<', block)
        digipin_match = re.search(r'data-label="DIGIPIN"[^>]*>\s*([0-9A-Z]{10})\s*<', block)
        coords_match = re.search(r"(-?\d+\.\d+)\s*(?:°|&deg;)\s*,\s*(-?\d+\.\d+)\s*(?:°|&deg;)", block)
        if not name_match:
            continue
        rows.append(
            {
                "name": name_match.group(1).strip(),
                "office_type": type_match.group(1).strip() if type_match else None,
                "delivery_status": delivery_match.group(1).strip() if delivery_match else None,
                "taluk": taluk_match.group(1).strip() if taluk_match else None,
                "digipin": digipin_match.group(1).strip() if digipin_match else None,
                "latitude": float(coords_match.group(1)) if coords_match else None,
                "longitude": float(coords_match.group(2)) if coords_match else None,
            }
        )
    return rows
