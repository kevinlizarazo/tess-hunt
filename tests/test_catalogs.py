import datetime as dt
import io
import json
from functools import partial

import numpy as np
import pandas as pd
import pytest
from fakes import FakeSession
from synthetic import ROOT, write_catalog_snapshot

from tess_hunt.catalogs import (
    ARCHIVE_URL,
    CTOI_URL,
    TOI_URL,
    CatalogError,
    known_ephemerides,
    load_known,
    normalise_archive,
    normalise_ctoi,
    normalise_toi,
    refresh,
    snapshot_inputs,
)
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.sources import SOURCES, Source, SourceError, tic_positions

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


def normalised_ctoi_with(column, value):
    df = pd.read_csv(io.StringIO(CTOI_CSV))
    df[column] = value
    return normalise_ctoi(df).iloc[0]


# MJD with 2457000 added, as some community uploads give it, and an epoch from the 1860s.
@pytest.mark.parametrize("bjd", [2514000.5, 2401426.781])
def test_ctoi_epoch_outside_window_is_missing(bjd):
    assert np.isnan(normalised_ctoi_with("Transit Epoch (BJD)", bjd)["t0"])


def test_old_archive_epoch_inside_window_is_kept():
    df = pd.read_csv(io.StringIO(ARCHIVE_CSV))
    df["pl_tranmid"] = 2440619.0
    assert normalise_archive(df).iloc[0]["t0"] == pytest.approx(-16381.0)


def test_ctoi_duration_over_a_day_is_missing():
    assert np.isnan(normalised_ctoi_with("Duration (hrs)", 378.5)["duration"])


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


def test_known_ephemerides_can_keep_only_mask_sources():
    known = pd.DataFrame(
        [
            {
                "source": "TOI",
                "name": "TOI-1.01",
                "tic": 1,
                "ra": 0.0,
                "dec": 0.0,
                "period": 3.0,
                "t0": 100.0,
                "duration": 0.1,
                "depth_ppm": 500.0,
            },
            {
                "source": "SPOC-TCE",
                "name": "t",
                "tic": 1,
                "ra": 0.0,
                "dec": 0.0,
                "period": 7.0,
                "t0": 101.0,
                "duration": 0.1,
                "depth_ppm": 500.0,
            },
        ]
    )
    ephs = known_ephemerides(known, 1, 0.25, sources=("TOI", "CTOI", "archive"))
    assert [e.period for e in ephs] == [3.0]


def test_snapshot_inputs_follow_the_snapshot_version(tmp_path):
    v1 = write_catalog_snapshot(tmp_path / "v1")
    assert snapshot_inputs(v1) == {
        name: v1 / name for name in ("toi.csv", "ctoi.csv", "pscomppars.csv")
    }
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "known.parquet").touch()
    assert snapshot_inputs(v2) == {
        "known": v2 / "known.parquet",
        "catalog_manifest": v2 / "manifest.json",
    }


NOW = dt.datetime(2026, 10, 13, 12, 0, 0, tzinfo=dt.UTC)


def fake_source(name, kind, rows=1, fail=False):
    def fetch(ctx):
        if fail:
            raise ConnectionError(f"{name} is down")
        ctx.download(name, f"https://x/{name}.csv", f"{name}.csv")
        return pd.DataFrame(
            [
                {
                    "source": name,
                    "kind": kind,
                    "name": f"{name}-{i}",
                    "tic": 100 + i,
                    "ra": 1.0,
                    "dec": 2.0,
                    "period": 3.0,
                    "t0": 100.0,
                    "duration": 0.1,
                    "depth_ppm": 500.0,
                }
                for i in range(rows)
            ]
        )

    return Source(name, kind, fetch)


def session_for(*names):
    return FakeSession(routes={f"https://x/{n}.csv": b"x\n" for n in names})


def test_refresh_writes_known_and_manifest(tmp_path):
    snap = refresh(
        tmp_path,
        session_for("a", "b"),
        sources=[fake_source("a", "planet"), fake_source("b", "tce", 2)],
        now=NOW,
    )
    assert snap.name == "2026-10-13T120000Z"
    known = load_known(snap)
    assert list(known["kind"]) == ["planet", "tce", "tce"]
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["sources"]["b"] == {"kinds": {"tce": 2}, "rows": 2}
    assert {f["file"] for f in manifest["files"]} == {"a/a.csv", "b/b.csv"}
    assert set(snapshot_inputs(snap)) == {"known", "catalog_manifest"}


def test_failed_source_leaves_no_snapshot(tmp_path):
    with pytest.raises(CatalogError, match="b is down"):
        refresh(
            tmp_path,
            session_for("a"),
            sources=[fake_source("a", "planet"), fake_source("b", "tce", fail=True)],
            now=NOW,
        )
    assert list(tmp_path.iterdir()) == []


def test_empty_source_fails_the_refresh(tmp_path):
    with pytest.raises(CatalogError, match="no rows"):
        refresh(tmp_path, session_for("a"), sources=[fake_source("a", "planet", rows=0)], now=NOW)
    assert list(tmp_path.iterdir()) == []


def test_manifest_counts_the_kinds_a_source_returns(tmp_path):
    def mixed(ctx):
        return fake_source("m", "tce", 3).fetch(ctx).assign(kind=["community", "tce", "tce"])

    snap = refresh(tmp_path, session_for("m"), sources=[Source("m", "community", mixed)], now=NOW)
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["sources"]["m"] == {"kinds": {"community": 1, "tce": 2}, "rows": 3}


def test_unknown_kind_fails_the_refresh(tmp_path):
    with pytest.raises(CatalogError, match="unknown kinds"):
        refresh(tmp_path, session_for("a"), sources=[fake_source("a", "confirmed")], now=NOW)
    assert list(tmp_path.iterdir()) == []


def test_refresh_never_overwrites(tmp_path):
    refresh(tmp_path, session_for("a"), sources=[fake_source("a", "planet")], now=NOW)
    with pytest.raises(CatalogError, match="exists"):
        refresh(tmp_path, session_for("a"), sources=[fake_source("a", "planet")], now=NOW)


def test_v1_snapshots_still_load_with_kinds(tmp_path):
    known = load_known(write_catalog_snapshot(tmp_path / "snap"))
    assert dict(zip(known["source"], known["kind"], strict=True)) == {
        "TOI": "candidate",
        "CTOI": "candidate",
        "archive": "planet",
    }
    assert set(snapshot_inputs(tmp_path / "snap")) == {"toi.csv", "ctoi.csv", "pscomppars.csv"}


M1_COLUMNS = ["source", "name", "tic", "ra", "dec", "period", "t0", "duration", "depth_ppm"]
MASK_SOURCES = tuple(load_criteria(ROOT / "criteria" / "search-v2.toml")["detrend"]["mask_sources"])
NAN = float("nan")
# Rows that exercise each M1 normaliser's conversions and bounds.
PIN_TOI = [
    {
        "TIC ID": 100,
        "TOI": 100.01,
        "RA": "12:00:00.0",
        "Dec": "-30:00:00.0",
        "Period (days)": 3.25,
        "Epoch (BJD)": 2459500.123456,
        "Duration (hours)": 2.5,
        "Depth (ppm)": 800.0,
    },
    {
        "TIC ID": 100,
        "TOI": 100.02,
        "RA": "12:00:00.0",
        "Dec": "-30:00:00.0",
        "Period (days)": 7.1,
        "Epoch (BJD)": 2459501.5,
        "Duration (hours)": NAN,
        "Depth (ppm)": 300.0,
    },
    {
        "TIC ID": 100,
        "TOI": 100.04,
        "RA": "12:00:00.0",
        "Dec": "-30:00:00.0",
        "Period (days)": NAN,
        "Epoch (BJD)": 2459502.0,
        "Duration (hours)": 1.0,
        "Depth (ppm)": 200.0,
    },
]
PIN_CTOI = [
    {
        "TIC ID": 100,
        "CTOI": 100.03,
        "RA": 180.0,
        "Dec": -30.0,
        "Period (days)": 11.0,
        "Transit Epoch (BJD)": 1500.25,
        "Duration (hrs)": 30.0,
        "Depth ppm": 400.0,
    },
    {
        "TIC ID": 200,
        "CTOI": 200.01,
        "RA": 181.0,
        "Dec": -31.0,
        "Period (days)": 5.0,
        "Transit Epoch (BJD)": 2514000.5,
        "Duration (hrs)": 3.0,
        "Depth ppm": 500.0,
    },
]
PIN_ARCHIVE = [
    {
        "pl_name": "Near b",
        "tic_id": "TIC 100",
        "pl_orbper": 3.25,
        "pl_tranmid": 2459500.123,
        "pl_trandep": 0.08,
        "pl_trandur": 2.5,
        "ra": 180.0,
        "dec": -30.0,
    },
    {
        "pl_name": "Old b",
        "tic_id": "TIC 200",
        "pl_orbper": 1.5,
        "pl_tranmid": 2440619.0,
        "pl_trandep": 1.2,
        "pl_trandur": 1.5,
        "ra": 181.0,
        "dec": -31.0,
    },
]
# What load_known and known_ephemerides(..., 0.25) gave for these rows at e4047f1, before kinds and v2
# snapshots. The search masks with them, outside its code hash, so they may not move.
PINNED_KNOWN = [
    ("TOI", "TOI-9001.01", 999001, 0.0, 80.0, 2.5, 2000.0, 0.08333333333333333, 1000.0),
    (
        "TOI",
        "TOI-100.01",
        100,
        179.99999999999997,
        -30.0,
        3.25,
        2500.1234559998848,
        0.10416666666666667,
        800.0,
    ),
    ("TOI", "TOI-100.02", 100, 179.99999999999997, -30.0, 7.1, 2501.5, NAN, 300.0),
    ("TOI", "TOI-100.04", 100, 179.99999999999997, -30.0, NAN, 2502.0, 0.041666666666666664, 200.0),
    ("CTOI", "CTOI-999002.01", 999002, 1.0, 80.0, 3.5, 2001.0, 0.08333333333333333, 900.0),
    ("CTOI", "CTOI-100.03", 100, 180.0, -30.0, 11.0, 1500.25, NAN, 400.0),
    ("CTOI", "CTOI-200.01", 200, 181.0, -31.0, 5.0, NAN, 0.125, 500.0),
    ("archive", "Far b", 999003, 2.0, 80.0, 4.5, 2002.0, 0.08333333333333333, 1000.0),
    ("archive", "Near b", 100, 180.0, -30.0, 3.25, 2500.123000000138, 0.10416666666666667, 800.0),
    ("archive", "Old b", 200, 181.0, -31.0, 1.5, -16381.0, 0.0625, 12000.0),
]
PINNED_EPHEMERIDES = {
    100: [
        (3.25, 2500.1234559998848, 0.10416666666666667),
        (7.1, 2501.5, 0.25),
        (11.0, 1500.25, 0.25),
        (3.25, 2500.123000000138, 0.10416666666666667),
    ],
    200: [(1.5, -16381.0, 0.0625)],
    999001: [(2.5, 2000.0, 0.08333333333333333)],
    999002: [(3.5, 2001.0, 0.08333333333333333)],
    999003: [(4.5, 2002.0, 0.08333333333333333)],
}


def ephemerides(known, sources):
    return {
        tic: [(e.period, e.t0, e.duration) for e in known_ephemerides(known, tic, 0.25, sources)]
        for tic in PINNED_EPHEMERIDES
    }


def test_m1_snapshots_load_and_mask_exactly_as_before(tmp_path):
    known = load_known(write_catalog_snapshot(tmp_path / "snap", PIN_TOI, PIN_CTOI, PIN_ARCHIVE))
    assert [c for c in known.columns if c != "kind"] == M1_COLUMNS
    pd.testing.assert_frame_equal(
        known[M1_COLUMNS], pd.DataFrame(PINNED_KNOWN, columns=M1_COLUMNS), check_exact=True
    )
    assert ephemerides(known, None) == ephemerides(known, MASK_SOURCES) == PINNED_EPHEMERIDES


def test_v2_snapshots_keep_m1_source_labels_and_masks(tmp_path):
    v1 = write_catalog_snapshot(tmp_path / "v1", PIN_TOI, PIN_CTOI, PIN_ARCHIVE)
    session = FakeSession(
        routes={
            TOI_URL: (v1 / "toi.csv").read_bytes(),
            CTOI_URL: (v1 / "ctoi.csv").read_bytes(),
            ARCHIVE_URL: (v1 / "pscomppars.csv").read_bytes(),
        }
    )
    m1_sources = [s for s in SOURCES if s.name in MASK_SOURCES]
    v2 = refresh(tmp_path / "catalogs", session, sources=m1_sources, now=NOW)
    known = load_known(v2)
    assert set(known["source"]) == set(MASK_SOURCES)
    pd.testing.assert_frame_equal(known, load_known(v1), check_exact=True)
    assert ephemerides(known, MASK_SOURCES) == PINNED_EPHEMERIDES


def without_positions(ctx):
    return fake_source("t", "tce", 2).fetch(ctx).assign(ra=np.nan, dec=np.nan)


def test_refresh_keeps_tic_positions_and_counts_the_tics_it_could_not_place(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tess_hunt.sources.tic_positions",
        lambda tics: pd.DataFrame({"tic": [100], "ra": [9.0], "dec": [8.0]}),
    )
    snap = refresh(
        tmp_path, session_for("t"), sources=[Source("t", "tce", without_positions)], now=NOW
    )
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["unplaced_tics"] == 1
    assert {f["file"] for f in manifest["files"]} == {"t/t.csv", "TIC/tic_positions.parquet"}
    assert list(load_known(snap)["ra"].fillna(-1.0)) == [9.0, -1.0]


def test_failed_tic_lookup_leaves_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))

    def down(ids):
        raise ConnectionError("MAST is down")

    monkeypatch.setattr(
        "tess_hunt.sources.tic_positions", partial(tic_positions, query=down, backoff=0)
    )
    root = tmp_path / "catalogs"
    with pytest.raises(SourceError, match="MAST is down"):
        refresh(root, session_for("t"), sources=[Source("t", "tce", without_positions)], now=NOW)
    assert list(root.iterdir()) == []


def test_cmd_refresh_reports_the_snapshot_it_wrote(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    sources = [fake_source("a", "planet"), fake_source("b", "tce", 2)]
    monkeypatch.setattr(
        "tess_hunt.catalogs.refresh",
        partial(refresh, session=session_for("a", "b"), sources=sources, now=NOW),
    )
    assert main(["catalogs", "refresh"]) == 0
    run = next((tmp_path / "data" / "runs").iterdir())
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["summary"] == {"snapshot": "2026-10-13T120000Z", "rows_a": 1, "rows_b": 2}
    assert set(provenance["inputs"]) == {"known", "catalog_manifest"}
    assert "b: 2 rows (tce 2)" in capsys.readouterr().out
