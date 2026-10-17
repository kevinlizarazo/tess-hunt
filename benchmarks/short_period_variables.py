"""Short-period variables among a production search's signals, and how often the injection benchmark
recovered planets on their stars against the rest.

A star counts when every one of its signals at or above the threshold has a period within the search
criteria's [match] period tolerance of n/m times one of them that is under PERIOD_MAX_DAYS, with n and m
from 1 to MAX_TERM (1/1, the signal itself, included), and LEO-Vetter's false-alarm tests failed every one
of those signals on at least one of TESTS. The tolerance is ephemeris_match's on period alone, sigma_p read
from the criteria file the search ran.

The signals and the searched stars come from the search run's signals.parquet and stars.parquet, the
threshold from the triage run's provenance, the failed tests from the triage run's evidence, and the
injections from the inject run's injections.csv. All three are run directories under $TESS_HUNT_DATA/runs.

Usage, from the repository root:
    uv run python benchmarks/short_period_variables.py SEARCH_RUN TRIAGE_RUN INJECT_RUN \
        > results/benchmarks/short-period-variables-<UTC date>.txt
"""

import json
import math
import sys
from fractions import Fraction
from pathlib import Path

import pandas as pd

from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, ephemeris_match

PERIOD_MAX_DAYS = 5.0
MAX_TERM = 5
TESTS = ("non_unique", "sinusoidal")
RATIOS = tuple(
    sorted({float(Fraction(n, m)) for n in range(1, MAX_TERM + 1) for m in range(1, MAX_TERM + 1)})
)

search, triage, inject = (Path(arg) for arg in sys.argv[1:4])
search_prov, triage_prov, inject_prov = (
    json.loads((run / "provenance.json").read_text()) for run in (search, triage, inject)
)
if triage_prov["search_run"] != search.name:
    raise SystemExit(f"{triage.name} triaged {triage_prov['search_run']}, not {search.name}")
if inject_prov["threshold"]["run_id"] != triage_prov["threshold"]["run_id"]:
    raise SystemExit(f"{inject.name} and {triage.name} ran at different thresholds")
entry = search_prov["criteria"][0]
criteria = load_criteria(entry["file"])
if criteria.sha256 != entry["sha256"]:
    raise SystemExit(f"{entry['file']} has changed since {search.name}")
sigma_p = criteria["match"]["sigma_p"]
threshold = triage_prov["threshold"]["value"]

signals = pd.read_parquet(search / "signals.parquet")
signals = signals[~signals["control"].astype(bool) & (signals["sde"] >= threshold)]
stars = pd.read_parquet(search / "stars.parquet")
searched = stars[~stars["control"].astype(bool) & (stars["status"] == "ok")]


def at_ratios(periods: list[float]) -> bool:
    def near(period: float, base: float) -> bool:
        a, b = Ephemeris(period, math.nan, math.nan), Ephemeris(base, math.nan, math.nan)
        return ephemeris_match(a, b, RATIOS, sigma_p) is not None

    return any(all(near(p, base) for p in periods) for base in periods if base < PERIOD_MAX_DAYS)


def rejected(tic: int, rank: int) -> bool:
    evidence = json.loads((triage / "evidence" / f"{tic}-{rank}.json").read_text())
    return bool(set(TESTS) & set(evidence["leo_flux"]["evidence"].get("fa_failed", [])))


by_star = {int(tic): group for tic, group in signals.groupby("tic")}
harmonic = [tic for tic, group in by_star.items() if at_ratios(list(group["period"]))]
variables = {tic for tic in harmonic if all(rejected(tic, int(r)) for r in by_star[tic]["rank"])}
injections = pd.read_csv(inject / "injections.csv")
injections = injections[injections["status"] == "ok"]
on = injections["tic"].isin(variables)


def recovered(rows: pd.DataFrame) -> str:
    found = int(rows["recovered"].sum())
    return f"{found} of {len(rows)} ({found / len(rows):.3f})" if len(rows) else "none searched"


tolerance = math.erfc(sigma_p / math.sqrt(2.0))
print(
    f"Short-period variables in search {search.name}, triage {triage.name}, inject {inject.name}.\n"
    f"Rule: every signal of a star at or above the threshold (SDE {threshold:.2f}) has a period within "
    f"{tolerance:.2%} ([match] sigma_p {sigma_p:g} in {entry['file']}) of n/m times one of them under "
    f"{PERIOD_MAX_DAYS:g} d, n and m from 1 to {MAX_TERM}, and LEO-Vetter failed every one of them on "
    f"{' or '.join(TESTS)}.\n"
)
print(f"Sample stars searched (status ok): {len(searched)}")
print(f"Stars with a signal at or above the threshold: {len(by_star)} ({len(signals)} signals)")
print(f"Stars whose signals sit at n/m of one period under {PERIOD_MAX_DAYS:g} d: {len(harmonic)}")
print(
    f"Of those, every signal failed on {' or '.join(TESTS)}: {len(variables)} "
    f"({int(signals['tic'].isin(variables).sum())} signals)"
)
print(f"Injections recovered on those stars: {recovered(injections[on])}")
print(f"Injections recovered on the other stars: {recovered(injections[~on])}")
