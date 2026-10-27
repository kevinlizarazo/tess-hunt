import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tess_hunt.cli import main

VET = "20261020T000000Z-vetting-run-abc1234-a"
TRIC = "20261020T010000Z-vetting-triceratops-abc1234-b"
RERUN = "20261020T020000Z-vetting-triceratops-abc1234-c"
PIXELS = "20261019T000000Z-benchmark-pixel-completeness-abc1234-d"
# Not in alphabetical order, so the columns show they keep the vetting run's order.
CHECKS = ["novelty", "odd_even", "secondary", "holdout"]
# name: (kind, tic, each check's outcome, the neighbour table's `possible` column or None for no table)
SIGNALS = {
    "TOI-1.01": ("control", 11, ["fail", "pass", "pass", "pass"], [True, False]),
    "TOI-2.01": ("control", 12, ["fail", "pass", "fail", "pass"], [False]),
    "TOI-3.01": ("control", 13, ["fail", "pass", "pass", "inconclusive"], None),
    "TOI-9.01": ("negative_control", 19, ["fail", "fail", "pass", "pass"], [True]),
    # Not a control: left out, and it needs no TRICERATOPS result.
    "5-1": ("candidate", 5, ["pass", "pass", "pass", "pass"], []),
}
PIXEL_ROWS = [
    {"toi": "1.01", "tic": 11, "pixels": "pass", "pixels_reason": "ok", "offset_qual_arcsec": 1.25},
    {
        "toi": "2.01",
        "tic": 12,
        "pixels": "fail",
        "pixels_reason": 'centroid offset 20.5" exceeds 15"',
        "offset_qual_arcsec": 20.5,
    },
    {
        "toi": "3.01",
        "tic": 13,
        "pixels": "inconclusive",
        "pixels_reason": "no sector with data",
        "offset_qual_arcsec": np.nan,
    },
]
RUWE = "RUWE 1.48 > 1.4: an unresolved companion the priors don't condition on"
STOPPED = "TESScut gave 1 of 2 sectors' cutouts"
NO_TABLE = "no neighbour table: Gaia archive failed"
CRASHED = "raised RuntimeError: PyTransit failed"
COLUMNS = [
    "name",
    "kind",
    "tic",
    *CHECKS,
    "neighbours",
    "possible_hosts",
    "pixels",
    "offset_qual_arcsec",
    "triceratops",
    "fpp_mean",
    "fpp_sd",
    "nfpp_mean",
    "nfpp_sd",
    "blockers",
    "triceratops_run",
    "superseded",
]


def checks_json(name: str) -> dict:
    kind, tic, outcomes, possible = SIGNALS[name]
    if possible is None:
        neighbours = {
            "outcome": "inconclusive",
            "reason": NO_TABLE,
            "evidence": {"error": "Gaia archive failed"},
        }
    else:
        neighbours = {
            "outcome": "pass",
            "reason": f"{sum(possible)} of {len(possible)} neighbours could host the signal",
            "evidence": {
                "table": [{"source_id": i, "possible": p} for i, p in enumerate(possible)]
            },
        }
    return {
        "signal": {"name": name, "kind": kind},
        "star": {"tic": tic},
        "checks": [
            {"check": c, "outcome": o, "reason": f"{c} {o}"}
            for c, o in zip(CHECKS, outcomes, strict=True)
        ],
        "neighbours": neighbours,
        # Controls never went through triage.
        "pixels": None,
    }


def tric_json(outcome: str, fpp=0.02, nfpp=1e-4, blockers=(), reason=None) -> dict:
    return {
        "check": "triceratops",
        "outcome": outcome,
        "reason": reason or f"mean FPP {fpp}, mean NFPP {nfpp}",
        "evidence": {
            "fpp_mean": fpp,
            "nfpp_mean": nfpp,
            # No calc_probs run, no spread.
            "fpp_sd": None if fpp is None else 0.003,
            "nfpp_sd": None if nfpp is None else 2e-5,
            "blockers": list(blockers),
            "stopped": None,
            "ruwe": 1.0,
        },
    }


FIRST = {
    "TOI-1.01": tric_json("pass"),
    "TOI-2.01": tric_json("inconclusive", fpp=0.15, nfpp=0.034, blockers=[RUWE], reason=RUWE),
    "TOI-3.01": tric_json("inconclusive", fpp=None, nfpp=None, blockers=[STOPPED], reason=STOPPED),
    "TOI-9.01": tric_json("fail", fpp=1.0, nfpp=0.99),
}


def write_run(data: Path, run_id: str, stage: str, files: dict, **provenance) -> Path:
    """A finished `stage` run holding `files` ({path in the run: content})."""
    path = data / "runs" / run_id
    for name, content in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(content if isinstance(content, str) else json.dumps(content))
    record = {
        "run_id": run_id,
        "stage": stage,
        "production": False,
        "ended_at": "2026-10-20T03:00:00+00:00",
        "criteria": [
            {"file": "criteria/search-v2.toml", "sha256": "a"},
            {"file": "criteria/vet-v3.toml", "sha256": "b"},
        ],
        **provenance,
    }
    (path / "provenance.json").write_text(json.dumps(record))
    return path


def runs(tmp_path, monkeypatch) -> dict[str, Path]:
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    return {
        "vet": write_run(
            data,
            VET,
            "vetting-run",
            {f"signals/{n}/checks.json": checks_json(n) for n in SIGNALS},
            evidence_only=False,
            summary={"errors": {}},
        ),
        "tric": write_run(
            data,
            TRIC,
            "vetting-triceratops",
            {f"signals/{n}/triceratops.json": r for n, r in FIRST.items()},
            vetting_run=VET,
            summary={"errors": {}},
        ),
        # TOI-3.01 again, with every sector's cutout; TOI-1.01 raised, so it wrote no record.
        "rerun": write_run(
            data,
            RERUN,
            "vetting-triceratops",
            {"signals/TOI-3.01/triceratops.json": tric_json("pass", fpp=0.05)},
            vetting_run=VET,
            summary={"errors": {"TOI-1.01": CRASHED}},
        ),
        "pixels": write_run(
            data,
            PIXELS,
            "benchmark-pixel-completeness",
            {"pixels.csv": pd.DataFrame(PIXEL_ROWS).to_csv(index=False)},
            criteria=[{"file": "criteria/triage-v1.toml", "sha256": "c"}],
        ),
    }


def argv(r: dict[str, Path], *tric: str) -> list[str]:
    given = [a for role in tric or ("tric",) for a in ("--triceratops", str(r[role]))]
    return [
        "benchmark",
        "controls",
        "--vet-run",
        str(r["vet"]),
        *given,
        "--pixels",
        str(r["pixels"]),
    ]


def made(tmp_path) -> list[Path]:
    return sorted((tmp_path / "data" / "runs").glob("*-benchmark-controls-*"))


def rates(run: Path, controls: str) -> dict[str, tuple]:
    table = pd.read_csv(run / "pass_rates.csv")
    part = table[table["controls"].eq(controls)].set_index("check")
    return {
        c: tuple(int(part.loc[c, k]) for k in ("signals", "pass", "fail", "inconclusive"))
        for c in part.index
    }


def test_controls_counts_each_check_over_the_known_planets(tmp_path, monkeypatch):
    r = runs(tmp_path, monkeypatch)
    assert main(argv(r)) == 0
    [run] = made(tmp_path)
    table = pd.read_csv(run / "controls.csv", keep_default_na=False).set_index("name")
    assert list(table.reset_index().columns) == COLUMNS
    # Controls first, then the negative controls; the candidate is not a control.
    assert list(table.index) == ["TOI-1.01", "TOI-2.01", "TOI-3.01", "TOI-9.01"]
    assert table.loc["TOI-2.01", "secondary"] == "fail"
    assert table.loc["TOI-3.01", "holdout"] == "inconclusive"
    # TOI-3.01's neighbour table was never built: no count, not none counted.
    assert list(table["possible_hosts"]) == ["1", "0", "", "1"]
    assert table.loc["TOI-3.01", "neighbours"] == "inconclusive"
    assert table.loc["TOI-2.01", "pixels"] == "fail"
    assert float(table.loc["TOI-2.01", "offset_qual_arcsec"]) == 20.5
    # The pixel check ran on the known planets only.
    assert table.loc["TOI-9.01", "pixels"] == table.loc["TOI-9.01", "offset_qual_arcsec"] == ""
    assert table.loc["TOI-2.01", "blockers"] == RUWE
    assert float(table.loc["TOI-2.01", "nfpp_mean"]) == 0.034
    assert set(table["triceratops_run"]) == {TRIC} and set(table["superseded"]) == {""}

    counts = rates(run, "all")
    assert list(counts) == [*CHECKS, "neighbours", "pixels", "triceratops"]
    assert counts == {
        "novelty": (3, 0, 3, 0),
        "odd_even": (3, 3, 0, 0),
        "secondary": (3, 2, 1, 0),
        "holdout": (3, 2, 0, 1),
        "neighbours": (3, 2, 0, 1),
        "pixels": (3, 1, 1, 1),
        "triceratops": (3, 1, 0, 2),
    }
    # Nothing left out: the second table is the first.
    assert rates(run, "without_left_out") == counts
    rate = pd.read_csv(run / "pass_rates.csv").set_index(["controls", "check"])["pass_rate"]
    assert rate[("all", "secondary")] == pytest.approx(2 / 3)

    summary = (run / "summary.md").read_text()
    assert summary.startswith("# vet-v3 controls (")
    assert (
        f"- Vetting run: `{VET}`" in summary and f"- Pixel-completeness run: `{PIXELS}`" in summary
    )
    assert f"  - `{TRIC}`: none\n" in summary
    assert (
        "`pass_rate` is pass over all the `signals` counted, inconclusives in the denominator."
        in summary
    )
    assert "Novelty fails every known planet by design" in summary
    # Each fail and inconclusive of a known planet, by check, with the reason its run gave.
    head = "## Failed and inconclusive controls, by check\n\n"
    flagged = summary.split(head)[1].split("\n\n")[0].split("\n")
    # The header, its rule and one row for each.
    assert len(flagged) == 2 + 3 + 1 + 1 + 1 + 2 + 2
    for line in (
        "| novelty | TOI-1.01 | fail | novelty fail |",
        "| secondary | TOI-2.01 | fail | secondary fail |",
        "| holdout | TOI-3.01 | inconclusive | holdout inconclusive |",
        f"| neighbours | TOI-3.01 | inconclusive | {NO_TABLE} |",
        '| pixels | TOI-2.01 | fail | centroid offset 20.5" exceeds 15" |',
        "| pixels | TOI-3.01 | inconclusive | no sector with data |",
        f"| triceratops | TOI-2.01 | inconclusive | {RUWE} |",
        f"| triceratops | TOI-3.01 | inconclusive | {STOPPED} |",
    ):
        assert line in flagged
    # The negative control's column.
    assert "| odd_even | fail |" in summary
    assert "## Left out\n\nNone." in summary
    assert "## Superseded TRICERATOPS outcomes\n\nNone." in summary
    provenance = json.loads((run / "provenance.json").read_text())
    assert (provenance["vetting_run"], provenance["triceratops_runs"]) == (VET, [TRIC])
    assert provenance["pixel_run"] == PIXELS and provenance["criteria"] == []
    assert {"checks_TOI-9.01", "triceratops_1_TOI-9.01", "pixels"} <= set(provenance["inputs"])
    assert "checks_5-1" not in provenance["inputs"]
    assert provenance["summary"] == {
        "controls": 3,
        "negative_controls": 1,
        "left_out": [],
        "superseded": 0,
    }


def test_a_left_out_control_leaves_only_the_second_table(tmp_path, monkeypatch):
    r = runs(tmp_path, monkeypatch)
    assert main([*argv(r), "--leave-out", "TOI-2.01"]) == 0
    [run] = made(tmp_path)
    assert rates(run, "all")["secondary"] == (3, 2, 1, 0)
    kept = rates(run, "without_left_out")
    assert kept["secondary"] == (2, 2, 0, 0)
    assert kept["pixels"] == (2, 1, 0, 1)
    assert kept["triceratops"] == (2, 1, 0, 1)
    summary = (run / "summary.md").read_text()
    assert "## Pass rates over all 3 controls" in summary
    assert "## Pass rates without the left-out controls (2 controls)" in summary
    assert "## Left out\n\nTOI-2.01\n" in summary
    # Its row stays in the table of fails.
    assert "| secondary | TOI-2.01 | fail | secondary fail |" in summary
    assert json.loads((run / "provenance.json").read_text())["left_out"] == ["TOI-2.01"]


@pytest.mark.parametrize("order", [("tric", "rerun"), ("rerun", "tric")])
def test_the_last_triceratops_run_given_wins(tmp_path, monkeypatch, order):
    r = runs(tmp_path, monkeypatch)
    assert main(argv(r, *order)) == 0
    [run] = made(tmp_path)
    table = pd.read_csv(run / "controls.csv", keep_default_na=False).set_index("name")
    first, last = (r[role].name for role in order)
    used, earlier = ("pass", "inconclusive") if last == RERUN else ("inconclusive", "pass")
    assert table.loc["TOI-3.01", "triceratops"] == used
    assert table.loc["TOI-3.01", "triceratops_run"] == last
    reason = {RERUN: "mean FPP 0.05, mean NFPP 0.0001", TRIC: STOPPED}[first]
    assert table.loc["TOI-3.01", "superseded"] == f"{first}: {earlier}, {reason}"
    # The others were judged by the first run only.
    assert set(table.drop(index="TOI-3.01")["triceratops_run"]) == {TRIC}
    assert set(table.drop(index="TOI-3.01")["superseded"]) == {""}
    summary = (run / "summary.md").read_text()
    assert f"| TOI-3.01 | {first} | {earlier} | {reason} | {last} |" in summary
    # Each run in the order given, with what it failed to judge: the rerun's crash on TOI-1.01 shows.
    errors = {TRIC: "none", RERUN: f"TOI-1.01 ({CRASHED})"}
    listed = "\n".join(f"  - `{run_id}`: {errors[run_id]}" for run_id in (first, last))
    assert listed in summary
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["triceratops_runs"] == [first, last]
    assert {"triceratops_1_TOI-3.01", "triceratops_2_TOI-3.01"} <= set(provenance["inputs"])
    assert provenance["summary"]["superseded"] == 1


def edit(path: Path, **changes) -> None:
    file = path / "provenance.json"
    file.write_text(json.dumps({**json.loads(file.read_text()), **changes}))


def pixel_rows(r: dict[str, Path], rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(r["pixels"] / "pixels.csv", index=False)


def edit_checks(r: dict[str, Path], name: str, change) -> None:
    file = r["vet"] / "signals" / name / "checks.json"
    checks = json.loads(file.read_text())
    change(checks)
    file.write_text(json.dumps(checks))


def only_the_candidate(r: dict[str, Path]) -> None:
    for name, (kind, *_) in SIGNALS.items():
        if kind != "candidate":
            shutil.rmtree(r["vet"] / "signals" / name)


@pytest.mark.parametrize(
    "prepare, extra, message",
    [
        (
            lambda r: edit(r["vet"], evidence_only=True),
            [],
            f"{VET} is an evidence-only vetting run",
        ),
        (
            lambda r: edit(r["vet"], summary={"errors": {"TOI-1.01": "raised"}}),
            [],
            f"{VET} failed to vet TOI-1.01",
        ),
        (
            lambda r: edit(r["vet"], stage="vetting-triceratops"),
            [],
            f"{VET} is not a vetting-run run",
        ),
        (
            lambda r: edit(r["tric"], vetting_run="other"),
            [],
            f"{TRIC} ran TRICERATOPS on vetting run other, not {VET}",
        ),
        (
            lambda r: (r["tric"] / "signals" / "TOI-9.01" / "triceratops.json").unlink(),
            [],
            "no TRICERATOPS run given judged TOI-9.01",
        ),
        (
            lambda r: pixel_rows(r, PIXEL_ROWS[:2]),
            [],
            f"{PIXELS}'s planets are not {VET}'s controls: only in the pixel run none; only in the "
            "vetting run TOI-3.01 (TIC 13)",
        ),
        (
            lambda r: pixel_rows(r, [*PIXEL_ROWS[:2], {**PIXEL_ROWS[2], "tic": 14}]),
            [],
            "only in the pixel run TOI-3.01 (TIC 14); only in the vetting run TOI-3.01 (TIC 13)",
        ),
        (
            None,
            ["--leave-out", "TOI-9.01"],
            f"--leave-out takes a control {VET} vetted, not TOI-9.01",
        ),
        (None, ["--leave-out", "TOI-7.01"], "--leave-out takes a control"),
        (None, ["--triceratops", "{tric}"], "a TRICERATOPS run is given more than once"),
        (None, ["--production"], f"needs production runs, not {VET}, {TRIC}, {PIXELS}"),
        (lambda r: edit(r["tric"], ended_at=None), [], f"{TRIC} has not finished"),
        (None, ["--triceratops", "{pixels}"], f"{PIXELS} is not a vetting-triceratops run"),
        # The last --pixels given is the one read.
        (None, ["--pixels", "{tric}"], f"{TRIC} is not a benchmark-pixel-completeness run"),
        (
            lambda r: edit_checks(r, "TOI-2.01", lambda c: c["checks"].pop()),
            [],
            "TOI-2.01's checks (novelty, odd_even, secondary) differ from TOI-1.01's "
            "(novelty, odd_even, secondary, holdout)",
        ),
        (
            lambda r: edit_checks(r, "TOI-9.01", lambda c: c["checks"].reverse()),
            [],
            "TOI-9.01's checks (holdout, secondary, odd_even, novelty) differ from TOI-1.01's",
        ),
        (only_the_candidate, [], f"{VET} vetted no control or negative control"),
    ],
    ids=[
        "evidence only",
        "vet errors",
        "not a vetting run",
        "another vetting run",
        "no triceratops",
        "a planet missing",
        "another star",
        "leave out a negative control",
        "leave out an unknown name",
        "a run twice",
        "production",
        "unfinished",
        "not a triceratops run",
        "not a pixel run",
        "a check missing",
        "checks in another order",
        "no control",
    ],
)
def test_controls_refuses(tmp_path, monkeypatch, prepare, extra, message):
    r = runs(tmp_path, monkeypatch)
    if prepare:
        prepare(r)
    extra = [a.format(**{role: str(path) for role, path in r.items()}) for a in extra]
    with pytest.raises(SystemExit, match=re.escape(message)):
        main([*argv(r), *extra])
    assert not made(tmp_path)
