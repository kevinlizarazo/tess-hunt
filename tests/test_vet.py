from pathlib import Path

import pytest
from synthetic import correlated_noise, make_transit_lc, write_catalog_snapshot

from tess_hunt.catalogs import load_known
from tess_hunt.checks.photometry import box_depth
from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.vet import other_known_transits, vet_signal

ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v1.toml").values
VET = load_criteria(ROOT / "criteria" / "vet-v1.toml").values
FAST_VET = {**VET, "fit": {**VET["fit"], "steps": 1500, "burn": 700}}
STAR = {"tic": 1, "ra": 30.0, "dec": -40.0, "rho": 1.0, "e_rho": 0.1}
SECTORS = (1, 2, 14, 15, 28, 29)


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
    assert set(outcomes) == {
        "novelty",
        "odd_even",
        "secondary",
        "sector_depth",
        "holdout",
        "shape",
        "density",
    }
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
