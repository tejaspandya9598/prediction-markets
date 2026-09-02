"""
Turn raw Polymarket markets into tradeable signals.

  * `to_frame`            — flatten markets into prices, spreads, volume, event id.
  * `event_consistency`   — the real edge: mutually-exclusive outcomes in a neg-risk
                            event must price to ~1. When their YES prices sum away from
                            1, there's a static arbitrage (short the overpriced basket).
  * `summary`             — book-wide stats, incl. the favorite-longshot price spread.

The mid price says whether an event is *inconsistent*. Whether it is *tradeable* is a
different question, and one the quoted spread answers: you buy the basket at the asks
and sell it at the bids, so a 2c dislocation across three legs quoting 3c wide is not
an arbitrage, it's a fee. `event_consistency` reports both.
"""
from __future__ import annotations

import json

import pandas as pd

COLUMNS = ["question", "outcome", "yes", "no", "binary_sum", "spread", "volume",
           "liquidity", "neg_risk", "event_id", "event_title"]

NO_EVENT = "<no-event>"


def _outcome_prices(market: dict):
    p = market.get("outcomePrices")
    if isinstance(p, str):
        if not p:
            return None
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            return None
    return p


def to_frame(markets: list[dict]) -> pd.DataFrame:
    rows = []
    for m in markets:
        prices = _outcome_prices(m)
        if not prices or len(prices) < 2:
            continue
        try:
            yes, no = float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            continue
        event = (m.get("events") or [{}])[0]
        rows.append({
            "question": (m.get("question") or "")[:80],
            "outcome": m.get("groupItemTitle") or "Yes",
            "yes": yes, "no": no, "binary_sum": yes + no,
            "spread": float(m.get("spread") or 0.0),
            "volume": float(m.get("volumeNum") or m.get("volume") or 0.0),
            "liquidity": float(m.get("liquidityNum") or m.get("liquidity") or 0.0),
            "neg_risk": bool(m.get("negRisk")),
            # groupby drops NaN keys, so an event-less market would vanish without
            # a word. Give it a name and let it be counted and then filtered.
            "event_id": event.get("id") or NO_EVENT,
            "event_title": (event.get("title") or "")[:80],
        })
    # An empty list must still carry the schema — callers index these columns.
    return pd.DataFrame(rows, columns=COLUMNS)


def event_consistency(df: pd.DataFrame, threshold: float = 0.02) -> pd.DataFrame:
    """Neg-risk events whose mutually-exclusive YES prices sum far from 1.

    `deviation` is the mid-price dislocation. `long_edge` / `short_edge` are what
    survives crossing the quoted spread on every leg — buy the basket at the asks
    for 1 - Σask, sell it at the bids for Σbid - 1. `net_edge` is the better of the
    two, floored at zero, and `tradeable` is whether anything is left at all.
    """
    rows = []
    neg = df[df["neg_risk"] & (df["event_id"] != NO_EVENT)]
    for (_eid, title), g in neg.groupby(["event_id", "event_title"]):
        if len(g) < 2:
            continue
        half = g["spread"] / 2.0
        yes_sum = g["yes"].sum()
        ask_sum = (g["yes"] + half).sum()
        bid_sum = (g["yes"] - half).sum()
        long_edge = 1.0 - ask_sum        # buy every outcome, collect $1 at expiry
        short_edge = bid_sum - 1.0       # sell the basket, pay $1 at expiry
        net_edge = max(long_edge, short_edge, 0.0)
        rows.append({"event_title": title, "n_outcomes": len(g), "yes_sum": yes_sum,
                     "deviation": yes_sum - 1.0, "ask_sum": ask_sum, "bid_sum": bid_sum,
                     "long_edge": long_edge, "short_edge": short_edge,
                     "net_edge": net_edge, "tradeable": net_edge > 0.0,
                     "volume": g["volume"].sum()})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Rank on what you could actually capture, then on the raw dislocation. Sorting
    # on signed deviation buried the underpriced baskets, which are the long arb.
    hits = out[out["deviation"].abs() > threshold]
    return hits.sort_values(["net_edge", "deviation"],
                            key=lambda c: c.abs() if c.name == "deviation" else c,
                            ascending=False)


def summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"markets": 0, "total_volume": 0.0, "mean_yes_prob": float("nan"),
                "mean_spread_cents": float("nan"), "wide_spread_>5c": 0,
                "neg_risk_markets": 0}
    return {
        "markets": len(df),
        "total_volume": float(df["volume"].sum()),
        "mean_yes_prob": float(df["yes"].mean()),
        "mean_spread_cents": float(df["spread"].mean() * 100),
        "wide_spread_>5c": int((df["spread"] > 0.05).sum()),
        "neg_risk_markets": int(df["neg_risk"].sum()),
    }
