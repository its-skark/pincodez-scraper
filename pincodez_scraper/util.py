from __future__ import annotations

import re

DROP_CHARS = "&'`()\\,./+’"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    lowered = value.lower()
    for char in DROP_CHARS:
        lowered = lowered.replace(char, "")
    return _NON_ALNUM.sub("-", lowered).strip("-")


def post_office_slug(name: str, pincode: str, district_key: str) -> str:
    return f"{slugify(name)}-{pincode}-{district_key}"


def post_office_id(slug: str) -> str:
    return f"pz:po:{slug}"


def state_slug(name: str) -> str:
    return slugify(name)


def state_id(slug: str) -> str:
    return f"pz:state:{slug}"


def district_slug(name: str, state_name: str) -> str:
    return f"{slugify(name)}-{slugify(state_name)}"


def district_id(slug: str) -> str:
    return f"pz:district:{slug}"


def pincode_id(pincode: str) -> str:
    return f"pz:pin:{pincode}"


def normalize_office_type(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def normalize_delivery_status(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    return cleaned.title()


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None
