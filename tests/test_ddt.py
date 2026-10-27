import json
import tomllib
from pathlib import Path

import pytest
from test_dossier import section, table_rows

from tess_hunt import ddt, dossier, provenance
from tess_hunt.cli import main

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "results" / "vetting" / "241522065-1"
FACTS = REPO / "results" / "ddt" / "241522065-1" / "facts.toml"
SECTORS = [112, 113, 114]
# The record's files the proposal reads.
READ = (
    "checks.json",
    "triceratops.json",
    "literature.json",
    "call.toml",
    "review.json",
    "provenance-checks.json",
)


def record(path: Path) -> Path:
    """A copy of 241522065-1's published record, holding the files the proposal reads, for a test to edit."""
    path.mkdir(parents=True)
    for name in READ:
        (path / name).write_bytes((RECORD / name).read_bytes())
    return path


def edit_checks(path: Path, change) -> None:
    checks = json.loads((path / "checks.json").read_text())
    change(checks)
    (path / "checks.json").write_text(json.dumps(checks))


def test_values_come_from_the_record():
    values = ddt.values(RECORD, FACTS, [113, 114])
    checks = json.loads((RECORD / "checks.json").read_text())
    prior = checks["fit_prior"]
    tric = json.loads((RECORD / "triceratops.json").read_text())["evidence"]
    assert values["period"] == f"{prior['period']['median']:.6f}" == "17.436716"
    assert values["fpp"] == f"{tric['fpp_mean']:.3g}" == "0.0215"
    assert values["nfpp"] == "0.000148" and values["tic"] == "241522065"

    # Each number as the published dossier shows it.
    page = (RECORD / "dossier.md").read_text()
    for shown in (
        f"Teff {values['teff']} K, radius {values['radius_sun']} solar radii, Tmag {values['tmag']}",
        f"depth {values['depth_ppm']} ppm",
        f"Rp {values['rp_rearth']} Earth radii (16th to 84th percentile {values['rp_lo']} to {values['rp_hi']})",
        f"period {values['period']} d (sd {values['period_sd']}), t0 BTJD {values['t0']} (sd {values['t0_sd']} d)",
        f"mean FPP {values['fpp']}",
        f"mean NFPP {values['nfpp']}",
        f"combined depth is {values['snr']} sigma",
        f"In the sectors fetched, the star never had SPOC 2-min data ({values['products']}).",
        # The counts and bars the proposal states, as the checks' own reasons give them.
        f"Held-out seasons: {values['holdout_outcome']}, {values['n_tested']} season(s) could be tested;",
        f"| triceratops | {values['tric_outcome']} | mean FPP {values['fpp']} < {values['fpp_pass']} and mean "
        f"NFPP {values['nfpp']} < {values['nfpp_pass']} over {values['tric_runs']} run(s): likely a planet |",
        f"Criteria | search-v2, {values['criteria']} |",
    ):
        assert shown in page, shown
    assert values["duration_h"] == f"{checks['window_duration']['days'] * 24:.2f}" == "4.03"
    # The checks that did not pass, the TCE novelty matched, and the held-out seasons by their counts.
    assert (values["n_checks"], values["n_passed"]) == (str(len(checks["checks"])), "7")
    assert values["inconclusive"] == "novelty and holdout"
    assert values["tce"] == "ExoMiner vetting_catalog_FFI 241522065-1-S38"
    seasons = next(c for c in checks["checks"] if c["check"] == "holdout")["evidence"]["seasons"]
    assert [s["training_seasons"] for s in seasons] == [int(values["season_training"])] * 2
    assert (values["n_seasons"], values["season_years"]) == ("2", "2021 and 2023")
    assert values["min_training_seasons"] == "2"

    # Every window in the asked sectors and none other, each row as the dossier shows it.
    rows = table_rows(values["windows"])[2:]
    asked = [w for w in checks["windows"] if w["sector"] in (113, 114)]
    assert len(rows) == len(asked) == int(values["n_windows"]) == 3
    published = table_rows(section(page, "Next TESS looks"))
    for row, w in zip(rows, asked, strict=True):
        assert row.startswith(f"| {w['sector']} | {w['epoch']} | {w['mid_btjd']:.3f} | "), row
        assert any(p.startswith(row) for p in published), row
    assert "| 112 |" not in values["windows"]
    with pytest.raises(ValueError, match="111"):
        ddt.values(RECORD, FACTS, [111, 112])

    # The dates are those of the sectors asked for; a sector facts.toml gives no date for raises.
    assert (values["first_start"], values["last_end"]) == ("2027-01-17", "2027-03-14")
    whole = ddt.values(RECORD, FACTS, SECTORS)
    assert (whole["first_start"], whole["last_end"]) == ("2026-12-22", "2027-03-14")
    with pytest.raises(KeyError, match="s113_end"):
        ddt.values(RECORD, FACTS, [112, 113])

    # The facts by their values, the review's claims word for word, the call's deciding evidence.
    facts = tomllib.loads(FACTS.read_text())
    for key, fact in facts.items():
        assert values[f"fact_{key}"] == str(fact["value"]), key
    assert values["facts_read"] == "2026-10-27"
    assert values["fact_sources"].split("; ") == list(
        dict.fromkeys(f["source"] for f in facts.values())
    )
    review = json.loads((RECORD / "review.json").read_text())
    # Each claim as the dossier quotes it.
    for finding in review["findings"]:
        key = f"review_{finding['id']}"
        assert f"Claim: {values[key]}\n" in page, key
    assert values["deciding_evidence"].startswith("A third TESS season: sectors 112 to 114")

    # No Gaia DR3 data: results/ddt/ is CC BY 4.0 whole, and a DR3 source id is Gaia data.
    assert values["names"] == "HIP 67102, HD 119555, TYC 8663-626-1, 2MASS J13451278-5318310"
    assert str(checks["star"]["dr3_source_id"]) not in " ".join(values.values())


def test_render_fails_on_a_missing_value(tmp_path):
    template = tmp_path / "proposal.template.md"
    template.write_text("FPP $fpp, NFPP $nfpp; period $period d\n")
    good = record(tmp_path / "good")
    assert (
        ddt.render(template, good, FACTS, SECTORS)
        == "FPP 0.0215, NFPP 0.000148; period 17.436716 d\n"
    )

    no_triceratops = record(tmp_path / "no-triceratops")
    (no_triceratops / "triceratops.json").unlink()
    with pytest.raises(KeyError, match="fpp"):
        ddt.render(template, no_triceratops, FACTS, SECTORS)

    no_prior = record(tmp_path / "no-fit-prior")
    edit_checks(no_prior, lambda c: c.update(fit_prior=None))
    with pytest.raises(KeyError, match="period"):
        ddt.render(template, no_prior, FACTS, SECTORS)

    # A NaN is no value either: the proposal never shows "nan" or "missing".
    nan = record(tmp_path / "nan")
    tric = json.loads((nan / "triceratops.json").read_text())
    tric["evidence"]["fpp_mean"] = float("nan")
    (nan / "triceratops.json").write_text(json.dumps(tric))
    with pytest.raises(KeyError, match="fpp"):
        ddt.render(template, nan, FACTS, SECTORS)

    # An empty list is no value either: "the star's Sectors  are left out" never renders.
    lists = tmp_path / "lists.template.md"
    for key, change in (
        ("suspect_sectors", lambda c: c.update(dropped_suspect=[])),
        ("families", lambda c: c.update(families={})),
    ):
        lists.write_text(f"${key}\n")
        assert ddt.render(lists, good, FACTS, SECTORS)
        empty = record(tmp_path / f"no-{key}")
        edit_checks(empty, change)
        with pytest.raises(KeyError, match=key):
            ddt.render(lists, empty, FACTS, SECTORS)

    # A template naming a value nobody filled in raises too.
    template.write_text("$unfilled\n")
    with pytest.raises(KeyError, match="unfilled"):
        ddt.render(template, good, FACTS, SECTORS)


def test_the_review_is_quoted_as_the_dossier_quotes_it(tmp_path, monkeypatch):
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    path = record(tmp_path / "record")
    review = json.loads((path / "review.json").read_text())
    f6 = next(f for f in review["findings"] if f["id"] == "F6")
    f6["claim"] += f" See {home}/notes.txt."
    (path / "review.json").write_text(json.dumps(review))
    quoted = ddt.values(path, FACTS, SECTORS)["review_F6"]
    assert quoted == dossier._scrub(f6["claim"]) and quoted.endswith(" See ~/notes.txt.")


def test_targets_csv():
    # The TESS office's target-list template: its header block, the column line, one row per target, CRLF.
    assert ddt.targets_csv(RECORD, "planet candidate;transit").split("\r\n") == [
        "# DDT PI: <proposer name>",
        "# Cadence: 2m",
        "# Subject: Planet candidate 241522065-1 on TIC 241522065",
        "# DDT: <to be supplied by TESS team>",
        "#",
        "# Original filename: targets.csv",
        "# Created by: Name",
        "# Created on: date",
        "# Number of targets: 1",
        "# ",
        "# Column 1: TIC ID",
        "# Column 2: Priority (floating point: 0=low, 1=high)",
        "# Column 3: Keywords (separated by semi-colon)",
        "# tic,priority,keywords",
        "241522065,1.0,planet candidate;transit",
        "",
    ]


def test_ddt_render_writes_the_proposal_and_the_target_list(tmp_path):
    template = tmp_path / "proposal.template.md"
    template.write_text("TIC $tic: period $period d.\n\n$windows\n")
    out = tmp_path / "out"
    argv = [
        "ddt",
        "render",
        "--record",
        str(RECORD),
        "--template",
        str(template),
        "--facts",
        str(FACTS),
    ]
    assert main([*argv, "--sectors", "112", "113", "114", "--out", str(out)]) == 0
    assert (out / "proposal.md").read_text() == ddt.render(template, RECORD, FACTS, SECTORS)
    assert (out / "targets.csv").read_bytes() == ddt.targets_csv(RECORD, ddt.KEYWORDS).encode()


def test_the_committed_proposal_is_its_render():
    # results/ddt/241522065-1/ holds the proposal exactly as `ddt render` makes it, so a template edit left
    # unrendered, or a hand edit to the output, fails here.
    out = FACTS.parent
    proposal = (out / "proposal.md").read_text()
    targets = (out / "targets.csv").read_bytes().decode()
    assert proposal == ddt.render(out / "proposal.template.md", RECORD, FACTS, SECTORS)
    assert targets == ddt.targets_csv(RECORD, ddt.KEYWORDS)
    # The F6 quote, word for word and said to be one (decision 0037).
    review = json.loads((RECORD / "review.json").read_text())
    [f6] = [f["claim"] for f in review["findings"] if f["id"] == "F6"]
    assert f'Quoted word for word from the review\'s finding F6: "{dossier._scrub(f6)}"' in proposal
    # Plain sentences, not the checks' reason strings, and placeholders that show in rendered Markdown.
    assert "(s)" not in proposal and "<" not in proposal
    assert "[proposer name] ([institution] | [contact email])" in proposal
    assert "[repository URL]" in proposal
    # No machine path, no one named and no Gaia DR3 source id.
    checks = json.loads((RECORD / "checks.json").read_text())
    for text in (proposal, targets):
        assert provenance.scrub(text) == text
        assert not any(n.lower() in text.lower() for n in provenance.maintainer() or ())
        assert str(checks["star"]["dr3_source_id"]) not in text
