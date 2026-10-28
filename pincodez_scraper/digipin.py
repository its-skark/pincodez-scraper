from __future__ import annotations

from typing import Any

LAT_MIN = 2.5
LAT_MAX = 38.5
LON_MIN = 63.5
LON_MAX = 99.5
ENVELOPE = 36.0
LEVELS = 10

SPIRAL: dict[tuple[int, int], str] = {
    (0, 0): "L", (0, 1): "M", (0, 2): "P", (0, 3): "T",
    (1, 0): "K", (1, 1): "4", (1, 2): "5", (1, 3): "6",
    (2, 0): "J", (2, 1): "3", (2, 2): "2", (2, 3): "7",
    (3, 0): "F", (3, 1): "C", (3, 2): "9", (3, 3): "8",
}
INVERSE: dict[str, tuple[int, int]] = {symbol: cell for cell, symbol in SPIRAL.items()}


class DigipinError(ValueError):
    pass


def cell_size(level: int) -> float:
    if not 1 <= level <= LEVELS:
        raise DigipinError(f"level must be 1..{LEVELS}")
    return ENVELOPE / (4**level)


def encode(latitude: float, longitude: float) -> str:
    if not LAT_MIN <= latitude <= LAT_MAX:
        raise DigipinError(f"latitude {latitude} outside {LAT_MIN}..{LAT_MAX}")
    if not LON_MIN <= longitude <= LON_MAX:
        raise DigipinError(f"longitude {longitude} outside {LON_MIN}..{LON_MAX}")
    code = []
    for level in range(1, LEVELS + 1):
        size = cell_size(level)
        row = int((latitude - LAT_MIN) // size) % 4
        col = int((longitude - LON_MIN) // size) % 4
        code.append(SPIRAL[(row, col)])
    return "".join(code)


def format_code(code: str) -> str:
    return f"{code[0:3]} {code[3:7]} {code[7:10]}"


def decode(code: str) -> dict[str, Any]:
    normalized = code.strip().upper()
    if len(normalized) != LEVELS or any(ch not in INVERSE for ch in normalized):
        raise DigipinError(f"invalid digipin code {code!r}")
    row = 0
    col = 0
    for symbol in normalized:
        sub_row, sub_col = INVERSE[symbol]
        row = row * 4 + sub_row
        col = col * 4 + sub_col
    size = cell_size(LEVELS)
    min_lat = LAT_MIN + row * size
    min_lon = LON_MIN + col * size
    max_lat = min_lat + size
    max_lon = min_lon + size
    return {
        "digipin": normalized,
        "formatted": format_code(normalized),
        "min_latitude": min_lat,
        "max_latitude": max_lat,
        "min_longitude": min_lon,
        "max_longitude": max_lon,
        "center_latitude": min_lat + size / 2,
        "center_longitude": min_lon + size / 2,
        "precision_level": LEVELS,
        "approx_accuracy_meters": 3.8,
    }
