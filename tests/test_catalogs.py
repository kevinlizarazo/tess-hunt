import io

import numpy as np
import pandas as pd
import pytest
from synthetic import write_catalog_snapshot

from tess_hunt.catalogs import (
    CatalogError,
    known_ephemerides,
    load_known,
    normalise_archive,
    normalise_ctoi,
    normalise_toi,
)

TOI_CSV = (
    "TIC ID,TOI,RA,Dec,Period (days),Epoch (BJD),Duration (hours),Depth (ppm)\n"
    "231663901,101.01,21:14:56.88,-55:52:18.71,1.43037,2458326.009117,1.6166,18960.7\n"
)
CTOI_CSV = (
    "TIC ID,CTOI,RA,Dec,Transit Epoch (BJD),Period (days),Duration (hrs),Depth ppm\n"
    "17361,17361.01,219.336233,-24.958522,2458596.9598,3.60677,0.089,10036.0\n"
)
ARCHIVE_CSV = (
    "pl_name,tic_id,pl_orbper,pl_tranmid,pl_trandep,pl_trandur,ra,dec\n"
    "HAT-P-8 b,TIC 188876052,3.07634,2456052.75596,0.83,3.9016058,343.0414932,35.4471778\n"
)


def test_normalise_toi_converts_units():
    row = normalise_toi(pd.read_csv(io.StringIO(TOI_CSV))).iloc[0]
    assert row["name"] == "TOI-101.01" and row["tic"] == 231663901
    assert row["ra"] == pytest.approx(318.737, abs=1e-3)
    assert row["dec"] == pytest.approx(-55.87186, abs=1e-4)
    assert row["t0"] == pytest.approx(1326.009117)
    assert row["duration"] == pytest.approx(1.6166 / 24)


def test_normalise_ctoi():
    row = normalise_ctoi(pd.read_csv(io.StringIO(CTOI_CSV))).iloc[0]
    assert row["name"] == "CTOI-17361.01" and row["ra"] == pytest.approx(219.336233)
    assert row["t0"] == pytest.approx(1596.9598)


def test_normalise_archive_percent_depth_and_tic_string():
    row = normalise_archive(pd.read_csv(io.StringIO(ARCHIVE_CSV))).iloc[0]
    assert row["tic"] == 188876052
    assert row["depth_ppm"] == pytest.approx(8300.0)
    assert row["t0"] == pytest.approx(-947.24404)


def test_load_known_needs_all_three(tmp_path):
    snap = write_catalog_snapshot(tmp_path / "s")
    assert set(load_known(snap)["source"]) == {"TOI", "CTOI", "archive"}
    (snap / "ctoi.csv").unlink()
    with pytest.raises(CatalogError, match="ctoi.csv"):
        load_known(snap)


def test_load_known_rejects_empty_file(tmp_path):
    snap = write_catalog_snapshot(tmp_path / "s")
    header = (snap / "pscomppars.csv").read_text().splitlines()[0]
    (snap / "pscomppars.csv").write_text(header + "\n")
    with pytest.raises(CatalogError, match="empty"):
        load_known(snap)


def test_known_ephemerides_skip_rows_without_period_and_fill_duration():
    known = pd.DataFrame(
        [
            {
                "source": "TOI",
                "name": "a",
                "tic": 5,
                "ra": 0,
                "dec": 0,
                "period": 2.0,
                "t0": 10.0,
                "duration": np.nan,
                "depth_ppm": 1,
            },
            {
                "source": "TOI",
                "name": "b",
                "tic": 5,
                "ra": 0,
                "dec": 0,
                "period": np.nan,
                "t0": 10.0,
                "duration": 0.1,
                "depth_ppm": 1,
            },
            {
                "source": "TOI",
                "name": "c",
                "tic": 6,
                "ra": 0,
                "dec": 0,
                "period": 3.0,
                "t0": 10.0,
                "duration": 0.1,
                "depth_ppm": 1,
            },
        ]
    )
    ephs = known_ephemerides(known, 5, fallback_duration=0.25)
    assert len(ephs) == 1 and ephs[0].period == 2.0 and ephs[0].duration == 0.25
