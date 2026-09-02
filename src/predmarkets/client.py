"""
Polymarket Gamma API client (public, no key, no synthetic data).

Pulls live markets; results are cached to data/ so analysis is reproducible offline
after the first pull. The cache is deliberately dumb — a flat JSON dump — but it is
checked against what was asked for: a cache holding 100 markets does not satisfy a
request for 400, and a cache from last month does not describe today's book.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

GAMMA = "https://gamma-api.polymarket.com"
CACHE = Path(__file__).resolve().parents[2] / "data" / "markets.json"

# Gamma caps a page at 100 no matter what `limit` asks for. Requesting 400 returns
# 100, so a paginator that stops when a page comes back shorter than requested stops
# on the first page and reports a quarter of the book as the whole book.
PAGE = 100
MAX_CACHE_AGE_S = 12 * 3600


def _paged(path: str, limit: int, order: str) -> list[dict]:
    out: list[dict] = []
    while len(out) < limit:
        params = {"limit": min(PAGE, limit - len(out)), "offset": len(out),
                  "closed": "false", "active": "true", "order": order, "ascending": "false"}
        resp = requests.get(f"{GAMMA}/{path}", params=params, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        out.extend(page)
    return out[:limit]


def fetch_markets(limit: int = 400, order: str = "volume24hr") -> list[dict]:
    """Active markets, most-traded first. Pages until `limit` is met or the feed ends."""
    return _paged("markets", limit, order)


def fetch_events(limit: int = 200, order: str = "volume24hr") -> list[dict]:
    """Active events, each carrying its **complete** list of member markets.

    This is the right source for the neg-risk arbitrage check. Assembling events by
    grouping a page of /markets gives you whichever legs happened to be in that page,
    and an event whose outcomes sum to 1 looks like a 99% arbitrage when you are
    holding five of its fifty legs.
    """
    return _paged("events", limit, order)


def _cache_is_usable(limit: int, max_age_s: float) -> bool:
    if not CACHE.exists():
        return False
    if time.time() - CACHE.stat().st_mtime > max_age_s:
        return False
    try:
        return len(json.loads(CACHE.read_text())) >= limit
    except (json.JSONDecodeError, TypeError):
        return False


def load_markets(limit: int = 400, use_cache: bool = True,
                 max_age_s: float = MAX_CACHE_AGE_S) -> list[dict]:
    if use_cache and _cache_is_usable(limit, max_age_s):
        return json.loads(CACHE.read_text())[:limit]
    markets = fetch_markets(limit=limit)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(markets))
    return markets
