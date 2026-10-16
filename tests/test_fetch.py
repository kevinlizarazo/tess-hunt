from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from astropy.io import fits
from fakes import FakeSession

from tess_hunt.fetch import fetch_star, read_product, timing_suspect
from tess_hunt.lightcurve import LightCurve
from tess_hunt.mast import MAST_API, PRODUCT_COLUMNS, S3_BASE

FIX = Path(__file__).parent / "fixtures"
QLP = FIX / "hlsp_qlp_tess_ffi_s0001-0000000261136679_tess_v01_llc.fits"
TSPOC = FIX / "hlsp_tess-spoc_tess_phot_0000000261136679-s0001_tess_v1_lc.fits"
TIC = 261136679

FETCH = {
    "min_good_cadences": 100,
    "timing_suspect": [
        {"provenance": "QLP", "sectors": [99, 100, 101, 102, 103, 104], "version": "v01"}
    ],
}
LATE_QLP = "hlsp_qlp_tess_ffi_s0100-0000000261136679_tess_v01_llc.fits"


def products(with_spoc=True) -> pd.DataFrame:
    rows = [
        (TIC, 1, "TESS-SPOC", 1800.0, TSPOC.name, "u2", TSPOC.stat().st_size, "k/tspoc"),
        (TIC, 1, "QLP", 1800.0, QLP.name, "u3", QLP.stat().st_size, "k/qlp"),
    ]
    if with_spoc:
        rows.insert(0, (TIC, 1, "SPOC", 120.0, "tess-s0001-spoc_lc.fits", "u1", 10, "k/spoc"))
    return pd.DataFrame(rows, columns=PRODUCT_COLUMNS)


def routes() -> dict:
    return {S3_BASE + "k/tspoc": TSPOC.read_bytes(), S3_BASE + "k/qlp": QLP.read_bytes()}


def test_read_qlp_drops_flagged_cadences():
    time, flux, err, facts = read_product(QLP, "QLP")
    assert 900 < len(time) < 1281  # 288 of 1281 cadences carry a QLP quality flag
    assert abs(np.median(flux) - 1.0) < 1e-9
    assert np.all(err > 0) and np.all(np.diff(time) > 0)
    assert facts == {}


def test_read_tess_spoc_keeps_crowding():
    time, flux, err, facts = read_product(TSPOC, "TESS-SPOC")
    assert 1100 < len(time) <= 1282
    assert abs(np.median(flux) - 1.0) < 1e-9
    assert 0.99 < facts["crowdsap"] <= 1.0


def test_fetch_falls_back_when_best_missing(tmp_path):
    entry = fetch_star(TIC, products(), tmp_path, FETCH, session=FakeSession(routes()))
    assert entry["status"] == "ok" and entry["sectors"] == [1]
    assert entry["problems"]["1"][0].startswith("SPOC")
    lc = LightCurve.load(tmp_path / f"{TIC}.npz")
    assert lc.sources["1"]["provenance"] == "TESS-SPOC"
    assert lc.sources["1"]["cadence_s"] == 1800.0
    assert len(lc.sources["1"]["sha256"]) == 64
    assert entry["sources"]["1"]["s3_key"] == "k/tspoc"
    assert len(entry["sources"]["1"]["sha256"]) == 64


def test_fetch_falls_back_when_best_unreadable(tmp_path):
    served = routes() | {S3_BASE + "k/spoc": b"0123456789"}
    entry = fetch_star(TIC, products(), tmp_path, FETCH, session=FakeSession(served))
    assert entry["status"] == "ok"
    assert entry["sources"]["1"]["provenance"] == "TESS-SPOC"
    assert entry["problems"]["1"][0].startswith("SPOC: unreadable (")


def test_fetch_records_empty_and_writes_nothing(tmp_path):
    entry = fetch_star(TIC, products(), tmp_path, FETCH, session=FakeSession())
    assert entry["status"] == "empty"
    assert list(tmp_path.iterdir()) == []


def test_fetch_skips_sector_with_too_few_good_cadences(tmp_path):
    entry = fetch_star(
        TIC,
        products(),
        tmp_path,
        {**FETCH, "min_good_cadences": 5000},
        session=FakeSession(routes()),
    )
    assert entry["status"] == "empty"
    assert any("good cadences" in p for p in entry["problems"]["1"])


def test_fetch_uses_cache_when_sources_unchanged(tmp_path):
    fetch_star(TIC, products(with_spoc=False), tmp_path, FETCH, session=FakeSession(routes()))
    session = FakeSession()
    entry = fetch_star(TIC, products(with_spoc=False), tmp_path, FETCH, session=session)
    assert entry["status"] == "cached" and session.urls == []
    assert entry["sources"]["1"]["s3_key"] == "k/tspoc"
    assert len(entry["sources"]["1"]["sha256"]) == 64


def test_empty_fetch_deletes_a_stale_light_curve(tmp_path):
    stale = make_stale(tmp_path)
    entry = fetch_star(TIC, products(), tmp_path, FETCH, session=FakeSession())
    assert entry["status"] == "empty" and not stale.exists()


def make_stale(tmp_path):
    lc = LightCurve(
        TIC,
        np.arange(5.0),
        np.ones(5),
        np.ones(5),
        np.full(5, 1, dtype=np.int16),
        {"1": {"s3_key": "old"}},
    )
    lc.save(tmp_path / f"{TIC}.npz")
    return tmp_path / f"{TIC}.npz"


def late_qlp_products(filename=LATE_QLP, key="k/qlp100", uri="u100") -> pd.DataFrame:
    return pd.DataFrame(
        [(TIC, 100, "QLP", 200.0, filename, uri, QLP.stat().st_size, key)], columns=PRODUCT_COLUMNS
    )


def test_fetch_falls_back_to_mast_api(tmp_path):
    session = FakeSession(routes={MAST_API + "u100": QLP.read_bytes()})
    entry = fetch_star(TIC, late_qlp_products(), tmp_path, FETCH, session=session)
    assert entry["status"] == "ok"
    assert entry["sources"]["100"]["route"] == "mast_api"


def test_qlp_v01_late_sectors_are_timing_suspect(tmp_path):
    session = FakeSession(routes={MAST_API + "u100": QLP.read_bytes()})
    fetch_star(TIC, late_qlp_products(), tmp_path, FETCH, session=session)
    lc = LightCurve.load(tmp_path / f"{TIC}.npz")
    assert lc.sources["100"]["timing_suspect"] is True
    assert (
        timing_suspect("QLP", 100, LATE_QLP.replace("v01", "v02"), FETCH["timing_suspect"]) is False
    )
    assert timing_suspect("QLP", 98, LATE_QLP, FETCH["timing_suspect"]) is False
    assert timing_suspect("TESS-SPOC", 100, LATE_QLP, FETCH["timing_suspect"]) is False


def test_unreadable_version_in_an_affected_sector_is_timing_suspect():
    unversioned = LATE_QLP.replace("_v01", "")
    assert timing_suspect("QLP", 100, unversioned, FETCH["timing_suspect"]) is True
    assert timing_suspect("QLP", 98, unversioned, FETCH["timing_suspect"]) is False
    assert timing_suspect("TESS-SPOC", 100, unversioned, FETCH["timing_suspect"]) is False


def test_new_product_key_refetches(tmp_path):
    first = FakeSession(routes={MAST_API + "u100": QLP.read_bytes()})
    fetch_star(TIC, late_qlp_products(), tmp_path, FETCH, session=first)
    v02 = LATE_QLP.replace("v01", "v02")
    second = FakeSession(routes={S3_BASE + "k/qlp100v2": QLP.read_bytes()})
    entry = fetch_star(
        TIC, late_qlp_products(v02, "k/qlp100v2", "u100v2"), tmp_path, FETCH, session=second
    )
    assert entry["status"] == "ok" and entry["sources"]["100"]["s3_key"] == "k/qlp100v2"
    assert LightCurve.load(tmp_path / f"{TIC}.npz").sources["100"]["timing_suspect"] is False


def test_cached_file_without_timing_flags_refetches(tmp_path):
    fetch_star(TIC, products(with_spoc=False), tmp_path, FETCH, session=FakeSession(routes()))
    old = LightCurve.load(tmp_path / f"{TIC}.npz")
    for info in old.sources.values():
        del info["route"], info["timing_suspect"]
    old.save(tmp_path / f"{TIC}.npz")
    entry = fetch_star(
        TIC, products(with_spoc=False), tmp_path, FETCH, session=FakeSession(routes())
    )
    assert entry["status"] == "ok"
    assert (
        entry["sources"]["1"]["route"] == "s3" and entry["sources"]["1"]["timing_suspect"] is False
    )


def test_all_nan_errors_become_scatter_errors(tmp_path):
    broken = tmp_path / QLP.name
    with fits.open(QLP) as hdul:
        for name in hdul[1].columns.names:
            if name.upper().endswith("_ERR"):
                hdul[1].data[name] = np.nan
        hdul.writeto(broken)
    time, flux, err, facts = read_product(broken, "QLP")
    assert facts["errors_from_scatter"] is True
    assert 900 < len(time) < 1281 and np.all(err > 0) and len(np.unique(err)) == 1


def test_production_fetch_refuses_an_unfinished_targets_run(tmp_path, monkeypatch):
    from tess_hunt.cli import main

    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    run = tmp_path / "targets-run"
    run.mkdir()
    pd.DataFrame({"tic": [TIC]}).to_parquet(run / "targets.parquet")
    (run / "provenance.json").write_text('{"ended_at": null}')
    monkeypatch.setattr(
        "tess_hunt.fetch.start_run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")),
    )
    with pytest.raises(SystemExit, match="not finished"):
        main(["fetch", "--targets", str(run / "targets.parquet"), "--production"])
