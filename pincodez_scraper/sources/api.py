from __future__ import annotations

from typing import Any

from ..http import Client
from ..util import to_float, to_int

STATES_PATH = "/api/v1/states"
STATE_DETAIL_PATH = "/api/v1/states/{slug}"
DISTRICT_DETAIL_PATH = "/api/v1/districts/{slug}"
PIN_DETAIL_PATH = "/pincodes/{pin}/download"


async def fetch_state_index(client: Client) -> list[dict[str, Any]]:
    result = await client.get(STATES_PATH)
    if not result.ok or not isinstance(result.data, dict):
        return []
    return list(result.data.get("states") or [])


async def fetch_state_detail(client: Client, slug: str) -> dict[str, Any]:
    result = await client.get(STATE_DETAIL_PATH.format(slug=slug))
    if not result.ok or not isinstance(result.data, dict):
        return {}
    state = dict(result.data.get("state") or {})
    state["districts"] = list(result.data.get("districts") or [])
    return state


async def fetch_district_detail(client: Client, slug: str) -> dict[str, Any]:
    result = await client.get(DISTRICT_DETAIL_PATH.format(slug=slug))
    if not result.ok or not isinstance(result.data, dict):
        return {}
    district = dict(result.data.get("district") or {})
    district["pincodes"] = list(result.data.get("pincodes") or [])
    return district


async def fetch_pin_detail(client: Client, pincode: str) -> dict[str, Any]:
    result = await client.get(PIN_DETAIL_PATH.format(pin=pincode), params={"format": "json"})
    if not result.ok or not isinstance(result.data, dict):
        return {}
    return result.data


def normalize_pincode_record(payload: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback or {}
    pin = dict(payload.get("pincode") or {})
    provenance = dict(payload.get("provenance") or {})
    return {
        "id": pin.get("pincodez_id") or fallback.get("id"),
        "pincode": pin.get("pincode") or fallback.get("pincode"),
        "state_id": pin.get("state_id") or fallback.get("state_id"),
        "state_name": pin.get("state_name") or fallback.get("state_name"),
        "district_id": pin.get("district_id") or fallback.get("district_id"),
        "district_name": pin.get("district_name") or fallback.get("district_name"),
        "circle_name": pin.get("circle_name") or fallback.get("circle_name"),
        "region_name": pin.get("region_name") or fallback.get("region_name"),
        "division_name": pin.get("division_name") or fallback.get("division_name"),
        "latitude": to_float(pin.get("latitude")) if pin.get("latitude") is not None else fallback.get("latitude"),
        "longitude": to_float(pin.get("longitude")) if pin.get("longitude") is not None else fallback.get("longitude"),
        "digipin": pin.get("digipin") or fallback.get("digipin"),
        "post_office_count": to_int(pin.get("post_office_count")) or fallback.get("post_office_count"),
        "delivery_offices_count": to_int(pin.get("delivery_offices_count")) if fallback.get("delivery_offices_count") is not None else to_int(pin.get("delivery_offices_count")),
        "office_types": pin.get("office_types") or fallback.get("office_types"),
        "confidence": pin.get("confidence") or fallback.get("confidence"),
        "source_id": pin.get("source_id") or fallback.get("source_id"),
        "release_id": pin.get("release_id") or provenance.get("release") or fallback.get("release_id"),
    }


def normalize_post_office_record(payload: dict[str, Any], pincode: str) -> dict[str, Any]:
    return {
        "id": payload.get("pincodez_id"),
        "slug": payload.get("slug"),
        "name": payload.get("name"),
        "canonical_name": payload.get("canonical_name") or payload.get("name"),
        "pincode": payload.get("pincode") or pincode,
        "office_type": payload.get("office_type"),
        "delivery_status": payload.get("delivery_status"),
        "state_id": payload.get("state_id"),
        "state_name": payload.get("state_name"),
        "district_id": payload.get("district_id"),
        "district_name": payload.get("district_name"),
        "circle_name": payload.get("circle_name"),
        "region_name": payload.get("region_name"),
        "division_name": payload.get("division_name"),
        "latitude": to_float(payload.get("latitude")),
        "longitude": to_float(payload.get("longitude")),
        "digipin": payload.get("digipin"),
        "taluk": (payload.get("taluk") or None),
        "confidence": payload.get("confidence"),
        "source_id": payload.get("source_id"),
        "release_id": payload.get("release_id"),
    }
