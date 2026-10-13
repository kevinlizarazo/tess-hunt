import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from astropy.table import Table

from tess_hunt import targets as targets_module
from tess_hunt.cli import main
from tess_hunt.targets import (
    DEC_BANDS,
    TIC_FIELDS,
    TicQueryError,
    build_sample,
    covered,
    covered_sources,
    flame_cut,
    query_tic_band,
    sample_hosts,
    select_known,
)

ROOT = Path(__file__).resolve().parents[1]
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


def test_build_sample_pick_ignores_row_order():
    stars = pd.DataFrame([star(t) for t in range(1, 9)])
    sectors = {t: [1, 2, 3, 98] for t in range(1, 9)}
    a = build_sample(stars, sectors, SAMPLE, limit=3, seed=1)
    b = build_sample(stars.iloc[::-1], sectors, SAMPLE, limit=3, seed=1)
    assert list(a["tic"]) == list(b["tic"])


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


def test_sample_hosts_cuts_on_tic_values_and_keeps_forced():
    # ExoFOP's stellar values pass for all three; only the TIC frame decides.
    toi = pd.DataFrame([toi_row(1001.01, 11), toi_row(1002.01, 12), toi_row(144.01, 261136679)])
    stars = pd.DataFrame([star(11), star(12, logg=float("nan")), star(261136679, teff=4000.0)])
    out = sample_hosts(toi, stars, SAMPLE)
    assert sorted(f"{v:.2f}" for v in out["TOI"]) == ["1001.01", "144.01"]


def tic_table(n, dec=-70.0, start=1):
    """A TIC query result: TIC column names, values from star(), the errors as NaN."""
    rows = []
    for i in range(n):
        values = star(start + i)
        rows.append(
            {column: values.get(name, np.nan) for column, name in TIC_FIELDS.items()}
            | {"dec": dec, "GAIA": "1000", "disposition": ""}
        )
    return Table.from_pandas(pd.DataFrame(rows))


def test_bands_cover_the_sky_once():
    assert DEC_BANDS[0] == (-90.0, -80.0) and DEC_BANDS[-1] == (80.0, 90.0) and len(DEC_BANDS) == 18


def test_query_band_refuses_a_full_band():
    with pytest.raises(TicQueryError, match="split"):
        query_tic_band(SAMPLE, (-90.0, -80.0), query=lambda **kw: tic_table(3), row_cap=3)


def test_query_band_retries():
    calls = []

    def flaky(**kw):
        calls.append(kw["dec"])
        if len(calls) == 1:
            raise ConnectionError("MAST timeout")
        return tic_table(2)

    out = query_tic_band(SAMPLE, (-90.0, -80.0), query=flaky, backoff=0.0)
    assert len(out) == 2 and calls == [[-90.0, -80.0], [-90.0, -80.0]]


def test_flame_cut_keeps_missing_values():
    stars = pd.DataFrame({"logg_flame": [4.2, 3.9, np.nan]})
    assert list(flame_cut(stars, 4.0)) == [True, False, True]


def test_covered_sources_counts_fetched_sectors():
    assert covered_sources({"1": {}, "2": {}, "3": {}, "98": {}}, SAMPLE)
    assert not covered_sources({"1": {}, "2": {}, "3": {}, "4": {}}, SAMPLE)


def all_sky(tmp_path, monkeypatch, discover, resume=None):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    crit = tmp_path / "search.toml"
    crit.write_text((ROOT / "criteria" / "search-v2.toml").read_text())
    band_of = {band: i for i, band in enumerate(DEC_BANDS)}
    monkeypatch.setattr(
        targets_module,
        "query_tic_band",
        lambda sample, dec, **kw: targets_module._tic_frame(
            tic_table(1, dec=dec[0] + 5.0, start=100 + band_of[tuple(dec)])
        ),
    )
    monkeypatch.setattr(
        targets_module,
        "dr3_join",
        lambda stars, **kw: pd.DataFrame(
            {
                "tic": stars["tic"],
                "dr3_source_id": 1,
                "angular_distance": 0.1,
                "ruwe": 1.0,
                "logg_gspphot": 4.4,
                "mass_flame": 1.0,
                "radius_flame": 1.0,
                "logg_flame": 4.438,
                "eb_frequency": np.where(stars["tic"] == 101, 0.5, np.nan),
                "eb_reference_time": np.where(stars["tic"] == 101, 100.0, np.nan),
            }
        ),
    )
    monkeypatch.setattr(targets_module.mast, "discover", discover)
    argv = ["targets", "sample", "--all-sky", "--criteria", str(crit)]
    monkeypatch.chdir(ROOT)
    return main(argv + (["--resume", resume] if resume else []))


def products_for(tics):
    rows = [
        {
            "tic": t,
            "sector": s,
            "provenance": "QLP",
            "cadence_s": 200.0,
            "filename": f"{t}-{s}.fits",
            "data_uri": f"u{t}-{s}",
            "size": 1,
            "s3_key": f"k{t}-{s}",
        }
        for t in tics
        for s in (1, 2, 3, 98)
    ]
    return pd.DataFrame(rows, columns=targets_module.mast.PRODUCT_COLUMNS)


def latest_run(tmp_path):
    return sorted((tmp_path / "data" / "runs").iterdir())[-1]


def test_all_sky_writes_targets_products_and_eb(tmp_path, monkeypatch):
    assert all_sky(tmp_path, monkeypatch, lambda tics, **kw: products_for(tics)) == 0
    run = latest_run(tmp_path)
    targets = pd.read_parquet(run / "targets.parquet")
    assert len(targets) == 18 and {"ruwe", "logg_flame", "e_rad"} <= set(targets.columns)
    assert list(pd.read_parquet(run / "dr3_eb.parquet")["tic"]) == [101]
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert summary["complete"] and summary["covered"] == 18


def test_failed_batch_marks_run_incomplete(tmp_path, monkeypatch):
    def discover(tics, failed=None, **kw):
        if 100 in tics:
            failed.extend(tics)
            return products_for([])
        return products_for(tics)

    assert all_sky(tmp_path, monkeypatch, discover) == 1
    run = latest_run(tmp_path)
    assert json.loads((run / "provenance.json").read_text())["ended_at"] is None
    assert json.loads((run / "products" / "dec-90_-80.failed.json").read_text()) == [100]
    assert (
        all_sky(tmp_path, monkeypatch, lambda tics, **kw: products_for(tics), resume=run.name) == 0
    )
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert summary["covered"] == 18 and summary["complete"]


def test_resume_redoes_a_band_whose_failed_list_never_landed(tmp_path, monkeypatch):
    # A crash between a band's two checkpoint files must not drop the TICs that failed.
    def discover(tics, failed=None, **kw):
        if 100 in tics:
            failed.extend(tics)
            return products_for([])
        return products_for(tics)

    assert all_sky(tmp_path, monkeypatch, discover) == 1
    run = latest_run(tmp_path)
    (run / "products" / "dec-90_-80.failed.json").unlink()
    assert (
        all_sky(tmp_path, monkeypatch, lambda tics, **kw: products_for(tics), resume=run.name) == 0
    )
    assert json.loads((run / "provenance.json").read_text())["summary"]["covered"] == 18


def test_resume_skips_finished_bands(tmp_path, monkeypatch):
    seen = []

    def crash_on_band_five(tics, failed=None, **kw):
        seen.extend(tics)
        if 105 in tics:
            raise KeyboardInterrupt
        return products_for(tics)

    with pytest.raises(KeyboardInterrupt):
        all_sky(tmp_path, monkeypatch, crash_on_band_five)
    run_id = latest_run(tmp_path).name
    seen.clear()
    assert (
        all_sky(
            tmp_path,
            monkeypatch,
            lambda tics, **kw: seen.extend(tics) or products_for(tics),
            resume=run_id,
        )
        == 0
    )
    assert 100 not in seen and 105 in seen
    assert json.loads((tmp_path / "data" / "runs" / run_id / "provenance.json").read_text())[
        "summary"
    ]["complete"]
