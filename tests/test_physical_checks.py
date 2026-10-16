from pathlib import Path

import numpy as np
import pytest
from synthetic import make_transit_lc

from tess_hunt.checks import Outcome
from tess_hunt.checks.physical import density, radius, shape
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.fit import NAMES, FitResult, fit_transit

VET = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "vet-v2.toml").values
SUNLIKE_LOG_RHO = float(np.log10(1.41))


def fake_fit(b=0.3, rp_rs=0.03, log_rho=SUNLIKE_LOG_RHO, log_rho_sd=0.1, rho_prior=None, n=4000):
    rng = np.random.default_rng(0)
    samples = np.zeros((n, len(NAMES)))
    samples[:, NAMES.index("b")] = rng.normal(b, 0.02, n)
    samples[:, NAMES.index("rp_rs")] = rng.normal(rp_rs, 0.002, n)
    samples[:, NAMES.index("log_rho")] = rng.normal(log_rho, log_rho_sd, n)
    return FitResult(samples, 0.3, rho_prior)


def test_shape_negative_control_grazing_fails():
    assert shape(fake_fit(b=1.05, rp_rs=0.15), 0.5).outcome is Outcome.FAIL


@pytest.mark.slow
def test_shape_negative_control_end_to_end_grazing_eclipse():
    # The criteria's step counts, not the shorter ones other tests use: after 1500 steps with 700
    # burned, the walkers still sit near b 0.67, short of the grazing geometry, and this eclipse passes.
    fit_cfg = VET["fit"]
    lc = make_transit_lc(rp_rs=0.25, b=0.95)
    fit = fit_transit(lc, Ephemeris(5.0, 1326.1, 0.10, 0.004), fit_cfg, seed=fit_cfg["seed"])
    result = shape(fit, VET["shape"]["max_grazing_probability"])
    assert result.outcome is Outcome.FAIL, result.evidence
    assert result.evidence["grazing_probability"] > 0.5


def test_shape_central_transit_passes():
    assert shape(fake_fit(), 0.5).outcome is Outcome.PASS


def test_shape_of_an_empty_posterior_is_inconclusive():
    empty = FitResult(np.empty((0, len(NAMES))), 0.3, None)
    assert shape(empty, 0.5).outcome is Outcome.INCONCLUSIVE


def test_density_negative_control_giant_host_fails():
    result = density(fake_fit(log_rho=np.log10(0.014), log_rho_sd=0.05), 1.0, 0.1, 3.0, 0.1)
    assert result.outcome is Outcome.FAIL and result.evidence["tension_sigma"] > 3.0


def test_density_consistent_star_passes():
    assert density(fake_fit(), 1.0, 0.1, 3.0, 0.1).outcome is Outcome.PASS


def test_density_without_tic_density_is_inconclusive():
    assert density(fake_fit(), float("nan"), float("nan"), 3.0, 0.1).outcome is Outcome.INCONCLUSIVE


def test_density_refuses_a_fit_that_used_a_density_prior():
    with pytest.raises(ValueError):
        density(fake_fit(rho_prior=(0.15, 0.1)), 1.0, 0.1, 3.0, 0.1)


def skewed_fit(median=SUNLIKE_LOG_RHO, low_sd=0.6, high_sd=0.05, n=20000):
    """A log-density posterior with a long low tail, as low-SNR transits give."""
    rng = np.random.default_rng(1)
    z = rng.normal(size=n)
    log_rho = median + np.where(z < 0, z * low_sd, z * high_sd)
    samples = np.zeros((n, len(NAMES)))
    samples[:, NAMES.index("b")] = 0.3
    samples[:, NAMES.index("rp_rs")] = 0.03
    samples[:, NAMES.index("log_rho")] = log_rho
    return FitResult(samples, 0.3, None)


def test_density_uses_the_side_facing_the_tic_value():
    # The TIC value sits 1.3 dex below the median, inside the long low tail: about 2.1 sigma on that
    # side, but 3.8 sigma with the symmetric error M1 used, which failed it.
    rho_tic = 10 ** (SUNLIKE_LOG_RHO - 1.3) / 1.408
    result = density(skewed_fit(), rho_tic, None, 3.0, 0.1)
    assert result.outcome is Outcome.PASS, result.evidence
    assert result.evidence["fit_log_rho_sd"] == pytest.approx(0.6, abs=0.03)


def test_density_still_fails_on_the_short_side():
    rho_tic = 10 ** (SUNLIKE_LOG_RHO + 1.0) / 1.408
    assert density(skewed_fit(), rho_tic, None, 3.0, 0.1).outcome is Outcome.FAIL


def test_nan_samples_are_inconclusive():
    fit = fake_fit()
    fit.samples[0, NAMES.index("b")] = np.nan
    assert shape(fit, 0.5).outcome is Outcome.INCONCLUSIVE
    assert density(fit, 1.0, 0.1, 3.0, 0.1).outcome is Outcome.INCONCLUSIVE


def test_vet_v1s_symmetric_density_error_still_fails_the_long_tail():
    # vet-v1 keeps M1's rule so its results reproduce (docs/decisions/0016).
    rho_tic = 10 ** (SUNLIKE_LOG_RHO - 1.3) / 1.408
    result = density(skewed_fit(), rho_tic, None, 3.0, 0.1, symmetric_error=True)
    assert result.outcome is Outcome.FAIL, result.evidence
    minus, plus = result.evidence["fit_log_rho_minus"], result.evidence["fit_log_rho_plus"]
    assert result.evidence["fit_log_rho_sd"] == pytest.approx((minus + plus) / 2)


def test_radius_negative_control_eclipsing_binary_fails():
    result = radius(fake_fit(rp_rs=0.6), 1.0, 22.0)
    assert result.outcome is Outcome.FAIL and result.evidence["rp_rearth"] > 60


@pytest.mark.slow
def test_radius_negative_control_end_to_end_deep_eclipse():
    # M1's deep-eclipse case: a central eclipse with a true Rp/R* of 0.6 on a Sun-sized star, fitted
    # with the criteria's bound and step counts.
    fit_cfg = VET["fit"]
    lc = make_transit_lc(rp_rs=0.6, b=0.0)
    fit = fit_transit(lc, Ephemeris(5.0, 1326.1, 0.3, 0.3), fit_cfg, seed=fit_cfg["seed"])
    result = radius(fit, 1.0, VET["radius"]["max_rearth"])
    assert result.outcome is Outcome.FAIL, result.evidence
    assert result.evidence["rp_rs_median"] > 0.5, result.evidence


def test_radius_of_a_planet_passes_and_missing_tic_radius_is_inconclusive():
    assert radius(fake_fit(rp_rs=0.03), 1.0, 22.0).outcome is Outcome.PASS
    assert radius(fake_fit(), float("nan"), 22.0).outcome is Outcome.INCONCLUSIVE
    assert radius(fake_fit(), None, 22.0).outcome is Outcome.INCONCLUSIVE
