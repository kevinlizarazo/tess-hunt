import numpy as np
from synthetic import make_lc

from tess_hunt.ephemeris import transit_times_in_data
from tess_hunt.inject import draw, inject, semi_major_axis_rs
from tess_hunt.transit import a_rs_from_density, density_from_duration, light_curve


def test_semi_major_axis_for_the_earth():
    assert abs(semi_major_axis_rs(365.25, 1.0, 1.0) - 215.032) < 0.01


def test_density_and_kepler_agree_for_the_sun():
    assert abs(a_rs_from_density(1.408, 365.25) - 215.0) < 1.0


def test_density_from_duration_round_trips():
    # A central transit for a Sun-like density at P = 5 d lasts about 0.129 d.
    assert abs(density_from_duration(5.0, 0.1286) - 1.43) < 0.05


def test_central_transit_depth_without_limb_darkening():
    t = np.linspace(-0.2, 0.2, 2001)
    flux = light_curve(t, np.full(len(t), 120 / 86400), 0.0, 3.0, 0.1, 10.0, 0.0, 0.0, 0.0)
    assert abs((1 - flux.min()) - 0.01) < 1e-4


def test_long_exposure_smears_a_short_transit():
    t = np.linspace(-0.1, 0.1, 401)
    sharp = light_curve(t, np.full(len(t), 120 / 86400), 0.0, 1.0, 0.1, 6.0, 0.0, 0.4, 0.2)
    smeared = light_curve(t, np.full(len(t), 1800 / 86400), 0.0, 1.0, 0.1, 6.0, 0.0, 0.4, 0.2)
    assert smeared.min() > sharp.min()


def test_draw_respects_ranges_and_transit_count():
    lc = make_lc(sectors=(1, 2, 3))
    rng = np.random.default_rng(0)
    for _ in range(20):
        inj = draw(rng, lc.time, 1.0, 1.0, (1.0, 40.0), (0.5, 16.0), 3)
        assert 1.0 <= inj.period <= 40.0 and 0.5 <= inj.rp_rearth <= 16.0 and 0 <= inj.b <= 1
        assert len(transit_times_in_data(lc.time, inj.ephemeris())) >= 3


def test_draw_gives_none_when_baseline_too_short():
    assert (
        draw(np.random.default_rng(0), np.linspace(0, 2, 500), 1.0, 1.0, (1.0, 40.0), (1.0, 2.0), 3)
        is None
    )


def test_inject_multiplies_flux():
    lc = make_lc(sectors=(1,), noise_ppm=1.0)
    inj = draw(np.random.default_rng(1), lc.time, 1.0, 1.0, (2.0, 5.0), (10.0, 12.0), 3)
    injected = inject(lc, inj, (0.4, 0.2))
    assert injected.flux.min() < lc.flux.min() - 1e-3
    assert np.allclose(injected.flux_err, lc.flux_err)
