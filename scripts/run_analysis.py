"""
Pull live Polymarket markets and scan for mispricing.

    python scripts/run_analysis.py                                   # live; saves a snapshot
    python scripts/run_analysis.py --snapshot data/snapshots/2026-10-02   # replay, offline
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from predmarkets.analysis import event_consistency, events_to_frame, summary, to_frame  # noqa: E402
from predmarkets.client import (fetch_events, fetch_markets, load_snapshot,  # noqa: E402
                                save_snapshot)
from predmarkets.viz import plot_prob_distribution, plot_spread_vs_liquidity  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Polymarket book summary and neg-risk arbitrage scan.")
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="replay a saved data/snapshots/<day>/ pull instead of calling the API")
    args = ap.parse_args()

    if args.snapshot:
        markets, events = load_snapshot(args.snapshot)
        print(f"Replaying snapshot {args.snapshot}")
    else:
        print("Fetching live Polymarket markets and events...")
        markets, events = fetch_markets(400), fetch_events(200)
        snap = save_snapshot(markets, events, date.today().isoformat())
        print(f"  saved snapshot -> {snap.relative_to(ROOT)}")
    df = to_frame(markets)
    print(f"  {len(df)} markets\n")

    print("Book summary:")
    for k, v in summary(df).items():
        print(f"  {k:<22} {v:,.2f}" if isinstance(v, float) else f"  {k:<22} {v}")

    # The arbitrage check needs whole baskets, so it comes from /events (each of
    # which carries its full market list) rather than from the /markets page above.
    ev_df = events_to_frame(events)
    print(f"  {ev_df['event_id'].nunique()} events, {len(ev_df)} legs")
    arb = event_consistency(ev_df)
    tradeable = int(arb["tradeable"].sum()) if not arb.empty else 0
    print(f"\nNeg-risk events off 1 at the mid: {len(arb)}"
          f"  |  still profitable after crossing the spread: {tradeable}")
    if not arb.empty:
        cols = ["event_title", "n_outcomes", "yes_sum", "deviation", "net_edge",
                "tradeable", "volume"]
        print(arb.head(10)[cols].to_string(index=False))

    out = ROOT / "reports"
    (out / "figures").mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "markets.csv", index=False)
    arb.to_csv(out / "arbitrage_candidates.csv", index=False)
    plot_prob_distribution(df, out / "figures" / "prob_distribution.png")
    plot_spread_vs_liquidity(df, out / "figures" / "spread_vs_liquidity.png")
    print(f"\nwrote -> {out}/ (markets.csv, arbitrage_candidates.csv, figures/)")


if __name__ == "__main__":
    main()
