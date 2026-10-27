"""Product families and good timestamps for vet-v3.

QLP depths read shallower than crowding-corrected PDCSAP depths on crowded stars, so depths are compared only
within one family (docs/decisions/0023-product-families.md). Sectors fetch flagged for wrong timestamps reach no
check (docs/decisions/0022-vet-without-timing-suspect-sectors.md)."""

from collections.abc import Mapping

import numpy as np

from tess_hunt.checks import CheckResult, Outcome, failed, inconclusive, passed
from tess_hunt.lightcurve import LightCurve


def family_of(source: Mapping, cfg: dict) -> str:
    """The family listing this source's provenance; any other provenance is a family of its own."""
    provenance = source["provenance"]
    # Only lists are families: `fit` is a string naming one, and `in` on it would match substrings.
    for name, members in cfg.items():
        if isinstance(members, list) and provenance in members:
            return name
    return str(provenance)


def family_labels(lc: LightCurve, cfg: dict) -> np.ndarray:
    """Each cadence's family."""
    labels = np.empty(len(lc.time), dtype=object)
    for sector in np.unique(lc.sector):
        labels[lc.sector == sector] = family_of(lc.sources[str(int(sector))], cfg)
    return labels


def split(lc: LightCurve, cfg: dict) -> dict[str, LightCurve]:
    labels = family_labels(lc, cfg)
    return {str(name): lc.select(labels == name) for name in np.unique(labels)}


def good_timestamps(lc: LightCurve) -> LightCurve:
    """Without the sectors whose source has `timing_suspect` set."""
    suspect = {int(s) for s, source in lc.sources.items() if source.get("timing_suspect")}
    good = lc.select(~np.isin(lc.sector, list(suspect)))
    good.sources = {s: source for s, source in lc.sources.items() if int(s) not in suspect}
    return good


def per_family(check: str, results: dict[str, CheckResult]) -> CheckResult:
    """Fails if any family failed; passes if one passed and none failed; otherwise inconclusive."""
    evidence = {"families": {name: r.to_dict() for name, r in results.items()}}

    def reasons(outcome: Outcome) -> str:
        return "; ".join(
            f"{name}: {r.reason}" for name, r in results.items() if r.outcome is outcome
        )

    outcomes = {r.outcome for r in results.values()}
    if Outcome.FAIL in outcomes:
        return failed(check, reasons(Outcome.FAIL), **evidence)
    if Outcome.PASS in outcomes:
        return passed(check, reasons(Outcome.PASS), **evidence)
    if not results:
        return inconclusive(check, "no product family has data", **evidence)
    return inconclusive(check, reasons(Outcome.INCONCLUSIVE), **evidence)
