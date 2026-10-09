from pathlib import Path

import numpy as np
import pandas as pd
from fakes import FakeSession

from tess_hunt.fetch import fetch_star, read_product
from tess_hunt.lightcurve import LightCurve
from tess_hunt.mast import PRODUCT_COLUMNS, S3_BASE

FIX = Path(__file__).parent / "fixtures"
QLP = FIX / "hlsp_qlp_tess_ffi_s0001-0000000261136679_tess_v01_llc.fits"
TSPOC = FIX / "hlsp_tess-spoc_tess_phot_0000000261136679-s0001_tess_v1_lc.fits"
TIC = 261136679


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
    entry = fetch_star(TIC, products(), tmp_path, min_good=100, session=FakeSession(routes()))
    assert entry["status"] == "ok" and entry["sectors"] == [1]
    assert entry["problems"]["1"][0].startswith("SPOC")
    lc = LightCurve.load(tmp_path / f"{TIC}.npz")
    assert lc.sources["1"]["provenance"] == "TESS-SPOC"
    assert lc.sources["1"]["cadence_s"] == 1800.0
    assert len(lc.sources["1"]["sha256"]) == 64


def test_fetch_records_empty_and_writes_nothing(tmp_path):
    entry = fetch_star(TIC, products(), tmp_path, min_good=100, session=FakeSession())
    assert entry["status"] == "empty"
    assert list(tmp_path.iterdir()) == []


def test_fetch_skips_sector_with_too_few_good_cadences(tmp_path):
    entry = fetch_star(TIC, products(), tmp_path, min_good=5000, session=FakeSession(routes()))
    assert entry["status"] == "empty"
    assert any("good cadences" in p for p in entry["problems"]["1"])


def test_fetch_uses_cache_when_sources_unchanged(tmp_path):
    fetch_star(TIC, products(with_spoc=False), tmp_path, 100, session=FakeSession(routes()))
    session = FakeSession()
    entry = fetch_star(TIC, products(with_spoc=False), tmp_path, 100, session=session)
    assert entry["status"] == "cached" and session.urls == []
