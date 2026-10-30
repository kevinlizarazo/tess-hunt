import json
import shutil
import tomllib
from pathlib import Path

import pytest
from test_dossier import section, table_rows

from tess_hunt import ddt, dossier, provenance
from tess_hunt.cli import main
from tess_hunt.provenance import sha256_file

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
    "provenance-triceratops.json",
    "checks-with-suspect.json",
)


def record(path: Path) -> Path:
    """A copy of 241522065-1's published record, holding the files the proposal reads, for a test to edit."""
    path.mkdir(parents=True)
    for name in READ:
        (path / name).write_bytes((RECORD / name).read_bytes())
    return path


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def edit_checks(path: Path, change) -> None:
    edit_json(path / "checks.json", change)


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
        f"period {values['period']} d (sd ",
        f"t0 BTJD {values['t0']} (sd ",
        f"combined depth is {values['snr']} sigma",
        # The TRICERATOPS bars the proposal states, as the check's own reason gives them.
        f"| triceratops | pass | mean FPP {values['fpp']} < {values['fpp_pass']} and mean "
        f"NFPP {values['nfpp']} < {values['nfpp_pass']} over {values['tric_runs']} run(s): likely a planet |",
    ):
        assert shown in page, shown
    assert values["tric_pass"] == "passes"
    # The sds in plain units: the dossier's 9.7e-05 d and 0.0031 d.
    fit = prior["ephemeris"]
    assert values["period_sd_s"] == f"{fit['period']['sd'] * 86400:.1f}" == "8.4"
    assert values["t0_sd_min"] == f"{fit['t0']['sd'] * 1440:.1f}" == "4.5"
    assert values["period_short"] == "17.4"
    assert values["duration_h"] == f"{checks['window_duration']['days'] * 24:.2f}" == "4.03"
    # The products by name only: QLP's S99 cadence in the record is MAST's metadata, not the data's.
    assert values["products"] == "QLP and TESS-SPOC" and values["vetted_products"] == "TESS-SPOC"
    assert values["hip"] == "HIP 67102" and values["bright_limit"] == "7"

    # The checks that did not pass, in words; the TCE's sector; the held-out seasons by their counts.
    assert (values["n_checks"], values["n_passed"]) == (str(len(checks["checks"])), "7")
    assert values["inconclusive"] == "the check against known objects and the held-out season test"
    assert values["tce_sectors"] == "38"
    holdout = next(c for c in checks["checks"] if c["check"] == "holdout")
    assert "Held-out seasons: inconclusive, 0 season(s) could be tested;" in page
    assert values["tested"] == "none"
    seasons = holdout["evidence"]["seasons"]
    assert [s["training_seasons"] for s in seasons] == [int(values["season_training"])] * 2
    assert (values["n_seasons"], values["season_years"]) == ("2", "2021 and 2023")
    assert values["min_training_seasons"] == "2"
    [second] = checks["other_signals"]
    assert values["second_depth_ppm"] == f"{second['depth'] * 1e6:.0f}" == "127"
    assert values["second_period"] == f"{second['period']:.2f}" == "5.58"
    # With the timing-suspect sectors kept in, the held-out check passes (the dossier's evidence-only table).
    assert values["holdout_with_suspect"] == "passes"

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

    # The facts by their values, the target lists the star is on none of.
    facts = tomllib.loads(FACTS.read_text())
    for key, fact in facts.items():
        assert values[f"fact_{key}"] == str(fact["value"]), key
    assert values["facts_read"] == "2026-10-27"
    assert values["not_on_lists"] == facts["two_minute_lists"]["value"]

    # The review: who made it, each claim as the dossier quotes it, and that every finding is a note.
    review = json.loads((RECORD / "review.json").read_text())
    assert (values["review_model"], values["review_date"]) == ("claude-opus-5-5", "2026-10-21")
    assert values["review_all_notes"] == str(len(review["findings"])) == "7"
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
    edit_json(nan / "triceratops.json", lambda t: t["evidence"].update(fpp_mean=float("nan")))
    with pytest.raises(KeyError, match="fpp"):
        ddt.render(template, nan, FACTS, SECTORS)

    def check(name):
        return lambda c: next(x for x in c["checks"] if x["check"] == name)

    # An empty list is no value either ("the star's Sectors  are left out" never renders), and a sentence that holds
    # only for some records renders only for them.
    one = tmp_path / "one.template.md"
    for key, path, change in (
        ("suspect_sectors", "checks.json", lambda c: c.update(dropped_suspect=[])),
        ("vetted_sectors", "checks.json", lambda c: c.update(families={})),
        # A check the proposal has no plain name for, or one that failed, is not named as inconclusive.
        ("inconclusive", "checks.json", lambda c: check("shape")(c).update(outcome="inconclusive")),
        ("inconclusive", "checks.json", lambda c: check("holdout")(c).update(outcome="fail")),
        # "Passes" only for a pass, "all notes" only when every finding is one.
        ("tric_pass", "triceratops.json", lambda t: t.update(outcome="inconclusive")),
        ("review_all_notes", "review.json", lambda r: r["findings"][0].update(rating="hold")),
        ("second_depth_ppm", "checks.json", lambda c: c.update(other_signals=[])),
        ("second_period", "checks.json", lambda c: c.update(other_signals=[])),
        (
            "holdout_with_suspect",
            "checks-with-suspect.json",
            lambda c: check("holdout")(c).update(outcome="inconclusive"),
        ),
    ):
        one.write_text(f"${key}\n")
        assert ddt.render(one, good, FACTS, SECTORS)
        changed = tmp_path / f"{key}-{path}"
        if changed.exists():
            shutil.rmtree(changed)
        edit_json(record(changed) / path, change)
        with pytest.raises(KeyError, match=key):
            ddt.render(one, changed, FACTS, SECTORS)

    # The target lists are named only when facts.toml finds the star on none of them.
    on_a_list = tmp_path / "facts.toml"
    on_a_list.write_text(FACTS.read_text().replace("241522065, ", ""))
    one.write_text("$not_on_lists\n")
    with pytest.raises(KeyError, match="not_on_lists"):
        ddt.render(one, good, on_a_list, SECTORS)

    # A template naming a value nobody filled in raises too.
    template.write_text("$unfilled\n")
    with pytest.raises(KeyError, match="unfilled"):
        ddt.render(template, good, FACTS, SECTORS)


def test_criteria_come_from_the_files_the_runs_read(tmp_path, monkeypatch):
    # The held-out check's minimum from the vetting run's criteria, TRICERATOPS's bars from the TRICERATOPS run's.
    repo = tmp_path / "repo"
    (repo / "criteria").mkdir(parents=True)
    (repo / "other").mkdir()
    vet = REPO / "criteria" / "vet-v3.toml"
    shutil.copy(vet, repo / "criteria" / "vet-v3.toml")
    other = repo / "other" / "vet-v3.toml"
    other.write_text(vet.read_text().replace("fpp_pass = 0.5 ", "fpp_pass = 0.4 "))
    monkeypatch.setattr(ddt, "repo_root", lambda: repo)
    path = record(tmp_path / "record")

    def tric_criteria(entry):
        edit_json(path / "provenance-triceratops.json", lambda p: p.update(criteria=[entry]))

    tric_criteria({"file": "other/vet-v3.toml", "sha256": sha256_file(other)})
    values = ddt.values(path, FACTS, SECTORS)
    assert (values["fpp_pass"], values["min_training_seasons"]) == ("0.4", "2")

    # A run that names no file for the criteria version, or a file that changed since the run read it, is refused.
    tric_criteria({"file": "criteria/search-v2.toml", "sha256": "0" * 64})
    with pytest.raises(ValueError, match="no single criteria file for vet-v3"):
        ddt.values(path, FACTS, SECTORS)
    tric_criteria({"file": "other/vet-v3.toml", "sha256": sha256_file(vet)})
    with pytest.raises(ValueError, match="other/vet-v3.toml is not the file"):
        ddt.values(path, FACTS, SECTORS)


def test_the_review_is_quoted_as_the_dossier_quotes_it(tmp_path, monkeypatch):
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    path = record(tmp_path / "record")
    review = json.loads((path / "review.json").read_text())
    f6 = next(f for f in review["findings"] if f["id"] == "F6")
    values = ddt.values(path, FACTS, SECTORS)
    # Each phrase quoted from the evidence is in it word for word.
    for key, (finding, text) in ddt.QUOTES.items():
        assert finding == "F6" and values[key] == text and text in f6["evidence"], key
    f6["claim"] += f" See {home}/notes.txt."
    f6["evidence"] = f6["evidence"].replace("tier C", "tier B")
    (path / "review.json").write_text(json.dumps(review))
    values = ddt.values(path, FACTS, SECTORS)
    assert values["review_F6"] == dossier._scrub(f6["claim"])
    assert values["review_F6"].endswith(" See ~/notes.txt.")
    # A phrase the evidence no longer holds is not quoted.
    assert "quote_eumemic_tier" not in values and "quote_eumemic_mes" in values


def test_targets_csv():
    # The TESS office's target-list template: its header block, the column line, one row per target, CRLF.
    assert ddt.targets_csv(RECORD, "planet candidate;transit").split("\r\n") == [
        "# DDT PI: <proposer name>",
        "# Cadence: 2m",
        "# Subject: Transiting planet candidate on TIC 241522065",
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
    # The proposal states the record's values in its own words and quotes no finding (decision 0039, 2026-10-28),
    # read with the template's line breaks as spaces.
    review = json.loads((RECORD / "review.json").read_text())
    flowed = " ".join(proposal.split())
    for finding in review["findings"]:
        assert dossier._scrub(finding["claim"]) not in flowed, finding["id"]
    assert "word for word" not in flowed
    # Plain sentences for readers outside the project: no reason strings, run ids, criteria names or finding ids,
    # and placeholders that show in rendered Markdown.
    for internal in ("(s)", "20261014T", "vet-v3", "finding F", "<proposer", "<repository"):
        assert internal not in proposal, internal
    # The text is pasted into the office's .tex template (OT1 encoding), so it holds none of the characters LaTeX
    # treats specially in running text ("<" prints as an inverted mark there, "&" stops compilation). Left out: the
    # Markdown heading marks, the table, and the author line, which is the template's own placeholder.
    pasted = [
        line.lstrip("#")
        for line in proposal.splitlines()
        if not line.startswith(("|", "[proposer name]"))
    ]
    for char in "<>&%$#_|~^\\{}`":
        assert not any(char in line for line in pasted), char
    assert "[proposer name] ([institution] | [contact email])" in proposal
    assert "[repository URL]" in proposal
    # No machine path, no one named and no Gaia DR3 source id.
    checks = json.loads((RECORD / "checks.json").read_text())
    for text in (proposal, targets):
        assert provenance.scrub(text) == text
        assert not any(n.lower() in text.lower() for n in provenance.maintainer() or ())
        assert str(checks["star"]["dr3_source_id"]) not in text
