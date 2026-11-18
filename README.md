# GTA VI Launch-Day Twitch Forecast

[![Competition](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![Rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Gas2405/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![Reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Gas2405/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Entry for the make.fun bounty [Forecast GTA VI's launch-day Twitch viewers hour by hour](https://make.fun/bounty/gta6-twitch-ccu-forecast-01): `main.py` (Python 3.13, standard library only, no network) reads each case in `$MAKEFUN_INPUT_DIR` and writes, for hours 2–24 of the release day, five quantiles (0.05 / 0.25 / 0.5 / 0.75 / 0.95) of the hour's concurrent viewers in the "Grand Theft Auto VI" Twitch category.

## The model

A similarity-weighted ensemble of past launch curves, using only what the case file provides:

- **Pool.** Comparables the kit labels tier "comparable" (early-access-contaminated, weak and target-history entries excluded), not clearly simultaneous-global unlocks, with a full release day of hourly points and an hour-1 audience of at least 2% of their day peak — a rolling-midnight launch already has viewers in hour 1; a simultaneous one starts near zero and would poison the shape pool.
- **Anchor.** Each launch's curve is divided by a level anchor: the geometric mean of its viewers over a few hours straddling the day boundary. The forecast is scaled by the target's own anchor, so the noisy single hour-1 print never stands alone.
- **Weights.** A comparable earns weight `exp(-d / 0.5)`, where `d` is the RMS distance between its pre-release ramp (log viewers relative to its hour 1 over the last few hours before the day) and the target's ramp — launches that were ramping the same way into midnight tend to share the day's shape.
- **Quantiles.** Two ensembles (anchor windows (−1, 0, 1) and (0, 1), ramp windows −4..1 and −6..1) are blended 50/50 in log space; each hour's quantiles are the weighted empirical quantiles of the pool's log ratios, with the spread around the median shrunk by 0.95. Fallbacks (thin pool → unweighted pool quantiles; empty pool → the house persistence spread) keep every case valid.

The program is a pure function of its input — no clock, no randomness — so repeated runs are byte-identical.

## Backtest (practice cases, pinball loss on log scale, lower is better)

Scored locally against the four practice launches' recorded release days (SullyGnome hourly averages, fetched as the kit's NOTICE describes), with the competition's own scoring rule:

| model | p00 Wolverine | p01 RDR2 | p02 God of War Ragnarök | p03 Spider-Man 2 | mean |
|---|---|---|---|---|---|
| this entry | 0.237 | 0.135 | 0.209 | 0.206 | **0.197** |
| house baseline (persistence) | 0.744 | 0.287 | 0.215 | 0.303 | 0.387 |
| flat at hour 1 | 1.061 | 0.503 | 0.351 | 0.497 | 0.603 |

On leave-one-out pseudo-cases over the rolling-midnight launches in the pool, the entry scores 0.263 against the house baseline's 0.369. Weakest spot: launches whose audience is heavily US-centric with a small hour 1 (Wolverine's late surge to ~9× hour 1 is the hardest shape in the set).

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Referral: [make.fun/r/9v18ghw6](https://make.fun/r/9v18ghw6)
