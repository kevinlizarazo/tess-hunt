import pandas as pd

from tess_hunt.targets import build_sample, covered, select_known

SAMPLE = {
    "teff_min": 5300.0,
    "teff_max": 6500.0,
    "tmag_max": 10.5,
    "logg_min": 4.0,
    "logg_max": 5.5,
    "min_sectors": 4,
    "recent_sector_min": 97,
    "recent_sector_max": 107,
}
SEARCH = {"period_min_days": 1.0, "period_max_days": 40.0}


def star(tic, teff=5800.0, tmag=9.0, logg=4.4, disposition=None):
    return {
        "tic": tic,
        "ra": 1.0,
        "dec": -70.0,
        "tmag": tmag,
        "teff": teff,
        "logg": logg,
        "rad": 1.0,
        "mass": 1.0,
        "rho": 1.0,
        "e_rho": 0.1,
        "contratio": 0.0,
        "gaia": "",
        "disposition": disposition,
    }


def test_covered_needs_count_and_recent_sector():
    assert covered([1, 2, 3, 97], SAMPLE)
    assert not covered([1, 2, 3], SAMPLE)
    assert not covered([97, 98, 99], SAMPLE)
    assert not covered([1, 2, 3, 96], SAMPLE)


def test_build_sample_filters_and_is_reproducible():
    stars = pd.DataFrame(
        [
            star(1),
            star(2, teff=5300.0),
            star(3, disposition="SPLIT"),
            star(4, tmag=11.0),
            star(5, logg=3.8),
            star(6),
            star(7),
            star(8),
        ]
    )
    sectors = {t: [1, 2, 3, 98] for t in range(1, 9)}
    sectors[6] = [1, 2, 3]
    out = build_sample(stars, sectors, SAMPLE, limit=0, seed=1)
    assert list(out["tic"]) == [1, 7, 8]
    assert out.loc[0, "sectors"] == "1,2,3,98"
    a = build_sample(stars, sectors, SAMPLE, limit=2, seed=1)
    b = build_sample(stars, sectors, SAMPLE, limit=2, seed=1)
    assert list(a["tic"]) == list(b["tic"]) and len(a) == 2


def test_build_sample_handles_no_survivors():
    stars = pd.DataFrame([star(1, teff=4000.0)])
    assert len(build_sample(stars, {1: [1, 2, 3, 98]}, SAMPLE, 0, 1)) == 0


def toi_row(
    toi, tic, disp="KP", teff=5800.0, tmag=9.0, logg=4.4, period=5.0, depth=500.0, snr=20.0
):
    return {
        "TIC ID": tic,
        "TOI": toi,
        "TFOPWG Disposition": disp,
        "TESS Mag": tmag,
        "Stellar Eff Temp (K)": teff,
        "Stellar log(g) (cm/s^2)": logg,
        "RA": "00:00:00",
        "Dec": "-70:00:00",
        "Period (days)": period,
        "Epoch (BJD)": 2459000.5,
        "Duration (hours)": 3.0,
        "Depth (ppm)": depth,
        "Planet SNR": snr,
        "Comments": "",
    }


def test_select_known_spreads_depths_and_forces_pi_men():
    toi = pd.DataFrame(
        [
            toi_row(1001.01, 11, depth=200.0, snr=8.0),
            toi_row(1002.01, 12, depth=800.0),
            toi_row(1003.01, 13, depth=3000.0),
            toi_row(1004.01, 14, disp="FP"),
            toi_row(1005.01, 15, teff=5000.0),
            toi_row(1006.01, 16, period=60.0),
            toi_row(1007.01, 17, depth=1500.0),
            toi_row(144.01, 261136679, depth=290.0),
        ]
    )
    sectors = {t: [1, 2, 3, 98] for t in (11, 12, 13, 14, 15, 16, 261136679)}
    out = select_known(toi, sectors, SAMPLE, SEARCH, count=3, required_snr=12.0)
    assert "144.01" in set(out["toi"])
    assert not {"1004.01", "1005.01", "1006.01", "1007.01"} & set(out["toi"])  # 1007 lacks coverage
    assert set(out["toi"]) == {"1001.01", "1003.01", "144.01"}
    assert not out.loc[out["toi"] == "1001.01", "required"].item()
    assert out.loc[out["toi"] == "1001.01", "t0"].item() == 2000.5
    assert out.loc[out["toi"] == "1001.01", "duration"].item() == 0.125
