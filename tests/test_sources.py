import io

import numpy as np
import pandas as pd
import pytest
import requests
from fakes import FakeResponse, FakeSession

from tess_hunt import sources
from tess_hunt.catalogs import KNOWN_COLUMNS

TCE_CSV = """#Select Statistics Per TCE From the Data Validation XML Files
#Mission = TESS
#Search = tess2026221140108
#Sectors = s0107-s0107
#Created Date = 2026-10-02
#
tceid,ticid,tce_plnt_num,sectors,tce_period,tce_time0bt,tce_time0,tce_duration,tce_depth,tce_max_mult_ev
00000594723-01,594723,1,s0107,2.05161,4263.80,2461263.80,2.85378,16534.4,40.1
"""
EXOMINER_V1 = """TCE ID,TIC ID,Sector Run,Planet Number,ExoMiner Score,Orbital Period [day],Transit Duration [hour],Transit Epoch [BTJD],Transit Depth [ppm]
410153553-1-S1,410153553,1,1,0.983,0.463,0.504,1325.726,4712.385
"""
EXOMINER_V2 = """# Description: Vetting catalog
# Created: 2025-12-10 14:40:00
uid,target_id,tce_plnt_num,sector_run,tce_period,tce_duration,tce_time0bt,tce_depth,mean_score,model_label
219852584-1-S26,219852584,1,26,3.197055,3.629138,2011.857988,8000.7,0.99,PC
"""
INDEX_HTML = """<a href="tess2018206190142-s0001-s0001_dvr-tcestats.csv">x</a>
<a href="tess2026221140108-s0107-s0107_dvr-tcestats.csv">y</a> <a href="TCE_csv_description.txt">z</a>
<a href="new_versions/">n</a>"""


def test_spoc_tce_rows_are_tce_kind_in_btjd_and_days():
    out = sources.normalise_spoc_tce(pd.read_csv(io.StringIO(TCE_CSV), comment="#"), "s0107-s0107")
    row = out.iloc[0]
    assert list(out.columns) == KNOWN_COLUMNS and row["kind"] == "tce"
    assert row["tic"] == 594723 and row["t0"] == pytest.approx(4263.80)
    assert (
        row["duration"] == pytest.approx(2.85378 / 24)
        and row["name"] == "TCE s0107-s0107 00000594723-01"
    )
    assert np.isnan(row["ra"])


def test_tce_file_list_comes_from_the_index():
    assert sources.tce_files(INDEX_HTML) == [
        "tess2018206190142-s0001-s0001_dvr-tcestats.csv",
        "tess2026221140108-s0107-s0107_dvr-tcestats.csv",
    ]


def test_exominer_versions_normalise_alike():
    v1 = sources.normalise_exominer_v1(pd.read_csv(io.StringIO(EXOMINER_V1)))
    v2 = sources.normalise_exominer_v2(pd.read_csv(io.StringIO(EXOMINER_V2), comment="#"), "2-min")
    assert v1.iloc[0]["tic"] == 410153553 and v1.iloc[0]["duration"] == pytest.approx(0.504 / 24)
    assert v2.iloc[0]["tic"] == 219852584 and v2.iloc[0]["t0"] == pytest.approx(2011.857988)
    assert set(v1["kind"]) == set(v2["kind"]) == {"tce"}


def test_fill_positions_looks_up_only_missing_rows():
    known = pd.DataFrame(
        [
            {**dict.fromkeys(KNOWN_COLUMNS, np.nan), "tic": 1, "ra": 5.0, "dec": -5.0},
            {**dict.fromkeys(KNOWN_COLUMNS, np.nan), "tic": 2},
        ]
    )
    asked = []

    def lookup(tics):
        asked.extend(tics)
        return pd.DataFrame({"tic": [2], "ra": [7.0], "dec": [-7.0]})

    out = sources.fill_positions(known, lookup)
    assert asked == [2] and list(out["ra"]) == [5.0, 7.0]


def test_context_download_records_the_file(tmp_path):
    ctx = sources.Context(
        FakeSession(routes={"https://x/a.csv": b"a,b\n1,2\n"}), tmp_path / "raw", None
    )
    path = ctx.download("demo", "https://x/a.csv", "a.csv")
    assert path.read_bytes() == b"a,b\n1,2\n"
    entry = ctx.files[0]
    assert entry["source"] == "demo" and entry["bytes"] == 8 and len(entry["sha256"]) == 64
    assert entry["last_modified"].startswith("Mon")
    with pytest.raises(sources.SourceError, match="404"):
        ctx.download("demo", "https://x/missing.csv", "m.csv")


def test_fill_positions_keeps_its_positions_and_counts_the_tics_it_could_not_place(tmp_path):
    known = pd.DataFrame(
        [
            {**dict.fromkeys(KNOWN_COLUMNS, np.nan), "tic": 1, "ra": 5.0, "dec": -5.0},
            {**dict.fromkeys(KNOWN_COLUMNS, np.nan), "tic": 2},
            {**dict.fromkeys(KNOWN_COLUMNS, np.nan), "tic": 3},
            {**dict.fromkeys(KNOWN_COLUMNS, np.nan), "tic": 3},
        ]
    )
    ctx = sources.Context(FakeSession(), tmp_path / "raw", None)
    out = sources.fill_positions(
        known, lambda tics: pd.DataFrame({"tic": [2], "ra": [7.0], "dec": [-7.0]}), ctx=ctx
    )
    assert list(out["ra"].fillna(-1.0)) == [5.0, 7.0, -1.0, -1.0]
    assert ctx.unplaced_tics == 1
    kept = pd.read_parquet(tmp_path / "raw" / "TIC" / "tic_positions.parquet")
    assert list(kept["tic"]) == [2, 3] and list(kept["ra"].fillna(-1.0)) == [7.0, -1.0]
    assert [f["file"] for f in ctx.files] == ["TIC/tic_positions.parquet"]


def test_context_download_retries_server_errors(tmp_path):
    session = FakeSession(
        sequence=[FakeResponse(503), requests.ConnectionError("reset"), FakeResponse(200, b"ok")]
    )
    ctx = sources.Context(session, tmp_path, None, backoff=0)
    assert ctx.download("demo", "https://x/a.csv", "a.csv").read_bytes() == b"ok"
    assert len(session.urls) == 3


def test_context_download_gives_up_and_never_retries_a_404(tmp_path):
    down = FakeSession(sequence=[FakeResponse(503)] * 3)
    ctx = sources.Context(down, tmp_path, None, backoff=0)
    with pytest.raises(sources.SourceError, match="failed 3 times"):
        ctx.download("demo", "https://x/a.csv", "a.csv")
    missing = FakeSession()
    with pytest.raises(sources.SourceError, match="404"):
        sources.Context(missing, tmp_path, None, backoff=0).download(
            "demo", "https://x/b.csv", "b.csv"
        )
    assert len(missing.urls) == 1 and ctx.files == []


def test_tic_positions_batch_retry_and_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    asked, hiccups = [], [ConnectionError("MAST hiccup")]

    def query(ids):
        asked.append(list(ids))
        if hiccups:
            raise hiccups.pop()
        # TIC 9 is not in the TIC, so it never comes back.
        ids = [i for i in ids if i != 9]
        return pd.DataFrame({"tic": ids, "ra": [float(i) for i in ids], "dec": [-1.0] * len(ids)})

    out = sources.tic_positions([3, 1, 2, 2, 9], query=query, batch=2, backoff=0)
    assert asked == [[1, 2], [1, 2], [3, 9]]
    assert sorted(out["tic"]) == [1, 2, 3]
    asked.clear()
    again = sources.tic_positions([1, 4], query=query, batch=2, backoff=0)
    assert asked == [[4]] and sorted(again["tic"]) == [1, 4]


def test_tic_positions_give_up_after_attempts(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))

    def down(ids):
        raise ConnectionError("MAST is down")

    with pytest.raises(sources.SourceError, match="MAST is down"):
        sources.tic_positions([1], query=down, backoff=0)
