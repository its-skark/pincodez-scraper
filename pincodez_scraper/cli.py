from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import digipin as digipin_module
from .config import Settings
from .http import FetchError
from .pipeline import (
    build_client,
    scrape_bulk,
    scrape_districts,
    scrape_pins,
    scrape_states,
    scrape_subdistricts,
)
from .storage import Checkpoints, build_database, read_jsonl, write_csv, write_csv_from_jsonl
from .validate import validate_database, write_report

console = Console()

app = typer.Typer(help="Rate-limited scraper for pincodez.info")
scrape_app = typer.Typer(help="Scrape phases")
digipin_app = typer.Typer(help="Local DIGIPIN grid tools")
app.add_typer(scrape_app, name="scrape")
app.add_typer(digipin_app, name="digipin")

options: dict = {}


@app.callback()
def main(
    data_dir: Path = typer.Option(Path("data"), "--data-dir", help="Directory for outputs and state."),
    rate: float = typer.Option(6.0, "--rate", help="Starting request rate per second (auto-tuned)."),
    rate_max: float = typer.Option(8.0, "--rate-max", help="Upper bound for auto-tuning."),
    rate_min: float = typer.Option(2.0, "--rate-min", help="Lower bound for auto-tuning."),
    workers: int = typer.Option(4, "--workers", help="Concurrent workers sharing one global rate limiter."),
    user_agent: Optional[str] = typer.Option(None, "--user-agent", help="Override the User-Agent header."),
    resume: bool = typer.Option(False, "--resume", help="Resume from checkpoints instead of starting fresh."),
) -> None:
    settings = Settings(
        data_dir=data_dir,
        rate=rate,
        rate_max=rate_max,
        rate_min=rate_min,
        workers=workers,
    )
    if user_agent:
        settings.user_agent = user_agent
    settings.ensure_dirs()
    options["settings"] = settings
    options["resume"] = resume


def get_settings() -> Settings:
    return options["settings"]


def get_resume() -> bool:
    return bool(options.get("resume"))


async def _run(phase: str, coroutine_factory) -> None:
    settings = get_settings()
    client, limiter = build_client(settings)
    checkpoints = Checkpoints(settings.state_dir / "checkpoints.db")
    try:
        result = await coroutine_factory(client, checkpoints)
        console.print(f"[bold green]{phase} complete[/bold green]: {result}")
        console.print(
            f"requests={limiter.requests} wall_hits={limiter.wall_hits} "
            f"final_rate={limiter.rate:.1f}/s"
        )
    except FetchError as exc:
        console.print(f"[red]{phase} failed:[/red] {exc}")
        raise typer.Exit(code=1)
    finally:
        await client.aclose()
        checkpoints.close()


@scrape_app.command("states")
def cmd_states() -> None:
    """Scrape 36 states/UTs and their district lists."""

    async def factory(client, checkpoints):
        return await scrape_states(get_settings(), client, checkpoints, get_resume())

    asyncio.run(_run("states", factory))


@scrape_app.command("districts")
def cmd_districts() -> None:
    """Scrape all 737 district records and their PIN membership."""

    async def factory(client, checkpoints):
        return await scrape_districts(get_settings(), client, checkpoints, get_resume())

    asyncio.run(_run("districts", factory))


@scrape_app.command("bulk")
def cmd_bulk() -> None:
    """Download the all-India bulk exports (post offices and PIN codes)."""

    async def factory(client, checkpoints):
        return await scrape_bulk(get_settings(), client, checkpoints, get_resume())

    asyncio.run(_run("bulk", factory))


@scrape_app.command("pins")
def cmd_pins(sample: Optional[int] = typer.Option(None, "--sample", help="Only fetch N PIN codes.")) -> None:
    """Scrape the authoritative per-PIN detail endpoint for every PIN code."""

    async def factory(client, checkpoints):
        return await scrape_pins(get_settings(), client, checkpoints, get_resume(), sample)

    asyncio.run(_run("pins", factory))


@scrape_app.command("subdistricts")
def cmd_subdistricts() -> None:
    """Scrape sub-district / tehsil names from district pages."""

    async def factory(client, checkpoints):
        return await scrape_subdistricts(get_settings(), client, checkpoints, get_resume())

    asyncio.run(_run("subdistricts", factory))


@scrape_app.command("all")
def cmd_all(sample: Optional[int] = typer.Option(None, "--sample", help="Limit the PIN phase to N codes.")) -> None:
    """Run every phase in order."""

    async def factory(client, checkpoints):
        settings = get_settings()
        resume = get_resume()
        results: dict = {}
        results.update(await scrape_states(settings, client, checkpoints, resume))
        results.update(await scrape_districts(settings, client, checkpoints, resume))
        results.update(await scrape_bulk(settings, client, checkpoints, resume))
        results.update(await scrape_pins(settings, client, checkpoints, resume, sample))
        results.update(await scrape_subdistricts(settings, client, checkpoints, resume))
        return results

    asyncio.run(_run("all", factory))


@app.command("verify")
def cmd_verify(
    sample: int = typer.Option(100, "--sample", help="Number of random PIN codes to re-fetch and diff."),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducible sampling."),
) -> None:
    """Re-fetch random PIN codes live and diff them against the stored dataset."""
    from .pipeline import verify_sample

    async def factory(client, checkpoints):
        return await verify_sample(get_settings(), client, sample, seed)

    asyncio.run(_run("verify", factory))


def flatten_rows(path):
    for record in read_jsonl(path):
        for entry in record.get("pincodes") or []:
            yield {
                "district_slug": record.get("district_slug"),
                "state_name": record.get("state_name"),
                "pincode": entry.get("pincode"),
                "post_office_count": entry.get("post_office_count"),
                "delivery_offices_count": entry.get("delivery_offices_count"),
                "digipin": entry.get("digipin"),
            }


@app.command("build-db")
def cmd_build_db() -> None:
    """Build the SQLite database and CSV mirrors from the scraped JSONL."""
    settings = get_settings()
    counts = build_database(settings.db_path, settings.jsonl_dir)
    console.print("[bold green]database built[/bold green]")
    table = Table("table", "rows")
    for name, value in counts.items():
        table.add_row(name, str(value))
    console.print(table)
    console.print(f"sqlite: {settings.db_path}")

    csv_specs = {
        "states.csv": ("states.jsonl", (
            "id", "name", "type", "slug", "state_code", "census_code",
            "total_districts", "total_pincodes", "total_post_offices", "source_id",
        )),
        "districts.csv": ("districts.jsonl", (
            "id", "name", "slug", "state_id", "state_name", "district_code", "census_code",
            "total_pincodes", "total_post_offices", "total_subdistricts", "source_id",
        )),
        "subdistricts.csv": ("subdistricts.jsonl", (
            "id", "district_id", "district_name", "state_name", "name", "ordinal",
        )),
        "pincodes.csv": ("pincodes.jsonl", (
            "id", "pincode", "state_id", "state_name", "district_id", "district_name",
            "circle_name", "region_name", "division_name", "latitude", "longitude", "digipin",
            "post_office_count", "delivery_offices_count", "office_types", "confidence",
            "source_id", "release_id",
        )),
        "post_offices.csv": ("post_offices.jsonl", (
            "id", "slug", "name", "canonical_name", "pincode", "office_type", "delivery_status",
            "state_id", "state_name", "district_id", "district_name", "circle_name",
            "region_name", "division_name", "latitude", "longitude", "digipin", "taluk",
            "confidence", "source_id", "release_id",
        )),
    }
    for filename, (source, columns) in csv_specs.items():
        path = settings.jsonl_dir / source
        if not path.exists():
            continue
        written = write_csv_from_jsonl(settings.csv_dir / filename, path, columns)
        console.print(f"csv: {filename} ({written} rows)")

    membership_path = settings.jsonl_dir / "district_pincodes.jsonl"
    if membership_path.exists():
        rows = list(flatten_rows(membership_path))
        written = write_csv(
            settings.csv_dir / "district_pincodes.csv",
            rows,
            ("district_slug", "state_name", "pincode", "post_office_count",
             "delivery_offices_count", "digipin"),
        )
        console.print(f"csv: district_pincodes.csv ({written} rows)")


@app.command("validate")
def cmd_validate() -> None:
    """Run every integrity gate against the built database."""
    settings = get_settings()
    if not settings.db_path.exists():
        console.print("[red]no database found; run build-db first[/red]")
        raise typer.Exit(code=1)
    report = validate_database(settings.db_path, settings.jsonl_dir, settings.conflicts_path)
    table = Table("check", "result", "detail")
    for check in report.checks:
        table.add_row(
            check["check"],
            "[green]PASS[/green]" if check["passed"] else "[red]FAIL[/red]",
            check["detail"],
        )
    console.print(table)
    write_report(report, settings.data_dir / "validation_report.json")
    console.print(f"report: {settings.data_dir / 'validation_report.json'}")
    if report.failures:
        console.print(f"[red]{len(report.failures)} checks failed[/red]")
        raise typer.Exit(code=1)
    console.print("[bold green]all checks passed[/bold green]")


@digipin_app.command("encode")
def cmd_digipin_encode(
    lat: float = typer.Option(..., "--lat", help="Latitude in degrees."),
    lon: float = typer.Option(..., "--lon", help="Longitude in degrees."),
) -> None:
    """Encode coordinates into a 10-character DIGIPIN."""
    code = digipin_module.encode(lat, lon)
    console.print(f"{code}  ({digipin_module.format_code(code)})")


@digipin_app.command("decode")
def cmd_digipin_decode(code: str = typer.Argument(..., help="10-character DIGIPIN code.")) -> None:
    """Decode a DIGIPIN into its bounding box and centre."""
    console.print_json(json.dumps(digipin_module.decode(code)))


@app.command("info")
def cmd_info() -> None:
    """Show the resolved configuration."""
    settings = get_settings()
    table = Table("setting", "value")
    for key, value in (
        ("base_url", settings.base_url),
        ("data_dir", str(settings.data_dir)),
        ("db_path", str(settings.db_path)),
        ("rate", f"{settings.rate}/s (auto-tune {settings.rate_min}-{settings.rate_max})"),
        ("workers", settings.workers),
        ("user_agent", settings.user_agent),
        ("resume", get_resume()),
    ):
        table.add_row(key, str(value))
    console.print(table)


if __name__ == "__main__":
    app()
