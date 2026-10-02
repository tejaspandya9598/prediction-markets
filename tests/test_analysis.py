"""Analysis logic on a fixture shaped like real Polymarket data (offline)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from predmarkets.analysis import event_consistency, summary, to_frame

# Three mutually-exclusive outcomes of one event priced to sum to 1.1 (an arb), plus an
# unrelated binary market.
MARKETS = [
    {"question": "Team A wins?", "groupItemTitle": "A", "outcomePrices": '["0.5","0.5"]',
     "spread": 0.02, "volumeNum": 1000, "negRisk": True, "events": [{"id": "E1", "title": "The Match"}]},
    {"question": "Team B wins?", "groupItemTitle": "B", "outcomePrices": '["0.4","0.6"]',
     "spread": 0.03, "volumeNum": 900, "negRisk": True, "events": [{"id": "E1", "title": "The Match"}]},
    {"question": "Team C wins?", "groupItemTitle": "C", "outcomePrices": '["0.2","0.8"]',
     "spread": 0.04, "volumeNum": 800, "negRisk": True, "events": [{"id": "E1", "title": "The Match"}]},
    {"question": "Rain tomorrow?", "outcomePrices": '["0.3","0.7"]',
     "spread": 0.01, "volumeNum": 500, "negRisk": False, "events": [{"id": "E2", "title": "Weather"}]},
]


def test_to_frame_parses_string_prices():
    df = to_frame(MARKETS)
    assert len(df) == 4
    assert abs(df.iloc[0]["yes"] - 0.5) < 1e-9


def test_summary_keys():
    s = summary(to_frame(MARKETS))
    assert s["markets"] == 4 and s["neg_risk_markets"] == 3


def test_event_consistency_flags_arbitrage():
    arb = event_consistency(to_frame(MARKETS))
    assert len(arb) == 1
    assert abs(arb.iloc[0]["yes_sum"] - 1.1) < 1e-9   # 0.5 + 0.4 + 0.2


def test_empty_input_keeps_the_schema():
    """to_frame([]) used to return a column-less frame and every caller hit KeyError."""
    df = to_frame([])
    assert df.empty and "neg_risk" in df.columns
    assert summary(df)["markets"] == 0
    assert event_consistency(df).empty


def test_malformed_prices_are_skipped_not_fatal():
    bad = [{"outcomePrices": "not json", "events": []},
           {"outcomePrices": '["abc","def"]', "events": []},
           {"outcomePrices": '["0.6","0.4"]', "events": [{"id": "E9", "title": "ok"}]}]
    assert len(to_frame(bad)) == 1


def test_arbitrage_is_netted_against_the_quoted_spread():
    """A dislocation smaller than the cost of crossing three books is not an arb."""
    tight = event_consistency(to_frame(MARKETS)).iloc[0]
    assert tight["tradeable"] and tight["short_edge"] > 0

    wide = [dict(m, spread=0.10) for m in MARKETS]
    row = event_consistency(to_frame(wide)).iloc[0]
    assert abs(row["deviation"]) > 0.02      # still off at the mid
    assert not row["tradeable"]              # but gone once you pay the spread
    assert row["net_edge"] == 0.0


def test_underpriced_baskets_rank_alongside_overpriced_ones():
    """Sorting on signed deviation buried the long arb at the bottom of the list."""
    cheap = [dict(m, outcomePrices='["0.20","0.80"]', spread=0.001,
                  events=[{"id": "E3", "title": "Cheap"}]) for m in MARKETS[:3]]
    out = event_consistency(to_frame(MARKETS + cheap))
    assert out.iloc[0]["event_title"] == "Cheap"   # 0.6 sum, biggest capturable edge
    assert out.iloc[0]["long_edge"] > 0


def test_placeholder_legs_are_dropped():
    """Polymarket ships untraded placeholder outcomes in multi-outcome events -
    active=False, zero volume, spread 1.00, price pinned at 0.5/0.5. The EPL 2027
    Champion event carries four ("Team A", "Team B", "Team C", "Other"), and summed
    with the real legs they put the basket at 3.04 instead of 1.04."""
    real = [{"groupItemTitle": "Arsenal", "outcomePrices": '["0.505","0.495"]',
             "spread": 0.01, "volumeNum": 733964, "negRisk": True, "active": True,
             "events": [{"id": "E1", "title": "EPL"}]},
            {"groupItemTitle": "Chelsea", "outcomePrices": '["0.135","0.865"]',
             "spread": 0.01, "volumeNum": 684221, "negRisk": True, "active": True,
             "events": [{"id": "E1", "title": "EPL"}]}]
    placeholders = [{"groupItemTitle": f"Team {c}", "outcomePrices": '["0.5","0.5"]',
                     "spread": 1, "volumeNum": 0.0, "negRisk": True, "active": False,
                     "events": [{"id": "E1", "title": "EPL"}]} for c in "ABC"]

    assert len(to_frame(real + placeholders)) == 2
    assert len(to_frame(real + placeholders, live_only=False)) == 5


def test_partial_baskets_are_not_reported_as_arbitrage():
    """A 50-outcome event seen five legs deep sums to ~0.01 and looks like a 99%
    arbitrage. Only complete baskets are reported."""
    from predmarkets.analysis import events_to_frame

    legs = [{"groupItemTitle": str(i), "outcomePrices": f'["{0.02:.3f}","{0.98:.3f}"]',
             "spread": 0.01, "volumeNum": 5000, "active": True} for i in range(5)]
    event = {"id": "BIG", "title": "Fifty-outcome race", "negRisk": True, "markets": legs}

    df = events_to_frame([event])
    assert df["n_event_markets"].iloc[0] == 5      # counts the live legs it holds

    # Pretend we only hold 3 of the 5 — the basket must not be called tradeable.
    partial = df.iloc[:3].copy()
    partial["n_event_markets"] = 5
    out = event_consistency(partial)
    assert out.empty or not out["complete"].any()


def test_events_to_frame_counts_every_leg_and_the_live_ones():
    from predmarkets.analysis import events_to_frame

    legs = [{"groupItemTitle": "A", "outcomePrices": '["0.6","0.4"]', "spread": 0.01,
             "volumeNum": 1000, "active": True},
            {"groupItemTitle": "B", "outcomePrices": '["0.4","0.6"]', "spread": 0.01,
             "volumeNum": 1000, "active": True},
            {"groupItemTitle": "Other", "outcomePrices": '["0.5","0.5"]', "spread": 1,
             "volumeNum": 0, "active": False}]
    df = events_to_frame([{"id": "E", "title": "T", "negRisk": True, "markets": legs}])
    assert len(df) == 2                              # the placeholder is not priced in
    assert df["n_event_markets"].iloc[0] == 3        # but it is still an outcome
    out = event_consistency(df, threshold=0.0)
    assert not out["complete"].any()


def _event(prices, extra_dead=0, eid="E"):
    legs = [{"groupItemTitle": f"L{i}", "outcomePrices": f'["{p:.3f}","{1 - p:.3f}"]',
             "spread": 0.002, "volumeNum": 1000, "active": True} for i, p in enumerate(prices)]
    legs += [{"groupItemTitle": f"D{i}", "outcomePrices": '["0.5","0.5"]', "spread": 1,
              "volumeNum": 0, "active": False} for i in range(extra_dead)]
    return {"id": eid, "title": eid, "negRisk": True, "markets": legs}


def test_long_basket_with_untradeable_legs_is_not_an_arbitrage():
    """Buying every LIVE leg of a cheap basket only pays $1 if one of them wins.
    The Nobel Peace Prize 2026 event (2026-10-02) had 32 live legs out of 71 and
    priced to 0.613; it was reported as a 32% riskless arbitrage."""
    from predmarkets.analysis import events_to_frame

    out = event_consistency(events_to_frame([_event([0.3, 0.2, 0.1], extra_dead=4)]))
    assert out.empty or not out["tradeable"].any()

    whole = event_consistency(events_to_frame([_event([0.3, 0.2, 0.1])]))
    assert whole.iloc[0]["tradeable"] and whole.iloc[0]["long_edge"] > 0


def test_short_basket_survives_untradeable_legs():
    """Selling an overpriced basket of live legs is riskless even if a dead leg
    exists: if that outcome wins, every sold leg expires worthless. The EPL 2027
    case: real legs at 1.04 alongside four placeholders."""
    from predmarkets.analysis import events_to_frame

    out = event_consistency(events_to_frame([_event([0.6, 0.5], extra_dead=4)]))
    assert len(out) == 1 and out.iloc[0]["tradeable"] and out.iloc[0]["short_edge"] > 0
