import inspect
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from leo_vetter import thresholds as lt
from leo_vetter.thresholds import _default_thresholds
from synthetic import make_lc, make_transit_lc

from tess_hunt.checks import Outcome
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.leo import FA_TESTS, FP_TESTS, evaluate, leo_flux, leo_star, prepare

# leo-vetter 1.2.0's secondary test negates with ~, which Python deprecates on a plain bool; the metrics
# here are plain floats, LEO-Vetter's own are mostly numpy. The verdict is still right: ~ flips the low bit.
pytestmark = pytest.mark.filterwarnings("ignore:Bitwise inversion '~' on bool:DeprecationWarning")

ROOT = Path(__file__).resolve().parents[1]
TRIAGE = load_criteria(ROOT / "criteria" / "triage-v1.toml").values
DETREND = load_criteria(ROOT / "criteria" / "search-v2.toml")["detrend"]
SUN = {
    "tic": 1,
    "ra": 10.0,
    "dec": -60.0,
    "rad": 1.0,
    "e_rad": 0.05,
    "mass": 1.0,
    "e_mass": 0.05,
    "teff": 5770.0,
    "e_teff": 100.0,
    "logg": 4.44,
}
# Every metric LEO-Vetter's tests read, at values that pass every test.
PASSING = {
    "MES": 20.0,
    "new_MES": 20.0,
    "new_N_transit": 10,
    "N_transit": 10,
    "SHP": 0.1,
    "sig_pri": 20.0,
    "Fred": 1.0,
    "FA1": 1.0,
    "sig_ter": 1.0,
    "FA2": 1.0,
    "sig_pos": 1.0,
    "mean_chases": 0.9,
    "DMM": 1.0,
    "max_SES": 5.0,
    "transit_aic": -1000.0,
    "line_aic": 0.0,
    "transit_chisqr": 1.0,
    "line_chisqr": 2.0,
    "sine_sig": 1.0,
    "per": 5.0,
    "transit_aRs": 10.0,
    "aRs": 10.0,
    "q": 0.02,
    "trap_qtran": 0.02,
    "sig_sec": 1.0,
    "trap_qtran_left": 0.01,
    "trap_qtran_right": 0.01,
    "trap_qtran_err_left": 0.01,
    "trap_qtran_err_right": 0.01,
    "CHI": 20.0,
    "N_gap_2.0": 0,
    "sig_dep": 0.0,
    "trap_sig_dep": 0.0,
    "trap_sig_epo": 0.0,
    "transit_sig_dep": 0.0,
    "transit_sig_epo": 0.0,
    "transit_b": 0.3,
    "transit_RpRs": 0.03,
    "Rp": 2.0,
    "albedo": 0.1,
    "dep_sec": 0.0,
    "dep": 0.001,
}


def test_paper_thresholds_differ_from_the_code_only_where_decided():
    leo = TRIAGE["leo"]
    differ = {k for k in _default_thresholds if float(leo[k]) != float(_default_thresholds[k])}
    assert differ == {"max_SES_to_MES", "ASYM"}
    assert leo["max_SES_to_MES"] == 0.88 and leo["ASYM"] == 10


def test_evaluate_passing_metrics_is_a_candidate():
    out = evaluate(PASSING, TRIAGE["leo"])
    assert out.disposition == "PC" and out.passes_fa and not out.unknown


def test_evaluate_weak_signal_is_a_false_alarm():
    # max_SES / MES stays under 0.88, so single_event does not fire alongside weak.
    out = evaluate({**PASSING, "MES": 3.0, "max_SES": 2.0}, TRIAGE["leo"])
    assert out.disposition == "FA" and out.fa_failed == ["weak"] and not out.passes_fa


def test_evaluate_counts_a_nan_input_as_unknown_not_a_pass():
    out = evaluate({**PASSING, "MES": float("nan")}, TRIAGE["leo"])
    assert out.disposition is None and "weak" in out.unknown and out.passes_fa


def test_evaluate_large_radius_is_a_false_positive():
    out = evaluate({**PASSING, "Rp": 30.0}, TRIAGE["leo"])
    assert out.disposition == "FP" and out.fp_failed == ["large"]


def test_evaluate_nan_radius_is_unknown():
    out = evaluate({**PASSING, "Rp": float("nan")}, TRIAGE["leo"])
    assert out.disposition is None and "large" in out.unknown


def test_evaluate_ignores_inputs_a_test_does_not_read():
    # chases reads mean_chases only for five transits or fewer.
    assert evaluate({**PASSING, "mean_chases": float("nan")}, TRIAGE["leo"]).disposition == "PC"


def test_evaluate_judges_a_branch_only_where_it_can_change_the_verdict():
    # odd_even reads the trapezoid and transit depth differences only when the box depths differ;
    # secondary's planet-like escape (albedo is NaN when no secondary is seen) can only make it fire.
    gated = {
        **PASSING,
        "trap_sig_dep": float("nan"),
        "transit_sig_dep": float("nan"),
        "albedo": float("nan"),
    }
    assert evaluate(gated, TRIAGE["leo"]).disposition == "PC"
    out = evaluate({**gated, "sig_dep": 5.0}, TRIAGE["leo"])
    assert out.disposition is None and out.unknown == ["odd_even"]
    out = evaluate({**gated, "sig_sec": 30.0}, TRIAGE["leo"])
    assert out.disposition == "FP" and out.fp_failed == ["secondary"]


def test_evaluate_missing_metric_is_unknown():
    metrics = dict(PASSING)
    del metrics["CHI"]
    out = evaluate(metrics, TRIAGE["leo"])
    assert out.disposition is None and any(u.startswith("chi") for u in out.unknown)


def test_wrapper_runs_every_test_leo_vetter_runs():
    # The wrapper lists LEO-Vetter's tests by hand; a test it missed would never be judged.
    source = inspect.getsource(lt.check_thresholds)
    fa, fp = (re.findall(r"\w+", block) for block in re.findall(r"tests = \[([^\]]*)\]", source))
    assert [name for name, _, _ in FA_TESTS] == fa
    assert [name for name, _, _ in FP_TESTS] == fp  # the pixel offset test runs in pixels.py
    assert all(test is getattr(lt, name) for name, test, _ in FA_TESTS + FP_TESTS)


def test_leo_missing_star_parameter_is_inconclusive():
    assert leo_star({**SUN, "rad": float("nan")}, TRIAGE["leo_metrics"]) is None
    lc = make_lc(sectors=(1, 2), signals=[(3.0, 1326.0, 0.1, 0.002)])
    result, outcome, _ = leo_flux(
        lc,
        {**SUN, "teff": None},
        Ephemeris(3.0, 1326.0, 0.1),
        [],
        np.zeros(len(lc.time), bool),
        DETREND,
        TRIAGE,
    )
    assert result.outcome is Outcome.INCONCLUSIVE and outcome is None


def test_leo_empty_light_curve_is_inconclusive():
    lc = make_lc(sectors=(1,), signals=[(3.0, 1326.0, 0.1, 0.002)])
    every = np.ones(len(lc.time), bool)
    result, _, _ = leo_flux(lc, SUN, Ephemeris(3.0, 1326.0, 0.1), [], every, DETREND, TRIAGE)
    assert result.outcome is Outcome.INCONCLUSIVE, result


def test_leo_star_fills_missing_errors_from_criteria():
    star = leo_star({**SUN, "e_rad": float("nan"), "e_teff": None}, TRIAGE["leo_metrics"])
    assert star["e_rad"] == pytest.approx(0.1) and star["e_Teff"] == 150.0
    assert star["rho"] == pytest.approx(1.0) and 0 < star["u1"] < 1


def test_leo_star_density_is_the_tic_value_else_mass_over_radius_cubed():
    tic = leo_star({**SUN, "rho": 0.8, "e_rho": 0.05}, TRIAGE["leo_metrics"])
    assert tic["rho"] == 0.8 and tic["e_rho"] == 0.05
    # targets.parquet records carry pd.NA for a missing value.
    star = {**SUN, "rad": 1.2, "e_rad": 0.06, "e_mass": 0.1, "rho": 0.8, "e_rho": pd.NA}
    derived = leo_star(star, TRIAGE["leo_metrics"])
    assert derived["rho"] == pytest.approx(1.0 / 1.2**3)
    assert derived["e_rho"] == pytest.approx(derived["rho"] * np.hypot(0.1, 3 * 0.06 / 1.2))


def test_prepare_drops_other_signals():
    a, b = Ephemeris(3.0, 1326.0, 0.15, 0.003), Ephemeris(7.3, 1328.0, 0.2, 0.004)
    lc = make_lc(
        sectors=(1, 2),
        noise_ppm=100.0,
        signals=[(3.0, 1326.0, 0.15, 0.003), (7.3, 1328.0, 0.2, 0.004)],
    )
    flat = prepare(lc, a, [b], np.zeros(len(lc.time), bool), DETREND, 2.0)
    assert not in_transit(flat.time, b, 1.0).any()
    inside = in_transit(flat.time, a, 0.5)
    assert inside.sum() > 20 and abs((1.0 - np.median(flat.flux[inside])) - 0.003) < 0.0005


@pytest.mark.slow
def test_leo_clean_planet_is_a_candidate():
    lc = make_transit_lc(rp_rs=0.04, period=5.0, t0=1326.1)
    result, outcome, tlc = leo_flux(
        lc, SUN, Ephemeris(5.0, 1326.1, 0.13), [], np.zeros(len(lc.time), bool), DETREND, TRIAGE
    )
    assert outcome.disposition == "PC", (outcome, result.evidence["metrics"])
    assert result.outcome is Outcome.PASS and tlc is not None


def _sinusoid(eph: Ephemeris):
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=200.0, seed=8)
    lc.flux = lc.flux + 0.003 * np.sin(2 * np.pi * (lc.time - 1326.0) / 3.0)
    return leo_flux(lc, SUN, eph, [], np.zeros(len(lc.time), bool), DETREND, TRIAGE)


@pytest.mark.slow
def test_leo_sinusoid_is_false_alarm():
    # At the troughs, where the search puts the dip.
    result, outcome, _ = _sinusoid(Ephemeris(3.0, 1328.25, 0.4))
    assert result.outcome is Outcome.FAIL and outcome.disposition == "FA", outcome
    assert "sinusoidal" in outcome.fa_failed, outcome


@pytest.mark.slow
def test_leo_sinusoid_at_four_times_its_period_is_false_alarm():
    # A multiple the search's harmonic exclusion leaves open (decision 0008): the fold shows three
    # other troughs as deep as the one under test. 6 h is within the search's duration bound at 12 d.
    result, outcome, _ = _sinusoid(Ephemeris(12.0, 1328.25, 0.25))
    assert result.outcome is Outcome.FAIL and outcome.disposition == "FA", outcome
    assert "non_unique" in outcome.fa_failed, outcome


def _eclipsing_binary(primary: float, secondary: float):
    # Primary and secondary of unequal depth, searched at half the binary period.
    lc = make_lc(
        sectors=(1, 2, 3),
        noise_ppm=200.0,
        seed=9,
        signals=[(6.0, 1326.0, 0.12, primary), (6.0, 1329.0, 0.12, secondary)],
    )
    return leo_flux(
        lc, SUN, Ephemeris(3.0, 1326.0, 0.12), [], np.zeros(len(lc.time), bool), DETREND, TRIAGE
    )


@pytest.mark.slow
def test_leo_eclipsing_binary_at_twice_the_period_is_a_false_positive():
    result, outcome, _ = _eclipsing_binary(0.003, 0.0015)
    assert result.outcome is Outcome.FAIL, outcome
    assert outcome.disposition == "FP" and "odd_even" in outcome.fp_failed, outcome


@pytest.mark.slow
def test_leo_deep_eclipsing_binary_is_a_false_alarm_on_its_individual_transits():
    # Every transit, deeper or shallower than the mean, fits LEO-Vetter's one transit model badly, so
    # all are dropped as bad transits before the false-positive tests run.
    result, outcome, _ = _eclipsing_binary(0.010, 0.004)
    assert result.outcome is Outcome.FAIL, outcome
    assert outcome.disposition == "FA" and outcome.fa_failed == ["invalid_transits"], outcome
