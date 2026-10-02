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

# A leg with no two-sided market quotes 1.00 wide and sits at the 0.5/0.5 default.
# Polymarket carries several of these in a multi-outcome event as placeholders -
# the EPL 2027 Champion event ships "Team A", "Team B", "Team C" and "Other", all
# active=False with zero volume and zero liquidity. Summed with the real legs they
# put the basket at 3.04 instead of 1.04, which reads as a 200% arbitrage.
MAX_LIVE_SPREAD = 0.999


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


def _is_live(market: dict, spread: float) -> bool:
    """Is there an actual two-sided market here, or only a placeholder row?"""
    if market.get("active") is False:
        return False
    return spread < MAX_LIVE_SPREAD


def to_frame(markets: list[dict], live_only: bool = True) -> pd.DataFrame:
    """Flatten markets. `live_only` drops placeholder legs — see MAX_LIVE_SPREAD."""
    rows = []
    for m in markets:
        prices = _outcome_prices(m)
        if not prices or len(prices) < 2:
            continue
        try:
            yes, no = float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            continue
        spread = float(m.get("spread") or 0.0)
        if live_only and not _is_live(m, spread):
            continue
        event = (m.get("events") or [{}])[0]
        rows.append({
            "question": (m.get("question") or "")[:80],
            "outcome": m.get("groupItemTitle") or "Yes",
            "yes": yes, "no": no, "binary_sum": yes + no,
            "spread": spread,
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

    Only events whose full outcome set is present are reported: a partial basket
    always looks mispriced and never is.

    `deviation` is the mid-price dislocation. `long_edge` / `short_edge` are what
    survives crossing the quoted spread on every leg — buy the basket at the asks
    for 1 - Σask, sell it at the bids for Σbid - 1.

    The two sides need different things. Selling an overpriced basket is riskless
    with or without the dead legs: if an outcome you did not sell wins, every leg
    you did sell expires worthless. Buying a cheap basket pays $1 only if the winner
    is in it, so the long side counts only when `complete` — every leg of the event
    live and held. The Nobel Peace Prize 2026 event priced its 32 live legs (of 71)
    at 0.613 on 2026-10-02, and counting live legs as the whole event reported that
    as a 32% riskless arbitrage. `net_edge` is the better usable side, floored at 0.
    """
    rows = []
    neg = df[df["neg_risk"] & (df["event_id"] != NO_EVENT)]
    has_counts = "n_event_markets" in df.columns
    for (_eid, title), g in neg.groupby(["event_id", "event_title"]):
        if len(g) < 2:
            continue
        # A neg-risk basket only sums to 1 when you hold *every* leg. Grouping a
        # page of /markets gives whichever legs landed in that page, and a
        # 50-outcome event seen 5 legs deep sums to ~0.01 and reads as a 99%
        # arbitrage. Events pulled from /events carry their true leg count.
        expected = int(g["n_event_markets"].iloc[0]) if has_counts else len(g)
        complete = len(g) >= expected > 0
        half = g["spread"] / 2.0
        yes_sum = g["yes"].sum()
        ask_sum = (g["yes"] + half).sum()
        bid_sum = (g["yes"] - half).sum()
        long_edge = 1.0 - ask_sum        # buy every outcome, collect $1 at expiry
        short_edge = bid_sum - 1.0       # sell the basket, pay $1 at expiry
        usable_long = long_edge if complete else 0.0
        net_edge = max(usable_long, short_edge, 0.0)
        rows.append({"event_title": title, "n_outcomes": len(g),
                     "n_event_markets": expected, "complete": complete,
                     "yes_sum": yes_sum,
                     "deviation": yes_sum - 1.0, "ask_sum": ask_sum, "bid_sum": bid_sum,
                     "long_edge": long_edge, "short_edge": short_edge,
                     "net_edge": net_edge, "tradeable": net_edge > 0.0,
                     "volume": g["volume"].sum()})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Rank on what you could actually capture, then on the raw dislocation. Sorting
    # on signed deviation buried the underpriced baskets, which are the long arb.
    # A partial basket is still worth reporting when it is overpriced (the short side
    # does not need every leg); an underpriced partial basket is not an arbitrage.
    hits = out[(out["deviation"].abs() > threshold) & (out["complete"] | (out["deviation"] > 0))]
    return hits.sort_values(["net_edge", "deviation"],
                            key=lambda c: c.abs() if c.name == "deviation" else c,
                            ascending=False)


def events_to_frame(events: list[dict]) -> pd.DataFrame:
    """Flatten `/events` payloads, keeping each event's complete market list.

    Every row carries `n_event_markets`, the number of legs the event actually has
    (placeholders and untraded legs included, since any of them can still win), so a
    basket of live legs can be checked for completeness rather than assumed.
    """
    rows = []
    totals: dict[str, int] = {}
    for ev in events:
        markets = ev.get("markets") or []
        totals[str(ev.get("id"))] = len(markets)
        for m in markets:
            m = dict(m)
            m.setdefault("events", [{"id": ev.get("id"), "title": ev.get("title")}])
            m.setdefault("negRisk", ev.get("negRisk"))
            rows.append(m)
    df = to_frame(rows)
    if df.empty:
        df["n_event_markets"] = pd.Series(dtype=int)
        return df
    # Every leg the event has, live or not. Counting only the legs that survived the
    # liveness filter made every basket look complete (2026-10-02 audit).
    df["n_event_markets"] = df["event_id"].astype(str).map(totals).fillna(0).astype(int)
    return df


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
