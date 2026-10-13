import gzip
import io
import json
import zipfile

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


def header_only(text: str) -> bytes:
    return "".join(text.splitlines(keepends=True)[:-1]).encode()


def test_an_empty_tce_file_fails_the_source(tmp_path):
    first, last = sources.tce_files(INDEX_HTML)
    routes = {
        sources.TCE_INDEX: INDEX_HTML.encode(),
        sources.TCE_INDEX + first: TCE_CSV.encode(),
        sources.TCE_INDEX + last: TCE_CSV.encode(),
    }
    out = sources.fetch_spoc_tce(sources.Context(FakeSession(routes), tmp_path / "full", None))
    assert [n.split()[1] for n in out["name"]] == ["s0001-s0001", "s0107-s0107"]
    routes[sources.TCE_INDEX + last] = header_only(TCE_CSV)
    with pytest.raises(sources.SourceError, match=f"{last} has no rows"):
        sources.fetch_spoc_tce(sources.Context(FakeSession(routes), tmp_path / "empty", None))


def test_an_empty_exominer_file_fails_the_source(tmp_path):
    record, name = sources.EXOMINER_V1
    v1 = sources.ZENODO_FILE.format(record=record, name=name)
    record, (two_min, ffi) = sources.EXOMINER_V2
    v2 = [sources.ZENODO_FILE.format(record=record, name=n) for n in (two_min, ffi)]
    routes = {v1: EXOMINER_V1.encode(), v2[0]: EXOMINER_V2.encode(), v2[1]: EXOMINER_V2.encode()}
    out = sources.fetch_exominer(sources.Context(FakeSession(routes), tmp_path / "full", None))
    assert list(out["source"]) == ["ExoMiner-v1", "ExoMiner-v2", "ExoMiner-v2"]
    routes[v2[1]] = header_only(EXOMINER_V2)
    with pytest.raises(sources.SourceError, match=f"{ffi} has no rows"):
        sources.fetch_exominer(sources.Context(FakeSession(routes), tmp_path / "empty", None))


def test_context_download_records_the_query_with_the_url(tmp_path):
    ctx = sources.Context(FakeSession(routes={"https://x/tap": b"a\n1\n"}), tmp_path, None)
    ctx.download("archive", "https://x/tap", "t.csv", {"query": "select a from t", "format": "csv"})
    assert ctx.files[0]["url"] == "https://x/tap?query=select+a+from+t&format=csv"


EUMEMIC_EPH = "TIC,tier,ra,dec,Tmag,period_d,period_err_d,T0_BJD_TDB,T0_err_min,duration_h,depth_ppm\n137499615,A,132.3,78.6,11.63,0.9919109,3.5e-06,2459606.43305,2.6,1.2,484\n"
EUMEMIC_ALLSKY = (
    "TIC,P_d,P_err,T0_BJD,T14_h,depth_ppm,tier\n270771873,2.331034,5e-06,2458519.55951,2.31,652,A\n"
)
EUMEMIC_TCE = "rank,period,t0,duration_h,bls_depth_ppm,tic\n1,12.761,1393.7675,1.34,488.2,3894266\n"
CAO = "# Table 1\n# t0_bjd = t0_mid_transit_bjd (BTJD) + 2457000.\ntic_id,dossier_name,period_days,t0_bjd,depth_ppm\n1006872,Dossier_1006872,9.733853,2458550.327331,6834.3\n"
RAVEN = "ticid,candidate,ra,dec,bls_per,bls_t0,bls_tdur,bls_depth\n17361,1,219.33,-24.95,3.6065,2336.301,1.4426,8986.4\n"
T16 = 'TICID\tP_med\tTc_med\tqtran\tra\tdec\n126747090\t4.5515\t1326.3306\t0.01185\t"315.95"\t"-46.94"\n'
# Zenodo 23289148 as published: CRLF lines, and an unquoted comma inside the depth's quantity name.
OZTURK = b"quantity,value,uncertainty,unit\r\nperiod,4.353304,0.000006,days\r\nmid-transit time (BJD_TDB),2459494.5967,0.0016,days\r\ntransit depth (model, fit B),1235,159,ppm\r\ntransit duration (fit B),1.46,0.09,hours\r\nplanet radius (fit B),2.49,0.16,Earth radii\r\nimpact parameter (fit B),0.82,0.06,\r\n"


def test_eumemic_files_normalise_with_kinds():
    tables = (pd.read_csv(io.StringIO(t)) for t in (EUMEMIC_EPH, EUMEMIC_ALLSKY, EUMEMIC_TCE))
    eph, allsky, tce = sources.normalise_eumemic(*tables, "abc123")
    assert (
        eph.iloc[0]["t0"] == pytest.approx(2459606.43305 - 2457000.0)
        and eph.iloc[0]["kind"] == "community"
    )
    assert allsky.iloc[0]["period"] == pytest.approx(2.331034)
    assert tce.iloc[0]["kind"] == "tce" and tce.iloc[0]["t0"] == pytest.approx(1393.7675)
    assert "abc123" in eph.iloc[0]["name"]


def test_cao_epochs_load_as_missing():
    out = sources.normalise_cao(pd.read_csv(io.StringIO(CAO), comment="#"))
    assert out.iloc[0]["tic"] == 1006872 and np.isnan(out.iloc[0]["t0"])


def test_raven_durations_are_hours():
    out = sources.normalise_raven(pd.read_csv(io.StringIO(RAVEN)))
    assert out.iloc[0]["duration"] == pytest.approx(1.4426 / 24) and out.iloc[0][
        "ra"
    ] == pytest.approx(219.33)


def test_t16_duration_from_qtran():
    out = sources.normalise_t16(pd.read_csv(io.StringIO(T16), sep="\t"))
    assert out.iloc[0]["duration"] == pytest.approx(0.01185 * 4.5515) and out.iloc[0][
        "dec"
    ] == pytest.approx(-46.94)


def test_durations_over_a_day_count_as_missing():
    table = pd.read_csv(io.StringIO(T16), sep="\t").assign(P_med=14.5, qtran=0.12)
    assert np.isnan(sources.normalise_t16(table).iloc[0]["duration"])


def test_record_parsers():
    flat = sources.parse_record(
        "flat_json",
        json.dumps(
            {
                "TIC": 156733696,
                "period_d": 1.817187,
                "t0_BJD_TDB": 2458468.48094,
                "duration_hr": 3.26,
                "depth_ppm": 465.6,
            }
        ).encode(),
    )
    assert flat[0]["tic"] == 156733696 and flat[0]["t0"] == pytest.approx(1468.48094)
    nested = sources.parse_record(
        "nested_json",
        json.dumps(
            {
                "name": "TIC 458191673.01",
                "host": {"tic": 458191673},
                "ephemeris": {"period_d": 2.5706872, "t0_bjd_tdb": 2458571.21248},
                "transit": {"duration_hr": 1.681, "depth_ppm": 802},
            }
        ).encode(),
    )
    assert nested[0]["period"] == pytest.approx(2.5706872)
    qv = sources.parse_record("quantity_value_csv", OZTURK, tic=257484419)
    assert qv[0]["period"] == pytest.approx(4.353304) and qv[0]["duration"] == pytest.approx(
        1.46 / 24
    )
    assert qv[0]["t0"] == pytest.approx(2494.5967) and qv[0]["depth_ppm"] == pytest.approx(1235)
    predicted = sources.parse_record(
        "predicted_csv",
        b"sector,epoch,mid_BJD_TDB,depth_ppm,duration_hr\n122,594,2461671.18018,279,1.59\n122,595,2461676.11371,279,1.59\n122,596,2461681.04725,279,1.59\n",
        tic=252721481,
    )
    assert predicted[0]["period"] == pytest.approx(4.93353, abs=1e-4)
    rab = sources.parse_record(
        "rabtsevich_json",
        json.dumps(
            {
                "A": {"P": 3.18278, "T0": 3998.7348, "T14": 0.0779},
                "B": {"P": 11.13275, "T0": 4000.8659, "T14": 0.0691},
            }
        ).encode(),
        tic=4206066,
    )
    assert [r["period"] for r in rab] == pytest.approx([3.18278, 11.13275])
    cert = sources.parse_record(
        "certificate_json",
        json.dumps(
            {
                "tic_id": 125757128,
                "primary_signal": {
                    "ephemeris": {
                        "period_d": 1.938344,
                        "t0_btjd": 2475.42348,
                        "duration_h": 3.36,
                        "bls_box_depth_ppm": 151.7,
                    }
                },
            }
        ).encode(),
    )
    assert cert[0]["t0"] == pytest.approx(2475.42348)


def test_eb_rows_match_on_period_only():
    prsa = sources.normalise_prsa(
        pd.DataFrame(
            {"tess_id": [1], "period": [2.5], "bjd0": [1544.16], "ra": [1.0], "dec": [2.0]}
        )
    )
    assert prsa.iloc[0]["kind"] == "eb" and prsa.iloc[0]["t0"] == pytest.approx(1544.16)
    gaia = sources.normalise_gaia_eb(
        pd.DataFrame({"tic": [5], "eb_frequency": [0.5], "eb_reference_time": [100.0]})
    )
    assert gaia.iloc[0]["period"] == pytest.approx(2.0) and np.isnan(gaia.iloc[0]["t0"])
    vsx = sources.normalise_vsx(
        pd.DataFrame(
            {
                "tic": [6, 7, 8],
                "Name": ["a", "b", "c"],
                "Type": ["EA", "EP", "ELL"],
                "Period": [3.0, 4.0, 5.0],
                "ra": [0.0] * 3,
                "dec": [0.0] * 3,
            }
        )
    )
    assert list(vsx["tic"]) == [6]


def test_vsx_keeps_eclipsing_types_only():
    # Real VSX types: eclipsing ones first, then ellipsoidal, EX Lupi eruptives, planets and the rest.
    types = [
        "E",
        "EA:",
        "EW",
        "EB|EW",
        "ESD|EC",
        "E-DO",
        "ELL",
        "ELL+SR",
        "EXOR",
        "EXOR:",
        "EP",
        "EP+ROT",
        "EP:",
        "ROT",
        "",
        None,
    ]
    table = pd.DataFrame(
        {
            "tic": range(len(types)),
            "Name": list("abcdefghijklmnop"),
            "Type": types,
            "Period": 1.0,
            "ra": 0.0,
            "dec": 0.0,
        }
    )
    assert list(sources.normalise_vsx(table)["tic"]) == [0, 1, 2, 3, 4, 5]


def test_sample_sources_need_a_targets_run(tmp_path):
    ctx = sources.Context(FakeSession(), tmp_path, None)
    with pytest.raises(sources.SourceError, match="--targets"):
        sources.fetch_gaia_eb(ctx)
    with pytest.raises(sources.SourceError, match="--targets"):
        sources.fetch_vsx(ctx)


def eumemic_routes(commit: str) -> dict:
    raw = f"https://raw.githubusercontent.com/{sources.EUMEMIC_REPO}/{commit}/"
    eph, allsky, tce = sources.EUMEMIC_FILES
    return {
        f"https://api.github.com/repos/{sources.EUMEMIC_REPO}/commits/main": json.dumps(
            {"sha": commit}
        ).encode(),
        raw + eph: EUMEMIC_EPH.encode(),
        raw + allsky: EUMEMIC_ALLSKY.encode(),
        raw + tce: gzip.compress(EUMEMIC_TCE.encode()),
    }


def test_an_empty_eumemic_file_fails_the_source(tmp_path):
    commit = "0123456789abcdef" * 2
    routes = eumemic_routes(commit)
    out = sources.fetch_eumemic(sources.Context(FakeSession(routes), tmp_path / "full", None))
    assert list(out["kind"]) == ["community", "community", "tce"]
    assert list(out["tic"]) == [137499615, 270771873, 3894266]
    allsky = f"https://raw.githubusercontent.com/{sources.EUMEMIC_REPO}/{commit}/{sources.EUMEMIC_FILES[1]}"
    routes[allsky] = header_only(EUMEMIC_ALLSKY)
    with pytest.raises(sources.SourceError, match="candidates_allsky.csv has no rows"):
        sources.fetch_eumemic(sources.Context(FakeSession(routes), tmp_path / "empty", None))


def zipped(member: str, content: dict) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(member, json.dumps(content))
    return archive.getvalue()


def test_records_fail_on_a_record_or_tree_without_rows(tmp_path, monkeypatch):
    records = [
        (1, "candidate.json", "flat_json", None),
        (2, "prereg.zip", "rabtsevich_json", 4206066),
    ]
    monkeypatch.setattr(sources, "RECORDS", records)
    repo, head = sources.TH0RGAL_REPO, "f" * 40
    tree_url = f"https://api.github.com/repos/{repo}/git/trees/{head}?recursive=1"
    certificate = "candidates/TIC-9/certificate.json"
    prereg = sources.ZENODO_FILE.format(record=2, name="prereg.zip")
    routes = {
        sources.ZENODO_FILE.format(record=1, name="candidate.json"): json.dumps(
            {
                "TIC": 7,
                "period_d": 1.8,
                "t0_BJD_TDB": 2458468.48,
                "duration_hr": 3.3,
                "depth_ppm": 466.0,
            }
        ).encode(),
        prereg: zipped(
            "prereg/ephemeris_final.json",
            {"note": "frozen", "A": {"P": 3.18, "T0": 3998.73, "T14": 0.078}},
        ),
        f"https://api.github.com/repos/{repo}/commits/main": json.dumps({"sha": head}).encode(),
        tree_url: json.dumps(
            {"truncated": False, "tree": [{"path": "README.md"}, {"path": certificate}]}
        ).encode(),
        f"https://raw.githubusercontent.com/{repo}/{head}/{certificate}": json.dumps(
            {
                "tic_id": 9,
                "primary_signal": {
                    "ephemeris": {
                        "period_d": 1.9,
                        "t0_btjd": 2475.4,
                        "duration_h": 3.4,
                        "bls_box_depth_ppm": 150.0,
                    }
                },
            }
        ).encode(),
    }
    out = sources.fetch_records(sources.Context(FakeSession(routes), tmp_path / "full", None))
    assert list(out["source"]) == ["zenodo-1", "zenodo-2", "th0rgal"] and list(out["tic"]) == [
        7,
        4206066,
        9,
    ]
    assert set(out["kind"]) == {"community"}
    no_signals = {**routes, prereg: zipped("prereg/ephemeris_final.json", {"note": "frozen"})}
    with pytest.raises(sources.SourceError, match="2_prereg.zip has no rows"):
        sources.fetch_records(sources.Context(FakeSession(no_signals), tmp_path / "record", None))
    no_certificates = {
        **routes,
        tree_url: json.dumps({"truncated": False, "tree": [{"path": "README.md"}]}).encode(),
    }
    with pytest.raises(sources.SourceError, match="no certificates"):
        sources.fetch_records(
            sources.Context(FakeSession(no_certificates), tmp_path / "tree", None)
        )
    truncated = {
        **routes,
        tree_url: json.dumps({"truncated": True, "tree": [{"path": certificate}]}).encode(),
    }
    with pytest.raises(sources.SourceError, match="truncated"):
        sources.fetch_records(sources.Context(FakeSession(truncated), tmp_path / "truncated", None))


def test_tess_eb_retries_vizier_and_refuses_an_empty_table(tmp_path, monkeypatch):
    calls = []

    def vizier(catalog, columns):
        calls.append(catalog)
        if len(calls) == 1:
            raise ConnectionError("VizieR hiccup")
        return pd.DataFrame({c: [7] if c == "TIC" else [1500.5] for c in columns})

    monkeypatch.setattr(sources, "_vizier", vizier)
    session = FakeSession(
        {sources.PRSA_URL: b"tess_id,period,bjd0,ra,dec\n1,2.5,1544.16,1.0,2.0\n"}
    )
    out = sources.fetch_tess_eb(sources.Context(session, tmp_path / "full", None, backoff=0))
    assert list(out["source"]) == [
        "Prsa2022",
        "J/ApJS/279/50/table3",
        "J/ApJS/279/50/table4",
        "J/ApJ/912/123/table2",
    ]
    assert set(out["kind"]) == {"eb"} and list(out["t0"][1:]) == [1500.5] * 3 and len(calls) == 4

    def table4_empty(catalog, columns):
        return (
            pd.DataFrame(columns=columns)
            if catalog.endswith("table4")
            else vizier(catalog, columns)
        )

    monkeypatch.setattr(sources, "_vizier", table4_empty)
    with pytest.raises(sources.SourceError, match="table4.csv has no rows"):
        sources.fetch_tess_eb(sources.Context(session, tmp_path / "empty", None, backoff=0))


def test_sample_sources_read_the_targets_run(tmp_path, monkeypatch):
    from astropy.table import Table
    from astroquery.xmatch import XMatch

    run = tmp_path / "20261013T000000Z-targets-abc1234-0000"
    run.mkdir()
    pd.DataFrame({"tic": [5], "eb_frequency": [0.25], "eb_reference_time": [100.0]}).to_parquet(
        run / "dr3_eb.parquet"
    )
    pd.DataFrame({"tic": [6, 7], "ra": [10.0, 20.0], "dec": [-5.0, -6.0]}).to_parquet(
        run / "targets.parquet"
    )
    hiccups = [ConnectionError("CDS hiccup")]

    def xmatch(**kwargs):
        if hiccups:
            raise hiccups.pop()
        assert kwargs["cat2"] == "vizier:B/vsx/vsx" and list(kwargs["cat1"]["tic"]) == [6, 7]
        return Table(
            {
                "angDist": [0.1, 0.2],
                "tic": [6, 7],
                "ra": [10.0, 20.0],
                "dec": [-5.0, -6.0],
                "Name": ["V1", "V2"],
                "Type": ["EA", "RRAB"],
                "Period": [1.5, 0.6],
            }
        )

    monkeypatch.setattr(XMatch, "query", xmatch)
    ctx = sources.Context(FakeSession(), tmp_path / "raw", run, backoff=0)
    gaia = sources.fetch_gaia_eb(ctx)
    vsx = sources.fetch_vsx(ctx)
    assert (
        list(gaia["period"]) == [4.0]
        and list(vsx["tic"]) == [6]
        and list(vsx["name"]) == ["VSX V1"]
    )
    assert [f["file"] for f in ctx.files] == ["Gaia-EB/dr3_eb.parquet", "VSX/xmatch.csv"]
    assert ctx.files[0]["url"] == f"targets run {run.name}"
