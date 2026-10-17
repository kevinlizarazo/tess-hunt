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
        }
    )


class FakeTarget:
    """TRICERATOPS's target as far as tricera uses it: the target and a TIC star 12.5" east of it."""

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
        degenerate=False,
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
        for name in lacking:
            self.stars.loc[0, name] = np.nan
        self.trilegal_fname = f"{tic}_gaia_background.csv" if field else None
        n = len(self.sectors) if cutouts is None else cutouts
        self.pix_coords = [np.array([[100.0, 200.0], [100.6, 200.0]]) for _ in range(n)]
        self.spoc, self.dark, self.outside = spoc, dark, outside
        self.fpp, self.nfpp, self.raises, self.degenerate = fpp, nfpp, raises, degenerate
        self.depths, self.calls = [], []

    def get_spoc_apertures(self):
        default = np.array([[100, 200], [101, 200]])
        return [self.spoc.get(int(s), default) if self.spoc else default for s in self.sectors]

    def calc_depths(self, tdepth, all_ap_pixels=None, dilution_corrected=True):
        self.depths.append((tdepth, all_ap_pixels, dilution_corrected))
        self.stars["fluxratio"] = [0.0, 1.0] if self.dark else [0.9, 0.1]
        self.stars["tdepth"] = [0.0, tdepth] if self.dark else [tdepth, 9.0 * tdepth]
        if self.outside:
            # Too little of its light in the apertures to make the dip.
            self.stars.loc[1, "tdepth"] = 0.0

    def calc_probs(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
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
    install(monkeypatch, raises=RuntimeError("PyTransit failed"))
    raised = check().evidence
    assert set(tricera.RUN_FIELDS) <= set(raised)
    assert raised["fpp"] == raised["nfpp"] == []
    assert all(raised[f] is None for f in tricera.RUN_FIELDS if f not in ("fpp", "nfpp"))


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
    found = gaia.dr3_join(stars).iloc[0]
    star.update(ruwe=float(found["ruwe"]), dr3_source_id=int(found["dr3_source_id"]))
    fetch.fetch_star(tic, mast.discover([tic]), tmp_path, SEARCH["fetch"])
    lc = good_timestamps(LightCurve.load(tmp_path / f"{tic}.npz"))
    pdcsap = split(detrend(lc, SEARCH["detrend"]), VET["families"])[VET["families"]["fit"]]
    depth = toi_table.set_index("TOI").loc[toi, "Depth (ppm)"] * 1e-6
    eph = Ephemeris(float(row.period), float(row.t0), float(row.duration), float(depth))
    assert in_transit(pdcsap.time, eph).any()
    cone = neighbours.gaia_cone(star["ra"], star["dec"], VET["neighbours"]["radius_arcmin"])
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
@pytest.mark.parametrize("toi", ["1058.01", "1175.01"])
def test_nearby_eb_controls_fail_triceratops(toi, toi_table, tmp_path):
    result = control_triceratops(toi, toi_table, tmp_path)
    assert result.outcome is Outcome.FAIL, result.reason


@pytest.mark.network
@pytest.mark.slow
def test_toi_1399_does_not_pass_triceratops(toi_table, tmp_path):
    result = control_triceratops("1399.01", toi_table, tmp_path)
    assert result.outcome is not Outcome.PASS, result.reason
