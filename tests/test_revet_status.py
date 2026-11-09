import json
import re
from functools import partial
from pathlib import Path

import pandas as pd
import pytest
from astropy.table import Table

from tess_hunt import mast, revet_status
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.mast import PRODUCT_COLUMNS
from tess_hunt.revet_status import COMPLETE, redelivery_rows, sector_rows, verdict

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "criteria" / "search-v2.toml"
RULES = load_criteria(SEARCH)["fetch"]["timing_suspect"]
TIC = 241522065
PACKAGE = "20261028T204003Z-predictions-aaaaaaa-0001"
TWO_MIN = ["SPOC 2-min", "TESS-SPOC"]
EVERY = ["SPOC 2-min", "TESS-SPOC", "QLP"]


def product(tic: int, sector: int, provenance: str, version: str = "v01") -> dict:
    """A light-curve file as MAST lists it, named as each producer names its files (pin P4)."""
    if provenance == "SPOC":
        name = f"tess2026357123456-s{sector:04d}-{tic:016d}-0294-s_lc.fits"
        uri, cadence = f"mast:TESS/product/{name}", 120.0
    elif provenance == "TESS-SPOC":
        name = f"hlsp_tess-spoc_tess_phot_{tic:016d}-s{sector:04d}_tess_v1_lc.fits"
        uri, cadence = f"mast:HLSP/tess-spoc/s{sector:04d}/target/{name}", 200.0
    else:
        name = f"hlsp_qlp_tess_ffi_s{sector:04d}-{tic:016d}_tess_{version}_llc.fits"
        uri, cadence = f"mast:HLSP/qlp/s{sector:04d}/{name}", 200.0
    return {
        "tic": tic,
        "sector": sector,
        "provenance": provenance,
        "cadence_s": cadence,
        "filename": name,
        "data_uri": uri,
        "size": 100,
        "s3_key": mast.s3_key(uri),
    }


def listing(*products: dict) -> pd.DataFrame:
    return pd.DataFrame(list(products), columns=PRODUCT_COLUMNS)


def signal(sectors: list[int], testable_with: list[str], tic: int = TIC) -> dict:
    return {"tic": tic, "sectors": sectors, "testable_with": testable_with}


class RecordedObservations:
    """MAST's answer from a recorded product table, each product its own observation. A query naming a star in
    `failing` fails, as MAST does in an outage."""

    def __init__(self, products: pd.DataFrame, failing=()):
        self.products, self.failing = products, set(failing)

    def query_criteria(self, target_name, **kw):
        if self.failing & {int(n) for n in target_name}:
            raise ConnectionError("MAST 503")
        rows = self.products[self.products["tic"].isin([int(n) for n in target_name])]
        return Table(
            {
                "target_name": [str(t) for t in rows["tic"]],
                "provenance_name": list(rows["provenance"]),
                "t_exptime": [float(c) for c in rows["cadence_s"]],
                "obs_id": [str(i) for i in rows.index],
                "sequence_number": [int(s) for s in rows["sector"]],
            }
        )

    def get_product_list(self, obs):
        rows = self.products.loc[[int(i) for i in obs["obs_id"]]]
        return Table(
            {
                "obs_id": list(obs["obs_id"]),
                "productFilename": list(rows["filename"]),
                "dataURI": list(rows["data_uri"]),
                "size": list(rows["size"]),
            }
        )


def observe(monkeypatch, products: pd.DataFrame, failing=()) -> None:
    """The command's `mast.discover` answered from `products`, one star per batch and no wait between tries."""
    discover = partial(
        mast.discover,
        observations=RecordedObservations(products, failing),
        batch=1,
        backoff=0.0,
    )
    monkeypatch.setattr(mast, "discover", discover)


def deposit(repo: Path, run_id: str, signals: dict, published: str | None = None) -> None:
    """A predictions package as `predictions publish` copies it, two transits in each predicted sector, and its
    `dois.toml` entry when it was deposited."""
    root = repo / "results" / "predictions"
    package = root / run_id
    package.mkdir(parents=True)
    (package / "provenance.json").write_text(json.dumps({"stage": "predictions"}))
    references = {
        name: {"tic": p["tic"], "testable_with": p["testable_with"]} for name, p in signals.items()
    }
    (package / "references.json").write_text(json.dumps({"signals": references}))
    rows = [
        {"signal": name, "tic": p["tic"], "sector": sector, "epoch": epoch}
        for name, p in signals.items()
        for sector in p["sectors"]
        for epoch in (1, 2)
    ]
    pd.DataFrame(rows).to_csv(package / "predictions.csv", index=False)
    if published:
        with open(root / "dois.toml", "a") as fh:
            fh.write(f'["{run_id}"]\ndoi = "10.5281/zenodo.1"\npublished = {published}\n\n')


def in_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    monkeypatch.setattr(revet_status, "repo_root", lambda: repo)
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    return repo


def status(*argv: str) -> int:
    return main(["revet", "status", "--criteria", str(SEARCH), *argv])


def test_a_sector_with_spoc_2min_is_usable_for_a_2min_signal():
    products = listing(product(TIC, 112, "SPOC"))
    [row] = sector_rows({"241522065-1": signal([112], TWO_MIN)}, products, RULES, [])
    assert row["usable"] is True and row["why"] is None
    assert row["taken_product"] == "SPOC 2-min"


def test_a_qlp_sector_cannot_test_a_pdcsap_signal():
    products = listing(product(TIC, 113, "QLP"))
    [row] = sector_rows({"241522065-1": signal([113], TWO_MIN)}, products, RULES, [])
    assert row["usable"] is False and row["why"] == "QLP, which can't test it"
    # A signal whose package trained a QLP family can be tested on it.
    [row] = sector_rows({"241522065-1": signal([113], EVERY)}, products, RULES, [])
    assert row["usable"] is True


def test_a_timing_suspect_product_is_not_usable():
    products = listing(product(TIC, 99, "QLP", "v01"), product(TIC, 102, "QLP", "v02"))
    rows = sector_rows({"241522065-1": signal([99, 102], EVERY)}, products, RULES, [])
    assert [(r["sector"], r["usable"], r["why"]) for r in rows] == [
        (99, False, "timing-suspect"),
        (102, True, None),
    ]
    assert [[p["suspect"] for p in r["listed"]] for r in rows] == [[True], [False]]


def test_taken_is_what_fetch_would_take(monkeypatch):
    products = listing(
        product(TIC, 112, "QLP"), product(TIC, 112, "TESS-SPOC"), product(TIC, 112, "SPOC")
    )
    signals = {"241522065-1": signal([112], TWO_MIN)}
    [row] = sector_rows(signals, products, RULES, [])
    assert row["taken"] == mast.best(products).loc[0, "filename"] == products.loc[2, "filename"]
    assert [(p["provenance"], p["cadence_s"], p["filename"]) for p in row["listed"]] == [
        (p.provenance, p.cadence_s, p.filename) for p in products.itertuples()
    ]
    # Read from fetch's own ranking, so the status follows it wherever it changes.
    monkeypatch.setattr(mast, "best", lambda p: p[p["provenance"] == "QLP"].reset_index(drop=True))
    [row] = sector_rows(signals, products, RULES, [])
    assert row["taken"] == products.loc[0, "filename"] and row["taken_product"] == "QLP"
    assert row["why"] == "QLP, which can't test it"


def test_complete_only_when_every_predicted_sector_is_usable():
    signals = {"241522065-1": signal([112, 113], TWO_MIN)}

    def said(*products: dict) -> str:
        return verdict(sector_rows(signals, listing(*products), RULES, []))["241522065-1"]

    s112 = product(TIC, 112, "SPOC")
    assert said(product(TIC, 113, "QLP")) == "not yet: S112 no data, S113 QLP, which can't test it"
    assert said(s112, product(TIC, 113, "QLP")) == "not yet: S113 QLP, which can't test it"
    assert said(s112, product(TIC, 113, "TESS-SPOC")) == COMPLETE
    assert COMPLETE == "complete: every predicted sector has data the test can use"


def test_a_star_mast_could_not_list_is_never_complete(tmp_path, monkeypatch, capsys):
    signals = {
        "241522065-1": signal([112], TWO_MIN),
        "103312990-1": signal([112], EVERY, tic=103312990),
    }
    products = listing(product(TIC, 112, "SPOC"))
    rows = sector_rows(signals, products, RULES, [103312990])
    unlisted = next(r for r in rows if r["tic"] == 103312990)
    assert unlisted["listed"] is None and unlisted["usable"] is False
    assert verdict(rows) == {
        "241522065-1": COMPLETE,
        "103312990-1": "unknown: MAST did not answer for TIC 103312990",
    }
    # MAST answered and lists nothing for the sector yet.
    rows = sector_rows(signals, products, RULES, [])
    assert verdict(rows)["103312990-1"] == "not yet: S112 no data"

    repo = in_repo(tmp_path, monkeypatch)
    deposit(repo, PACKAGE, signals, published="2026-10-28")
    observe(monkeypatch, products, failing=[103312990])
    assert status() == 1
    out = capsys.readouterr().out
    assert "103312990-1: unknown: MAST did not answer for TIC 103312990" in out
    assert f"241522065-1: {COMPLETE}" in out
    # Nor does the redelivery section read as nothing served for it.
    assert "| 103312990 | unknown | unknown | MAST did not answer | unknown |" in out
    assert "none listed" not in out


def test_redelivery_rows_show_the_served_qlp_version():
    products = listing(
        product(TIC, 99, "QLP", "v01"),
        product(TIC, 102, "QLP", "v02"),
        # Outside the timing-suspect rule's sectors, or not QLP: no redelivery to wait for.
        product(TIC, 105, "QLP", "v01"),
        product(TIC, 99, "SPOC"),
        product(146282666, 104, "QLP", "v01"),
        # Not one of the stars asked about.
        product(277774870, 101, "QLP", "v01"),
    )
    rows = redelivery_rows(products, [241522065, 146282666], RULES)
    assert [(r["tic"], r["sector"], r["version"], r["suspect"]) for r in rows] == [
        (146282666, 104, "v01", True),
        (241522065, 99, "v01", True),
        (241522065, 102, "v02", False),
    ]
    assert rows[0]["filename"] == products.loc[4, "filename"]


def test_the_default_package_is_the_latest_deposited(tmp_path, monkeypatch, capsys):
    repo = in_repo(tmp_path, monkeypatch)
    later = "20261119T120000Z-predictions-bbbbbbb-0002"
    deposit(repo, later, {"B-1": signal([113], TWO_MIN)}, published="2026-11-20")
    deposit(repo, PACKAGE, {"A-1": signal([112], TWO_MIN)}, published="2026-10-28")
    # Made last, but never deposited.
    deposit(repo, "20261125T120000Z-predictions-ccccccc-0003", {"C-1": signal([114], TWO_MIN)})
    observe(monkeypatch, listing())
    assert status() == 0
    out = capsys.readouterr().out
    assert out.startswith(f"package {later}\n")
    assert "B-1: not yet: S113 no data" in out and "A-1" not in out and "C-1" not in out
    assert status("--package", PACKAGE) == 0
    out = capsys.readouterr().out
    assert "A-1: not yet: S112 no data" in out and "B-1" not in out


def test_of_two_deposited_on_one_day_the_later_made_is_the_default(tmp_path, monkeypatch, capsys):
    repo = in_repo(tmp_path, monkeypatch)
    later = "20261119T120000Z-predictions-bbbbbbb-0002"
    # The earlier-made package comes first in dois.toml, so the date alone would pick it.
    deposit(repo, PACKAGE, {"A-1": signal([112], TWO_MIN)}, published="2026-11-20")
    deposit(repo, later, {"B-1": signal([113], TWO_MIN)}, published="2026-11-20")
    observe(monkeypatch, listing())
    assert status() == 0
    assert capsys.readouterr().out.startswith(f"package {later}\n")


def test_a_signal_the_package_predicts_no_transit_of_is_refused(tmp_path):
    deposit(tmp_path, PACKAGE, {"241522065-1": signal([112], TWO_MIN), "B-1": signal([], TWO_MIN)})
    # Given no row, it would get no verdict, and its absence would read as nothing missing.
    with pytest.raises(ValueError, match="predicts no transit of B-1"):
        revet_status.predicted(tmp_path / "results" / "predictions" / PACKAGE)


def tree(path: Path) -> dict | None:
    if not path.exists():
        return None
    return {str(p.relative_to(path)): p.is_file() and p.read_bytes() for p in path.rglob("*")}


def test_status_writes_nothing(tmp_path, monkeypatch, capsys):
    repo = in_repo(tmp_path, monkeypatch)
    deposit(repo, PACKAGE, {"241522065-1": signal([112], TWO_MIN)}, published="2026-10-28")
    observe(monkeypatch, listing(product(TIC, 112, "SPOC"), product(TIC, 99, "QLP")))
    # A data directory that isn't there yet, then one holding a light curve.
    assert status() == 0
    assert not (tmp_path / "data").exists()
    (tmp_path / "data" / "lc").mkdir(parents=True)
    (tmp_path / "data" / "lc" / f"{TIC}.npz").write_bytes(b"M2's light curve")
    before = tree(tmp_path / "data"), tree(repo / "results")
    assert status() == 0
    assert (tree(tmp_path / "data"), tree(repo / "results")) == before
    out = capsys.readouterr().out
    assert re.search(r"^\| 241522065-1 \| S112 \| SPOC 120 s \|", out, re.M)
    assert re.search(r"^\| 241522065 \| S99 \| v01 \| .*_v01_llc\.fits \| yes \|$", out, re.M)


@pytest.mark.network
def test_status_on_the_deposited_package(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    assert status() == 0
    out = capsys.readouterr().out
    print(out)
    run_id = re.match(r"package (\S+)\n", out).group(1)
    signals = revet_status.predicted(ROOT / "results" / "predictions" / run_id)
    assert signals
    for name in signals:
        assert re.search(rf"^{name}: (complete|not yet): ", out, re.M), name
    assert not (tmp_path / "data").exists()
