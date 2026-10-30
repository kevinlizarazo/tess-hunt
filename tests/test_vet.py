import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import (
    box,
    correlated_noise,
    make_lc,
    make_transit_lc,
    with_products,
    write_catalog_snapshot,
)

from tess_hunt import vet
from tess_hunt.catalogs import KNOWN_COLUMNS, load_known
from tess_hunt.checks.holdout import holdout
from tess_hunt.checks.photometry import box_depth
from tess_hunt.cli import main
from tess_hunt.config import load_criteria, runs_dir
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, ephemeris_match, in_transit
from tess_hunt.fit import NAMES, FitResult, fit_transit
from tess_hunt.serialize import jsonable
from tess_hunt.transit import a_rs_from_density, light_curve
from tess_hunt.vet import other_known_transits, vet_signal, with_v1_code_values

ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v2.toml").values
VET = load_criteria(ROOT / "criteria" / "vet-v2.toml").values
FAST_VET = {**VET, "fit": {**VET["fit"], "steps": 1500, "burn": 700}}
VET3 = load_criteria(ROOT / "criteria" / "vet-v3.toml").values
FAST_VET3 = {**VET3, "fit": {**VET3["fit"], "steps": 1500, "burn": 700}}
SEARCH_V1 = load_criteria(ROOT / "criteria" / "search-v1.toml").values
VET_V1 = load_criteria(ROOT / "criteria" / "vet-v1.toml").values
FAST_VET_V1 = {**VET_V1, "fit": {**VET_V1["fit"], "steps": 1500, "burn": 700}}
STAR = {"tic": 1, "ra": 30.0, "dec": -40.0, "rho": 1.0, "e_rho": 0.1, "rad": 1.0}
SECTORS = (1, 2, 14, 15, 28, 29)
M1_CHECKS = {"novelty", "odd_even", "secondary", "sector_depth", "holdout", "shape", "density"}


@pytest.mark.slow
def test_clean_planet_advances(tmp_path):
    lc = make_transit_lc(
        rp_rs=0.04,
        sectors=SECTORS,
        cadences={s: 30.0 for s in SECTORS},
        noise_ppm={s: 200.0 for s in SECTORS},
    )
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    report, fit = vet_signal(
        lc, STAR, Ephemeris(5.0, 1326.1, 0.13, 0.0017), known, SEARCH, FAST_VET, seed=1
    )
    outcomes = {c["check"]: c["outcome"] for c in report["checks"]}
    assert set(outcomes) == M1_CHECKS | {"signal_present", "radius"}
    assert all(o == "pass" for o in outcomes.values()), outcomes
    assert report["advances"] and fit is not None


@pytest.mark.slow
def test_known_toi_is_flagged_and_does_not_advance(tmp_path):
    lc = make_transit_lc(
        rp_rs=0.04,
        sectors=SECTORS,
        cadences={s: 30.0 for s in SECTORS},
        noise_ppm={s: 200.0 for s in SECTORS},
    )
    toi = {
        "TIC ID": 1,
        "TOI": 7777.01,
        "TFOPWG Disposition": "PC",
        "TESS Mag": 9.0,
        "Stellar Eff Temp (K)": 5800.0,
        "Stellar log(g) (cm/s^2)": 4.4,
        "RA": "02:00:00",
        "Dec": "-40:00:00",
        "Period (days)": 5.0,
        "Epoch (BJD)": 2458326.1,
        "Duration (hours)": 3.1,
        "Depth (ppm)": 1700.0,
        "Planet SNR": 30.0,
        "Comments": "",
    }
    known = load_known(write_catalog_snapshot(tmp_path / "snap", toi_rows=[toi]))
    report, _ = vet_signal(
        lc, STAR, Ephemeris(5.0, 1326.1, 0.13, 0.0017), known, SEARCH, FAST_VET, seed=1
    )
    novelty = next(c for c in report["checks"] if c["check"] == "novelty")
    assert novelty["outcome"] == "fail" and not report["advances"]
    others = {c["check"]: c["outcome"] for c in report["checks"] if c["check"] != "novelty"}
    assert all(o == "pass" for o in others.values()), others


@pytest.mark.slow
def test_report_carries_red_noise_and_depth_errors_use_it(tmp_path):
    lc = make_transit_lc()
    lc.flux += correlated_noise(lc, 300.0, 1.5, seed=4)
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    report, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET, seed=1)
    betas = report["red_noise"]
    assert set(betas) == {"1", "2", "64"}
    assert max(row["beta"] for row in betas.values()) > 1.3, betas
    flat = detrend(lc, SEARCH["detrend"])
    core = VET["depth"]["core_fraction"]
    sector_depth = next(c for c in report["checks"] if c["check"] == "sector_depth")
    for row in sector_depth["evidence"]["sectors"]:
        m = flat.sector == row["sector"]
        _, white_err, _ = box_depth(flat.time[m], flat.flux[m], flat.flux_err[m], eph, core)
        assert row["err"] == pytest.approx(white_err * betas[str(row["sector"])]["beta"])


@pytest.mark.slow
def test_eclipsing_binary_in_correlated_noise_fails_odd_even(tmp_path):
    eb = [(7.4, 1326.1, 0.12, 3000e-6), (7.4, 1326.1 + 3.7, 0.12, 1500e-6)]
    lc = make_lc(sectors=(1, 2), cadence_min=2.0, noise_ppm=500.0, signals=eb, seed=12)
    lc.flux += correlated_noise(lc, 200.0, 1.5, seed=12)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    eph = Ephemeris(3.7, 1326.1, 0.12, 2250e-6)
    report, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET, seed=1)
    assert min(row["beta"] for row in report["red_noise"].values()) > 1.3, report["red_noise"]
    odd_even = next(c for c in report["checks"] if c["check"] == "odd_even")
    assert odd_even["outcome"] == "fail" and not report["advances"], odd_even["evidence"]


def test_no_cadence_inside_the_transits_leaves_shape_and_density_inconclusive(tmp_path):
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    lc = make_transit_lc(rp_rs=0.04)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    report, fit = vet_signal(
        lc.select(~in_transit(lc.time, eph)), STAR, eph, known, SEARCH, FAST_VET, seed=1
    )
    outcomes = {c["check"]: c["outcome"] for c in report["checks"]}
    assert outcomes["shape"] == outcomes["density"] == outcomes["radius"] == "inconclusive", (
        outcomes
    )
    assert fit is None and not report["advances"]


def test_signal_with_stale_catalog_epoch_is_not_masked(tmp_path):
    # The catalog epoch is 0.05 d off: too far for an epoch match, near enough for the catalog
    # transit's mask to cover most of the transit under test.
    row = {"TIC ID": 1, "RA": "02:00:00", "Dec": "-40:00:00", "Duration (hours)": 1.44}
    stale = {**row, "TOI": 7777.01, "Period (days)": 1.0, "Epoch (BJD)": 2458326.15}
    other = {**row, "TOI": 7777.02, "Period (days)": 3.7, "Epoch (BJD)": 2458327.0}
    known = load_known(write_catalog_snapshot(tmp_path / "snap", toi_rows=[stale, other]))
    eph = Ephemeris(1.0, 1326.1, 0.06)
    harmonics = tuple(VET["novelty"]["harmonics"])
    sigma_p, sigma_t = SEARCH["match"]["sigma_p"], SEARCH["match"]["sigma_t"]
    assert ephemeris_match(eph, Ephemeris(1.0, 1326.15, 0.06), harmonics, sigma_p, sigma_t) is None
    masks = other_known_transits(eph, known, 1, harmonics, SEARCH)
    assert [m.period for m in masks] == [3.7]


def tce_only_snapshot(path: Path, eph: Ephemeris) -> Path:
    """A snapshot in the M2 layout whose only row on the star is a SPOC TCE at the signal's ephemeris."""
    base = load_known(write_catalog_snapshot(path / "csv"))
    tce = {
        "source": "SPOC-TCE",
        "kind": "tce",
        "name": "TCE 1-1",
        "tic": STAR["tic"],
        "ra": STAR["ra"],
        "dec": STAR["dec"],
        "period": eph.period,
        "t0": eph.t0,
        "duration": eph.duration,
        "depth_ppm": eph.depth * 1e6,
    }
    snapshot = path / "snapshot"
    snapshot.mkdir()
    known = pd.concat([base, pd.DataFrame([tce])], ignore_index=True)[KNOWN_COLUMNS]
    known.to_parquet(snapshot / "known.parquet")
    return snapshot


def test_tce_only_match_is_inconclusive_under_vet_v2_and_fails_under_v1(tmp_path):
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    known = load_known(tce_only_snapshot(tmp_path, eph))
    assert set(known.loc[known["tic"] == STAR["tic"], "kind"]) == {"tce"}
    # Novelty reads only the catalogs; without in-transit cadences the fit stops before sampling.
    lc = make_transit_lc(rp_rs=0.04)
    lc = lc.select(~in_transit(lc.time, eph))

    def novelty(search, vet):
        report, _ = vet_signal(lc, STAR, eph, known, search, vet, seed=1)
        return next(c for c in report["checks"] if c["check"] == "novelty")

    v2 = novelty(SEARCH, FAST_VET)
    assert v2["outcome"] == "inconclusive", v2
    assert v2["evidence"]["category"] == "known_to_spoc"
    assert v2["evidence"]["tce_matches"][0]["source"] == "SPOC-TCE"
    v1 = novelty(SEARCH_V1, FAST_VET_V1)
    assert v1["outcome"] == "fail" and v1["evidence"]["category"] == "known", v1


def test_vet_v1_gets_the_values_its_code_held():
    v1 = with_v1_code_values(VET_V1)
    for section in ("red_noise", "holdout"):
        assert v1[section] == VET[section], section
    # M1's code bounded Rp/R* at 0.5; vet-v2 lifts it to 1 (decision 0018).
    assert v1["fit"] == {**VET["fit"], "max_rp_rs": 0.5}
    assert v1["novelty"]["inconclusive_kinds"] == []
    assert "window_durations" in VET_V1["fit"], "the v1 criteria must not be changed in place"


@pytest.mark.slow
def test_clean_planet_still_advances_under_vet_v1_with_m1s_density_error(tmp_path):
    lc = make_transit_lc(
        rp_rs=0.04,
        sectors=SECTORS,
        cadences={s: 30.0 for s in SECTORS},
        noise_ppm={s: 200.0 for s in SECTORS},
    )
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    report, _ = vet_signal(
        lc,
        STAR,
        Ephemeris(5.0, 1326.1, 0.13, 0.0017),
        known,
        SEARCH_V1,
        FAST_VET_V1,
        seed=1,
    )
    outcomes = {c["check"]: c["outcome"] for c in report["checks"]}
    assert set(outcomes) == M1_CHECKS
    assert all(o == "pass" for o in outcomes.values()) and report["advances"], outcomes
    evidence = next(c for c in report["checks"] if c["check"] == "density")["evidence"]
    symmetric = (evidence["fit_log_rho_minus"] + evidence["fit_log_rho_plus"]) / 2
    assert evidence["fit_log_rho_sd"] == pytest.approx(symmetric)


def test_vet_v1_runs_neither_signal_present_nor_radius(tmp_path):
    # Without cadences inside the transits there is no fit, the path where vet-v2 adds an
    # inconclusive radius; the fitted path is covered by the vet-v1 clean planet above.
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    lc = make_transit_lc(rp_rs=0.04)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    v1, _ = vet_signal(
        lc.select(~in_transit(lc.time, eph)), STAR, eph, known, SEARCH_V1, FAST_VET_V1, seed=1
    )
    assert {c["check"] for c in v1["checks"]} == M1_CHECKS


@pytest.mark.slow
def test_noise_at_an_arbitrary_ephemeris_does_not_read_as_passes(tmp_path):
    # The M1 final review's R9: six of seven checks passed a signal that isn't there.
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, seed=16)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    report, _ = vet_signal(
        lc, STAR, Ephemeris(4.21, 1327.3, 0.12, 0.0003), known, SEARCH, FAST_VET, 1
    )
    checks = {c["check"]: c["outcome"] for c in report["checks"]}
    assert checks["signal_present"] == "inconclusive" and not report["advances"]


def test_vet_v1_criteria_that_also_set_a_value_its_code_held_are_refused():
    # The code's value would win the merge, and the file's would be dropped without a word.
    hybrid = {**VET_V1, "fit": {**VET_V1["fit"], "max_rp_rs": 1.0}}
    with pytest.raises(ValueError, match="max_rp_rs"):
        with_v1_code_values(hybrid)


def test_vet_refuses_a_bjd_epoch_or_a_missing_star_before_starting_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([STAR]).to_parquet(targets)
    args = [
        "vet",
        *("--period", "5.0", "--duration", "0.13"),
        *("--targets", str(targets), "--catalogs", str(tmp_path)),
        *("--criteria-search", str(ROOT / "criteria" / "search-v2.toml")),
        *("--criteria-vet", str(ROOT / "criteria" / "vet-v2.toml")),
    ]
    with pytest.raises(SystemExit, match="BTJD"):
        main([*args, "--tic", "1", "--t0", "2459326.1"])
    with pytest.raises(SystemExit, match="not in"):
        main([*args, "--tic", "2", "--t0", "1326.1"])
    with pytest.raises(SystemExit, match="no light curve"):
        main([*args, "--tic", "1", "--t0", "1326.1"])
    assert not runs_dir().exists() or not any(runs_dir().iterdir())


V3_FIELDS = {"criteria_version", "evidence_only", "families", "dropped_suspect"}


def outcomes(report: dict) -> dict[str, str]:
    return {c["check"]: c["outcome"] for c in report["checks"]}


def check(report: dict, name: str) -> dict:
    return next(c for c in report["checks"] if c["check"] == name)


def watch_the_fit(monkeypatch, sample: bool) -> list[list[int]]:
    """Records the sectors vet's fit is given. Tests of the depth checks stop it before sampling."""
    given = []

    def watched(lc, *args, **kwargs):
        given.append(np.unique(lc.sector).tolist())
        if not sample:
            raise ValueError("not fitted in this test")
        return fit_transit(lc, *args, **kwargs)

    monkeypatch.setattr(vet, "fit_transit", watched)
    return given


def test_vet_v3_keeps_every_vet_v2_value():
    for name, section in VET.items():
        assert VET3[name] == section, name


def test_vet_v3_mask_sources_match_the_search():
    assert VET3["masks"]["sources"] == SEARCH["detrend"]["mask_sources"]


def test_vet_v3_masks_only_the_search_kinds(tmp_path, monkeypatch):
    # PF21: a SPOC TCE at another period, whose only transit in these sectors lands on the signal's
    # at 1331.1. The search never masked TCEs; vet-v2 masked every other row on the star.
    watch_the_fit(monkeypatch, sample=False)
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    known = load_known(tce_only_snapshot(tmp_path, Ephemeris(9.08, 1331.1, 0.13, 0.0017)))
    lc = make_lc(sectors=(1, 2), noise_ppm=300.0, signals=[(5.0, 1326.1, 0.13, 0.0017)], seed=20)
    v2, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET, seed=1)
    v3, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1)
    assert [m["period"] for m in v2["masked"]] == [9.08] and v3["masked"] == []
    core = VET3["depth"]["core_fraction"]
    covered = int((np.abs(lc.time - 1331.1) < 0.5 * core * eph.duration).sum())
    kept = (
        check(v3, "signal_present")["evidence"]["n"] - check(v2, "signal_present")["evidence"]["n"]
    )
    assert covered > 0 and kept == covered
    assert not V3_FIELDS & set(v2), "vet-v2's report gains no vet-v3 field"


def test_suspect_sectors_never_reach_a_check(tmp_path, monkeypatch):
    # A planet in six PDCSAP sectors over three seasons. QLP S100, flagged for its timestamps, holds
    # an eclipsing binary's pattern on top: every even transit is deeper.
    watch_the_fit(monkeypatch, sample=False)
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    lc = make_lc(
        sectors=(*SECTORS, 100), noise_ppm=200.0, signals=[(5.0, 1326.1, 0.13, 0.0017)], seed=21
    )
    s100 = lc.sector == 100
    lc.flux[s100] += box(lc.time[s100], 10.0, 1326.1, 0.13, 0.003)
    with_products(lc, {**dict.fromkeys(SECTORS, "SPOC"), 100: "QLP"}, suspect={100})
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))

    report, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1)
    checks = outcomes(report)
    for name in ("odd_even", "secondary", "sector_depth", "holdout", "signal_present"):
        assert checks[name] == "pass", (name, checks)
    assert report["criteria_version"] == "vet-v3" and report["evidence_only"] is False
    assert report["dropped_suspect"] == [100]
    assert report["families"] == {"pdcsap": list(SECTORS)}
    assert "100" not in report["red_noise"]

    evidence, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1, include_suspect=True)
    assert evidence["evidence_only"] is True and evidence["dropped_suspect"] == []
    assert evidence["families"] == {"pdcsap": list(SECTORS), "qlp": [100]}
    odd_even = check(evidence, "odd_even")
    assert odd_even["outcome"] == "fail", odd_even
    assert odd_even["evidence"]["families"]["qlp"]["outcome"] == "fail"


@pytest.mark.slow
def test_diluted_qlp_does_not_fail_a_planet(tmp_path, monkeypatch):
    # PDCSAP at full depth in every season, QLP at 0.6 of it, the low end of
    # results/benchmarks/qlp-dilution-2026-10-13.txt.
    qlp = (3, 16, 30)
    lc = make_lc(sectors=sorted((*SECTORS, *qlp)), noise_ppm=200.0, seed=22)
    a_rs = a_rs_from_density(1.41, 5.0)
    model = light_curve(lc.time, lc.exposure_days(), 1326.1, 5.0, 0.04, a_rs, 0.3, 0.36, 0.24)
    dilution = np.where(np.isin(lc.sector, qlp), 0.6, 1.0)
    lc.flux *= 1.0 - dilution * (1.0 - model)
    with_products(lc, {**dict.fromkeys(SECTORS, "SPOC"), **dict.fromkeys(qlp, "QLP")})
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))

    watch_the_fit(monkeypatch, sample=False)
    v2, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET, seed=1)
    assert outcomes(v2)["sector_depth"] == "fail", check(v2, "sector_depth")["evidence"]

    fitted = watch_the_fit(monkeypatch, sample=True)
    v3, fit = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1)
    checks = outcomes(v3)
    assert checks["odd_even"] == checks["sector_depth"] == checks["holdout"] == "pass", checks
    # Both fits, the flat one and the density-prior one, read the PDCSAP family alone, so the planet
    # passes every check.
    assert fitted == [list(SECTORS)] * 2
    assert all(o == "pass" for o in checks.values()) and v3["advances"] and fit is not None, checks


def test_one_family_odd_even_binary_still_fails(tmp_path, monkeypatch):
    # An eclipsing binary at twice the period. Its odd and even eclipses differ in the PDCSAP
    # sectors; QLP's sector, diluted and noisier, can't tell them apart.
    watch_the_fit(monkeypatch, sample=False)
    lc = make_lc(
        sectors=(1, 2, 3),
        cadences={1: 2.0, 2: 2.0, 3: 10.0},
        noise_ppm={1: 500.0, 2: 500.0, 3: 4000.0},
        seed=23,
    )
    dilution = np.where(lc.sector == 3, 0.6, 1.0)
    for t0, depth in ((1326.1, 3000e-6), (1326.1 + 3.7, 1500e-6)):
        lc.flux += dilution * box(lc.time, 7.4, t0, 0.12, depth)
    with_products(lc, {1: "SPOC", 2: "SPOC", 3: "QLP"})
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    eph = Ephemeris(3.7, 1326.1, 0.12, 2250e-6)
    report, _ = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1)
    odd_even = check(report, "odd_even")
    families = odd_even["evidence"]["families"]
    assert families["pdcsap"]["outcome"] == "fail" and families["qlp"]["outcome"] == "pass", (
        families
    )
    assert odd_even["outcome"] == "fail" and not report["advances"]


def test_no_fit_family_data_leaves_fit_checks_inconclusive(tmp_path):
    lc = with_products(make_transit_lc(rp_rs=0.04), dict.fromkeys((1, 2, 64), "QLP"))
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    report, fit = vet_signal(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1)
    for name in ("shape", "density", "radius"):
        result = check(report, name)
        assert (result["outcome"], result["reason"]) == ("inconclusive", "no pdcsap data to fit")
    assert fit is None and report["fit"] is None and not report["advances"]
    assert report["families"] == {"qlp": [1, 2, 64]}


def test_density_prior_units_and_fallback():
    nan = float("nan")
    assert vet.density_prior({"rho": 1.0, "e_rho": nan}, 0.1) == pytest.approx(
        (np.log10(1.408), 0.1)
    )
    assert vet.density_prior({"rho": 2.0, "e_rho": 0.2}, 0.1) == pytest.approx(
        (np.log10(2.0 * 1.408), 0.2 / (2.0 * np.log(10)))
    )
    assert vet.density_prior({"rho": 1.0}, 0.07)[1] == 0.07
    # A TIC error of zero or below is no error: the default stands in, as for a missing one.
    for e_rho in (0.0, -0.1):
        assert vet.density_prior({"rho": 1.0, "e_rho": e_rho}, 0.07)[1] == 0.07, e_rho
    for rho in (nan, None, 0.0, -1.0):
        assert vet.density_prior({"rho": rho, "e_rho": 0.1}, 0.1) is None, rho


def quick_planet():
    return make_transit_lc(
        rp_rs=0.04,
        cadences={1: 30.0, 2: 30.0, 64: 30.0},
        noise_ppm=dict.fromkeys((1, 2, 64), 200.0),
    )


def test_vet_writes_the_density_prior_fits_samples_under_vet_v3(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    lc = with_products(quick_planet(), dict.fromkeys((1, 2, 64), "SPOC"))
    lc.tic = 1
    lc.save(tmp_path / "data" / "lc" / "1.npz")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([STAR]).to_parquet(targets)
    fits = []

    def fit(lc, eph, cfg, rho_prior=None, seed=None):
        # Each fit's own samples, so the two files can be told apart.
        rng = np.random.default_rng(len(fits))
        values = {
            "t0": eph.t0 + rng.normal(0.0, 1e-3, 400),
            "period": eph.period + rng.normal(0.0, 1e-5, 400),
            "rp_rs": np.full(400, 0.04),
            "b": np.full(400, 0.3),
            "log_rho": np.full(400, 0.15),
            "q1": np.full(400, 0.36),
            "q2": np.full(400, 0.36),
        }
        fits.append(FitResult(np.column_stack([values[n] for n in NAMES]), 0.3, rho_prior))
        return fits[-1]

    monkeypatch.setattr(vet, "fit_transit", fit)
    args = [
        "vet",
        *("--tic", "1", "--period", "5.0", "--t0", "1326.1", "--duration", "0.13"),
        *("--depth", "0.0017", "--targets", str(targets)),
        *("--catalogs", str(write_catalog_snapshot(tmp_path / "snap"))),
        *("--criteria-search", str(ROOT / "criteria" / "search-v2.toml")),
        *("--criteria-vet", str(ROOT / "criteria" / "vet-v3.toml")),
    ]
    assert main(args) == 0
    [run] = runs_dir().iterdir()
    flat, prior = fits
    assert flat.rho_prior is None
    assert prior.rho_prior == vet.density_prior(STAR, VET3["density"]["default_log_rho_error"])
    for name, made in (("fit_samples.npz", flat), ("fit_prior_samples.npz", prior)):
        with np.load(run / name) as z:
            assert np.array_equal(z["samples"], made.samples), name
    assert json.loads((run / "checks.json").read_text())["fit_prior"] is not None


@pytest.mark.slow
def test_prior_fit_reported_beside_the_flat_fit(tmp_path):
    lc = with_products(quick_planet(), dict.fromkeys((1, 2, 64), "SPOC"))
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    report, fit, fit_prior = vet.vet_with_fits(lc, STAR, eph, known, SEARCH, FAST_VET3, seed=1)
    assert fit.rho_prior is None
    assert fit_prior.rho_prior == vet.density_prior(STAR, VET3["density"]["default_log_rho_error"])
    flat, prior = report["fit"], report["fit_prior"]
    assert report["fit_prior_reason"] is None and prior["rho_prior"] == list(fit_prior.rho_prior)

    # shape, density and radius read the flat-prior fit.
    density = check(report, "density")["evidence"]
    assert density["fit_log_rho"] == pytest.approx(flat["log_rho"]["median"])
    assert check(report, "shape")["evidence"]["b_median"] == pytest.approx(flat["b"]["median"])
    radius = check(report, "radius")["evidence"]
    assert radius["rp_rs_median"] == pytest.approx(flat["rp_rs"]["median"])
    assert prior["log_rho"]["median"] != pytest.approx(flat["log_rho"]["median"])

    # The TIC density narrows the second fit's density posterior.
    spread = {
        name: f["log_rho"]["minus"] + f["log_rho"]["plus"]
        for name, f in (("flat", flat), ("prior", prior))
    }
    assert spread["prior"] < spread["flat"], spread

    rp = fit_prior.column("rp_rs") * STAR["rad"] * 109.076
    assert prior["rp_rearth"] == pytest.approx(
        dict(zip(("p16", "median", "p84"), np.percentile(rp, [16, 50, 84]), strict=True))
    )
    a_rs = [
        a_rs_from_density(10.0**r, p)
        for r, p in zip(fit_prior.column("log_rho"), fit_prior.column("period"), strict=True)
    ]
    assert prior["a_rs"]["median"] == pytest.approx(np.median(a_rs))
    for name in ("t0", "period"):
        assert prior["ephemeris"][name] == pytest.approx(
            {"median": np.median(fit_prior.column(name)), "sd": np.std(fit_prior.column(name))}
        )


def test_prior_fit_needs_fit_data_and_a_tic_density_inside_the_fit_range(tmp_path, monkeypatch):
    fitted = watch_the_fit(monkeypatch, sample=False)
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
    lc = with_products(quick_planet(), dict.fromkeys((1, 2, 64), "SPOC"))

    def prior_fit(lc, star, crit_vet):
        report, _, fit_prior = vet.vet_with_fits(lc, star, eph, known, SEARCH, crit_vet, seed=1)
        assert fit_prior is None
        return report

    report = prior_fit(lc, STAR, FAST_VET3)
    assert report["fit_prior"] is None
    assert report["fit_prior_reason"] == "no fit: not fitted in this test"
    assert len(fitted) == 2, "the flat fit and the density-prior fit"
    for rho, reason in (
        (float("nan"), "the TIC gives no stellar density"),
        # A white dwarf's density: walkers started there sit outside the flat bound and never move.
        (1e5, "the TIC density, log10 5.15 g/cm3, is outside the fit's range (-3, 2)"),
    ):
        report = prior_fit(lc, {**STAR, "rho": rho}, FAST_VET3)
        assert (report["fit_prior"], report["fit_prior_reason"]) == (None, reason)
    assert len(fitted) == 4, "only the flat fit ran"

    qlp = with_products(quick_planet(), dict.fromkeys((1, 2, 64), "QLP"))
    report = prior_fit(qlp, STAR, FAST_VET3)
    assert report["fit_prior_reason"] == "no pdcsap data to fit"

    v2 = prior_fit(lc, STAR, FAST_VET)
    assert not {"fit_prior", "fit_prior_reason"} & set(v2)
    assert len(fitted) == 5, "vet-v2 fits once"


SNAPSHOTS = ROOT / "tests" / "fixtures" / "m4-refactor"
EPH = Ephemeris(5.0, 1326.1, 0.13, 0.0017)
# A catalogued planet on the star at another period, which vet masks.
OTHER_TOI = {
    "TIC ID": 1,
    "TOI": 7777.02,
    "RA": "02:00:00",
    "Dec": "-40:00:00",
    "Period (days)": 3.7,
    "Epoch (BJD)": 2458327.0,
    "Duration (hours)": 1.44,
}


def planet_with_a_suspect_sector():
    """test_suspect_sectors_never_reach_a_check's star."""
    lc = make_lc(
        sectors=(*SECTORS, 100), noise_ppm=200.0, signals=[(5.0, 1326.1, 0.13, 0.0017)], seed=21
    )
    s100 = lc.sector == 100
    lc.flux[s100] += box(lc.time[s100], 10.0, 1326.1, 0.13, 0.003)
    return with_products(lc, {**dict.fromkeys(SECTORS, "SPOC"), 100: "QLP"}, suspect={100})


def diluted_qlp_planet():
    """test_diluted_qlp_does_not_fail_a_planet's star."""
    qlp = (3, 16, 30)
    lc = make_lc(sectors=sorted((*SECTORS, *qlp)), noise_ppm=200.0, seed=22)
    model = light_curve(
        lc.time,
        lc.exposure_days(),
        1326.1,
        5.0,
        0.04,
        a_rs_from_density(1.41, 5.0),
        0.3,
        0.36,
        0.24,
    )
    lc.flux *= 1.0 - np.where(np.isin(lc.sector, qlp), 0.6, 1.0) * (1.0 - model)
    return with_products(lc, {**dict.fromkeys(SECTORS, "SPOC"), **dict.fromkeys(qlp, "QLP")})


def planet(depth, qlp=()):
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, signals=[(5.0, 1326.1, 0.13, depth)], seed=24)
    return with_products(lc, {s: "QLP" if s in qlp else "SPOC" for s in SECTORS})


# Each case: the light curve, the ephemeris, the star's catalog rows, the criteria, include_suspect.
VET_CASES = {
    "planet_three_seasons": (planet_with_a_suspect_sector, EPH, [OTHER_TOI], SEARCH, VET3, False),
    "planet_three_seasons_evidence_only": (
        planet_with_a_suspect_sector,
        EPH,
        [OTHER_TOI],
        SEARCH,
        VET3,
        True,
    ),
    "planet_three_seasons_vet_v2": (
        planet_with_a_suspect_sector,
        EPH,
        [OTHER_TOI],
        SEARCH,
        VET,
        False,
    ),
    "planet_three_seasons_vet_v1": (
        planet_with_a_suspect_sector,
        EPH,
        [OTHER_TOI],
        SEARCH_V1,
        VET_V1,
        False,
    ),
    "mixed_family": (diluted_qlp_planet, EPH, [], SEARCH, VET3, False),
    # The last season all QLP, which no training season holds.
    "untestable_family": (lambda: planet(0.0017, qlp=(28, 29)), EPH, [], SEARCH, VET3, False),
    "underpowered_season": (
        lambda: planet(60e-6),
        Ephemeris(5.0, 1326.1, 0.13, 60e-6),
        [],
        SEARCH,
        VET3,
        False,
    ),
}


def vet_case(case: str, path: Path) -> dict:
    make, eph, rows, crit_search, crit_vet, include_suspect = VET_CASES[case]
    known = load_known(write_catalog_snapshot(path, toi_rows=rows))
    report, _, _ = vet.vet_with_fits(
        make(), STAR, eph, known, crit_search, crit_vet, 1, include_suspect
    )
    return report


@pytest.mark.parametrize("case", list(VET_CASES))
def test_vet_report_is_unchanged(case, tmp_path, monkeypatch):
    # Pinned before M4 lifted vet's light-curve preparation out of vet_with_fits. The fit is stopped
    # before sampling, whose last digits can differ between machines; the depth checks read the light
    # curve it would fit.
    watch_the_fit(monkeypatch, sample=False)
    expected = json.loads((SNAPSHOTS / "vet.json").read_text())[case]
    report = vet_case(case, tmp_path / "snap")
    assert json.dumps(jsonable(report), sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_prepare_matches_vet(tmp_path, monkeypatch):
    watch_the_fit(monkeypatch, sample=False)
    given = []

    def spy(lc, *args):
        given.append(lc)
        return holdout(lc, *args)

    monkeypatch.setattr(vet, "holdout", spy)
    known = load_known(write_catalog_snapshot(tmp_path / "snap", toi_rows=[OTHER_TOI]))
    report, _, _ = vet.vet_with_fits(
        planet_with_a_suspect_sector(), STAR, EPH, known, SEARCH, VET3, 1
    )
    prepared = vet.prepare(planet_with_a_suspect_sector(), STAR, EPH, known, SEARCH, VET3)
    [noisy] = given
    for name in ("time", "flux", "flux_err", "sector"):
        assert np.array_equal(getattr(prepared.noisy, name), getattr(noisy, name)), name
    assert prepared.noisy.sources == noisy.sources
    assert 100 not in prepared.good.sector
    assert prepared.dropped == report["dropped_suspect"] == [100]
    assert [asdict(k) for k in prepared.others] == report["masked"] and prepared.others
    assert prepared.betas == report["red_noise"]
