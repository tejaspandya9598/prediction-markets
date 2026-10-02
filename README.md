# Prediction-Market Analytics (Polymarket)

Pull **live Polymarket markets** and turn them into tradeable signals: implied
probabilities, the favorite–longshot price distribution, spreads/liquidity, and — the
real edge — **cross-outcome arbitrage** on multi-outcome (neg-risk) events.

## The edge

The outcomes of a neg-risk event are mutually exclusive and exhaustive, so their YES
prices must sum to ~1. When they don't, there's a **static arbitrage**: if three
mutually-exclusive outcomes price at 0.5 / 0.4 / 0.2 (sum 1.1), shorting the basket
locks in the 0.10 overround before fees. `event_consistency` scans every event for
exactly this and ranks events by the edge left after crossing the spread.

Getting a believable answer out of this takes four rules that the arithmetic
alone does not suggest, and each of them was found by running it against the live
book rather than by reasoning about it.

**Whole baskets only.** The check is over events pulled from `/events`, which carry
their complete market list. Assembling events by grouping a page of `/markets` gives
you whichever legs happened to land in that page: the Democratic Nominee 2028 event
has 51 outcomes, five of them showed up, they summed to 0.0095, and that reported as
a 99% arbitrage.

**Live legs priced, every leg counted.** Polymarket carries untraded placeholders inside
multi-outcome events — the EPL 2027 Champion event ships "Team A", "Team B", "Team C" and
"Other", each `active=False`, zero volume, zero liquidity, spread quoted at 1.00 and price
pinned at the 0.5/0.5 default. Four of those summed with 20 real legs put the basket at
3.04 instead of 1.04, so placeholders are left out of the price sum. They still count
toward the event's size, though, because a dropped outcome can still win.

**Long only from complete baskets.** Selling an overpriced basket is riskless even with
legs missing: if an outcome you did not sell wins, every leg you sold expires worthless.
Buying a cheap one pays $1 only if the winner is among the legs you hold, so the long
side is taken only when every outcome of the event is live. Without this rule a Nobel
Peace Prize basket holding 32 of its 71 outcomes, priced at 0.613, reported as a 32%
riskless arbitrage; two tests pin the rule.

**Net of the spread.** You buy the basket at the asks and sell it at the bids, so the
edge is `1 - Σask` or `Σbid - 1`, not the mid-price deviation. On the UEFA event a
5.8% dislocation at the mid survives as 0.7% after crossing 36 books.

With all four, on the committed 2026-10-02 snapshot (200 events, 5,342 live legs;
replay with `--snapshot data/snapshots/2026-10-02`), 15 baskets sit more than 2% off 1 at
the mid and 8 are still positive after crossing the spread:

| event | outcomes | Σ YES | deviation | net edge | side | volume |
|---|--:|--:|--:|--:|---|--:|
| # of views of next MrBeast video on day 1? | 7 | 1.0530 | +0.0530 | **1.7%** | sell | $0.08M |
| Balance of Power: 2026 Midterms | 5 | 1.0250 | +0.0250 | 0.9% | sell | $15.5M |
| Brazil 1st round: Renan Santos vote share | 5 | 1.0275 | +0.0275 | 0.5% | sell | $0.23M |
| Pro Football: 2027 Champion | 32 | 1.0360 | +0.0360 | 0.3% | sell | $62.7M |
| Fed Decision in December? | 5 | 0.9770 | −0.0230 | 0.3% | buy | $2.5M |
| Worlds 2026: Winner | 18 | 1.0600 | +0.0600 | 0.3% | sell | $0.24M |
| Which company has best AI model end of 2026? | 15 | 1.0325 | +0.0325 | 0.1% | sell | $2.0M |
| Brazil 1st round: margin of victory | 11 | 1.0325 | +0.0325 | 0.1% | sell | $0.81M |

Almost every survivor is an overround you sell, the bookmaker's margin on a book that
settles soon, and the edges are a fraction of a percent once the spread is paid. A
dislocation at the mid is mostly spread: Latvia vs Montenegro's exact-score book sums to
1.46 and still leaves nothing after crossing it. These are gross of fees and gas, and
they are candidates to size against the book, not free money.

## What it computes

- **Implied probabilities** from `outcomePrices` and their distribution (the
  favorite–longshot lens).
- **Event consistency / arbitrage** (`analysis.event_consistency`) — the signal above.
- **Spreads & liquidity** — where the tradeable, liquid markets actually are.

## The math

For a neg-risk event with mutually exclusive, exhaustive outcomes, no-arbitrage
requires the YES prices to behave like a probability measure:

$$\sum_i p_i = 1$$

If $\sum_i \text{ask}_i < 1$, buying one YES of everything costs less than the \$1
the winning outcome must pay — a static long arbitrage of $1 - \sum \text{ask}_i$
gross. If $\sum_i \text{bid}_i > 1$, selling the basket locks in the overround
$\sum \text{bid}_i - 1$ the same way. Both are riskless at expiry regardless of the
outcome, provided the long basket holds every outcome of the event; that is what
distinguishes them from a directional bet. The scanner ranks events by the edge left
after crossing the quoted spread on every leg, then by $|\,1 - \sum p_i\,|$. Exchange
fees and gas are not netted.

The favorite-longshot distribution view comes from the same identity: with prices as
implied probabilities, systematic overpricing of low-probability outcomes shows up
as mass at the extremes of the $p$ histogram — the classic bias documented in
betting and options markets alike.

## References

- Wolfers, J. & Zitzewitz, E. (2004), *Prediction Markets*, Journal of Economic Perspectives 18(2) — prices as probabilities and their calibration.
- Snowberg, E. & Wolfers, J. (2010), *Explaining the Favorite-Longshot Bias*, JPE 118(4).

## Run

```bash
uv sync
uv run python scripts/run_analysis.py   # live Polymarket pull -> summary, arb list, figures
uv run python scripts/run_analysis.py --snapshot data/snapshots/2026-10-02   # replay offline
uv run pytest                           # analysis logic on a fixture (offline)
```

A live run pulls markets and events from the Polymarket Gamma API and saves the payload
to `data/snapshots/<date>/` (about 3 MB gzipped), so any published table can be replayed
exactly; output (summary, `arbitrage_candidates.csv`, charts) lands in `reports/`.

## Structure

```
prediction-markets/
├── src/predmarkets/
│   ├── client.py     # Polymarket Gamma API client (public, cached)
│   ├── analysis.py   # implied probs, neg-risk arbitrage, book summary
│   └── viz.py        # probability distribution + spread/liquidity
├── scripts/run_analysis.py
└── tests/            # analysis logic on a real-shaped fixture
```

## Notes

- **Live data for the scan, fixtures for the tests.** Markets come live from Polymarket;
  the 12 unit tests run on fixtures shaped like the real API response, so the
  arbitrage logic is checked deterministically and offline.
- Edges are net of the quoted spread but gross of fees and gas, and the bid/ask is
  inferred as mid ± half the quoted spread rather than read from the book. Treat flagged
  events as candidates to size against the book, not free money.

---

*Built by Tejas Pandya — NYU MSFE.*
