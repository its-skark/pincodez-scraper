from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BASE_URL = "https://pincodez.info"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_8_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class Settings:
    base_url: str = BASE_URL
    data_dir: Path = field(default_factory=lambda: Path("data"))
    user_agent: str = DEFAULT_USER_AGENT
    rate: float = 6.0
    rate_min: float = 2.0
    rate_max: float = 8.0
    burst: int = 3
    workers: int = 4
    timeout: float = 30.0
    max_retries: int = 6
    wall_cooldown: float = 120.0
    wall_cooldown_max: float = 1800.0
    latency_fast: float = 0.6
    latency_slow: float = 1.5
    verbose: bool = True

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def jsonl_dir(self) -> Path:
        return self.data_dir / "jsonl"

    @property
    def csv_dir(self) -> Path:
        return self.data_dir / "csv"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pincodez.sqlite"

    @property
    def conflicts_path(self) -> Path:
        return self.data_dir / "conflicts.jsonl"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.raw_dir,
            self.jsonl_dir,
            self.csv_dir,
            self.state_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
