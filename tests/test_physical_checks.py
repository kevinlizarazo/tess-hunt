import numpy as np
import pytest

from tess_hunt.checks import Outcome
from tess_hunt.checks.physical import density, shape
from tess_hunt.fit import NAMES, FitResult

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


def test_shape_central_transit_passes():
    assert shape(fake_fit(), 0.5).outcome is Outcome.PASS


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
