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

from tess_hunt import revet
from tess_hunt.cli import main
from tess_hunt.fetch import fetch_star
from tess_hunt.lightcurve import LightCurve
from tess_hunt.mast import MAST_API, PRODUCT_COLUMNS, S3_BASE
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
        make_lc(sectors=(38, 64, 99, 100, 101), seed=1, tic=7),
        {
            38: ("TESS-SPOC", "tess-spoc/s0038", "tess-spoc 38", False),
            64: ("SPOC", "spoc/s0064", "spoc 64", False),
            99: ("QLP", "qlp/s0099_v01", "qlp 99 v01", True),
            100: ("QLP", "qlp/s0100_v01", "qlp 100 v01", True),
            101: ("QLP", "qlp/s0101_v01", "qlp 101 v01", True),
        },
    )
    fresh = with_keys(
        make_lc(sectors=(38, 64, 99, 100, 101, 112), seed=2, tic=7),
        {
            # A better product for an old sector, appearing after M2.
            38: ("SPOC", "spoc/s0038", "spoc 38", False),
            64: ("SPOC", "spoc/s0064", "spoc 64", False),
            99: ("QLP", "qlp/s0099_v02", "qlp 99 v02", False),
            # Replaced in place and still suspect: not a redelivery.
            100: ("QLP", "qlp/s0100_v01", "qlp 100 v01 again", True),
            # Another product over a suspect sector (TESS-SPOC reaching past S85) is no redelivery either.
            101: ("TESS-SPOC", "tess-spoc/s0101", "tess-spoc 101", False),
            112: ("SPOC", "spoc/s0112", "spoc 112", False),
        },
    )
    merged, record = merge(base, fresh, sorted(base.sources, key=int))

    assert {s: r["status"] for s, r in record.items()} == {
        "38": "kept_m2",
        "64": "kept",
        "99": "redelivered",
        "100": "kept_m2",
        "101": "kept_m2",
        "112": "added",
    }
    taken = ((38, base), (64, base), (99, fresh), (100, base), (101, base), (112, fresh))
    for sector, source in taken:
        got, want = in_sector(merged, sector), in_sector(source, sector)
        assert all(np.array_equal(g, w) for g, w in zip(got, want, strict=True)), sector
        assert merged.sources[str(sector)] == source.sources[str(sector)], sector
    assert list(merged.sources) == ["38", "64", "99", "100", "101", "112"]
    assert merged.tic == 7 and np.all(np.diff(merged.time) > 0)
    assert len(merged.time) == sum(len(in_sector(merged, s)[0]) for s, _ in taken)

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


def test_merge_takes_a_better_product_only_for_a_sector_an_earlier_revet_added():
    m3 = with_keys(
        make_lc(sectors=(38, 99), seed=1, tic=7),
        {
            38: ("TESS-SPOC", "tess-spoc/s0038", "tess-spoc 38", False),
            99: ("QLP", "qlp/s0099_v01", "qlp 99 v01", True),
        },
    )
    m2 = sorted(m3.sources, key=int)
    # r2: QLP is the only product for S112 so far, and SPOC 2-min has reached S38.
    r2_fresh = with_keys(
        make_lc(sectors=(38, 99, 112, 113, 114), seed=2, tic=7),
        {
            38: ("SPOC", "spoc/s0038", "spoc 38", False),
            99: ("QLP", "qlp/s0099_v01", "qlp 99 v01", True),
            112: ("QLP", "qlp/s0112_v01", "qlp 112", False),
            113: ("TESS-SPOC", "tess-spoc/s0113", "tess-spoc 113", False),
            114: ("QLP", "qlp/s0114_v01", "qlp 114", False),
        },
    )
    r2, record = merge(m3, r2_fresh, m2)
    assert {s: r["status"] for s, r in record.items()} == {
        "38": "kept_m2",
        "99": "kept",
        "112": "added",
        "113": "added",
        "114": "added",
    }
    # r3: SPOC 2-min data for S112 have landed; S113's SPOC file failed, so fetch fell back to QLP; S114's TESS-SPOC
    # file is timing-suspect.
    r3_fresh = with_keys(
        make_lc(sectors=(38, 99, 112, 113, 114), seed=3, tic=7),
        {
            38: ("SPOC", "spoc/s0038", "spoc 38", False),
            99: ("QLP", "qlp/s0099_v01", "qlp 99 v01", True),
            112: ("SPOC", "spoc/s0112", "spoc 112", False),
            113: ("QLP", "qlp/s0113_v01", "qlp 113", False),
            114: ("TESS-SPOC", "tess-spoc/s0114", "tess-spoc 114", True),
        },
    )
    r3, record = merge(r2, r3_fresh, m2)
    assert {s: r["status"] for s, r in record.items()} == {
        # M2's sector keeps its rule: a better product appearing later is not taken.
        "38": "kept_m2",
        "99": "kept",
        "112": "upgraded",
        "113": "kept_earlier",
        "114": "kept_earlier",
    }
    taken = ((38, m3), (99, m3), (112, r3_fresh), (113, r2_fresh), (114, r2_fresh))
    for sector, source in taken:
        got, want = in_sector(r3, sector), in_sector(source, sector)
        assert all(np.array_equal(g, w) for g, w in zip(got, want, strict=True)), sector
        assert r3.sources[str(sector)] == source.sources[str(sector)], sector
    assert record["112"]["base"]["provenance"] == "QLP"
    assert record["112"]["fresh"]["provenance"] == "SPOC"


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
    assert record["unfetched"] == ["1", "100"]
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["summary"]["failed"] == [tf.TIC]


def test_revet_fetch_fails_a_star_it_got_no_new_sector_for(tmp_path, monkeypatch, capsys):
    # MAST lists QLP S100, but its file never comes: the fetch gets S1 again, which M2's light curve already holds.
    _, argv = revet_inputs(tmp_path, monkeypatch, tf.routes())

    assert main(argv) == 1
    run = only_run(tmp_path)
    assert not (run / "lc" / f"{tf.TIC}.npz").exists()
    record = json.loads((run / "merge.json").read_text())[str(tf.TIC)]
    assert record["fetch"]["status"] == "ok" and list(record["fetch"]["problems"]) == ["100"]
    assert {s: r["status"] for s, r in record["sectors"].items()} == {"1": "kept"}
    assert record["lc_sha256"] is None and record["unfetched"] == ["100"]
    assert json.loads((run / "provenance.json").read_text())["summary"]["failed"] == [tf.TIC]
    out = capsys.readouterr().out
    assert f"TIC {tf.TIC}: no sector added, redelivered or upgraded" in out and "S100" in out


def test_revet_fetch_names_the_sectors_a_merged_star_got_no_file_for(tmp_path, monkeypatch, capsys):
    # S100 comes; S101, listed beside it, never does.
    served = tf.routes() | {MAST_API + "u100": tf.QLP.read_bytes()}
    _, argv = revet_inputs(tmp_path, monkeypatch, served)
    table = tmp_path / "products.parquet"
    s101 = tf.late_qlp_products(key="k/qlp101", uri="u101").assign(sector=101)
    pd.concat([pd.read_parquet(table), s101]).to_parquet(table)

    assert main(argv) == 0
    record = json.loads((only_run(tmp_path) / "merge.json").read_text())[str(tf.TIC)]
    assert record["lc_sha256"] is not None and record["unfetched"] == ["101"]
    out = capsys.readouterr().out
    assert f"TIC {tf.TIC}: merged, but sectors fetched with problems and no file: S101" in out


@pytest.mark.parametrize("without", ["[[fetch.timing_suspect]]", "[fetch]"])
def test_revet_fetch_refuses_fetch_criteria_without_timing_rules(tmp_path, monkeypatch, without):
    _, argv = revet_inputs(tmp_path, monkeypatch, {})
    text = SEARCH.read_text()
    rules = text[text.index(without) : text.index("[detrend]")]
    path = tmp_path / "search-no-timing-rules.toml"
    path.write_text(text.replace(rules, ""))
    argv[argv.index(str(SEARCH))] = str(path)
    # Every fresh product would read as clean, and a suspect one delivered again as a redelivery.
    with pytest.raises(SystemExit, match=r"no \[\[fetch.timing_suspect\]\] rules"):
        main(argv)
    assert not list((tmp_path / "data" / "runs").glob("*-revet-fetch-*"))


def rewrite(path: Path) -> None:
    lc = LightCurve.load(path)
    lc.flux = lc.flux * 1.01
    lc.save(path)


def test_revet_fetch_merges_the_base_it_recorded(tmp_path, monkeypatch):
    served = tf.routes() | {MAST_API + "u100": tf.QLP.read_bytes()}
    base_dir, argv = revet_inputs(tmp_path, monkeypatch, served)
    base = base_dir / f"{tf.TIC}.npz"
    m2 = LightCurve.load(base)
    fetch_star = revet.fetch.fetch_star

    def rewrites_the_base(*args, **kwargs):
        # Another stage rewrites the shared cache while the fetch runs.
        rewrite(base)
        return fetch_star(*args, **kwargs)

    monkeypatch.setattr(revet.fetch, "fetch_star", rewrites_the_base)
    assert main(argv) == 0
    run = only_run(tmp_path)
    merged = LightCurve.load(run / "lc" / f"{tf.TIC}.npz")
    assert np.array_equal(merged.select(merged.sector == 1).flux, m2.flux)
    inputs = json.loads((run / "provenance.json").read_text())["inputs"]
    record = json.loads((run / "merge.json").read_text())[str(tf.TIC)]
    assert record["base_sha256"] == inputs[f"base_light_curve_{tf.TIC}"]["sha256"]


def test_revet_fetch_refuses_a_base_rewritten_after_it_was_recorded(tmp_path, monkeypatch):
    served = tf.routes() | {MAST_API + "u100": tf.QLP.read_bytes()}
    base_dir, argv = revet_inputs(tmp_path, monkeypatch, served)
    session = FakeSession(served)

    def rewrites_then_serves():
        # The run has recorded every star's base by now, and fetched nothing yet.
        rewrite(base_dir / f"{tf.TIC}.npz")
        return session

    monkeypatch.setattr(requests, "Session", rewrites_then_serves)
    with pytest.raises(SystemExit, match=f"light curve for TIC {tf.TIC} in --base-lc-dir changed"):
        main(argv)
    assert not (only_run(tmp_path) / "lc").exists()


def product_row(sector: int, provenance: str, fixture: Path, key: str) -> tuple:
    names = {
        "QLP": f"hlsp_qlp_tess_ffi_s{sector:04d}-{tf.TIC:016d}_tess_v01_llc.fits",
        "TESS-SPOC": f"hlsp_tess-spoc_tess_phot_{tf.TIC:016d}-s{sector:04d}_tess_v1_lc.fits",
    }
    size = fixture.stat().st_size
    return (tf.TIC, sector, provenance, 1800.0, names[provenance], f"u-{key}", size, key)


def revet_fetch(tmp_path: Path, base_dir: Path, rows: list[tuple]) -> Path:
    """A revet fetch run onto `base_dir` from a products table of `rows`."""
    targets, table = tmp_path / "targets.parquet", tmp_path / "products.parquet"
    pd.DataFrame({"tic": [tf.TIC]}).to_parquet(targets)
    pd.DataFrame(rows, columns=PRODUCT_COLUMNS).to_parquet(table)
    before = set((tmp_path / "data" / "runs").glob("*-revet-fetch-*"))
    argv = [
        *("revet", "fetch", "--targets", str(targets), "--products", str(table)),
        *("--base-lc-dir", str(base_dir), "--criteria", str(SEARCH)),
    ]
    assert main(argv) == 0
    [run] = set((tmp_path / "data" / "runs").glob("*-revet-fetch-*")) - before
    return run


def test_a_revet_onto_a_revets_light_curve_takes_a_better_product_for_a_sector_a_revet_added(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    served = {S3_BASE + key: tf.QLP.read_bytes() for key in ("k/qlp1", "k/qlp112")}
    served |= {S3_BASE + key: tf.TSPOC.read_bytes() for key in ("k/tspoc1", "k/tspoc112")}
    session = FakeSession(served)
    monkeypatch.setattr(requests, "Session", lambda: session)
    qlp = [product_row(1, "QLP", tf.QLP, "k/qlp1"), product_row(112, "QLP", tf.QLP, "k/qlp112")]
    tspoc = [
        product_row(1, "TESS-SPOC", tf.TSPOC, "k/tspoc1"),
        product_row(112, "TESS-SPOC", tf.TSPOC, "k/tspoc112"),
    ]
    # M2 fetched S1 as QLP; r2 adds S112, for which QLP is all there is yet.
    m2_dir = tmp_path / "data" / "lc"
    first = pd.DataFrame(qlp[:1], columns=PRODUCT_COLUMNS)
    fetch_star(tf.TIC, first, m2_dir, tf.FETCH, session=session)
    r2 = revet_fetch(tmp_path, m2_dir, qlp)
    star = json.loads((r2 / "merge.json").read_text())[str(tf.TIC)]
    assert star["m2_sectors"] == ["1"]
    assert {s: r["status"] for s, r in star["sectors"].items()} == {"1": "kept", "112": "added"}

    # r3, onto r2's light curve: TESS-SPOC has reached both sectors. S112, which r2 added, takes it; M2's S1 does not.
    r3 = revet_fetch(tmp_path, r2 / "lc", tspoc + qlp)
    star = json.loads((r3 / "merge.json").read_text())[str(tf.TIC)]
    assert star["m2_sectors"] == ["1"]
    assert star["base_sha256"] == sha256_file(r2 / "lc" / f"{tf.TIC}.npz")
    statuses = {s: r["status"] for s, r in star["sectors"].items()}
    assert statuses == {"1": "kept_m2", "112": "upgraded"}
    merged = LightCurve.load(r3 / "lc" / f"{tf.TIC}.npz")
    m2 = LightCurve.load(m2_dir / f"{tf.TIC}.npz")
    assert merged.sources["1"] == m2.sources["1"]
    assert np.array_equal(merged.select(merged.sector == 1).flux, m2.flux)
    assert merged.sources["112"]["provenance"] == "TESS-SPOC"

    # A revet fetch run that recorded no M2 sectors is not merged onto: its sectors can't be told apart.
    edited = json.loads((r3 / "merge.json").read_text())
    del edited[str(tf.TIC)]["m2_sectors"]
    # A finished run's files are read-only.
    (r3 / "merge.json").chmod(0o644)
    (r3 / "merge.json").write_text(json.dumps(edited))
    runs = set((tmp_path / "data" / "runs").glob("*-revet-fetch-*"))
    with pytest.raises(SystemExit, match=f"records no M2 sectors for TIC {tf.TIC}"):
        revet_fetch(tmp_path, r3 / "lc", tspoc)
    assert set((tmp_path / "data" / "runs").glob("*-revet-fetch-*")) == runs
