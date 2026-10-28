from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

WALL_MARKERS = (
    "bot verification",
    "recaptcha",
    "lsrecaptcha",
    "grecaptcha",
    "service unavailable",
)


class FetchError(RuntimeError):
    def __init__(self, url: str, status: int | None, detail: str = "") -> None:
        super().__init__(f"{url} failed status={status} {detail}".strip())
        self.url = url
        self.status = status
        self.detail = detail


class WallHit(RuntimeError):
    def __init__(self, url: str, status: int, cooldown: float) -> None:
        super().__init__(f"bot wall at {url} status={status} cooldown={cooldown:.0f}s")
        self.url = url
        self.status = status
        self.cooldown = cooldown


@dataclass(slots=True)
class LimiterState:
    rate: float
    cooldown: float
    wall_until: float = 0.0
    consecutive_walls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "cooldown": self.cooldown,
            "wall_until": self.wall_until,
            "consecutive_walls": self.consecutive_walls,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], default_rate: float, default_cooldown: float) -> "LimiterState":
        return cls(
            rate=float(raw.get("rate", default_rate)),
            cooldown=float(raw.get("cooldown", default_cooldown)),
            wall_until=float(raw.get("wall_until", 0.0)),
            consecutive_walls=int(raw.get("consecutive_walls", 0)),
        )


class RateLimiter:
    def __init__(
        self,
        rate: float,
        rate_min: float,
        rate_max: float,
        burst: int,
        latency_fast: float,
        latency_slow: float,
        state_path: Path | None = None,
    ) -> None:
        self.rate = rate
        self.rate_min = rate_min
        self.rate_max = rate_max
        self.burst = max(1, burst)
        self.latency_fast = latency_fast
        self.latency_slow = latency_slow
        self.state_path = state_path
        self._tokens = float(self.burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self._latencies: list[float] = []
        self._wall_until = 0.0
        self._cooldown = 120.0
        self._consecutive_walls = 0
        self.requests = 0
        self.wall_hits = 0
        self.retries = 0

    def load_state(self, default_rate: float, default_cooldown: float) -> None:
        if self.state_path is None or not self.state_path.exists():
            self._cooldown = default_cooldown
            return
        try:
            raw = json.loads(self.state_path.read_text())
        except (json.JSONDecodeError, OSError):
            self._cooldown = default_cooldown
            return
        state = LimiterState.from_dict(raw, default_rate, default_cooldown)
        self.rate = min(max(state.rate, self.rate_min), self.rate_max)
        self._cooldown = state.cooldown
        self._wall_until = state.wall_until
        self._consecutive_walls = state.consecutive_walls
        self._tokens = float(self.burst)

    def save_state(self) -> None:
        if self.state_path is None:
            return
        payload = LimiterState(
            rate=self.rate,
            cooldown=self._cooldown,
            wall_until=self._wall_until,
            consecutive_walls=self._consecutive_walls,
        ).to_dict()
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.state_path)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(float(self.burst), self._tokens + elapsed * self.rate)
        self._last_refill = now

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                if self._wall_until > now:
                    delay = self._wall_until - now
                else:
                    self._refill()
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        self.requests += 1
                        return
                    delay = (1.0 - self._tokens) / max(self.rate, 0.01)
            await asyncio.sleep(max(delay, 0.005) * (0.85 + random.random() * 0.3))

    def observe_latency(self, elapsed: float) -> None:
        self._latencies.append(elapsed)
        if len(self._latencies) > 40:
            self._latencies.pop(0)
        if len(self._latencies) < 12:
            return
        ordered = sorted(self._latencies)
        median = ordered[len(ordered) // 2]
        if median < self.latency_fast and self.rate < self.rate_max:
            self.rate = min(self.rate_max, self.rate + 0.5)
            self._latencies.clear()
        elif median > self.latency_slow and self.rate > self.rate_min:
            self.rate = max(self.rate_min, self.rate - 0.5)
            self._latencies.clear()

    def register_wall(self, cooldown_max: float) -> float:
        self._consecutive_walls += 1
        self.wall_hits += 1
        self._cooldown = min(cooldown_max, self._cooldown * 2 if self._consecutive_walls > 1 else self._cooldown)
        self._wall_until = time.time() + self._cooldown
        self._tokens = 0.0
        self.save_state()
        return self._cooldown

    def register_success(self) -> None:
        if self._consecutive_walls:
            self._consecutive_walls = 0
            self._cooldown = 120.0
        self.save_state()

    def wall_remaining(self) -> float:
        return max(0.0, self._wall_until - time.time())


@dataclass(slots=True)
class Result:
    url: str
    status: int
    data: Any = None
    text: str = ""
    elapsed: float = 0.0
    not_found: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Client:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        limiter: RateLimiter,
        timeout: float = 30.0,
        max_retries: int = 6,
        cooldown_max: float = 1800.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.limiter = limiter
        self.timeout = timeout
        self.max_retries = max_retries
        self.cooldown_max = cooldown_max
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=15.0),
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            },
            http2=True,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @staticmethod
    def looks_like_wall(status: int, text: str) -> bool:
        if status == 429:
            return True
        if status not in (403, 503):
            return False
        lowered = text.lower()
        return any(marker in lowered for marker in WALL_MARKERS) or status in (403, 503)

    async def get(self, path: str, params: dict[str, Any] | None = None, parse_json: bool = True) -> Result:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            await self.limiter.acquire()
            started = time.monotonic()
            try:
                response = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    raise FetchError(url, None, str(exc)) from exc
                await asyncio.sleep(min(60.0, 2**attempt) * (0.5 + random.random()))
                self.limiter.retries += 1
                continue
            elapsed = time.monotonic() - started
            text = response.text
            self.limiter.observe_latency(elapsed)

            if response.status_code == 404:
                return Result(url=url, status=404, text=text, elapsed=elapsed, not_found=True)

            if self.looks_like_wall(response.status_code, text):
                if attempt > self.max_retries:
                    raise FetchError(url, response.status_code, "wall")
                cooldown = self.limiter.register_wall(self.cooldown_max)
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        cooldown = max(cooldown, float(retry_after))
                        self.limiter._wall_until = time.time() + cooldown
                await asyncio.sleep(cooldown + random.random() * 5)
                continue

            if response.status_code >= 500:
                if attempt > self.max_retries:
                    raise FetchError(url, response.status_code, text[:200])
                await asyncio.sleep(min(60.0, 2**attempt) * (0.5 + random.random()))
                self.limiter.retries += 1
                continue

            self.limiter.register_success()
            data: Any = None
            if parse_json and response.status_code < 300:
                try:
                    data = response.json()
                except ValueError:
                    data = None
            return Result(url=url, status=response.status_code, data=data, text=text, elapsed=elapsed)

    async def download(self, path: str, params: dict[str, Any] | None, destination: Path) -> Result:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            await self.limiter.acquire()
            started = time.monotonic()
            tmp = destination.with_suffix(destination.suffix + ".part")
            try:
                async with self._client.stream("GET", path, params=params) as response:
                    if response.status_code == 404:
                        return Result(url=url, status=404, not_found=True)
                    body = await response.aread()
                    text = body.decode("utf-8", "ignore")
                    if self.looks_like_wall(response.status_code, text):
                        if attempt > self.max_retries:
                            raise FetchError(url, response.status_code, "wall")
                        cooldown = self.limiter.register_wall(self.cooldown_max)
                        await asyncio.sleep(cooldown + random.random() * 5)
                        continue
                    if response.status_code >= 400:
                        if attempt > self.max_retries:
                            raise FetchError(url, response.status_code, text[:200])
                        await asyncio.sleep(min(60.0, 2**attempt) * (0.5 + random.random()))
                        continue
                    tmp.write_bytes(body)
                    tmp.replace(destination)
            except httpx.HTTPError as exc:
                tmp.unlink(missing_ok=True)
                if attempt > self.max_retries:
                    raise FetchError(url, None, str(exc)) from exc
                await asyncio.sleep(min(60.0, 2**attempt) * (0.5 + random.random()))
                continue
            elapsed = time.monotonic() - started
            self.limiter.register_success()
            return Result(url=url, status=200, elapsed=elapsed)
