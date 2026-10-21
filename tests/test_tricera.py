import contextlib
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests
import test_vetting as tv
from astropy.io import fits
from synthetic import make_lc, with_products

from tess_hunt import fetch, gaia, mast, neighbours, targets, tricera
from tess_hunt.catalogs import TOI_URL
from tess_hunt.checks import Outcome
from tess_hunt.checks.families import good_timestamps, split
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit, phase_days
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file

ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v2.toml")
VET = load_criteria(ROOT / "criteria" / "vet-v3.toml")
CFG = VET["triceratops"]
TIC, RA, DEC = 1, 30.0, -40.0
EPH = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
STAR = {"tic": TIC, "ra": RA, "dec": DEC, "ruwe": 1.0}
NEIGHBOURS = {
    "outcome": "pass",
    "reason": "1 of 1 neighbours could host the signal",
    "evidence": {},
}
REPORT = {"neighbours": NEIGHBOURS}


def cfg(**changes) -> dict:
    return {**CFG, "runs": 2, "draws": 1000, **changes}


def east(arcsec: float) -> float:
    return RA + arcsec / 3600.0 / np.cos(np.radians(DEC))


def hosts(*seps) -> pd.DataFrame:
    """Gaia DR3 stars the neighbour table says could host the signal, east of the target."""
    return pd.DataFrame(
        {
            "source_id": list(range(7, 7 + len(seps))),
            "ra": [east(s) for s in seps],
            "dec": [DEC] * len(seps),
            "sep_arcsec": list(seps),
            "required_depth": [0.02] * len(seps),
            # No proper motion: each matches where it is.
            "pmra": [np.nan] * len(seps),
            "pmdec": [np.nan] * len(seps),
        }
    )


# As the TIC lists a split star after the target: TIC 11, a second entry for TIC 13 at its position; TIC 12, a spurious
# 2MASS source; TIC 13, the entry the TIC keeps; and TIC 14, the fainter Gaia star split from it, which names it in
# duplicate_id (Paegert et al. 2021, section 3.1).
SPLIT_FIELD = (
    {
        "ID": "11",
        "Tmag": 13.0,
        "ra": east(20.0),
        "dec": DEC,
        "disposition": "DUPLICATE",
        "duplicate_id": "13",
    },
    {"ID": "12", "Tmag": 14.0, "ra": east(5.0), "dec": DEC, "disposition": "ARTIFACT"},
    {"ID": "13", "Tmag": 13.0, "ra": east(20.0), "dec": DEC, "disposition": "SPLIT"},
    {"ID": "14", "Tmag": 15.0, "ra": east(25.0), "dec": DEC, "duplicate_id": "13"},
)


class FakeTarget:
    """TRICERATOPS's target as far as tricera uses it: the target and a TIC star 12.5" east of it, with `between`'s
    rows listed between them. Its star list has a `disposition` column only when `between` or `flag` gives one."""

    def __init__(
        self,
        tic,
        sectors,
        search_radius,
        field=True,
        cutouts=None,
        spoc=None,
        lacking=(),
        first=None,
        dark=False,
        outside=False,
        fpp=None,
        nfpp=None,
        raises=None,
        runs_before_raise=0,
        degenerate=False,
        between=(),
        flag=None,
    ):
        self.ID, self.sectors, self.search_radius = tic, np.asarray(sectors), search_radius
        self.stars = pd.DataFrame(
            {
                "ID": [str(first or tic), "999"],
                "Tmag": [9.0, 12.0],
                "ra": [RA, east(12.5)],
                "dec": [DEC, DEC],
                "mass": [1.0, 0.8],
                "rad": [1.0, 0.8],
                "Teff": [5800.0, 5000.0],
                "plx": [10.0, 2.0],
            }
        )
        if between:
            self.stars = pd.concat(
                [self.stars.iloc[:1], pd.DataFrame(list(between)), self.stars.iloc[1:]],
                ignore_index=True,
            )
        if flag:
            self.stars.loc[0, "disposition"] = flag
        for name in lacking:
            self.stars.loc[0, name] = np.nan
        self.trilegal_fname = f"{tic}_gaia_background.csv" if field else None
        n = len(self.sectors) if cutouts is None else cutouts
        # Each star in a pixel of its own, moved a little from sector to sector.
        x = 100.0 + 0.6 * np.arange(len(self.stars))
        self.pix_coords = [np.column_stack([x, np.full(len(x), 200.0 + 0.1 * k)]) for k in range(n)]
        self.pixels = {
            star: [p[i].tolist() for p in self.pix_coords]
            for i, star in enumerate(self.stars["ID"])
        }
        self.spoc, self.dark, self.outside = spoc, dark, outside
        self.fpp, self.nfpp, self.raises, self.degenerate = fpp, nfpp, raises, degenerate
        self.runs_before_raise = runs_before_raise
        self.depths, self.calls = [], []

    def get_spoc_apertures(self):
        default = np.array([[100, 200], [101, 200]])
        return [self.spoc.get(int(s), default) if self.spoc else default for s in self.sectors]

    def calc_depths(self, tdepth, all_ap_pixels=None, dilution_corrected=True):
        self.depths.append((tdepth, all_ap_pixels, dilution_corrected))
        # Each star's pixel position in each sector as calc_depths reads it, by row (triceratops.py:777-778).
        self.seen = {
            star: [p[i].tolist() for p in self.pix_coords]
            for i, star in enumerate(self.stars["ID"])
        }
        others = len(self.stars) - 1
        self.stars["fluxratio"] = (
            [0.0] + [1.0 / others] * others if self.dark else [0.9] + [0.1 / others] * others
        )
        self.stars["tdepth"] = (
            [0.0] + [tdepth] * others if self.dark else [tdepth] + [9.0 * tdepth] * others
        )
        if self.outside:
            # Too little of its light in the apertures to make the dip.
            self.stars.loc[1, "tdepth"] = 0.0

    def calc_probs(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises and len(self.calls) > self.runs_before_raise:
            raise self.raises
        fpp, nfpp = 0.1 * np.random.rand(), 1e-4 * np.random.rand()
        self.FPP = fpp if self.fpp is None else self.fpp
        self.NFPP = nfpp if self.nfpp is None else self.nfpp
        self.FPP_degenerate = self.degenerate
        self.probs = pd.DataFrame(
            {"ID": [self.ID, 999], "scenario": ["TP", "NEB"], "prob": [1.0 - self.NFPP, self.NFPP]}
        )


def install(monkeypatch, **behaviour) -> list[FakeTarget]:
    made = []

    def new_target(tic, sectors, search_radius):
        made.append(FakeTarget(tic, sectors, search_radius, **behaviour))
        return made[-1]

    monkeypatch.setattr(tricera, "new_target", new_target)
    return made


def light_curve(sectors=(1, 2, 3), cadence=2.0, provenance="SPOC") -> LightCurve:
    lc = make_lc(
        sectors=sectors,
        cadence_min=cadence,
        noise_ppm=300.0,
        signals=[(EPH.period, EPH.t0, EPH.duration, EPH.depth)],
        tic=TIC,
    )
    if isinstance(provenance, str):
        provenance = dict.fromkeys(sectors, provenance)
    return with_products(lc, provenance)


def check(lc=None, star=STAR, eph=EPH, report=REPORT, possible=None, config=None, contrast=()):
    return tricera.check(
        light_curve() if lc is None else lc,
        star,
        eph,
        report,
        hosts(12.5) if possible is None else possible,
        config or cfg(),
        list(contrast),
    )


def test_outcome_pass_fail_and_between():
    c = cfg()
    result = tricera.outcome([0.01, 0.03], [1e-4, 3e-4], c, [], False)
    assert result.outcome is Outcome.PASS, result.reason
    ev = result.evidence
    assert ev["fpp"] == [0.01, 0.03] and ev["nfpp"] == [1e-4, 3e-4]
    assert ev["fpp_mean"] == pytest.approx(0.02) and ev["nfpp_mean"] == pytest.approx(2e-4)
    assert ev["fpp_sd"] == pytest.approx(np.std([0.01, 0.03], ddof=1))
    assert ev["validated_label"] is False

    result = tricera.outcome([0.9, 0.95], [0.2, 0.4], c, [], False)
    assert result.outcome is Outcome.FAIL
    assert "nearby false positive" in result.reason

    # A likely planet needs both; NFPP at the fail line is not over it.
    for fpp, nfpp in (([0.6], [1e-4]), ([0.1], [0.01]), ([0.1], [0.1])):
        assert tricera.outcome(fpp, nfpp, c, [], False).outcome is Outcome.INCONCLUSIVE, (fpp, nfpp)

    blocked = tricera.outcome([0.01], [1e-4], c, ["one", "two"], True)
    assert blocked.outcome is Outcome.INCONCLUSIVE
    assert blocked.reason == "one; two" and blocked.evidence["blockers"] == ["one", "two"]
    assert blocked.evidence["validated_label"] is False


def test_missing_field_population_is_inconclusive(monkeypatch):
    install(monkeypatch, field=False)
    result = check()
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "no field-star population" in result.reason
    assert result.evidence["field_population"] is False


@pytest.mark.parametrize(
    "behaviour, reason",
    [
        ({"fpp": float("nan")}, "non-finite"),
        ({"nfpp": float("inf")}, "non-finite"),
        ({"raises": RuntimeError("PyTransit failed")}, "raised RuntimeError: PyTransit failed"),
        ({"degenerate": True}, "degenerate"),
    ],
)
def test_nan_or_raise_is_inconclusive(monkeypatch, behaviour, reason):
    install(monkeypatch, **behaviour)
    result = check()
    assert result.outcome is Outcome.INCONCLUSIVE
    assert reason in result.reason
    assert result.evidence["validated_label"] is False


def test_every_path_records_the_same_fields(monkeypatch):
    """The dossier reads each field by name, so every path writes every field `run` records, None where not
    reached."""
    install(monkeypatch)
    assert set(tricera.run(light_curve(), STAR, EPH, EPH.depth, cfg(), [])) == set(
        tricera.RUN_FIELDS
    )
    assert check().evidence["raised"] is None

    def down(*args):
        raise requests.ConnectionError("TESScut did not answer")

    monkeypatch.setattr(tricera, "cadence_group", down)
    raised = check().evidence
    assert set(tricera.RUN_FIELDS) <= set(raised)
    assert raised["fpp"] == raised["nfpp"] == raised["degenerate"] == []
    assert all(
        raised[f] is None for f in tricera.RUN_FIELDS if f not in ("fpp", "nfpp", "degenerate")
    )
    assert raised["raised"] == "ConnectionError: TESScut did not answer"


def test_a_run_that_raised_keeps_what_it_reached(monkeypatch):
    """The record says how far TRICERATOPS got before it raised, so the dossier can say exactly that."""

    def down(tic, sectors, search_radius):
        raise requests.ConnectionError("TESScut did not answer")

    # After the cadence group and the fold, before any star list.
    monkeypatch.setattr(tricera, "new_target", down)
    result = check()
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "TRICERATOPS raised ConnectionError: TESScut did not answer" in result.reason
    ev = result.evidence
    assert ev["exposure_s"] == pytest.approx(120.0) and ev["sectors"] == [1, 2, 3]
    assert ev["groups"] and ev["points"] > 0 and ev["flux_err_0"] > 0
    assert ev["stars"] is ev["apertures"] is ev["missing_hosts"] is ev["hosts_tdepth_zero"] is None
    assert ev["dropped_stars"] is None
    assert ev["fpp"] == [] and ev["raised"] == "ConnectionError: TESScut did not answer"

    # On the second seed's calc_probs: the first run, the star list and the host match are kept.
    made = install(monkeypatch, raises=RuntimeError("PyTransit failed"), runs_before_raise=1)
    result = check(config=cfg(runs=3))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "TRICERATOPS raised RuntimeError: PyTransit failed" in result.reason
    ev = result.evidence
    assert len(made[0].calls) == 2
    assert len(ev["fpp"]) == len(ev["nfpp"]) == len(ev["degenerate"]) == 1
    assert ev["fpp_mean"] == ev["fpp"][0]
    assert [s["ID"] for s in ev["stars"]] == [str(TIC), "999"] and ev["dropped_stars"] == []
    assert set(ev["apertures"]) == {1, 2, 3}
    assert ev["missing_hosts"] == [] and ev["hosts"][0]["tic"] == "999"
    assert ev["hosts_tdepth_zero"] == []
    assert ev["probs"] is None and ev["raised"] == "RuntimeError: PyTransit failed"


def test_a_non_finite_or_missing_run_is_inconclusive():
    for fpp, nfpp in (([0.01, float("nan")], [1e-4, 1e-4]), ([], [])):
        result = tricera.outcome(fpp, nfpp, cfg(), [], True)
        assert result.outcome is Outcome.INCONCLUSIVE, (fpp, nfpp)


@pytest.mark.parametrize(
    "behaviour, reason",
    [
        # TRICERATOPS skips a sector whose TESScut cutout fails and carries on.
        ({"cutouts": 2}, "TESScut gave 2 of 3"),
        # calc_probs stops at a target without these and reports probabilities from no scenario.
        ({"lacking": ("plx",)}, "the TIC gives the target no plx"),
        ({"first": 5}, "first star is TIC 5"),
        # calc_probs would take the first star left as the target.
        ({"dark": True}, "left the target no light in the apertures"),
    ],
)
def test_a_target_triceratops_cannot_weigh_is_inconclusive(monkeypatch, behaviour, reason):
    made = install(monkeypatch, **behaviour)
    result = check()
    assert result.outcome is Outcome.INCONCLUSIVE
    assert reason in result.reason
    assert made[0].calls == []
    # The star list is matched either way; a stop before calc_depths computed no depth to call zero.
    assert result.evidence["missing_hosts"] == []
    zero = result.evidence["hosts_tdepth_zero"]
    assert zero is None if made[0].depths == [] else zero == []


def test_triceratops_weighs_no_tic_duplicate_or_artifact(monkeypatch):
    """The TIC flags a second entry for a star already in it DUPLICATE and a spurious 2MASS source ARTIFACT, so that
    neither is taken into account; TRICERATOPS selects the column and never reads it (decision 0036). Both go from its
    star list and its pixel positions before calc_depths. A SPLIT star and the star split from it stay."""
    made = install(monkeypatch, between=SPLIT_FIELD)
    # Gaia DR3 8 sits on TIC 13, whose duplicate TIC 11 comes first in the star list.
    result = check(possible=hosts(12.5, 20.0))
    assert result.outcome is Outcome.PASS, result.reason
    [target] = made
    # Every star calc_depths weighs keeps its own pixel in every sector. With TRICERATOPS's remove_star, which leaves
    # the pixel positions alone, each star after a dropped row would take its neighbour's.
    assert list(target.seen) == ["1", "13", "14", "999"]
    assert target.seen == {star: target.pixels[star] for star in target.seen}
    ev = result.to_dict()["evidence"]
    assert ev["dropped_stars"] == [
        {"ID": "11", "disposition": "DUPLICATE", "duplicate_id": "13"},
        {"ID": "12", "disposition": "ARTIFACT", "duplicate_id": None},
    ]
    assert [(s["ID"], s["disposition"]) for s in ev["stars"]] == [
        ("1", None),
        ("13", "SPLIT"),
        ("14", None),
        ("999", None),
    ]
    # The host is matched to the entry the TIC keeps.
    assert [h["tic"] for h in ev["hosts"]] == ["999", "13"] and ev["missing_hosts"] == []


@pytest.mark.parametrize("flag", ["DUPLICATE", "ARTIFACT"])
def test_a_target_the_tic_flags_is_inconclusive(monkeypatch, flag):
    """Only rows after the target are dropped: a flagged target stops the run before calc_depths."""
    made = install(monkeypatch, between=SPLIT_FIELD, flag=flag)
    result = check()
    assert result.outcome is Outcome.INCONCLUSIVE
    assert f"the TIC flags the target {flag}" in result.reason
    assert made[0].depths == [] and made[0].calls == []
    ev = result.to_dict()["evidence"]
    assert (ev["stars"][0]["ID"], ev["stars"][0]["disposition"]) == (str(TIC), flag)
    assert [s["ID"] for s in ev["dropped_stars"]] == ["11", "12"]


def test_a_star_list_without_dispositions_runs_as_before(monkeypatch):
    made = install(monkeypatch)
    result = check()
    assert result.outcome is Outcome.PASS, result.reason
    assert result.evidence["dropped_stars"] == []
    assert list(made[0].seen) == [str(TIC), "999"]
    assert all("disposition" not in s for s in result.evidence["stars"])


def test_missing_aperture_is_inconclusive(monkeypatch):
    made = install(monkeypatch, spoc={2: None})
    result = check()
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "no aperture for sector(s) [2]" in result.reason
    assert made[0].depths == [] and made[0].calls == []
    assert result.evidence["apertures"][2]["reason"] == "TRICERATOPS found no SPOC aperture"

    # QLP publishes no pixel aperture; vet-v3 keeps it out, and one that got in is never weighed without one.
    made = install(monkeypatch)
    result = check(lc=light_curve(provenance={1: "SPOC", 2: "SPOC", 3: "QLP"}))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "no aperture for sector(s) [3]" in result.reason
    assert made[0].calls == []


def test_high_ruwe_is_inconclusive(monkeypatch):
    install(monkeypatch)
    assert check().outcome is Outcome.PASS
    result = check(star={**STAR, "ruwe": 6.21})
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "RUWE 6.21 > 1.4" in result.reason
    # A missing RUWE can't rule out a companion either.
    result = check(star={**STAR, "ruwe": None})
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "no RUWE" in result.reason


def test_a_possible_host_triceratops_did_not_weigh_is_inconclusive(monkeypatch):
    install(monkeypatch)
    weighed = check(possible=hosts(12.5))
    assert weighed.outcome is Outcome.PASS, weighed.reason
    [host] = weighed.evidence["hosts"]
    assert host["source_id"] == 7 and host["tic"] == "999" and host["tdepth"] > 0

    # A star the TIC lacks: a Gaia star 30" out with no TRICERATOPS star near it.
    result = check(possible=hosts(12.5, 30.0))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert "did not weigh: Gaia DR3 8" in result.reason
    assert result.evidence["missing_hosts"] == [8]

    # TRICERATOPS's first star is the target.
    stars = pd.DataFrame({"ID": ["1", "999"], "ra": [RA, east(12.5)], "dec": [DEC, DEC]})
    assert tricera.missing_hosts(hosts(11.0, 14.0), stars, 2.0) == []
    assert tricera.missing_hosts(hosts(10.0, 15.0), stars, 2.0) == [7, 8]
    # A close companion the TIC merged into the target: only the target sits near it, and the target
    # is weighed as the target, not as a nearby star.
    assert tricera.missing_hosts(hosts(1.5), stars, 2.0) == [7]
    assert tricera.missing_hosts(hosts(12.5), stars.iloc[:1], 2.0) == [7]
    assert tricera.missing_hosts(hosts(), stars, 2.0) == []
    # A TIC star without a position matches nothing.
    assert tricera.missing_hosts(hosts(12.5), stars.assign(ra=np.nan), 2.0) == [7]


def moving(north: float, east_: float, pmra: float, pmdec: float) -> pd.DataFrame:
    """One possible host at Gaia DR3's epoch, `north` and `east_` arcsec from the TIC star 12.5" east of the
    target, with its proper motion in mas/yr (pmra times cos dec, as DR3 gives it)."""
    dec = DEC + north / 3600.0
    return pd.DataFrame(
        {
            "source_id": [7],
            "ra": [east(12.5) + east_ / 3600.0 / np.cos(np.radians(dec))],
            "dec": [dec],
            "sep_arcsec": [12.5],
            "required_depth": [0.02],
            "pmra": [pmra],
            "pmdec": [pmdec],
        }
    )


def test_a_host_is_matched_at_the_tic_epoch(monkeypatch):
    """TRICERATOPS's stars sit at TIC v8's epoch (J2000.0), the neighbour table's at Gaia DR3's (J2016.0): 44926986's
    12.5" host and its TIC star are 2.78" apart for a common motion of about 172 mas/yr (Ruling S)."""
    stars = pd.DataFrame({"ID": ["1", "999"], "ra": [RA, east(12.5)], "dec": [DEC, DEC]})
    years = tricera.GAIA_DR3_EPOCH - tricera.TIC_EPOCH
    assert years == 16.0
    # 16 years at (100, 140) mas/yr is (1.60", 2.24"); 0.02" more each way leaves 0.028" at J2000.
    host = moving(2.26, 1.62, 100.0, 140.0)
    at_2016 = tricera._separation_arcsec(host["ra"], host["dec"], east(12.5), DEC)[0]
    assert at_2016 == pytest.approx(2.78, abs=0.01)
    assert tricera.missing_hosts(host, stars, 2.0) == []
    # Without a proper motion (a two-parameter solution) the host stays where DR3 puts it.
    assert tricera.missing_hosts(host.assign(pmra=np.nan, pmdec=np.nan), stars, 2.0) == [7]
    # 1" from the TIC star at J2016, and its motion puts it 3.75" from it at J2000.
    assert tricera.missing_hosts(moving(1.0, 0.0, 0.0, -172.0), stars, 2.0) == [7]
    assert tricera.missing_hosts(moving(1.0, 0.0, np.nan, np.nan), stars, 2.0) == []

    # The evidence keeps each host's position at the TIC's epoch and its distance from the TIC star there.
    install(monkeypatch)
    result = check(possible=host)
    assert result.outcome is Outcome.PASS, result.reason
    [h] = result.evidence["hosts"]
    assert h["tic"] == "999" and h["distance_arcsec"] == pytest.approx(0.028, abs=0.002)
    assert h["pmra"] == 100.0 and h["pmdec"] == 140.0
    assert h["dec_2000"] == pytest.approx(DEC + 0.02 / 3600.0, abs=1e-9)
    assert h["ra_2000"] == pytest.approx(
        east(12.5) + 0.02 / 3600.0 / np.cos(np.radians(DEC)), abs=1e-8
    )
    still = check(possible=host.assign(pmra=np.nan, pmdec=np.nan)).evidence["hosts"][0]
    assert still["ra_2000"] == host["ra"][0] and still["dec_2000"] == host["dec"][0]
    assert still["pmra"] is None and still["tic"] is None


def test_a_host_moved_back_across_ra_zero_stays_in_range():
    # 16 years at +100 mas/yr on the equator is 0.000444 deg: a host at RA 0.0002 sat west of 0 at J2000.0.
    host = pd.DataFrame(
        {
            "source_id": [7],
            "ra": [0.0002],
            "dec": [0.0],
            "sep_arcsec": [12.5],
            "required_depth": [0.02],
            "pmra": [100.0],
            "pmdec": [0.0],
        }
    )
    west = 0.0002 - 100.0 * 16.0 / 3.6e6
    ra, _ = tricera.at_tic_epoch(host)
    assert 0.0 <= ra[0] < 360.0 and ra[0] == pytest.approx(360.0 + west, abs=1e-12)
    stars = pd.DataFrame({"ID": ["1", "999"], "ra": [0.004, 360.0 + west], "dec": [0.0, 0.0]})
    assert tricera.missing_hosts(host, stars, 2.0) == []
    [h] = tricera._hosts(host, stars.assign(tdepth=[0.002, 0.02]), 2.0)
    assert h["tic"] == "999" and h["ra_2000"] == pytest.approx(360.0 + west, abs=1e-12)


def test_a_host_triceratops_gave_no_depth_is_evidence_not_a_blocker(monkeypatch):
    # Ruling M: the TIC star at the host's place is weighed through the aperture and can't make the
    # dip, where the neighbour table assumed all its light in the aperture.
    install(monkeypatch, outside=True)
    result = check(possible=hosts(12.5))
    assert result.outcome is Outcome.PASS, result.reason
    assert result.evidence["missing_hosts"] == []
    assert result.evidence["hosts_tdepth_zero"] == [7]
    [host] = result.evidence["hosts"]
    assert host["tic"] == "999" and host["tdepth"] == 0.0

    install(monkeypatch)
    assert check(possible=hosts(12.5)).evidence["hosts_tdepth_zero"] == []


def test_an_inconclusive_neighbour_table_is_inconclusive(monkeypatch):
    install(monkeypatch)
    table = {
        "outcome": "inconclusive",
        "reason": "no neighbour table: Gaia archive failed",
        "evidence": {},
    }
    result = check(report={"neighbours": table}, possible=hosts())
    assert result.outcome is Outcome.INCONCLUSIVE
    assert (
        "the neighbour table is inconclusive: no neighbour table: Gaia archive failed"
        in result.reason
    )


def test_validated_label_needs_contrast_and_2min(monkeypatch, tmp_path):
    curve = tmp_path / "curve.csv"
    curve.write_text("0.1,3.0\n1.0,7.0\n")
    made = install(monkeypatch, fpp=0.01, nfpp=1e-4)
    result = check(contrast=[(curve, "Vis")])
    assert result.outcome is Outcome.PASS and result.evidence["validated_label"] is True
    assert made[-1].calls[0]["contrast_curve_file"] == [str(curve)]
    assert made[-1].calls[0]["filt"] == ["Vis"]

    without = check()
    assert without.outcome is Outcome.PASS and without.evidence["validated_label"] is False
    assert made[-1].calls[0]["contrast_curve_file"] is None

    ten_minutes = check(lc=light_curve(cadence=10.0), contrast=[(curve, "Vis")])
    assert ten_minutes.outcome is Outcome.PASS
    assert ten_minutes.evidence["validated_label"] is False

    install(monkeypatch, fpp=0.02, nfpp=1e-4)
    assert check(contrast=[(curve, "Vis")]).evidence["validated_label"] is False


def test_runs_are_seeded_and_averaged(monkeypatch):
    made = install(monkeypatch)
    # calc_probs reads a numpy float64 period as a period range and raises (pins: TRICERATOPS gotchas).
    eph = Ephemeris(np.float64(EPH.period), EPH.t0, EPH.duration, EPH.depth)
    result = check(eph=eph, config=cfg(runs=3, draws=1234))
    expected = []
    for seed in range(3):
        np.random.seed(seed)
        expected.append((0.1 * np.random.rand(), 1e-4 * np.random.rand()))
    ev = result.evidence
    assert ev["fpp"] == pytest.approx([f for f, _ in expected])
    assert ev["nfpp"] == pytest.approx([n for _, n in expected])
    assert ev["fpp_mean"] == pytest.approx(np.mean([f for f, _ in expected]))
    assert ev["nfpp_mean"] == pytest.approx(np.mean([n for _, n in expected]))
    assert ev["nfpp_sd"] == pytest.approx(np.std([n for _, n in expected], ddof=1))

    [target] = made
    assert target.sectors.tolist() == [1, 2, 3] and target.search_radius == 10
    [(depth, apertures, corrected)] = target.depths
    assert depth == EPH.depth and corrected is True and len(apertures) == 3
    # Ruling O: the pixels calc_depths got, kept for an audit after the archive has moved on.
    for sector, pixels in zip((1, 2, 3), apertures, strict=True):
        assert ev["apertures"][sector]["ccd_pixels"] == pixels.tolist()
    assert len(target.calls) == 3
    for call in target.calls:
        assert type(call["P_orb"]) is float and type(call["flux_err_0"]) is float
        assert call["N"] == 1234 and call["parallel"] is False and call["verbose"] == 0
        assert call["exptime"] == pytest.approx(120.0 / 86400.0)
        assert call["dilution_corrected"] is True
        assert len(call["time"]) == ev["points"]
    assert ev["exposure_s"] == pytest.approx(120.0) and ev["sectors"] == [1, 2, 3]
    assert all(ev["apertures"][s]["target_in_aperture"] for s in (1, 2, 3))
    assert ev["probs"][1]["scenario"] == "NEB"


def test_cadence_group_picks_the_richest_group():
    # Two 2-min sectors and one 10-min sector: averaging the 2-min data to 10 minutes adds the third
    # sector's transits but leaves a fifth of the in-transit cadences.
    lc = make_lc(
        sectors=(1, 2, 3),
        cadences={1: 2.0, 2: 2.0, 3: 10.0},
        signals=[(EPH.period, EPH.t0, EPH.duration, EPH.depth)],
    )
    exposure, sectors, groups = tricera.cadence_group(lc, EPH, 3)
    assert exposure == pytest.approx(120.0 / 86400.0) and sectors == [1, 2]
    by = {g["exposure_s"]: g for g in groups}
    assert by[600.0]["transits"] > by[120.0]["transits"] >= 3
    assert by[120.0]["in_transit"] > by[600.0]["in_transit"]

    # A group with too few transits is passed over for one that has them.
    exposure, sectors, _ = tricera.cadence_group(lc, EPH, by[120.0]["transits"] + 1)
    assert exposure == pytest.approx(600.0 / 86400.0) and sectors == [1, 2, 3]
    exposure, sectors, groups = tricera.cadence_group(lc, EPH, 100)
    assert exposure is None and sectors == [] and len(groups) == 2


def mixed() -> tuple[LightCurve, Ephemeris]:
    """441010857's case: two transits in a 600-s sector, one in a 200-s sector."""
    eph = Ephemeris(24.0, 1326.0, 0.2)
    lc = make_lc(
        sectors=(1, 2), cadences={1: 10.0, 2: 200.0 / 60.0}, signals=[(24.0, 1326.0, 0.2, 2e-3)]
    )
    # As MAST gives it; 200 / 60 * 60 is not 200.0 in floating point.
    lc.sources["2"]["cadence_s"] = 200.0
    return lc, eph


def test_cadence_group_averages_faster_sectors_to_the_slower_exposure():
    lc, eph = mixed()
    exposure, sectors, groups = tricera.cadence_group(lc, eph, 3)
    assert {g["exposure_s"]: g["transits"] for g in groups} == {200.0: 1, 600.0: 3}
    assert exposure == pytest.approx(600.0 / 86400.0) and sectors == [1, 2]


def test_faster_sectors_are_averaged_to_the_exposure():
    lc, _ = mixed()
    fast = lc.select(lc.sector == 2)
    # Drop the second and third cadences of the first bin and the third of the second: one of three
    # is not enough, two of three is.
    keep = np.ones(len(fast.time), dtype=bool)
    keep[[1, 2, 5]] = False
    fast = fast.select(keep)
    binned = tricera.to_exposure(fast, 600.0 / 86400.0)
    assert (
        binned.sources["2"]["cadence_s"] == 600.0 and binned.sources["2"]["binned_from_s"] == 200.0
    )
    assert binned.time[0] == pytest.approx(np.mean(fast.time[1:3]))
    assert binned.flux[0] == pytest.approx(np.mean(fast.flux[1:3]))
    assert binned.flux_err[0] == pytest.approx(np.sqrt(np.sum(fast.flux_err[1:3] ** 2)) / 2)
    # Full bins sit one exposure apart.
    assert np.diff(binned.time[1:50]) == pytest.approx(600.0 / 86400.0, rel=1e-3)
    assert len(binned.time) == pytest.approx(len(fast.time) / 3, rel=0.01)
    # A sector already at the exposure is left as it is.
    slow = lc.select(lc.sector == 1)
    same = tricera.to_exposure(slow, 600.0 / 86400.0)
    assert np.array_equal(same.time, slow.time) and "binned_from_s" not in same.sources["1"]


def test_phase_bins_keep_one_exposure_sampling():
    lc = light_curve()
    exposure = 120.0 / 86400.0
    # The synthetic cadences fall exactly on bin edges at EPH's epoch; 37 s keeps them off.
    eph = Ephemeris(EPH.period, EPH.t0 + 37.0 / 86400.0, EPH.duration, EPH.depth)
    near = np.abs(phase_days(lc.time, eph)) < 2.0 * eph.duration
    time, flux, err = tricera.fold(lc, eph, exposure, bin_phase=False)
    assert len(time) == near.sum() and err == pytest.approx(np.median(lc.flux_err[near]))

    time, flux, err = tricera.fold(lc, eph, exposure, bin_phase=True)
    assert np.diff(time) == pytest.approx(exposure)
    assert time.min() > -2.0 * eph.duration and time.max() < 2.0 * eph.duration
    counts = np.unique(np.floor(phase_days(lc.time, eph)[near] / exposure), return_counts=True)[1]
    assert len(time) == len(counts)
    assert err == pytest.approx(np.median(np.median(lc.flux_err[near]) / np.sqrt(counts)))
    # The binned fold still shows the transit.
    inside = np.abs(time) < 0.25 * eph.duration
    assert 1.0 - flux[inside].mean() == pytest.approx(eph.depth, rel=0.1)


def fits_file(bits: np.ndarray, col0=1642, row0=1772) -> bytes:
    aperture = fits.ImageHDU(bits.astype(np.int32), name="APERTURE")
    aperture.header["CRVAL1P"], aperture.header["CRVAL2P"] = col0, row0
    table = fits.BinTableHDU.from_columns(
        [fits.Column(name="TIME", format="D", array=np.zeros(3))], name="LIGHTCURVE"
    )
    buffer = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(), table, aperture]).writeto(buffer)
    return buffer.getvalue()


def test_tess_spoc_aperture_comes_from_the_light_curve_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    bits = np.array([[1, 3, 0], [3, 3, 1], [0, 1, 0]])
    blob = fits_file(bits)
    key = "mast/hlsp/tess-spoc/s0064/target/x/hlsp_tess-spoc_tess_phot_x-s0064_tess_v1_lc.fits"
    asked = []

    def download(k, size, session, **kwargs):
        asked.append(k)
        return blob, "s3"

    monkeypatch.setattr(mast, "download", download)
    sha = hashlib.sha256(blob).hexdigest()
    sources = {
        "64": {"provenance": "TESS-SPOC", "cadence_s": 200.0, "s3_key": key, "sha256": sha},
        "65": {"provenance": "TESS-SPOC", "cadence_s": 200.0, "s3_key": key, "sha256": "0" * 64},
    }
    target = FakeTarget(TIC, [64, 65], 10)
    found, notes = tricera.apertures(TIC, [64], sources, target)
    # Bit 2 is the optimal aperture; columns and rows are offset to the CCD.
    assert sorted(map(tuple, found[64].tolist())) == [(1642, 1773), (1643, 1772), (1643, 1773)]
    assert notes[64]["sha256"] == sha and notes[64]["pixels"] == 3
    assert (tmp_path / "data" / "lc_fits" / Path(key).name).is_file()
    tricera.apertures(TIC, [64], sources, target)
    assert asked == [key], "the second call reads the cache"

    # A file that is not the one fetch read gives no aperture.
    found, notes = tricera.apertures(TIC, [65], sources, target)
    assert found[65] is None and "not the" in notes[65]["reason"]


SPECKLE = """# objectname: TEST
# Telescope: test
# wavelength: 832nm
# annulus range&center vs. measured relative mag. limit:
0.050000 0.150000 0.100000 4.000000
0.150000 0.200000 0.175000 5.000000
0.200000 0.250000 0.225000 4.800000
0.250000 0.300000 0.275000 6.000000
# fit of angular separation vs. relative mag. limit:
0.000000 0.000000
0.010000 0.500000
"""
PHARO = """Target = TEST
Filter = Brgamma
Pixel_Scale [arsec/pix] = 0.025
arcsec, dmag, dmrms
0.000, 0.000, 0.000
0.124, 1.927, 0.663
0.226, 3.730, 0.319
0.329, 3.700, 0.072
0.437, 5.550, 0.104
"""


@pytest.mark.parametrize(
    "text, layout, measured, expected",
    [
        # Annulus centre and delta mag; the reduction's fitted curve after them is not read.
        (
            SPECKLE,
            "speckle",
            [(0.1, 4.0), (0.175, 5.0), (0.225, 4.8), (0.275, 6.0)],
            [(0.1, 4.0), (0.225, 4.8), (0.275, 6.0)],
        ),
        # The zero-separation row goes.
        (
            PHARO,
            "pharo",
            [(0.124, 1.927), (0.226, 3.73), (0.329, 3.7), (0.437, 5.55)],
            [(0.124, 1.927), (0.329, 3.7), (0.437, 5.55)],
        ),
    ],
    ids=["speckle", "pharo"],
)
def test_contrast_curves_convert_to_triceratops_two_columns(
    tmp_path, text, layout, measured, expected
):
    path = tmp_path / "curve.dat"
    path.write_text(text)
    curve, info = tricera.read_contrast(path)
    # A dip in delta mag is lowered from outside in, and of a run of equal values the widest
    # separation stays, so np.interp in TRICERATOPS reads an increasing curve.
    np.testing.assert_allclose(curve, expected)
    assert info["layout"] == layout and info["lowered"] == 1
    # Interpolated as TRICERATOPS interpolates, the curve never claims more contrast than was measured.
    separations, dmags = np.array(measured).T
    assert np.all(np.interp(separations, curve[:, 0], curve[:, 1]) <= dmags + 1e-12)
    out = tmp_path / "curve.csv"
    tricera.write_contrast(curve, out)
    from triceratops.funcs import file_to_contrast_curve

    separations, contrasts = file_to_contrast_curve(str(out))
    assert separations.tolist() == pytest.approx([s for s, _ in expected])
    assert np.all(np.diff(contrasts) > 0)


@pytest.mark.parametrize(
    "text",
    [
        "sep,dmag\n0.1,3.0\n0.2,4.0\n",
        SPECKLE.replace("0.150000 0.200000 0.175000 5.000000", "0.15 0.2 0.175"),
        PHARO.replace("arcsec, dmag, dmrms", "sep, dm"),
        "# only a header\n",
    ],
)
def test_a_contrast_file_in_neither_layout_is_refused(tmp_path, text):
    path = tmp_path / "curve.dat"
    path.write_text(text)
    with pytest.raises(tricera.ContrastError):
        tricera.read_contrast(path)


def vetting_run(tmp_path, monkeypatch, *extra) -> tuple[Path, list[str]]:
    # The control's TIC radius makes its radius check fail, so only the candidate has no failed check.
    monkeypatch.setattr(tv, "CONTROL", {**tv.CONTROL, "rad": 10.0})
    argv, _ = tv.setup(tmp_path, monkeypatch, fit=tv.fake_fit)
    assert main([*argv, *extra]) == 0
    run = max((tmp_path / "data" / "runs").glob("*-vetting-run-*"), key=lambda p: p.stat().st_mtime)
    return run, [
        "vetting",
        "triceratops",
        *("--run", str(run)),
        *("--criteria-search", str(tv.SEARCH)),
        *("--criteria-vet", str(tv.VET3)),
        *("--workers", "1"),
    ]


def triceratops_runs(tmp_path) -> list[Path]:
    return list((tmp_path / "data" / "runs").glob("*-vetting-triceratops-*"))


def test_triceratops_runs_on_the_signals_no_check_failed(tmp_path, monkeypatch):
    run, argv = vetting_run(tmp_path, monkeypatch)
    control = json.loads((run / "signals" / "TOI-9.01" / "checks.json").read_text())
    assert any(c["outcome"] == "fail" for c in control["checks"])
    made = install(monkeypatch)
    assert main(argv) == 0
    [out] = triceratops_runs(tmp_path)
    assert [p.name for p in (out / "signals").iterdir()] == ["1-1"]
    record = json.loads((out / "signals" / "1-1" / "triceratops.json").read_text())
    assert record["check"] == "triceratops" and record["signal"] == {"name": "1-1", "tic": 1}
    # The targets fixture has no RUWE, so the runs are made and recorded but can't pass.
    assert record["outcome"] == "inconclusive" and "no RUWE" in record["reason"]
    assert len(record["evidence"]["fpp"]) == CFG["runs"]
    assert "probs" not in record["evidence"]
    probs = pd.read_csv(out / "signals" / "1-1" / "probs.csv")
    assert probs["scenario"].tolist() == ["TP", "NEB"]
    checks = json.loads((run / "signals" / "1-1" / "checks.json").read_text())
    prior = checks["fit_prior"]["ephemeris"]
    assert record["ephemeris_from"] == {"ephemeris": "fit_prior", "duration": "fit_prior"}
    assert record["evidence"]["ephemeris"]["period"] == prior["period"]["median"]
    assert record["evidence"]["ephemeris"]["depth"] == checks["neighbours"]["evidence"]["depth"]
    [target] = made
    assert target.sectors.tolist() == [1, 2, 64]
    assert record["evidence"]["exposure_s"] == 1800.0
    for sector in ("1", "2", "64"):
        assert record["evidence"]["apertures"][sector]["ccd_pixels"] == [[100, 200], [101, 200]]

    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["vetting_run"] == run.name
    assert provenance["criteria"][1]["sha256"] == load_criteria(tv.VET3).sha256
    inputs = provenance["inputs"]
    assert inputs["vetting_provenance"]["sha256"] == sha256_file(run / "provenance.json")
    assert inputs["checks_1-1"]["sha256"] == sha256_file(run / "signals" / "1-1" / "checks.json")
    assert inputs["light_curve_1"]["sha256"] == sha256_file(tmp_path / "data" / "lc" / "1.npz")
    assert provenance["summary"]["signals"]["1-1"]["outcome"] == "inconclusive"
    assert provenance["summary"]["errors"] == {}

    # Named, a signal that failed a check gets TRICERATOPS too; the control has no density-prior fit.
    assert main([*argv, "--signals", "TOI-9.01"]) == 0
    [named] = [p for p in triceratops_runs(tmp_path) if p != out]
    record = json.loads((named / "signals" / "TOI-9.01" / "triceratops.json").read_text())
    assert record["ephemeris_from"] == {"ephemeris": "signal", "duration": "signal"}
    assert record["evidence"]["ephemeris"]["period"] == tv.SIGNAL["period"]


def test_contrast_curves_are_converted_into_the_run(tmp_path, monkeypatch):
    run, argv = vetting_run(tmp_path, monkeypatch)
    curve = tmp_path / "TOI-9I-test-832.dat"
    curve.write_text(SPECKLE)
    listing = tmp_path / "contrast.csv"
    pd.DataFrame(
        [{"tic": 1, "file": curve.name, "filt": "Vis", "source_url": "https://example.org/1"}]
    ).to_csv(listing, index=False)
    made = install(monkeypatch)
    assert main([*argv, "--contrast", str(listing)]) == 0
    [out] = triceratops_runs(tmp_path)
    [converted] = (out / "contrast").iterdir()
    assert converted.read_text().splitlines()[0] == "0.100000,4.000000"
    assert made[0].calls[0]["contrast_curve_file"] == [str(converted)]
    assert made[0].calls[0]["filt"] == ["Vis"]
    record = json.loads((out / "signals" / "1-1" / "triceratops.json").read_text())
    [used] = record["contrast"]
    assert used["file"] == curve.name and used["sha256"] == sha256_file(curve)
    assert used["converted"] == converted.name and used["converted_sha256"] == sha256_file(
        converted
    )
    assert used["filt"] == "Vis" and used["source_url"] == "https://example.org/1"
    assert used["layout"] == "speckle"
    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["inputs"]["contrast"]["sha256"] == sha256_file(listing)
    assert provenance["inputs"]["contrast_1"]["sha256"] == sha256_file(curve)
    # 30-minute data: a contrast curve alone never earns the paper's label.
    assert record["evidence"]["validated_label"] is False


def other_vet_criteria(tmp_path, run) -> list[str]:
    path = tmp_path / "vet-other.toml"
    path.write_text(tv.VET3.read_text() + "# not the file the vetting run used\n")
    return ["--criteria-vet", str(path)]


def contrast_in_neither_layout(tmp_path, run) -> list[str]:
    (tmp_path / "curve.dat").write_text("sep,dmag\n0.1,3.0\n0.2,4.0\n")
    listing = tmp_path / "contrast.csv"
    listing.write_text("tic,file,filt,source_url\n1,curve.dat,Vis,https://example.org\n")
    return ["--contrast", str(listing)]


def changed_light_curve(tmp_path, run) -> list[str]:
    path = tmp_path / "data" / "lc" / "1.npz"
    lc = LightCurve.load(path)
    lc.flux = lc.flux * 1.0001
    lc.save(path)
    return []


@pytest.mark.parametrize(
    "extra, message",
    [
        (other_vet_criteria, "is not the criteria/vet-v3.toml that"),
        (lambda tmp_path, run: ["--signals", "9-9"], "vetted no 9-9"),
        (lambda tmp_path, run: ["--production"], "not a production vetting run"),
        (contrast_in_neither_layout, "neither ExoFOP layout"),
        (changed_light_curve, "light curve for TIC 1 changed since"),
    ],
)
def test_triceratops_refuses_what_it_cannot_stand_behind(tmp_path, monkeypatch, extra, message):
    run, argv = vetting_run(tmp_path, monkeypatch)
    install(monkeypatch)
    with pytest.raises(SystemExit, match=message):
        main([*argv, *extra(tmp_path, run)])
    assert triceratops_runs(tmp_path) == []


def test_triceratops_refuses_an_evidence_only_run(tmp_path, monkeypatch):
    _, argv = vetting_run(tmp_path, monkeypatch, "--include-suspect")
    install(monkeypatch)
    with pytest.raises(SystemExit, match="evidence-only"):
        main(argv)
    assert triceratops_runs(tmp_path) == []


CONTROLS = pd.read_csv(ROOT / "benchmarks" / "pixel_controls.csv", dtype={"toi": str}).set_index(
    "toi"
)


@pytest.fixture(scope="module")
def toi_table():
    response = requests.get(TOI_URL, timeout=120)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text), dtype={"TOI": str})


def control_triceratops(toi, toi_table, tmp_path):
    """A pixel control through vet-v3's light curve and neighbour table into TRICERATOPS, one run."""
    row = CONTROLS.loc[toi]
    tic = int(row.tic)
    stars = targets.query_tic_ids([tic])
    star = stars.iloc[0].to_dict()
    # A float64 row would lose a Gaia id's low digits.
    found = gaia.dr3_join(stars).to_dict("records")[0]
    star.update(ruwe=float(found["ruwe"]), dr3_source_id=int(found["dr3_source_id"]))
    fetch.fetch_star(tic, mast.discover([tic]), tmp_path, SEARCH["fetch"])
    lc = good_timestamps(LightCurve.load(tmp_path / f"{tic}.npz"))
    pdcsap = split(detrend(lc, SEARCH["detrend"]), VET["families"])[VET["families"]["fit"]]
    depth = toi_table.set_index("TOI").loc[toi, "Depth (ppm)"] * 1e-6
    eph = Ephemeris(float(row.period), float(row.t0), float(row.duration), float(depth))
    assert in_transit(pdcsap.time, eph).any()
    cone = neighbours.gaia_cone(
        star["ra"],
        star["dec"],
        VET["neighbours"]["radius_arcmin"],
        source_id=star["dr3_source_id"],
    )
    table = neighbours.required_depths(
        cone, depth, star["tmag"], star["dr3_source_id"], VET["neighbours"]
    )
    report = {"neighbours": neighbours.neighbour_check(table, None).to_dict()}
    with contextlib.chdir(tmp_path):
        result = tricera.check(
            pdcsap, star, eph, report, table[table["possible"]], {**CFG, "runs": 1}, []
        )
    ev = result.evidence
    print(f"TOI-{toi} (TIC {tic}): {result.outcome.value}, {result.reason}")
    print(
        f"group {ev.get('exposure_s')} s, sectors {ev.get('sectors')}; FPP {ev['fpp']}, NFPP {ev['nfpp']}"
    )
    return result


@pytest.mark.network
@pytest.mark.slow
# The design's expectation, kept visible; strict, so a binary that starts to fail TRICERATOPS is reported. `raises`
# keeps out only errors that escape the test: a network failure inside TRICERATOPS becomes a blocker and an
# inconclusive outcome, which counts as the expected failure.
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="decision 0032: both nearby binaries read inconclusive, not fail; the pixel check kills them",
)
@pytest.mark.parametrize("toi", ["1058.01", "1175.01"])
def test_nearby_eb_controls_fail_triceratops(toi, toi_table, tmp_path):
    result = control_triceratops(toi, toi_table, tmp_path)
    assert result.outcome is Outcome.FAIL, result.reason


@pytest.mark.network
@pytest.mark.slow
@pytest.mark.parametrize("toi", ["1058.01", "1175.01"])
def test_nearby_eb_controls_do_not_pass_triceratops(toi, toi_table, tmp_path):
    """Decision 0032's standard: TRICERATOPS never passes them, so their pixel fail stands."""
    result = control_triceratops(toi, toi_table, tmp_path)
    assert result.outcome is not Outcome.PASS, result.reason


@pytest.mark.network
@pytest.mark.slow
def test_toi_1399_does_not_pass_triceratops(toi_table, tmp_path):
    result = control_triceratops("1399.01", toi_table, tmp_path)
    assert result.outcome is not Outcome.PASS, result.reason
