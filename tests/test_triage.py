import json
import pickle
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, make_transit_lc, write_catalog_snapshot

from tess_hunt import triage
from tess_hunt.catalogs import KNOWN_COLUMNS, snapshot_inputs
from tess_hunt.checks import failed, inconclusive, passed
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, in_transit, transit_times_in_data
from tess_hunt.leo import LeoOutcome
from tess_hunt.pixels import asked_ephemeris
from tess_hunt.provenance import sha256_file
from tess_hunt.search import search_code_sha256

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = load_criteria(ROOT / "criteria" / "search-v2.toml")
TRIAGE = load_criteria(ROOT / "criteria" / "triage-v1.toml")
SIGNALS = [  # (tic, rank, period, t0, sde)
    (11, 1, 3.0, 1326.0, 40.0),  # matches only a SPOC TCE
    (12, 1, 4.0, 1327.0, 35.0),  # matches a TOI
    (13, 1, 5.0, 1328.0, 30.0),  # new
    (13, 2, 7.3, 1329.0, 20.0),  # new, the same star's second signal
    (14, 1, 6.0, 1330.0, 5.0),  # below the threshold
]
THRESHOLD_RUN = "20261020T000000Z-threshold-abc-1"
NULL_RUN = "20261019T000000Z-search-abc-0"
HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
).stdout.strip()


def write_run(path: Path, provenance: dict, **tables) -> Path:
    path.mkdir(parents=True)
    (path / "provenance.json").write_text(
        json.dumps({"ended_at": "2026-10-20T00:00:00+00:00", **provenance})
    )
    for name, frame in tables.items():
        frame.to_parquet(path / f"{name}.parquet")
    return path


def setup(
    tmp_path,
    monkeypatch,
    controls_valid=True,
    threshold=10.0,
    suspect=(),
    masks_known=None,
    rows=SIGNALS,
    **target_columns,
):
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    for tic in (11, 12, 13, 14):
        lc = make_lc(sectors=(1, 2, 98), tic=tic)
        for sector in suspect:
            lc.sources[str(sector)]["timing_suspect"] = True
        lc.save(data / "lc" / f"{tic}.npz")
    if masks_known is None:
        masks = write_catalog_snapshot(tmp_path / "masks")
    else:
        masks = tmp_path / "masks"
        masks.mkdir()
        masks_known.to_parquet(masks / "known.parquet")
        (masks / "manifest.json").write_text("{}")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame(
        {
            "tic": [11, 12, 13, 14],
            "ra": [1.0 + 0.5 * 3, 1.0 + 0.5 * 4, 9.0, 11.0],
            "dec": -70.0,
            "rad": 1.0,
            "mass": 1.0,
            "teff": 5800.0,
            "logg": 4.4,
            "ruwe": 1.0,
            **target_columns,
        }
    ).to_parquet(targets)
    signals = pd.DataFrame(
        [
            {
                "tic": t,
                "rank": r,
                "period": p,
                "t0": t0,
                "duration": 0.1,
                "depth": 1e-3,
                "depth_snr": 10.0,
                "sde": s,
                "n_transits": 5,
                "engine": "bls",
                "control": False,
            }
            for t, r, p, t0, s in rows
        ]
    )
    hashes = {
        "search_criteria_sha256": CRITERIA.sha256,
        "search_code_sha256": search_code_sha256(ROOT),
    }
    inputs = {
        name: {"file": p.name, "sha256": sha256_file(p)}
        for name, p in snapshot_inputs(masks).items()
    }
    # What the search searched: triage holds a run to its targets and light curves.
    inputs["targets"] = {"file": targets.name, "sha256": sha256_file(targets)}
    lc_sha256 = [sha256_file(data / "lc" / f"{tic}.npz") for tic in (11, 12, 13, 14)]
    stars = pd.DataFrame(
        {"tic": [11, 12, 13, 14], "status": "ok", "control": False, "lc_sha256": lc_sha256}
    )
    # The null behind the threshold searched the same light curves.
    write_run(data / "runs" / NULL_RUN, {}, stars=stars)
    search = write_run(
        data / "runs" / "s1",
        {
            "criteria": [{"file": "criteria/search-v2.toml", "sha256": CRITERIA.sha256}],
            "search_code_sha256": hashes["search_code_sha256"],
            "threshold": {"value": threshold, "file": "threshold.json"},
            "inputs": inputs,
            "summary": {"controls_valid": controls_valid},
        },
        signals=signals,
        stars=stars,
    )
    criteria = [
        {"file": "criteria/search-v2.toml", "sha256": CRITERIA.sha256},
        {"file": "criteria/triage-v1.toml", "sha256": TRIAGE.sha256},
    ]
    # Made at this checkout, so LEO-Vetter judges here as it did there.
    thr = write_run(
        data / "runs" / THRESHOLD_RUN,
        {
            "run_id": THRESHOLD_RUN,
            "criteria": criteria,
            "git": {"commit": HEAD, "dirty_paths": []},
            "uv_lock_sha256": sha256_file(ROOT / "uv.lock"),
        },
    )
    (thr / "threshold.json").write_text(
        json.dumps({"threshold": threshold, "null_run": NULL_RUN, **hashes})
    )
    snap = tmp_path / "snap"
    snap.mkdir()
    base = {"ra": 1.0, "dec": -70.0, "duration": 0.1, "depth_ppm": 1000.0}
    known = pd.DataFrame(
        [
            {**base, "source": s, "kind": k, "name": n, "tic": t, "period": p, "t0": t0}
            for s, k, n, t, p, t0 in [
                ("TOI", "candidate", "far", 999, 2.5, 100.0),
                ("CTOI", "candidate", "far2", 998, 3.5, 100.0),
                ("archive", "planet", "far3", 997, 4.5, 100.0),
                ("SPOC-TCE", "tce", "TCE s0098 x", 11, 3.0, 1326.0),
                ("TOI", "candidate", "TOI-5.01", 12, 4.0, 1327.0),
                ("TESS-EB", "eb", "far EB", 996, 5.5, 100.0),
            ]
        ]
    )[KNOWN_COLUMNS]
    for i in known.index:
        known.loc[i, "ra"] = 1.0 + 0.5 * i  # spread the stars beyond each other's 2.5' radius
    known.to_parquet(snap / "known.parquet")
    (snap / "manifest.json").write_text("{}")
    leo_calls = []

    def fake_leo(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        leo_calls.append((int(star["tic"]), eph.period, sorted(o.period for o in others)))
        return (
            passed("leo_flux", "planet candidate", disposition="PC"),
            LeoOutcome("PC"),
            type("T", (), {"metrics": {"tic": star["tic"]}})(),
        )

    monkeypatch.setattr(triage, "leo_flux", fake_leo)
    monkeypatch.setattr(
        triage,
        "pixel_check",
        lambda tlc, star, sectors, cfg, tdi: passed("pixels", "ok", offset_qual_arcsec=3.0),
    )
    monkeypatch.setattr(
        triage.literature,
        "search",
        lambda tic, session, pause=3.0: {"zenodo": {"status": "ok", "hits": []}},
    )
    monkeypatch.chdir(ROOT)
    argv = [
        "triage",
        "run",
        "--search",
        str(search),
        "--threshold",
        str(thr),
        "--catalogs",
        str(snap),
        "--mask-catalogs",
        str(masks),
        "--targets",
        str(targets),
        "--workers",
        "1",
    ]
    return argv, leo_calls


def latest_triage(tmp_path):
    return sorted((tmp_path / "data" / "runs").glob("*-triage-*"))[-1]


def test_triage_shortlists_only_new_signals(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    assert main(argv) == 0
    run = latest_triage(tmp_path)
    table = pd.read_parquet(run / "signals.parquet").set_index(["tic", "rank"])
    assert len(table) == 4  # the SDE 5 signal is below the threshold
    assert table.loc[(11, 1), "novelty_category"] == "known_to_spoc"
    assert table.loc[(12, 1), "novelty"] == "fail"
    shortlist = pd.read_csv(run / "shortlist.csv")
    assert sorted(zip(shortlist["tic"], shortlist["rank"], strict=True)) == [(13, 1), (13, 2)]
    assert list(pd.read_csv(run / "known_to_spoc.csv")["tic"]) == [11]
    assert (run / "evidence" / "13-1.json").exists() and (run / "summary.md").exists()


def test_triage_two_signals_on_one_star(tmp_path, monkeypatch):
    # The star's third signal is below the threshold: neither vetted nor dropped from the others.
    argv, calls = setup(tmp_path, monkeypatch, rows=[*SIGNALS, (13, 3, 9.1, 1330.0, 5.0)])
    main(argv)
    by_period = {p: others for tic, p, others in calls if tic == 13}
    assert by_period[5.0] == [7.3] and by_period[7.3] == [5.0]
    assert 9.1 not in by_period


def test_triage_refuses_an_invalid_search(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch, controls_valid=False)
    with pytest.raises(SystemExit, match="controls"):
        main(argv)


def test_triage_refuses_a_search_below_a_grown_null(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    grown = tmp_path / "data" / "runs" / "20261021T000000Z-threshold-abc-2"
    write_run(grown, {})
    hashes = {
        "search_criteria_sha256": CRITERIA.sha256,
        "search_code_sha256": search_code_sha256(ROOT),
    }
    (grown / "threshold.json").write_text(json.dumps({"threshold": 12.5, **hashes}))
    with pytest.raises(SystemExit, match="12.5"):
        main(argv)


def test_inconclusive_leo_keeps_a_signal_off_the_shortlist(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        triage,
        "leo_flux",
        lambda *a, **k: (
            inconclusive("leo_flux", "tests not judged: chi"),
            LeoOutcome(None, unknown=["chi"]),
            None,
        ),
    )
    main(argv)
    assert len(pd.read_csv(latest_triage(tmp_path) / "shortlist.csv")) == 0


def table_of(run: Path) -> pd.DataFrame:
    return pd.read_parquet(run / "signals.parquet").set_index(["tic", "rank"])


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def tlc(metrics=None):
    return type("T", (), {"metrics": metrics or {}})()


def no_triage_run(tmp_path) -> bool:
    return not list((tmp_path / "data" / "runs").glob("*-triage-*"))


def change_null_star(tmp: Path, tic: int) -> None:
    """The null searched another light curve of `tic` than the search did."""
    path = tmp / "data/runs" / NULL_RUN / "stars.parquet"
    stars = pd.read_parquet(path)
    stars.loc[stars["tic"] == tic, "lc_sha256"] = "0" * 64
    stars.to_parquet(path)


def test_triage_records_each_step_and_searches_the_literature_of_shortlisted_stars(
    tmp_path, monkeypatch
):
    argv, _ = setup(tmp_path, monkeypatch)
    searched = []

    def search(tic, session, pause=3.0):
        searched.append(tic)
        return {
            "zenodo": {"status": "error", "hits": [], "error": "HTTP 503"},
            "arxiv": {"status": "ok", "hits": []},
        }

    monkeypatch.setattr(triage.literature, "search", search)
    assert main(argv) == 0
    run = latest_triage(tmp_path)
    assert searched == [13] and [p.name for p in (run / "literature").iterdir()] == ["13.json"]
    evidence = json.loads((run / "evidence" / "12-1.json").read_text())
    assert evidence["novelty"]["outcome"] == "fail" and evidence["leo_flux"]["outcome"] == "pass"
    assert (
        evidence["pixels"]["outcome"] == "inconclusive"
        and "not run" in evidence["pixels"]["reason"]
    )
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["threshold"] == {
        "value": 10.0,
        "file": "threshold.json",
        "run_id": THRESHOLD_RUN,
    }
    assert provenance["search_run"] == "s1"
    summary = provenance["summary"]
    assert (summary["signals"], summary["shortlisted"], summary["known_to_spoc"]) == (4, 2, 1)
    assert summary["novelty"] == {"pass": 2, "fail": 1, "inconclusive": 1}
    assert summary["pixels"] == {"pass": 2, "fail": 0, "inconclusive": 0}
    assert summary["literature_incomplete"] == [13]
    text = (run / "summary.md").read_text()
    assert "| novelty | 4 | 2 | 1 | 1 |" in text and "| pixels | 2 | 2 | 0 | 0 |" in text
    assert "TIC 13 (zenodo)" in text


def test_leo_input_masks_only_the_search_mask_sources(tmp_path, monkeypatch):
    base = {"ra": 9.0, "dec": -70.0, "tic": 13, "duration": 0.1, "depth_ppm": 1000.0}
    masks = pd.DataFrame(
        [
            {
                **base,
                "source": "TOI",
                "kind": "candidate",
                "name": "TOI-7.01",
                "period": 9.0,
                "t0": 1326.5,
            },
            {
                **base,
                "source": "SPOC-TCE",
                "kind": "tce",
                "name": "TCE s0001 y",
                "period": 11.0,
                "t0": 1327.5,
            },
        ]
    )[KNOWN_COLUMNS]
    argv, _ = setup(tmp_path, monkeypatch, masks_known=masks)
    excluded = {}

    def leo(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        excluded[eph.period] = lc.time[exclude]
        return passed("leo_flux", "planet candidate", disposition="PC"), LeoOutcome("PC"), tlc()

    monkeypatch.setattr(triage, "leo_flux", leo)
    main(argv)
    time = make_lc(sectors=(1, 2, 98), tic=13).time
    toi = in_transit(time, Ephemeris(9.0, 1326.5, 0.1), CRITERIA["detrend"]["known_mask_width"])
    assert toi.any() and np.array_equal(excluded[5.0], time[toi])


def test_each_signal_gets_its_own_difference_image_directory(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    seen = []

    def check(tlc, star, sectors, cfg, tdi):
        seen.append((Path(tdi), int(star["tic"]), sorted(sectors), cfg["max_offset_arcsec"]))
        return passed("pixels", "ok", offset_qual_arcsec=3.0)

    monkeypatch.setattr(triage, "pixel_check", check)
    main(argv)
    tdi = tmp_path / "data" / "tdi" / latest_triage(tmp_path).name
    assert sorted(seen) == [
        (tdi / "13-1", 13, [1, 2, 98], 15.0),
        (tdi / "13-2", 13, [1, 2, 98], 15.0),
    ]


@pytest.mark.parametrize(
    ("result", "outcome", "why"),
    [
        (
            failed("pixels", 'centroid offset 40.0" exceeds 15"', offset_qual_arcsec=40.0),
            "fail",
            "exceeds",
        ),
        (
            inconclusive("pixels", "no sector gave a usable difference image", sectors=[]),
            "inconclusive",
            "usable",
        ),
        (RuntimeError("tess-point broke"), "inconclusive", "RuntimeError: tess-point broke"),
    ],
)
def test_a_pixel_fail_or_inconclusive_is_listed_with_its_reason_not_shortlisted(
    tmp_path, monkeypatch, result, outcome, why
):
    argv, _ = setup(tmp_path, monkeypatch)

    def check(tlc, star, sectors, cfg, tdi):
        if Path(tdi).name == "13-2":
            return passed("pixels", "ok", offset_qual_arcsec=3.0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(triage, "pixel_check", check)
    main(argv)
    run = latest_triage(tmp_path)
    table = table_of(run)
    assert list(pd.read_csv(run / "shortlist.csv")["rank"]) == [2]
    assert table.loc[(13, 1), "pixels"] == outcome and why in table.loc[(13, 1), "pixels_reason"]
    assert table.loc[(13, 1), "pixels_reason"] in (run / "summary.md").read_text()


def test_a_flux_false_positive_stays_off_the_shortlist_and_skips_pixels(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)

    def leo(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        if eph.period == 5.0:
            return (
                failed("leo_flux", "FP: odd_even", disposition="FP"),
                LeoOutcome("FP", fp_failed=["odd_even"]),
                tlc(),
            )
        return passed("leo_flux", "planet candidate", disposition="PC"), LeoOutcome("PC"), tlc()

    looked = []
    monkeypatch.setattr(triage, "leo_flux", leo)
    monkeypatch.setattr(
        triage,
        "pixel_check",
        lambda tlc, star, sectors, cfg, tdi: (
            looked.append(Path(tdi).name) or passed("pixels", "ok")
        ),
    )
    main(argv)
    run = latest_triage(tmp_path)
    table = table_of(run)
    assert looked == ["13-2"] and list(pd.read_csv(run / "shortlist.csv")["rank"]) == [2]
    assert (table.loc[(13, 1), "leo_flux"], table.loc[(13, 1), "leo_disposition"]) == ("fail", "FP")


def test_leo_unknowns_are_counted_per_test_and_an_exception_is_inconclusive(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    unknown = ["asymmetric", "sinusoidal: KeyError"]

    def leo(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        if eph.period == 5.0:
            raise ValueError("odd light curve")
        return (
            inconclusive("leo_flux", f"tests not judged: {', '.join(unknown)}"),
            LeoOutcome(None, unknown=unknown),
            tlc(),
        )

    monkeypatch.setattr(triage, "leo_flux", leo)
    main(argv)
    run = latest_triage(tmp_path)
    table = table_of(run)
    assert (
        table.loc[(13, 1), "leo_flux"] == "inconclusive"
        and "ValueError: odd light curve" in table.loc[(13, 1), "leo_reason"]
    )
    assert json.loads((run / "provenance.json").read_text())["summary"]["leo_unknown"] == {
        "asymmetric": 3,
        "sinusoidal": 3,
    }
    assert "asymmetric 3" in (run / "summary.md").read_text()
    assert len(pd.read_csv(run / "shortlist.csv")) == 0


def test_triage_counts_transits_in_timing_suspect_sectors(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch, suspect=(98,))
    main(argv)
    expected = len(transit_times_in_data(make_lc(sectors=(98,)).time, Ephemeris(5.0, 1328.0, 0.1)))
    assert (
        expected > 0
        and table_of(latest_triage(tmp_path)).loc[(13, 1), "timing_suspect_transits"] == expected
    )


def test_triage_shows_ruwe_and_takes_a_missing_value_as_missing(tmp_path, monkeypatch):
    argv, _ = setup(
        tmp_path,
        monkeypatch,
        ruwe=[1.1, 1.2, np.nan, 1.4],
        dr3_source_id=pd.array([1, 2, pd.NA, 4], dtype="Int64"),
    )
    assert main(argv) == 0
    table = table_of(latest_triage(tmp_path))
    assert table.loc[(11, 1), "ruwe"] == 1.1 and np.isnan(table.loc[(13, 1), "ruwe"])
    assert (table["timing_suspect_transits"] == 0).all()


def test_triage_with_no_signal_above_the_threshold_writes_empty_tables(tmp_path, monkeypatch):
    argv, calls = setup(tmp_path, monkeypatch, threshold=50.0)
    assert main(argv) == 0
    run = latest_triage(tmp_path)
    assert calls == [] and len(pd.read_parquet(run / "signals.parquet")) == 0
    assert (
        len(pd.read_csv(run / "shortlist.csv")) == 0
        and "Shortlisted: 0" in (run / "summary.md").read_text()
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda tmp: edit_json(
                tmp / "data/runs/s1/provenance.json", lambda p: p.update(ended_at=None)
            ),
            "s1 has not finished",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / THRESHOLD_RUN / "provenance.json",
                lambda p: p.update(ended_at=None),
            ),
            f"{THRESHOLD_RUN} has not finished",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs/s1/provenance.json",
                lambda p: p["criteria"][0].update(sha256="0" * 64),
            ),
            "criteria file changed",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs/s1/provenance.json",
                lambda p: p.update(search_code_sha256="0" * 64),
            ),
            "search code changed",
        ),
        (lambda tmp: (tmp / "masks" / "toi.csv").write_text("TIC ID\n1\n"), "mask-catalogs"),
        (
            lambda tmp: pd.DataFrame({"tic": [11, 12, 13, 14]}).to_parquet(tmp / "targets.parquet"),
            "targets",
        ),
        (
            lambda tmp: (tmp / "targets.parquet").unlink(),
            "--targets targets.parquet does not exist",
        ),
        (
            lambda tmp: make_lc(sectors=(1, 2, 98), tic=13, seed=1).save(tmp / "data/lc/13.npz"),
            r"light curves of 1 search star differ .*\[13\]",
        ),
        (
            lambda tmp: (tmp / "data/lc/12.npz").unlink(),
            r"light curves of 1 search star differ .*\[12\]",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / THRESHOLD_RUN / "provenance.json",
                lambda p: p["criteria"][1].update(sha256="0" * 64),
            ),
            r"criteria/triage-v1.toml changed since .* \[leo\] and \[leo_metrics\]",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / THRESHOLD_RUN / "provenance.json",
                lambda p: p.update(run_id="20261020T000000Z-threshold-abc-2"),
            ),
            f"{THRESHOLD_RUN} is not the run its provenance names",
        ),
        (
            lambda tmp: change_null_star(tmp, 13),
            f"light curves of 1 triaged star differ from the ones the null {NULL_RUN} searched "
            rf"for {THRESHOLD_RUN}: \[13\]",
        ),
        (
            lambda tmp: (tmp / "data/runs" / NULL_RUN / "stars.parquet").unlink(),
            f"{THRESHOLD_RUN} names a null run with no stars.parquet: {NULL_RUN}",
        ),
    ],
)
def test_triage_refuses_a_run_it_cannot_trust(tmp_path, monkeypatch, change, message):
    argv, _ = setup(tmp_path, monkeypatch)
    change(tmp_path)
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert no_triage_run(tmp_path)


def test_triage_refuses_a_threshold_below_the_current_null(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    # The search ran at the grown null's value, so only the cut at the older threshold is wrong.
    edit_json(
        tmp_path / "data/runs/s1/provenance.json", lambda p: p["threshold"].update(value=12.5)
    )
    grown = tmp_path / "data" / "runs" / "20261021T000000Z-threshold-abc-2"
    write_run(grown, {})
    hashes = {
        "search_criteria_sha256": CRITERIA.sha256,
        "search_code_sha256": search_code_sha256(ROOT),
    }
    (grown / "threshold.json").write_text(json.dumps({"threshold": 12.5, **hashes}))
    with pytest.raises(
        SystemExit, match=f"{THRESHOLD_RUN} sets 10.0, below the current null threshold 12.5"
    ):
        main(argv)
    assert no_triage_run(tmp_path)


def drop_eb_rows(tmp: Path) -> None:
    known = pd.read_parquet(tmp / "snap" / "known.parquet")
    known[known["kind"] != "eb"].to_parquet(tmp / "snap" / "known.parquet")


@pytest.mark.parametrize(
    ("catalogs", "change", "message"),
    [
        # The v1 mask snapshot: TOIs, CTOIs and archive planets only.
        ("masks", lambda tmp: None, "masks is not a v2 snapshot"),
        ("snap", drop_eb_rows, "no rows of kind eb"),
    ],
)
def test_triage_refuses_a_novelty_catalog_without_tce_or_binary_rows(
    tmp_path, monkeypatch, catalogs, change, message
):
    argv, _ = setup(tmp_path, monkeypatch)
    change(tmp_path)
    argv[argv.index("--catalogs") + 1] = str(tmp_path / catalogs)
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert no_triage_run(tmp_path)


@pytest.mark.parametrize(
    ("old", "new", "refused"),
    [
        ("\nMES = 6.2\n", "\nMES = 7.1\n", True),
        ("max_offset_arcsec = 15.0", "max_offset_arcsec = 20.0", False),
    ],
)
def test_triage_takes_only_the_leo_settings_the_threshold_was_counted_under(
    tmp_path, monkeypatch, old, new, refused
):
    argv, _ = setup(tmp_path, monkeypatch)
    text = (ROOT / "criteria" / "triage-v1.toml").read_text()
    assert old in text
    criteria = tmp_path / "triage.toml"
    criteria.write_text(text.replace(old, new))
    argv += ["--criteria-triage", str(criteria)]
    if refused:
        with pytest.raises(SystemExit, match=r"\[leo\] and \[leo_metrics\]"):
            main(argv)
        assert no_triage_run(tmp_path)
    else:
        assert main(argv) == 0


def test_production_triage_refuses_a_search_that_was_not_production(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="s1 is not a production search"):
        main([*argv, "--production"])
    assert no_triage_run(tmp_path)


def test_production_triage_refuses_a_threshold_run_that_was_not_production(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    edit_json(tmp_path / "data/runs/s1/provenance.json", lambda p: p.update(production=True))
    with pytest.raises(SystemExit, match=f"{THRESHOLD_RUN} is not a production threshold run"):
        main([*argv, "--production"])
    assert no_triage_run(tmp_path)


def test_triage_refuses_a_threshold_run_under_another_lock(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    edit_json(
        tmp_path / "data/runs" / THRESHOLD_RUN / "provenance.json",
        lambda p: p.update(uv_lock_sha256="0" * 64),
    )
    with pytest.raises(
        SystemExit, match=f"LEO-Vetter would not judge as in {THRESHOLD_RUN}: uv.lock differs"
    ):
        main(argv)
    assert no_triage_run(tmp_path)


def test_triage_compares_only_the_triaged_stars_light_curves_with_the_null(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    # Star 14's only signal is below the threshold, so no signal of it is judged.
    change_null_star(tmp_path, 14)
    assert main(argv) == 0


# leo-vetter 1.2.0's secondary test negates a bool with ~ (see test_leo.py).
@pytest.mark.filterwarnings("ignore:Bitwise inversion '~' on bool:DeprecationWarning")
def test_real_leo_vetter_metrics_come_back_from_a_worker_and_reach_the_pixel_check(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    lc = make_transit_lc(rp_rs=0.04, period=5.0, t0=1326.1)
    lc.tic = 13
    lc.save(tmp_path / "lc" / "13.npz")
    star = {
        "tic": 13,
        "ra": 10.0,
        "dec": -60.0,
        "rad": 1.0,
        "e_rad": 0.05,
        "mass": 1.0,
        "e_mass": 0.05,
        "teff": 5770.0,
        "e_teff": 100.0,
        "logg": 4.44,
        "dr3_source_id": pd.NA,
    }
    row = {"tic": 13, "rank": 1, "period": 5.0, "t0": 1326.1, "duration": 0.13, "depth": 1.6e-3}
    job = {
        "star": star,
        "rows": [row],
        "known": [],
        "detrend": CRITERIA["detrend"],
        "triage": TRIAGE.values,
    }
    [out] = pickle.loads(pickle.dumps(triage._leo_star_job(job)))  # as a process pool hands it back
    asked = []
    monkeypatch.setattr(
        triage,
        "pixel_check",
        lambda tlc, star, sectors, cfg, tdi: (
            asked.append(asked_ephemeris(tlc.metrics)) or passed("pixels", "ok")
        ),
    )
    pixels = triage._pixel_job(
        {
            "metrics": out["metrics"],
            "star": star,
            "sectors": out["sectors"],
            "cfg": TRIAGE["pixels"],
            "tdi": tmp_path / "tdi",
        }
    )
    assert (
        out["leo"]["outcome"] == "pass"
        and out["metrics"]["tic"] == 13
        and out["sectors"] == [1, 2, 64]
    )
    assert pixels["outcome"] == "pass" and asked[0][0] == pytest.approx(5.0, rel=1e-3)


def publish(tmp_path, monkeypatch, run_id: str) -> int:
    monkeypatch.setattr(triage, "repo_root", lambda: tmp_path / "repo")
    return main(["triage", "publish", "--run", run_id])


def test_triage_publish_copies_the_results_and_the_threshold_they_were_cut_at(
    tmp_path, monkeypatch
):
    argv, _ = setup(tmp_path, monkeypatch)
    main(argv)
    run = latest_triage(tmp_path)
    assert publish(tmp_path, monkeypatch, run.name) == 0
    dest = tmp_path / "repo" / "results" / "triage" / run.name
    names = [
        "known_to_spoc.csv",
        "provenance.json",
        "shortlist.csv",
        "signals.csv",
        "summary.md",
        "threshold.json",
    ]
    assert sorted(p.name for p in dest.iterdir()) == names
    threshold = tmp_path / "data" / "runs" / THRESHOLD_RUN / "threshold.json"
    assert sha256_file(dest / "threshold.json") == sha256_file(threshold)
    with pytest.raises(SystemExit, match="exists"):
        publish(tmp_path, monkeypatch, run.name)


def bare_triage_run(tmp: Path) -> None:
    """A finished triage run that left only its summary."""
    threshold = tmp / "data/runs" / THRESHOLD_RUN / "threshold.json"
    provenance = {
        "stage": "triage",
        "threshold": {"run_id": THRESHOLD_RUN},
        "inputs": {"threshold": {"sha256": sha256_file(threshold)}},
    }
    (write_run(tmp / "data/runs/t1", provenance) / "summary.md").write_text("# t\n")


@pytest.mark.parametrize(
    ("change", "run_id", "message"),
    [
        (
            lambda tmp: (tmp / "data/runs" / THRESHOLD_RUN / "threshold.json").write_text("{}"),
            None,
            "not the threshold file",
        ),
        (lambda tmp: None, "s1", "not a triage run"),
        (bare_triage_run, "t1", "has no shortlist.csv"),
    ],
)
def test_triage_publish_refuses_a_changed_threshold_another_stage_or_missing_outputs(
    tmp_path, monkeypatch, change, run_id, message
):
    argv, _ = setup(tmp_path, monkeypatch)
    main(argv)
    run_id = run_id or latest_triage(tmp_path).name
    change(tmp_path)
    with pytest.raises(SystemExit, match=message):
        publish(tmp_path, monkeypatch, run_id)
    assert not (tmp_path / "repo" / "results" / "triage" / run_id).exists()
