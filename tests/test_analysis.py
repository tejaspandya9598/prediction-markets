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
