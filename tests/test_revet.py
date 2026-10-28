import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests
import test_fetch as tf
from fakes import FakeSession
from synthetic import make_lc

from tess_hunt.cli import main
from tess_hunt.fetch import fetch_star
from tess_hunt.lightcurve import LightCurve
from tess_hunt.mast import MAST_API
from tess_hunt.provenance import sha256_file
from tess_hunt.revet import merge

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "criteria" / "search-v2.toml"


def with_keys(lc: LightCurve, rows: dict) -> LightCurve:
    """Each sector's product as fetch records it: (provenance, s3 key, file contents, timing flag)."""
    for sector, (provenance, key, blob, suspect) in rows.items():
        lc.sources[str(sector)].update(
            provenance=provenance,
            s3_key=key,
            sha256=hashlib.sha256(blob.encode()).hexdigest(),
            timing_suspect=suspect,
        )
    return lc


def in_sector(lc: LightCurve, sector: int) -> tuple:
    part = lc.select(lc.sector == sector)
    return part.time, part.flux, part.flux_err


def test_merge_keeps_m2_sectors_and_takes_only_a_suspect_redelivery():
    base = with_keys(
        make_lc(sectors=(38, 64, 99, 100), seed=1, tic=7),
        {
            38: ("TESS-SPOC", "tess-spoc/s0038", "tess-spoc 38", False),
            64: ("SPOC", "spoc/s0064", "spoc 64", False),
            99: ("QLP", "qlp/s0099_v01", "qlp 99 v01", True),
            100: ("QLP", "qlp/s0100_v01", "qlp 100 v01", True),
        },
    )
    fresh = with_keys(
        make_lc(sectors=(38, 64, 99, 100, 112), seed=2, tic=7),
        {
            # A better product for an old sector, appearing after M2.
            38: ("SPOC", "spoc/s0038", "spoc 38", False),
            64: ("SPOC", "spoc/s0064", "spoc 64", False),
            99: ("QLP", "qlp/s0099_v02", "qlp 99 v02", False),
            # Replaced in place and still suspect: not a redelivery.
            100: ("QLP", "qlp/s0100_v01", "qlp 100 v01 again", True),
            112: ("SPOC", "spoc/s0112", "spoc 112", False),
        },
    )
    merged, record = merge(base, fresh)

    assert {s: r["status"] for s, r in record.items()} == {
        "38": "kept_m2",
        "64": "kept",
        "99": "redelivered",
        "100": "kept_m2",
        "112": "added",
    }
    for sector, source in ((38, base), (64, base), (99, fresh), (100, base), (112, fresh)):
        got, want = in_sector(merged, sector), in_sector(source, sector)
        assert all(np.array_equal(g, w) for g, w in zip(got, want, strict=True)), sector
        assert merged.sources[str(sector)] == source.sources[str(sector)], sector
    assert list(merged.sources) == ["38", "64", "99", "100", "112"]
    assert merged.tic == 7 and np.all(np.diff(merged.time) > 0)
    assert len(merged.time) == sum(len(in_sector(merged, s)[0]) for s in (38, 64, 99, 100, 112))

    def product(lc, sector):
        info = lc.sources[str(sector)]
        return {k: info[k] for k in ("provenance", "s3_key", "sha256", "timing_suspect")}

    assert record["38"] == {
        "status": "kept_m2",
        "base": product(base, 38),
        "fresh": product(fresh, 38),
    }
    assert record["99"]["base"] == product(base, 99)
    assert record["99"]["fresh"] == product(fresh, 99)
    assert record["100"]["base"]["sha256"] != record["100"]["fresh"]["sha256"]
    assert record["112"] == {"status": "added", "base": None, "fresh": product(fresh, 112)}


def revet_inputs(tmp_path: Path, monkeypatch, served: dict) -> tuple[Path, list[str]]:
    """M2's light curve of the fixture star in the shared cache (S1, TESS-SPOC), and `revet fetch`'s arguments for a
    products table that adds QLP S100."""
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    base_dir = tmp_path / "data" / "lc"
    fetch_star(
        tf.TIC,
        tf.products(with_spoc=False),
        base_dir,
        tf.FETCH,
        session=FakeSession(tf.routes()),
    )
    targets, table = tmp_path / "targets.parquet", tmp_path / "products.parquet"
    pd.DataFrame({"tic": [tf.TIC]}).to_parquet(targets)
    pd.concat([tf.products(with_spoc=False), tf.late_qlp_products()]).to_parquet(table)
    session = FakeSession(served)
    monkeypatch.setattr(requests, "Session", lambda: session)
    argv = [
        "revet",
        "fetch",
        *("--targets", str(targets)),
        *("--products", str(table)),
        *("--base-lc-dir", str(base_dir)),
        *("--criteria", str(SEARCH)),
    ]
    return base_dir, argv


def only_run(tmp_path: Path) -> Path:
    [run] = (tmp_path / "data" / "runs").glob("*-revet-fetch-*")
    return run


def test_revet_fetch_never_writes_the_base(tmp_path, monkeypatch):
    served = tf.routes() | {MAST_API + "u100": tf.QLP.read_bytes()}
    base_dir, argv = revet_inputs(tmp_path, monkeypatch, served)
    base = base_dir / f"{tf.TIC}.npz"
    before = base.read_bytes(), base.stat().st_mtime_ns

    assert main(argv) == 0
    assert (base.read_bytes(), base.stat().st_mtime_ns) == before
    assert list(base_dir.iterdir()) == [base]

    run = only_run(tmp_path)
    written = run / "lc" / f"{tf.TIC}.npz"
    merged, m2 = LightCurve.load(written), LightCurve.load(base)
    assert sorted(merged.sources) == ["1", "100"]
    assert merged.sources["1"] == m2.sources["1"]
    assert np.array_equal(merged.select(merged.sector == 1).flux, m2.flux)
    assert merged.sources["100"]["timing_suspect"] is True

    record = json.loads((run / "merge.json").read_text())[str(tf.TIC)]
    assert {s: r["status"] for s, r in record["sectors"].items()} == {"1": "kept", "100": "added"}
    assert record["base_sha256"] == sha256_file(base)
    assert record["lc_sha256"] == sha256_file(written)
    assert record["fetch"] == {"status": "ok", "problems": {}}
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["ended_at"] is not None
    assert provenance["inputs"][f"base_light_curve_{tf.TIC}"]["sha256"] == sha256_file(base)


def test_revet_fetch_refuses_a_star_without_a_base(tmp_path, monkeypatch):
    base_dir, argv = revet_inputs(tmp_path, monkeypatch, {})
    (base_dir / f"{tf.TIC}.npz").unlink()
    with pytest.raises(SystemExit, match=f"no light curve for TIC {tf.TIC}"):
        main(argv)
    assert not list((tmp_path / "data" / "runs").glob("*-revet-fetch-*"))


def test_revet_fetch_writes_no_light_curve_for_a_star_it_fetched_nothing_for(tmp_path, monkeypatch):
    base_dir, argv = revet_inputs(tmp_path, monkeypatch, {})

    assert main(argv) == 1
    run = only_run(tmp_path)
    assert not (run / "lc" / f"{tf.TIC}.npz").exists()
    record = json.loads((run / "merge.json").read_text())[str(tf.TIC)]
    assert record["fetch"]["status"] == "empty" and record["fetch"]["problems"]
    assert record["lc_sha256"] is None and record["sectors"] is None
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["summary"]["failed"] == [tf.TIC]
