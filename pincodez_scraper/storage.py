from __future__ import annotations

import csv
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS states (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    slug TEXT NOT NULL UNIQUE,
    state_code TEXT,
    census_code TEXT,
    canonical_name TEXT,
    total_districts INTEGER,
    total_pincodes INTEGER,
    total_post_offices INTEGER,
    source_id TEXT
);

CREATE TABLE IF NOT EXISTS districts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    state_id TEXT NOT NULL REFERENCES states(id),
    state_name TEXT NOT NULL,
    district_code TEXT,
    census_code TEXT,
    canonical_name TEXT,
    total_pincodes INTEGER,
    total_post_offices INTEGER,
    total_subdistricts INTEGER,
    source_id TEXT
);

CREATE TABLE IF NOT EXISTS subdistricts (
    id TEXT PRIMARY KEY,
    district_id TEXT NOT NULL REFERENCES districts(id),
    district_name TEXT NOT NULL,
    state_name TEXT NOT NULL,
    name TEXT NOT NULL,
    ordinal INTEGER
);

CREATE TABLE IF NOT EXISTS pincodes (
    id TEXT PRIMARY KEY,
    pincode TEXT NOT NULL UNIQUE,
    state_id TEXT REFERENCES states(id),
    state_name TEXT NOT NULL,
    district_id TEXT REFERENCES districts(id),
    district_name TEXT NOT NULL,
    circle_name TEXT,
    region_name TEXT,
    division_name TEXT,
    latitude REAL,
    longitude REAL,
    digipin TEXT,
    post_office_count INTEGER,
    delivery_offices_count INTEGER,
    office_types TEXT,
    confidence TEXT,
    source_id TEXT,
    release_id TEXT
);

CREATE TABLE IF NOT EXISTS post_offices (
    id TEXT PRIMARY KEY,
    slug TEXT,
    name TEXT NOT NULL,
    canonical_name TEXT,
    pincode TEXT NOT NULL REFERENCES pincodes(pincode),
    office_type TEXT,
    delivery_status TEXT,
    state_id TEXT,
    state_name TEXT,
    district_id TEXT,
    district_name TEXT,
    circle_name TEXT,
    region_name TEXT,
    division_name TEXT,
    latitude REAL,
    longitude REAL,
    digipin TEXT,
    taluk TEXT,
    confidence TEXT,
    source_id TEXT,
    release_id TEXT
);

CREATE TABLE IF NOT EXISTS district_pincodes (
    district_id TEXT NOT NULL REFERENCES districts(id),
    pincode TEXT NOT NULL REFERENCES pincodes(pincode),
    post_office_count INTEGER,
    delivery_offices_count INTEGER,
    digipin TEXT,
    PRIMARY KEY (district_id, pincode)
);

CREATE TABLE IF NOT EXISTS provenance (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_pincodes_district ON pincodes(district_id);
CREATE INDEX IF NOT EXISTS idx_pincodes_state ON pincodes(state_id);
CREATE INDEX IF NOT EXISTS idx_po_pincode ON post_offices(pincode);
CREATE INDEX IF NOT EXISTS idx_po_district ON post_offices(district_id);
CREATE INDEX IF NOT EXISTS idx_po_state ON post_offices(state_id);
CREATE INDEX IF NOT EXISTS idx_sd_district ON subdistricts(district_id);
CREATE INDEX IF NOT EXISTS idx_dp_pincode ON district_pincodes(pincode);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS post_offices_fts USING fts5(
    name,
    district_name,
    state_name,
    content='post_offices',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS pincodes_fts USING fts5(
    pincode,
    district_name,
    state_name,
    content='pincodes',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
"""


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], append: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: Sequence[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def write_csv_from_jsonl(
    path: Path,
    source: Path,
    fieldnames: Sequence[str],
    transform: Any = None,
) -> int:
    def generator() -> Iterator[dict[str, Any]]:
        for row in read_jsonl(source):
            yield transform(row) if transform else row

    return write_csv(path, generator(), fieldnames)


class Checkpoints:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS units (
                phase TEXT NOT NULL,
                key TEXT NOT NULL,
                completed_at REAL NOT NULL,
                PRIMARY KEY (phase, key)
            )
            """
        )
        self._conn.commit()

    def done(self, phase: str, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM units WHERE phase = ? AND key = ?", (phase, key)
        ).fetchone()
        return row is not None

    def mark(self, phase: str, key: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO units (phase, key, completed_at) VALUES (?, ?, ?)",
            (phase, key, time.time()),
        )
        self._conn.commit()

    def completed_keys(self, phase: str) -> set[str]:
        rows = self._conn.execute("SELECT key FROM units WHERE phase = ?", (phase,)).fetchall()
        return {row[0] for row in rows}

    def count(self, phase: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM units WHERE phase = ?", (phase,)
        ).fetchone()
        return int(row[0]) if row else 0

    def reset(self, phase: str) -> None:
        self._conn.execute("DELETE FROM units WHERE phase = ?", (phase,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def build_database(db_path: Path, jsonl_dir: Path) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        side = db_path.with_name(db_path.name + suffix)
        if side.exists():
            side.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    counts: dict[str, int] = {}

    state_by_name: dict[str, str] = {}
    for record in read_jsonl(jsonl_dir / "states.jsonl"):
        if record.get("name") and record.get("id"):
            state_by_name[record["name"]] = record["id"]
    district_by_pair: dict[tuple[str, str], str] = {}
    district_by_slug: dict[str, str] = {}
    for record in read_jsonl(jsonl_dir / "districts.jsonl"):
        if record.get("id"):
            district_by_pair[(record.get("state_name") or "", record.get("name") or "")] = record["id"]
            district_by_slug[record.get("slug") or ""] = record["id"]

    def resolve(record: dict[str, Any]) -> dict[str, Any]:
        if not record.get("state_id"):
            record["state_id"] = state_by_name.get(record.get("state_name") or "")
        if not record.get("district_id"):
            record["district_id"] = district_by_pair.get(
                (record.get("state_name") or "", record.get("district_name") or "")
            )
        return record

    def load(table: str, sources: Sequence[str], columns: Sequence[str], row_builder: Any) -> int:
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        total = 0
        skipped = 0
        seen_sources: list[str] = []
        for source in sources:
            if source in seen_sources:
                continue
            seen_sources.append(source)
            path = jsonl_dir / source
            if not path.exists():
                continue
            batch: list[tuple[Any, ...]] = []
            for record in read_jsonl(path):
                built = resolve(dict(row_builder(record)))
                batch.append(tuple(built.get(column) for column in columns))
                if len(batch) >= 2000:
                    written, violations = _flush(conn, sql, batch)
                    total += written
                    skipped += violations
                    batch.clear()
            if batch:
                written, violations = _flush(conn, sql, batch)
                total += written
                skipped += violations
        conn.commit()
        counts[table] = total
        if skipped:
            counts[f"{table}_skipped_violations"] = skipped
        return total

    def _flush(conn: sqlite3.Connection, sql: str, batch: list[tuple[Any, ...]]) -> tuple[int, int]:
        try:
            conn.executemany(sql, batch)
            return len(batch), 0
        except sqlite3.IntegrityError:
            written = 0
            violations = 0
            for row in batch:
                try:
                    conn.execute(sql, row)
                    written += 1
                except sqlite3.IntegrityError:
                    violations += 1
            return written, violations

    def pick(primary: str, fallback: str) -> str:
        primary_path = jsonl_dir / primary
        if primary_path.exists() and primary_path.stat().st_size > 0:
            return primary
        fallback_path = jsonl_dir / fallback
        if fallback_path.exists() and fallback_path.stat().st_size > 0:
            return fallback
        return primary

    load(
        "states",
        ["states.jsonl"],
        ("id", "name", "type", "slug", "state_code", "census_code", "canonical_name",
         "total_districts", "total_pincodes", "total_post_offices", "source_id"),
        lambda r: r,
    )
    load(
        "districts",
        ["districts.jsonl"],
        ("id", "name", "slug", "state_id", "state_name", "district_code", "census_code",
         "canonical_name", "total_pincodes", "total_post_offices", "total_subdistricts", "source_id"),
        lambda r: r,
    )
    load(
        "subdistricts",
        ["subdistricts.jsonl"],
        ("id", "district_id", "district_name", "state_name", "name", "ordinal"),
        lambda r: r,
    )
    load(
        "pincodes",
        ["bulk_pincodes.jsonl", pick("pincodes.jsonl", "bulk_pincodes.jsonl")],
        ("id", "pincode", "state_id", "state_name", "district_id", "district_name",
         "circle_name", "region_name", "division_name", "latitude", "longitude", "digipin",
         "post_office_count", "delivery_offices_count", "office_types", "confidence",
         "source_id", "release_id"),
        lambda r: r,
    )
    load(
        "post_offices",
        ["bulk_post_offices.jsonl", pick("post_offices.jsonl", "bulk_post_offices.jsonl")],
        ("id", "slug", "name", "canonical_name", "pincode", "office_type", "delivery_status",
         "state_id", "state_name", "district_id", "district_name", "circle_name", "region_name",
         "division_name", "latitude", "longitude", "digipin", "taluk", "confidence", "source_id",
         "release_id"),
        lambda r: r,
    )

    membership_sql = (
        "INSERT OR REPLACE INTO district_pincodes "
        "(district_id, pincode, post_office_count, delivery_offices_count, digipin) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    membership_total = 0
    for record in read_jsonl(jsonl_dir / "district_pincodes.jsonl"):
        district_id = district_by_slug.get(record.get("district_slug") or "")
        if not district_id:
            continue
        for entry in record.get("pincodes") or []:
            pincode = entry.get("pincode")
            if not pincode:
                continue
            try:
                conn.execute(
                    membership_sql,
                    (
                        district_id,
                        pincode,
                        entry.get("post_office_count"),
                        entry.get("delivery_offices_count"),
                        entry.get("digipin"),
                    ),
                )
                membership_total += 1
            except sqlite3.IntegrityError:
                counts["district_pincodes_skipped_violations"] = (
                    counts.get("district_pincodes_skipped_violations", 0) + 1
                )
    conn.commit()

    conn.executescript(FTS_SCHEMA)
    conn.execute("INSERT INTO post_offices_fts(post_offices_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO pincodes_fts(pincodes_fts) VALUES('rebuild')")
    conn.commit()
    for table in ("states", "districts", "subdistricts", "pincodes", "post_offices", "district_pincodes"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return counts
