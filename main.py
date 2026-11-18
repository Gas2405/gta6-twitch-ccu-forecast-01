"""gta6-twitch-ccu-forecast-01 entry: a comparable-ensemble forecast of launch-day Twitch viewers.

Model (chosen by backtests on the four practice cases and leave-one-out pseudo-cases over all
42 launches in the kit; see the repository README):

  * Pool: the case's comparables whose kit tier is "comparable" (early-access-contaminated, weak
    and target-history entries are out), whose unlock is not a clear simultaneous global one, that
    have a full release day of hourly points, and whose hour-1 viewers are at least 2% of their
    day peak (a rolling-midnight launch already has an audience in hour 1; a simultaneous one
    starts near zero and would poison the shape pool).
  * Each kept comparable becomes a ratio curve: its release-day hours divided by a level anchor,
    the geometric mean of its viewers over a small window of hours straddling the day boundary.
  * Two ensembles are blended 50/50 in log space: anchor windows (-1, 0, 1) and (0, 1), with
    similarity windows (-4..1) and (-6..1) respectively. A comparable's weight is
    exp(-d / 0.5), where d is the RMS distance between its pre-release ramp (log viewers relative
    to its own hour 1, over the similarity window) and the target's ramp; a comparable sharing
    fewer than 4 window hours with the target gets a fallback weight of 0.35.
  * Each hour's five quantiles are the weighted empirical quantiles of the pool's log ratios for
    that hour, with the spread around the median multiplied by 0.95, scaled by the target's own
    anchor. If fewer than 4 curves survive, the forecast falls back to the unweighted quantiles
    of every usable comparable's hour-1 ratios; if there are none, to persistence at hour 1.

Everything is a pure function of the case file: no clock, no randomness, no network, so two runs
write the same bytes. Runs as `python3 -P -s /bot/main.py` (Python 3.13, standard library only).
Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand in for /input
and /output.
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path
from statistics import NormalDist

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.644854, -0.674490, 0.0, 0.674490, 1.644854]
HOURS = list(range(2, 25))
GATE = 0.02          # a comparable's hour 1 must be at least this share of its day peak
SIM_TAU = 0.5        # similarity-weight scale, in log units
SIM_FALLBACK = 0.35  # weight when a comparable shares < 4 similarity-window hours with the target
SPREAD_MUL = 0.95    # shrink the pool's log-spread around its median by this factor
MIN_CURVES = 4
# (anchor window, similarity window) for the two blended ensembles
ENSEMBLES = [((-1, 0, 1), -4), ((0, 1), -6)]


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def series_by_hour(day_start, hourly):
    """Map whole-hour index (hour 1 starts at day_start) -> viewers, from {from, viewers} points."""
    start = parse_ts(day_start)
    out = {}
    for p in hourly or []:
        v = p.get("viewers")
        if v is None:
            continue
        k = int((parse_ts(p["from"]) - start).total_seconds() // 3600) + 1
        out[k] = float(v)
    return out


def tier_of(unlock):
    u = (unlock or "").lower()
    if "early-access-contaminated" in u:
        return "early"
    if "tier: weak" in u:
        return "weak"
    if "target-history" in u:
        return "target"
    return "comparable"


def shape_of(unlock):
    u = (unlock or "").lower()
    rolling = ("midnight local" in u) or ("rolling" in u) or ("midnight" in u and "local" in u)
    simul = ("simultaneous" in u) or ("single global" in u) or ("one global unlock" in u)
    if rolling and simul:
        return "mixed"
    if rolling:
        return "rolling"
    if simul:
        return "simul"
    return "unknown"


def geo_anchor(series, window):
    """Geometric mean of series over the window hours, or None if any is missing/non-positive."""
    vals = [series.get(h) for h in window]
    if any(v is None or v <= 0 for v in vals):
        return None
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def wquantile(pairs, tau):
    """Weighted quantile of (value, weight) pairs."""
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    if tot <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for i, (v, w) in enumerate(pairs):
        acc += w
        if acc >= tau * tot:
            if i + 1 < len(pairs):
                need = tau * tot - (acc - w)
                frac = need / w if w > 0 else 0.0
                return v + frac * (pairs[i + 1][0] - v)
            return v
    return pairs[-1][0]


def ramp_vector(series, lo):
    """Log viewers relative to hour 1 over hours lo..1, for the hours present."""
    if series.get(1, 0) <= 0:
        return {}
    return {h: math.log(series[h] / series[1]) for h in range(lo, 2)
            if series.get(h, 0) > 0}


def ensemble(target_series, pool, anchor_window, sim_lo, levels):
    """One ensemble's forecast {hour: [quantiles at levels]}, or None if its pool is empty."""
    anchor_t = geo_anchor(target_series, anchor_window)
    if anchor_t is None:
        anchor_t = geo_anchor(target_series, (0, 1))
    if anchor_t is None:
        anchor_t = target_series.get(1)
    if not anchor_t or anchor_t <= 0:
        return None
    picked = []
    for entry in pool:
        s = entry["series"]
        if any(s.get(h, 0) <= 0 for h in range(1, 25)):
            continue
        anchor_c = geo_anchor(s, anchor_window)
        if anchor_c is None:
            continue
        curve = {h: s[h] / anchor_c for h in HOURS}
        picked.append((entry, curve))
    if not picked:
        return None
    tv = ramp_vector(target_series, sim_lo)
    weights = []
    for entry, _ in picked:
        cv = ramp_vector(entry["series"], sim_lo)
        common = [h for h in tv if h in cv]
        if len(common) < 4:
            weights.append(SIM_FALLBACK)
        else:
            d = math.sqrt(sum((tv[h] - cv[h]) ** 2 for h in common) / len(common))
            weights.append(math.exp(-d / SIM_TAU))
    med_i = min(range(len(levels)), key=lambda i: abs(levels[i] - 0.5))
    out = {}
    for h in HOURS:
        logs = [(math.log(curve[h]), w) for (_, curve), w in zip(picked, weights)]
        qs = [wquantile(logs, t) for t in levels]
        med = qs[med_i]
        qs = [med + (q - med) * SPREAD_MUL for q in qs]
        out[h] = [anchor_t * math.exp(q) for q in qs]
    return out


def select_pool(comparables):
    """Filter the case's comparables to the shape pool the ensembles draw on."""
    pool = []
    for c in comparables:
        if tier_of(c.get("unlock")) != "comparable":
            continue
        if shape_of(c.get("unlock")) == "simul":
            continue
        s = series_by_hour(c["day_start"], c.get("hourly"))
        if any(s.get(h, 0) <= 0 for h in range(1, 25)):
            continue
        peak = max(s[h] for h in range(1, 25))
        if peak <= 0 or s[1] / peak < GATE:
            continue
        pool.append({"name": c.get("name", ""), "series": s})
    pool.sort(key=lambda e: e["name"])
    return pool


def fallback_forecast(target_series, comparables, levels):
    """Unweighted empirical quantiles of every usable comparable's hour-1 ratio curve."""
    p1 = max(1.0, target_series.get(1, 1.0))
    curves = []
    for c in comparables:
        if tier_of(c.get("unlock")) == "target":
            continue
        s = series_by_hour(c["day_start"], c.get("hourly"))
        if any(s.get(h, 0) <= 0 for h in range(1, 25)):
            continue
        curves.append({h: s[h] / s[1] for h in HOURS})
    if not curves:
        zs = [NormalDist().inv_cdf(t) for t in levels]
        return {h: [p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in zs] for h in HOURS}
    out = {}
    for h in HOURS:
        logs = sorted(math.log(c[h]) for c in curves)
        qs = []
        for t in levels:
            pos = t * (len(logs) - 1)
            lo = int(math.floor(pos))
            hi = min(lo + 1, len(logs) - 1)
            qs.append(logs[lo] * (1 - (pos - lo)) + logs[hi] * (pos - lo))
        out[h] = [p1 * math.exp(q) for q in qs]
    return out


def round2(x):
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


def forecast_case(case):
    p1 = None
    for k in case.get("known") or []:
        if k.get("hour") == 1 and k.get("viewers") is not None:
            p1 = float(k["viewers"])
            break
    target_series = series_by_hour(case["day_start"], case.get("history_hourly"))
    if p1 is not None:
        target_series[1] = p1
    elif target_series.get(1) is not None:
        p1 = target_series[1]
    comparables = case.get("comparables") or []
    levels = [float(t) for t in (case.get("levels") or LEVELS)]
    pool = select_pool(comparables)
    rows = None
    if len(pool) >= MIN_CURVES:
        parts = [ensemble(target_series, pool, aw, sl, levels) for aw, sl in ENSEMBLES]
        parts = [p for p in parts if p is not None]
        if parts:
            rows = {}
            for h in HOURS:
                rows[h] = [math.exp(sum(math.log(p[h][i]) for p in parts) / len(parts))
                           for i in range(len(levels))]
    if rows is None:
        rows = fallback_forecast(target_series, comparables, levels)
    hours_out = []
    for row in sorted(case.get("forecast") or [], key=lambda r: r["hour"]):
        h = row["hour"]
        qs = rows.get(h) or [max(1.0, p1 or 1.0)] * len(levels)
        fixed = []
        prev = 0.0
        for q in qs:
            q = min(max(float(q), 0.5), 1_000_000_000.0)
            q = max(q, prev)
            fixed.append(round2(q))
            prev = fixed[-1]
        hours_out.append({"hour": h, "q": fixed})
    return {"hours": hours_out}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
