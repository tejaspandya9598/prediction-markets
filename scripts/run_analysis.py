"""
Pull live Polymarket markets and scan for mispricing.

    python scripts/run_analysis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from predmarkets.analysis import event_consistency, summary, to_frame   # noqa: E402
from predmarkets.client import load_markets                            # noqa: E402
from predmarkets.viz import plot_prob_distribution, plot_spread_vs_liquidity  # noqa: E402


def main() -> None:
    print("Fetching live Polymarket markets (cached after first run)...")
    df = to_frame(load_markets())
    print(f"  {len(df)} markets\n")

    print("Book summary:")
    for k, v in summary(df).items():
        print(f"  {k:<22} {v:,.2f}" if isinstance(v, float) else f"  {k:<22} {v}")

    arb = event_consistency(df)
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
