from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from rich.console import Console

from .config import Settings
from .http import Client, RateLimiter
from .sources import api, exports, pages
from .storage import Checkpoints, read_jsonl, write_jsonl

console = Console()

PHASE_STATES = "states"
PHASE_DISTRICTS = "districts"
PHASE_BULK = "bulk"
PHASE_PINS = "pins"
PHASE_SUBDISTRICTS = "subdistricts"

RELEASE_ID = "2026-09"
DEFAULT_SOURCE_ID = "src:indiapost:pincodes"


class JsonlSink:
    def __init__(self, path: Path, append: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = path.open("a" if append else "w", encoding="utf-8")
        self._lock = asyncio.Lock()
        self.count = 0

    async def write(self, records: Iterable[dict[str, Any]]) -> int:
        written = 0
        async with self._lock:
            for record in records:
                self._handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                self._handle.write("\n")
                written += 1
            self._handle.flush()
        self.count += written
        return written

    def close(self) -> None:
        self._handle.close()


class Progress:
    def __init__(self, label: str, total: int) -> None:
        self.label = label
        self.total = total
        self.done = 0
        self.started = time.monotonic()
        self.last_report = 0.0

    def advance(self, count: int = 1) -> None:
        self.done += count
        now = time.monotonic()
        if now - self.last_report < 2.0 and self.done < self.total:
            return
        self.last_report = now
        elapsed = max(now - self.started, 0.001)
        rate = self.done / elapsed
        remaining = max(self.total - self.done, 0)
        eta = remaining / rate if rate > 0 else 0
        console.print(
            f"[cyan]{self.label}[/cyan] {self.done}/{self.total} "
            f"({rate:.1f}/s, eta {eta / 60:.1f}m)"
        )


def build_client(settings: Settings) -> tuple[Client, RateLimiter]:
    limiter = RateLimiter(
        rate=settings.rate,
        rate_min=settings.rate_min,
        rate_max=settings.rate_max,
        burst=settings.burst,
        latency_fast=settings.latency_fast,
        latency_slow=settings.latency_slow,
        state_path=settings.state_dir / "limiter.json",
    )
    limiter.load_state(settings.rate, settings.wall_cooldown)
    client = Client(
        base_url=settings.base_url,
        user_agent=settings.user_agent,
        limiter=limiter,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        cooldown_max=settings.wall_cooldown_max,
    )
    return client, limiter


async def run_bounded(
    items: list[Any],
    worker: Callable[[Any], Any],
    concurrency: int,
    progress: Progress | None = None,
) -> list[Any]:
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(item: Any) -> Any:
        async with semaphore:
            outcome = await worker(item)
            if progress:
                progress.advance()
            return outcome

    return await asyncio.gather(*(guarded(item) for item in items))


async def scrape_states(settings: Settings, client: Client, checkpoints: Checkpoints, resume: bool) -> dict[str, Any]:
    phase_file = settings.jsonl_dir / "states.jsonl"
    details_file = settings.jsonl_dir / "state_details.jsonl"
    if not resume:
        write_jsonl(phase_file, [])
        write_jsonl(details_file, [])

    if checkpoints.done(PHASE_STATES, "index") and resume:
        console.print("[yellow]states phase already complete, skipping[/yellow]")
        return {"states": checkpoints.count(PHASE_STATES) - 1}

    index = await api.fetch_state_index(client)
    console.print(f"[green]state index:[/green] {len(index)} states/UTs")

    detail_sink = JsonlSink(details_file, append=resume)
    progress = Progress("state details", len(index))

    async def worker(state: dict[str, Any]) -> dict[str, Any] | None:
        slug = state.get("slug")
        if not slug:
            return None
        detail = await api.fetch_state_detail(client, slug)
        if not detail:
            return None
        await detail_sink.write([detail])
        checkpoints.mark(PHASE_STATES, slug)
        return detail

    details = await run_bounded(index, worker, settings.workers, progress)
    detail_sink.close()
    checkpoints.mark(PHASE_STATES, "index")

    states = []
    for state in index:
        detail = next((d for d in details if d and d.get("slug") == state.get("slug")), {})
        merged = {**state, **detail}
        states.append(
            {
                "id": merged.get("pincodez_id") or f"pz:state:{merged.get('slug')}",
                "name": merged.get("name"),
                "type": merged.get("type"),
                "slug": merged.get("slug"),
                "state_code": merged.get("state_code"),
                "census_code": merged.get("census_code"),
                "canonical_name": merged.get("canonical_name") or merged.get("name"),
                "total_districts": merged.get("total_districts"),
                "total_pincodes": merged.get("total_pincodes"),
                "total_post_offices": merged.get("total_post_offices"),
                "source_id": merged.get("source_id") or "src:lgd:admin",
            }
        )
    write_jsonl(phase_file, states)
    return {"states": len(states)}


async def scrape_districts(settings: Settings, client: Client, checkpoints: Checkpoints, resume: bool) -> dict[str, Any]:
    details_file = settings.jsonl_dir / "district_details.jsonl"
    membership_file = settings.jsonl_dir / "district_pincodes.jsonl"
    if not resume:
        write_jsonl(details_file, [])
        write_jsonl(membership_file, [])

    state_details = list(read_jsonl(settings.jsonl_dir / "state_details.jsonl"))
    districts = list(read_jsonl(settings.jsonl_dir / "states.jsonl"))
    state_by_slug = {state.get("slug"): state for state in districts}
    slugs: list[tuple[str, str, str]] = []
    for detail in state_details:
        state = state_by_slug.get(detail.get("slug"), {})
        for district in detail.get("districts") or []:
            if district.get("slug"):
                slugs.append((district["slug"], state.get("name"), state.get("slug")))
    console.print(f"[green]districts to fetch:[/green] {len(slugs)}")

    already = checkpoints.completed_keys(PHASE_DISTRICTS) if resume else set()
    pending = [item for item in slugs if item[0] not in already]

    detail_sink = JsonlSink(details_file, append=resume)
    membership_sink = JsonlSink(membership_file, append=resume)
    progress = Progress("district details", len(pending))

    async def worker(item: tuple[str, str, str]) -> None:
        slug, state_name, state_slug = item
        detail = await api.fetch_district_detail(client, slug)
        if not detail:
            return
        detail["state_name_from_index"] = state_name
        detail["state_slug_from_index"] = state_slug
        await detail_sink.write([detail])
        await membership_sink.write(
            [
                {
                    "district_slug": slug,
                    "state_name": state_name,
                    "pincodes": [
                        {
                            "pincode": entry.get("pincode"),
                            "post_office_count": entry.get("post_office_count"),
                            "delivery_offices_count": entry.get("delivery_offices_count"),
                            "digipin": entry.get("digipin"),
                        }
                        for entry in detail.get("pincodes") or []
                    ],
                }
            ]
        )
        checkpoints.mark(PHASE_DISTRICTS, slug)

    await run_bounded(pending, worker, settings.workers, progress)
    detail_sink.close()
    membership_sink.close()

    merged = _merge_districts(settings)
    write_jsonl(settings.jsonl_dir / "districts.jsonl", merged)
    return {"districts": len(merged)}


def _merge_districts(settings: Settings) -> list[dict[str, Any]]:
    state_by_slug = {s.get("slug"): s for s in read_jsonl(settings.jsonl_dir / "states.jsonl")}
    districts: list[dict[str, Any]] = []
    for detail in read_jsonl(settings.jsonl_dir / "state_details.jsonl"):
        state_slug = detail.get("slug")
        state = state_by_slug.get(state_slug, {})
        for district in detail.get("districts") or []:
            districts.append(
                {
                    "id": district.get("pincodez_id"),
                    "name": district.get("name"),
                    "slug": district.get("slug"),
                    "state_id": state.get("id"),
                    "state_name": state.get("name"),
                    "state_code": state.get("state_code"),
                    "district_code": None,
                    "census_code": None,
                    "canonical_name": district.get("name"),
                    "total_pincodes": district.get("total_pincodes"),
                    "total_post_offices": district.get("total_post_offices"),
                    "total_subdistricts": None,
                    "source_id": "src:lgd:admin",
                }
            )
    enriched = {d.get("slug"): d for d in districts}
    for detail in read_jsonl(settings.jsonl_dir / "district_details.jsonl"):
        slug = detail.get("slug")
        target = enriched.get(slug)
        if not target:
            continue
        target["district_code"] = detail.get("district_code")
        target["census_code"] = detail.get("census_code")
        target["canonical_name"] = detail.get("canonical_name") or target.get("canonical_name")
        target["total_pincodes"] = detail.get("total_pincodes") or target.get("total_pincodes")
        target["total_post_offices"] = detail.get("total_post_offices") or target.get("total_post_offices")
        target["total_subdistricts"] = detail.get("total_subdistricts")
        target["source_id"] = detail.get("source_id") or target.get("source_id")
    return sorted(districts, key=lambda d: (d.get("state_name") or "", d.get("name") or ""))


async def scrape_bulk(settings: Settings, client: Client, checkpoints: Checkpoints, resume: bool) -> dict[str, Any]:
    po_path = settings.raw_dir / "post_offices.csv"
    pin_path = settings.raw_dir / "pincodes.csv"
    results: dict[str, Any] = {}

    for entity_type, destination, parser, output in (
        ("post_offices", po_path, exports.parse_post_offices, "bulk_post_offices.jsonl"),
        ("pincodes", pin_path, exports.parse_pincodes, "bulk_pincodes.jsonl"),
    ):
        if resume and checkpoints.done(PHASE_BULK, entity_type) and destination.exists():
            console.print(f"[yellow]bulk {entity_type} already downloaded[/yellow]")
            results[entity_type] = checkpoints.count(PHASE_BULK, entity_type)
            continue
        console.print(f"[cyan]downloading bulk {entity_type}...[/cyan]")
        ok = await exports.download_dataset(client, entity_type, destination)
        if not ok:
            raise RuntimeError(f"bulk download failed for {entity_type}")
        size = destination.stat().st_size
        records = list(parser(destination))
        write_jsonl(settings.jsonl_dir / output, records)
        checkpoints.mark(PHASE_BULK, entity_type)
        results[entity_type] = len(records)
        console.print(f"[green]bulk {entity_type}:[/green] {len(records)} records, {size / 1e6:.1f} MB")
    return results


async def scrape_pins(
    settings: Settings,
    client: Client,
    checkpoints: Checkpoints,
    resume: bool,
    sample: int | None = None,
) -> dict[str, Any]:
    pins_file = settings.jsonl_dir / "pincodes.jsonl"
    offices_file = settings.jsonl_dir / "post_offices.jsonl"
    if not resume:
        write_jsonl(pins_file, [])
        write_jsonl(offices_file, [])

    pincode_list = [record["pincode"] for record in read_jsonl(settings.jsonl_dir / "bulk_pincodes.jsonl")]
    if not pincode_list:
        collected: set[str] = set()
        for record in read_jsonl(settings.jsonl_dir / "district_pincodes.jsonl"):
            for entry in record.get("pincodes") or []:
                if entry.get("pincode"):
                    collected.add(entry["pincode"])
        pincode_list = sorted(collected)
    if not pincode_list:
        raise RuntimeError("no PIN codes discovered; run scrape bulk or scrape districts first")
    if sample:
        pincode_list = pincode_list[:sample]

    already = checkpoints.completed_keys(PHASE_PINS) if resume else set()
    pending = [pin for pin in pincode_list if pin not in already]
    console.print(f"[green]PIN detail phase:[/green] {len(pending)} pending of {len(pincode_list)}")

    pin_sink = JsonlSink(pins_file, append=resume)
    office_sink = JsonlSink(offices_file, append=resume)
    progress = Progress("pin details", len(pending))
    bulk_index = {r["pincode"]: r for r in read_jsonl(settings.jsonl_dir / "bulk_pincodes.jsonl")}

    async def worker(pincode: str) -> None:
        payload = await api.fetch_pin_detail(client, pincode)
        if not payload:
            return
        fallback = bulk_index.get(pincode)
        pin_record = api.normalize_pincode_record(payload, fallback)
        if not pin_record.get("release_id"):
            pin_record["release_id"] = RELEASE_ID
        if not pin_record.get("source_id"):
            pin_record["source_id"] = DEFAULT_SOURCE_ID
        await pin_sink.write([pin_record])
        offices = [api.normalize_post_office_record(office, pincode) for office in payload.get("post_offices") or []]
        offices = [office for office in offices if office.get("id")]
        await office_sink.write(offices)
        checkpoints.mark(PHASE_PINS, pincode)

    await run_bounded(pending, worker, settings.workers, progress)
    pin_sink.close()
    office_sink.close()
    return {
        "pins": pin_sink.count,
        "post_offices": office_sink.count,
        "pending_remaining": len(pending) - progress.done,
    }


async def scrape_subdistricts(
    settings: Settings, client: Client, checkpoints: Checkpoints, resume: bool
) -> dict[str, Any]:
    output = settings.jsonl_dir / "subdistricts.jsonl"
    if not resume:
        write_jsonl(output, [])

    districts = list(read_jsonl(settings.jsonl_dir / "districts.jsonl"))
    if not districts:
        raise RuntimeError("no districts discovered; run scrape states and scrape districts first")

    already = checkpoints.completed_keys(PHASE_SUBDISTRICTS) if resume else set()
    pending = [d for d in districts if d.get("slug") and d.get("slug") not in already]
    console.print(f"[green]sub-district phase:[/green] {len(pending)} district pages")

    sink = JsonlSink(output, append=resume)
    progress = Progress("subdistricts", len(pending))

    async def worker(district: dict[str, Any]) -> None:
        slug = district["slug"]
        result = await client.get(f"/districts/{slug}", parse_json=False)
        if not result.ok:
            return
        names = pages.parse_subdistricts(result.text)
        records = []
        for ordinal, name in enumerate(names):
            records.append(
                {
                    "id": f"pz:sd:{district.get('id')}:{slugify_ordinal(ordinal)}",
                    "district_id": district.get("id"),
                    "district_name": district.get("name"),
                    "state_name": district.get("state_name"),
                    "name": name,
                    "ordinal": ordinal,
                }
            )
        await sink.write(records)
        checkpoints.mark(PHASE_SUBDISTRICTS, slug)

    await run_bounded(pending, worker, settings.workers, progress)
    sink.close()
    return {"subdistricts": sink.count}


def slugify_ordinal(value: int) -> str:
    return f"{value:04d}"


async def verify_sample(
    settings: Settings,
    client: Client,
    sample: int = 100,
    seed: int = 42,
) -> dict[str, Any]:
    import random

    stored_pins = {record["pincode"]: record for record in read_jsonl(settings.jsonl_dir / "pincodes.jsonl")}
    stored_offices: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(settings.jsonl_dir / "post_offices.jsonl"):
        if record.get("id"):
            stored_offices[record["id"]] = record

    candidates = sorted(stored_pins)
    if not candidates:
        raise RuntimeError("no stored PIN codes found; run scrape pins first")
    random_generator = random.Random(seed)
    chosen = random_generator.sample(candidates, min(sample, len(candidates)))

    mismatches: list[dict[str, Any]] = []
    checked_offices = 0

    async def worker(pincode: str) -> None:
        nonlocal checked_offices
        payload = await api.fetch_pin_detail(client, pincode)
        if not payload:
            mismatches.append({"pincode": pincode, "error": "fetch failed"})
            return
        live_pin = api.normalize_pincode_record(payload)
        stored_pin = stored_pins.get(pincode, {})
        for field in ("state_name", "district_name", "circle_name", "region_name", "division_name", "digipin"):
            if (live_pin.get(field) or None) != (stored_pin.get(field) or None):
                mismatches.append(
                    {"pincode": pincode, "scope": "pincode", "field": field,
                     "stored": stored_pin.get(field), "live": live_pin.get(field)}
                )
        for latitude, longitude in (("latitude", live_pin.get("latitude")), ("longitude", live_pin.get("longitude"))):
            live_value = live_pin.get(latitude)
            stored_value = stored_pin.get(latitude)
            if live_value is None or stored_value is None:
                continue
            if abs(float(live_value) - float(stored_value)) > 1e-6:
                mismatches.append(
                    {"pincode": pincode, "scope": "pincode", "field": latitude,
                     "stored": stored_value, "live": live_value}
                )
        live_offices = {office.get("pincodez_id"): office for office in payload.get("post_offices") or []}
        for identifier, live_office in live_offices.items():
            stored_office = stored_offices.get(identifier)
            if not stored_office:
                mismatches.append({"pincode": pincode, "scope": "post_office", "id": identifier, "error": "missing locally"})
                continue
            checked_offices += 1
            for field in ("name", "office_type", "delivery_status", "digipin", "taluk"):
                live_value = live_office.get(field)
                stored_value = stored_office.get(field)
                if field == "taluk":
                    live_value = live_value or None
                    stored_value = stored_value or None
                if (live_value or None) != (stored_value or None):
                    mismatches.append(
                        {"pincode": pincode, "scope": "post_office", "id": identifier, "field": field,
                         "stored": stored_value, "live": live_value}
                    )
        missing_locally = set(live_offices) - set(stored_offices)
        for identifier in missing_locally:
            mismatches.append({"pincode": pincode, "scope": "post_office", "id": identifier, "error": "missing locally"})

    await run_bounded(chosen, worker, settings.workers, Progress("verify", len(chosen)))
    return {
        "pins_checked": len(chosen),
        "post_offices_checked": checked_offices,
        "mismatches": len(mismatches),
        "details": mismatches[:50],
    }
