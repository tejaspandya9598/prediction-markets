# Prediction-Market Analytics (Polymarket)

Pull **live Polymarket markets** and turn them into tradeable signals: implied
probabilities, the favorite–longshot price distribution, spreads/liquidity, and — the
real edge — **cross-outcome arbitrage** on multi-outcome (neg-risk) events.

## The edge

The outcomes of a neg-risk event are mutually exclusive and exhaustive, so their YES
prices must sum to ~1. When they don't, there's a **static arbitrage**: if three
mutually-exclusive outcomes price at 0.5 / 0.4 / 0.2 (sum 1.1), shorting the basket
locks in the 0.10 overround (minus fees). `event_consistency` scans every event for
exactly this and ranks the deviations by size and volume.

Getting a believable answer out of this takes three filters that the arithmetic
alone does not suggest, and each of them was found by running it against the live
book rather than by reasoning about it.

**Whole baskets only.** The check is over events pulled from `/events`, which carry
their complete market list. Assembling events by grouping a page of `/markets` gives
you whichever legs happened to land in that page: the Democratic Nominee 2028 event
has 51 outcomes, five of them showed up, they summed to 0.0095, and that reported as
a 99% arbitrage.

**Live legs only.** Polymarket carries untraded placeholders inside multi-outcome
events — the EPL 2027 Champion event ships "Team A", "Team B", "Team C" and "Other",
each `active=False`, zero volume, zero liquidity, spread quoted at 1.00 and price
pinned at the 0.5/0.5 default. Four of those summed with 20 real legs put the basket
at 3.04 instead of 1.04.

**Net of the spread.** You buy the basket at the asks and sell it at the bids, so the
edge is `1 - Σask` or `Σbid - 1`, not the mid-price deviation. On the UEFA event a
5.8% dislocation at the mid survives as 0.7% after crossing 36 books.

With all three, from a live run on 2026-09-02 (200 events, 3,367 live legs):

| event | outcomes | Σ YES | deviation | net edge | volume |
|---|--:|--:|--:|--:|--:|
| Republican Presidential Nominee 2028 | 42 | 0.9265 | −0.0735 | **5.0%** | $694M |
| Democratic Presidential Nominee 2028 | 51 | 0.9370 | −0.0630 | **3.4%** | $1,271M |
| Pro Football: 2027 Champion | 32 | 1.0500 | +0.0500 | 1.8% | $49M |
| F1 Drivers' Champion | 22 | 0.9710 | −0.0290 | 1.7% | $202M |
| UEFA Champions League: 2027 Champion | 36 | 1.0575 | +0.0575 | 0.7% | $22M |
| EPL: 2027 Champion | 20 | 1.0355 | +0.0355 | 0.3% | $14M |

The sums now sit where a probability measure should, and the sign splits along a
line worth noticing: **the sports books trade above 1 and the long-dated political
books trade below it.** An overround on a season that settles within the year is the
familiar bookmaker's margin. A basket at 0.9265 that pays 1.00 in 2028, though, is
not free money — it is roughly 8% over about two and a quarter years, or ~3.4%
annualised, which is what you would want for locking up collateral that long. Most
of the "arbitrage" at the top of this table is the time value of money, and a scanner
that reports it as edge is measuring the discount rate.

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
outcome, which is what distinguishes them from a directional bet; the scanner ranks
events by $|\,1 - \sum p_i\,|$ and available volume, and the report nets estimated
fees before calling anything a candidate.

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
uv run pytest                           # analysis logic on a fixture (offline)
```

The first run pulls live markets from the Polymarket Gamma API and caches them; output
(summary, `arbitrage_candidates.csv`, charts) lands in `reports/`.

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

- **Real data, no synthetic.** Markets come live from Polymarket; the unit tests run on
  a small fixture shaped like the real API response so the arbitrage logic is checked
  deterministically and offline.
- Arbitrage figures are gross of fees and gas; treat flagged events as candidates to
  size against the book, not free money.

---

*Built by Tejas Pandya — NYU MSFE.*
