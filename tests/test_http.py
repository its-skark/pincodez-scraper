import asyncio
import json
import time

import pytest

from pincodez_scraper.http import Client, RateLimiter

WALL_HTML = """
<html><head><title>Bot Verification</title></head><body>
<script>grecaptcha.render('recaptchadiv', {'sitekey': '6LewU34UAAAAAHvXqFOcQlm8z1MP1xpGAZCYEeZY'});</script>
</body></html>
"""

SERVICE_HTML = "<html><body><h1>503</h1><p>The server is temporarily busy, try again later!</p></body></html>"


def test_detects_bot_wall():
    assert Client.looks_like_wall(403, WALL_HTML)
    assert Client.looks_like_wall(503, SERVICE_HTML)
    assert Client.looks_like_wall(429, "too many requests")


def test_normal_responses_are_not_walls():
    assert not Client.looks_like_wall(200, WALL_HTML)
    assert not Client.looks_like_wall(404, '{"error": "Endpoint not found"}')
    assert not Client.looks_like_wall(500, "internal error")


def test_limiter_paces_requests():
    limiter = RateLimiter(rate=20.0, rate_min=2.0, rate_max=8.0, burst=1,
                           latency_fast=0.6, latency_slow=1.5)
    started = time.monotonic()

    async def run():
        for _ in range(3):
            await limiter.acquire()

    asyncio.run(run())
    elapsed = time.monotonic() - started
    assert elapsed >= 0.09
    assert limiter.requests == 3


def test_limiter_auto_tunes_up_then_down():
    limiter = RateLimiter(rate=3.0, rate_min=2.0, rate_max=8.0, burst=2,
                           latency_fast=0.6, latency_slow=1.5)
    for _ in range(15):
        limiter.observe_latency(0.1)
    assert limiter.rate == 3.5

    limiter.rate = 8.0
    for _ in range(15):
        limiter.observe_latency(2.5)
    assert limiter.rate == 7.5

    limiter.rate = 2.0
    for _ in range(15):
        limiter.observe_latency(3.0)
    assert limiter.rate == 2.0


def test_wall_cooldown_escalates_and_persists(tmp_path):
    state_path = tmp_path / "limiter.json"
    limiter = RateLimiter(rate=6.0, rate_min=2.0, rate_max=8.0, burst=3,
                           latency_fast=0.6, latency_slow=1.5, state_path=state_path)
    limiter._cooldown = 120.0
    first = limiter.register_wall(1800.0)
    second = limiter.register_wall(1800.0)
    assert first == 120.0
    assert second == 240.0
    assert limiter.wall_remaining() > 0

    saved = json.loads(state_path.read_text())
    assert saved["consecutive_walls"] == 2
    assert saved["cooldown"] == 240.0

    restored = RateLimiter(rate=6.0, rate_min=2.0, rate_max=8.0, burst=3,
                            latency_fast=0.6, latency_slow=1.5, state_path=state_path)
    restored.load_state(6.0, 120.0)
    assert restored.rate == 6.0
    assert restored.wall_remaining() > 0


def test_wall_cooldown_is_capped(tmp_path):
    limiter = RateLimiter(rate=6.0, rate_min=2.0, rate_max=8.0, burst=3,
                           latency_fast=0.6, latency_slow=1.5, state_path=tmp_path / "l.json")
    limiter._cooldown = 120.0
    for _ in range(10):
        limiter.register_wall(1800.0)
    assert limiter._cooldown == 1800.0


def test_success_resets_wall_state(tmp_path):
    limiter = RateLimiter(rate=6.0, rate_min=2.0, rate_max=8.0, burst=3,
                           latency_fast=0.6, latency_slow=1.5, state_path=tmp_path / "l.json")
    limiter._cooldown = 120.0
    limiter.register_wall(1800.0)
    limiter.register_success()
    assert limiter._consecutive_walls == 0
    assert limiter._cooldown == 120.0
