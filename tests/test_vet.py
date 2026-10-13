from pathlib import Path

import pandas as pd
import pytest
from synthetic import correlated_noise, make_lc, make_transit_lc, write_catalog_snapshot

from tess_hunt.catalogs import KNOWN_COLUMNS, load_known
from tess_hunt.checks.photometry import box_depth
from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, ephemeris_match, in_transit
from tess_hunt.vet import other_known_transits, vet_signal, with_v1_code_values

ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v2.toml").values
VET = load_criteria(ROOT / "criteria" / "vet-v2.toml").values
FAST_VET = {**VET, "fit": {**VET["fit"], "steps": 1500, "burn": 700}}
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
