from pathlib import Path

import numpy as np
import pytest
from synthetic import make_transit_lc

from tess_hunt.checks import Outcome
from tess_hunt.checks.physical import density
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, in_transit, phase_days
from tess_hunt.fit import fit_transit

FIT = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "vet-v2.toml")["fit"]
CFG = {**FIT, "steps": 3000, "burn": 1500}
SMALL = {**FIT, "walkers": 16, "steps": 200, "burn": 100}


@pytest.mark.slow
def test_fit_recovers_planet():
    lc = make_transit_lc()
    fit = fit_transit(lc, Ephemeris(5.0, 1326.1, 0.13, 0.0008), CFG, seed=1)
    s = fit.summary()
    for name, truth in (("rp_rs", 0.03), ("log_rho", np.log10(1.41))):
        spread = max(s[name]["minus"], s[name]["plus"])
        assert abs(s[name]["median"] - truth) < 3 * spread
    assert density(fit, 1.0, 0.1, 3.0, 0.1).outcome is Outcome.PASS


@pytest.mark.slow
def test_density_negative_control_end_to_end_giant():
    lc = make_transit_lc(rho_gcc=0.014)
    fit = fit_transit(lc, Ephemeris(5.0, 1326.1, 0.6, 0.0008), CFG, seed=2)
    assert density(fit, 1.0, 0.1, 3.0, 0.1).outcome is Outcome.FAIL


def test_fit_refuses_without_data_near_transit():
    lc = make_transit_lc()
    with pytest.raises(ValueError):
        fit_transit(lc.select(lc.time > 5000), Ephemeris(5.0, 1326.1, 0.13), CFG, seed=1)


def test_fit_window_is_a_half_width():
    # The window counts cadences within window_half_width_durations either side of mid-transit;
    # in_transit's width of the same number spans only half as far.
    lc = make_transit_lc()
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0008)
    width = FIT["window_half_width_durations"]
    near = int((np.abs(phase_days(lc.time, eph)) < width * eph.duration).sum())
    assert near > in_transit(lc.time, eph, width).sum()
    with pytest.raises(ValueError, match=f"only {near} cadences near transit"):
        fit_transit(lc, eph, {**SMALL, "min_points": near + 1}, seed=1)


def test_fit_refuses_a_window_with_no_cadence_inside_the_transit():
    lc = make_transit_lc()
    eph = Ephemeris(5.0, 1326.1, 0.13, 0.0008)
    with pytest.raises(ValueError, match="inside the transit"):
        fit_transit(lc.select(~in_transit(lc.time, eph)), eph, SMALL, seed=1)


def test_fit_refuses_a_burn_in_that_leaves_no_samples():
    lc = make_transit_lc()
    no_samples = {**SMALL, "burn": SMALL["steps"]}
    with pytest.raises(ValueError, match="burn"):
        fit_transit(lc, Ephemeris(5.0, 1326.1, 0.13, 0.0008), no_samples, seed=1)


def test_eclipse_deeper_than_the_prior_still_starts_inside_it():
    lc = make_transit_lc(rp_rs=0.6)
    fit = fit_transit(lc, Ephemeris(5.0, 1326.1, 0.2, 0.3), SMALL, seed=1)
    assert fit.acceptance > FIT["min_acceptance"]
    assert len(np.unique(fit.column("b"))) > SMALL["walkers"]


def test_fit_below_the_criteria_acceptance_raises():
    lc = make_transit_lc()
    with pytest.raises(ValueError, match="acceptance"):
        fit_transit(
            lc, Ephemeris(5.0, 1326.1, 0.13, 0.0008), {**SMALL, "min_acceptance": 1.0}, seed=1
        )


# Judging each rejected proposal, emcee subtracts the walker's -inf log probability from the proposal's.
@pytest.mark.filterwarnings("ignore:invalid value encountered in scalar subtract:RuntimeWarning")
def test_fit_whose_walkers_never_move_raises():
    lc = make_transit_lc()
    white_dwarf_prior = (6.0, 0.1)
    with pytest.raises(ValueError, match="acceptance"):
        fit_transit(lc, Ephemeris(5.0, 1326.1, 0.13, 0.0008), SMALL, white_dwarf_prior, seed=1)


@pytest.mark.slow
def test_deep_eclipse_is_not_pinned_at_the_bound():
    lc = make_transit_lc(rp_rs=0.6, b=0.0, noise_ppm={1: 600.0, 2: 600.0, 64: 150.0})
    fit = fit_transit(lc, Ephemeris(5.0, 1326.1, 0.3, 0.3), CFG, seed=3)
    rp_rs = fit.column("rp_rs")
    assert np.median(rp_rs) > 0.52 and np.mean(rp_rs > 0.495) > 0.5
