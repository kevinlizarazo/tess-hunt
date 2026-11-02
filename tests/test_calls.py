import json
import re
from pathlib import Path

import pytest

from tess_hunt import calls
from tess_hunt.config import load_criteria

ROOT = Path(__file__).resolve().parents[1]
NAME = "44926986-1"
EPHEMERIS = {"period": 24.1145, "t0": 1556.3563, "duration": 0.125, "depth": 0.00078}
CHECKS = [
    "novelty",
    "odd_even",
    "secondary",
    "sector_depth",
    "holdout",
    "signal_present",
    "shape",
    "density",
    "radius",
]
REFUTED = {"refuted": True, "reason": "the offset is the PSF's, not a shift"}
STANDS = {"refuted": False, "reason": "reproduced from the run"}
REVIEW = {
    "signal": NAME,
    "model": "claude-opus-5-5",
    "date": "2026-10-27",
    "findings": [
        {
            "id": "F1",
            "lens": "real_new",
            "rating": "note",
            "claim": "one sector carries most of the depth",
            "evidence": "sector_depth",
            "refuters": [],
        },
        {
            "id": "F2",
            "lens": "on_star",
            "rating": "hold",
            "claim": "a star 12.5 arcsec away could host the dip",
            "evidence": "neighbours.csv",
            "refuters": [STANDS, STANDS],
        },
        {
            "id": "F3",
            "lens": "planet",
            "rating": "kill",
            "claim": "the secondary at phase 0.76 is an eccentric eclipse",
            "evidence": "modshift",
            "refuters": [STANDS, REFUTED],
        },
    ],
    "hits_flagged": ["2306.16587"],
    "summary": "One hold stands.",
}
PASSED = """\
signal = "44926986-1"
outcome = "passed"
date = 2026-10-28
reasons = "Every check and TRICERATOPS passed; the one hold is answered."
rests_on = ["triceratops", "F2"]
criteria = ["vet-v3", "triage-v1"]
hits_read = ["2306.16587"]

[answers]
F2 = "TRICERATOPS weighed that star and the centroids sit on the target."

[sentences]
not_a_binary = "Odd and even depths agree and nothing shows at any phase."
not_another_star = "TRICERATOPS weighed every star that could host it."
not_an_artefact_or_known = "Each season shows it and nobody lists it."
"""


TRIAGE_NOT_RUN = {
    "check": "pixels",
    "outcome": "inconclusive",
    "reason": "not run: novelty or the flux tests did not pass",
    "evidence": {},
}


def edit(text: str, old: str, new: str) -> str:
    assert old in text
    return text.replace(old, new)


def signal_dir(
    tmp_path: Path,
    call: str | None = PASSED,
    review: dict | None = REVIEW,
    outcomes: dict | None = None,
    kind: str = "candidate",
    novelty_category: str | None = None,
    triceratops: str | None = "pass",
    literature: str | None = "pass",
    planets: list | None = None,
    name: str = NAME,
    pixels: str | None = "pass",
) -> Path:
    """A signal's record as `vetting publish` lays it out, with only what the call is checked against. `pixels` is
    the pixel check's outcome where the record keeps it: the second list's pixels.json for a second-list row, triage's
    evidence in checks.json for the rest."""
    path = tmp_path / name
    path.mkdir(parents=True)
    outcomes = outcomes or {}
    pixel = pixels and {
        "check": "pixels",
        "outcome": pixels,
        "reason": f"pixels {pixels}",
        "evidence": {},
    }
    checks = [
        {
            "check": name,
            "outcome": outcomes.get(name, "pass"),
            "reason": f"{name} {outcomes.get(name, 'pass')}",
            "evidence": {"category": novelty_category} if name == "novelty" else {},
        }
        for name in CHECKS
    ]
    record = {
        "signal": {"name": name, "kind": kind},
        "ephemeris": EPHEMERIS,
        "checks": checks,
        "criteria_version": "vet-v3",
        "evidence_only": False,
        "neighbours": {
            "check": "neighbours",
            "outcome": "pass",
            "reason": "7 of 29",
            "evidence": {},
        },
        # Triage runs its pixel check only on novelty passes, so a second-list row's triage evidence says so.
        "pixels": pixel if kind != "second" else TRIAGE_NOT_RUN,
    }
    (path / "checks.json").write_text(json.dumps(record))
    if pixel and kind == "second":
        (path / "pixels.json").write_text(json.dumps(pixel))
    criteria = [
        {
            "file": f"criteria/{name}.toml",
            "sha256": load_criteria(ROOT / "criteria" / f"{name}.toml").sha256,
        }
        for name in ("search-v2", "vet-v3")
    ]
    (path / "provenance-checks.json").write_text(
        json.dumps({"stage": "vetting-run", "criteria": criteria})
    )
    if triceratops:
        (path / "triceratops.json").write_text(
            json.dumps(
                {
                    "check": "triceratops",
                    "outcome": triceratops,
                    "reason": f"TRICERATOPS {triceratops}",
                }
            )
        )
    if literature:
        exofop = {"status": "ok", "planets": [] if planets is None else planets}
        (path / "literature.json").write_text(
            json.dumps(
                {
                    "check": "literature",
                    "outcome": literature,
                    "reason": f"literature {literature}",
                    "search": {"exofop": exofop},
                }
            )
        )
    if review is not None:
        (path / "review.json").write_text(json.dumps(review))
    if call is not None:
        (path / "call.toml").write_text(call)
    return path


def test_confirmed_finding_needs_both_refuters_unrefuted():
    # F1 is a note, F3 has one refuter that refuted it: only F2 is confirmed.
    assert calls.confirmed(REVIEW) == ["F2"]
    unrefuted = {**REVIEW["findings"][2], "refuters": [STANDS, STANDS]}
    assert calls.confirmed({**REVIEW, "findings": [unrefuted]}) == ["F3"]
    both_refuted = {**REVIEW["findings"][1], "refuters": [REFUTED, REFUTED]}
    assert calls.confirmed({**REVIEW, "findings": [both_refuted]}) == []
    # A finding no refuter has looked at yet has not been refuted, so it stands.
    unchecked = {**REVIEW["findings"][1], "refuters": []}
    assert calls.confirmed({**REVIEW, "findings": [unchecked]}) == ["F2"]


def test_a_pass_the_evidence_supports_has_no_problems(tmp_path):
    assert calls.problems(signal_dir(tmp_path)) == []


PLANET_AT_THE_PERIOD = {
    "provenance": "TOIs (TESS Project)",
    "name": "TIC 44926986.01",
    "toi": "TOI 9999.01",
    "period": EPHEMERIS["period"] * 2,
    "epoch_bjd": 2459000.5,
    "duration_hours": 3.0,
    "disposition": "PC",
}

# Without triceratops.json or review.json, a call resting on them would be refused for that alone.
RESTS_ON_A_CHECK = edit(PASSED, '["triceratops", "F2"]', '["odd_even"]')
REFUSED = [
    ({"outcomes": {"odd_even": "fail"}}, "odd_even is fail"),
    ({"outcomes": {"holdout": "inconclusive"}}, "holdout is inconclusive"),
    ({"literature": "inconclusive"}, "the literature search is inconclusive"),
    ({"literature": None}, "no literature.json"),
    ({"triceratops": "inconclusive"}, "TRICERATOPS is inconclusive"),
    ({"triceratops": None, "call": RESTS_ON_A_CHECK}, "no triceratops.json"),
    ({"call": edit(PASSED, 'F2 = "TRICERATOPS', 'F9 = "TRICERATOPS')}, "F2 .*no answer"),
    (
        {
            "call": edit(
                PASSED,
                'not_another_star = "TRICERATOPS weighed every star that could host it."\n',
                "",
            )
        },
        "not_another_star",
    ),
    ({"call": edit(PASSED, 'hits_read = ["2306.16587"]', "hits_read = []")}, "2306.16587"),
    ({"call": edit(PASSED, 'hits_read = ["2306.16587"]\n', "")}, "hits_read"),
    ({"review": None, "call": RESTS_ON_A_CHECK}, "no review.json"),
    ({"planets": [PLANET_AT_THE_PERIOD]}, "TOI 9999.01"),
    ({"novelty_category": "known_to_spoc", "outcomes": {"novelty": "inconclusive"}}, "novelty"),
]


@pytest.mark.parametrize("change, message", REFUSED)
def test_a_pass_the_evidence_does_not_support_is_refused(tmp_path, change, message):
    found = calls.problems(signal_dir(tmp_path, **change))
    assert found, change
    assert any(re.search(message, p) for p in found), found


def test_a_pass_on_an_evidence_only_vet_is_refused(tmp_path):
    path = signal_dir(tmp_path)
    checks = json.loads((path / "checks.json").read_text())
    (path / "checks.json").write_text(json.dumps({**checks, "evidence_only": True}))
    assert calls.problems(path) == ["checks.json is an evidence-only vet, which never makes a call"]


def test_a_pass_on_criteria_changed_since_the_vetting_run_is_refused(tmp_path):
    # Bar 2 matches ExoFOP's rows at the period tolerance of the criteria the vetting run recorded.
    path = signal_dir(tmp_path)
    made = json.loads((path / "provenance-checks.json").read_text())
    made["criteria"][0]["sha256"] = "0" * 64
    (path / "provenance-checks.json").write_text(json.dumps(made))
    assert calls.problems(path) == [
        "criteria/search-v2.toml changed since the vetting run; its period tolerance is unknown"
    ]


def test_a_review_of_another_signal_is_refused(tmp_path):
    found = calls.problems(signal_dir(tmp_path, review={**REVIEW, "signal": "44926986-2"}))
    assert found == [f"review.json is for 44926986-2, not {NAME}"]


def test_a_planet_elsewhere_on_exofop_does_not_stand_in_the_way(tmp_path):
    elsewhere = {**PLANET_AT_THE_PERIOD, "period": 3.3}
    no_period = {**PLANET_AT_THE_PERIOD, "name": "TIC 44926986.02", "toi": None, "period": None}
    assert calls.problems(signal_dir(tmp_path, planets=[elsewhere, no_period])) == []


KILLED = """\
signal = "44926986-1"
outcome = "killed"
date = 2026-10-28
reasons = "It fails odd and even."
rests_on = ["odd_even"]
criteria = ["vet-v3", "triage-v1"]
"""


def test_kill_must_rest_on_a_failure(tmp_path):
    def found(name, call, **kwargs):
        return calls.problems(signal_dir(tmp_path / name, call=call, **kwargs))

    assert found("a", KILLED, outcomes={"odd_even": "fail"}) == []
    [problem] = found("b", KILLED)
    assert "rests on" in problem and "odd_even" in problem
    assert found("c", edit(KILLED, '["odd_even"]', '["F2"]')) == []
    # F3 was refuted, so it is not a confirmed finding a kill can rest on.
    assert found("d", edit(KILLED, '["odd_even"]', '["F3"]'))
    assert found("e", edit(KILLED, '["odd_even"]', '["triceratops"]'), triceratops="fail") == []


def test_a_kill_may_rest_on_a_failed_pixel_check(tmp_path):
    on_pixels = edit(KILLED, '["odd_even"]', '["pixels"]')

    def found(name, **kwargs):
        return calls.problems(signal_dir(tmp_path / name, call=on_pixels, **kwargs))

    # A pixel fail kills a second-list row as it would have in triage (M3 design, section 4.10; Ruling U).
    assert found("a", kind="second", pixels="fail") == []
    assert found("b", pixels="fail") == []
    [problem] = found("c", kind="second", pixels="pass")
    assert "rests on" in problem and "pixels" in problem
    # Triage's pixel check never ran on a second-list row; without the second list's, there is none to rest on.
    [problem] = found("d", kind="second", pixels=None)
    assert "pixels" in problem and "neither a check" in problem


def test_a_second_list_pass_needs_the_pixel_check_to_pass(tmp_path):
    def found(name, **kwargs):
        record = signal_dir(tmp_path / name, call=PROMOTED, kind="second", **SPOC, **kwargs)
        return calls.problems(record)

    assert found("a", pixels="pass") == []
    [problem] = found("b", pixels=None)
    assert "pixels.json" in problem
    for name, outcome in (("c", "fail"), ("d", "inconclusive")):
        [problem] = found(name, pixels=outcome)
        assert f"the pixel check is {outcome}" in problem


def test_a_candidate_pass_needs_triages_pixel_pass(tmp_path):
    # Ruling W: `vetting run` never checks that a candidate was shortlisted, so the pass bar reads its pixel record.
    def found(name, **kwargs):
        return calls.problems(signal_dir(tmp_path / name, **kwargs))

    assert found("a") == []
    [problem] = found("b", pixels="inconclusive")
    assert "the pixel check is inconclusive" in problem
    [problem] = found("c", pixels=None)
    assert "no pixel check" in problem and "triage" in problem


HELD = """\
signal = "44926986-1"
outcome = "held"
date = 2026-10-28
reasons = "The public data can't tell the two stars apart."
rests_on = ["F2"]
criteria = ["vet-v3", "triage-v1"]
deciding_evidence = "High-resolution imaging of the 12.5 arcsec companion."
"""


def test_hold_needs_deciding_evidence(tmp_path):
    assert calls.problems(signal_dir(tmp_path / "a", call=HELD)) == []
    without = edit(
        HELD, 'deciding_evidence = "High-resolution imaging of the 12.5 arcsec companion."\n', ""
    )
    [problem] = calls.problems(signal_dir(tmp_path / "b", call=without))
    assert "deciding_evidence" in problem


PROMOTED = edit(
    PASSED,
    'hits_read = ["2306.16587"]\n',
    'hits_read = ["2306.16587"]\npromotion = "SPOC TCE s0036 at 24.11 d, never made a TOI; the maintainer promotes it."\n',
)


SPOC = {"novelty_category": "known_to_spoc", "outcomes": {"novelty": "inconclusive"}}


def test_promotion_stands_in_for_known_to_spoc(tmp_path):
    second = {"kind": "second", "pixels": "pass"}
    assert calls.problems(signal_dir(tmp_path / "a", call=PROMOTED, **second, **SPOC)) == []
    # Without the promotion, the novelty check stands unpassed.
    [problem] = calls.problems(signal_dir(tmp_path / "b", **second, **SPOC))
    assert "novelty is inconclusive" in problem
    # A promotion stands in only for known_to_spoc, and only on a second-list row.
    stale = {"novelty_category": "stale_catalog_epoch", "outcomes": {"novelty": "inconclusive"}}
    assert calls.problems(signal_dir(tmp_path / "c", call=PROMOTED, kind="second", **stale))
    found = calls.problems(signal_dir(tmp_path / "d", call=PROMOTED, **SPOC))
    assert any("second-list" in p for p in found)
    # A failed novelty is a known object, whatever the promotion says.
    failed = {"novelty_category": "known", "outcomes": {"novelty": "fail"}}
    assert calls.problems(signal_dir(tmp_path / "e", call=PROMOTED, kind="second", **failed))


@pytest.mark.parametrize(
    "call, message",
    [
        (edit(KILLED, 'outcome = "killed"', 'outcome = "dead"'), "outcome"),
        (edit(KILLED, "date = 2026-10-28", 'date = "Oct 28"'), "date"),
        (edit(KILLED, '["odd_even"]', '["odd_eve"]'), "odd_eve"),
        (edit(KILLED, 'reasons = "It fails odd and even."\n', ""), "reasons"),
        (KILLED + 'deciding_evidance = "x"\nnote = "a misspelt key"\n', "note"),
        (edit(KILLED, 'signal = "44926986-1"', 'signal = "44926986-2"'), "44926986-2"),
        (edit(KILLED, '["vet-v3", "triage-v1"]', '["vet-v2"]'), "vet-v3"),
        ("outcome = ", "call.toml"),
    ],
)
def test_a_call_file_that_breaks_the_schema_is_refused(tmp_path, call, message):
    found = calls.problems(signal_dir(tmp_path, call=call, outcomes={"odd_even": "fail"}))
    assert found and any(message in p for p in found), found


def test_a_review_file_that_breaks_the_schema_is_refused(tmp_path):
    # "Hold" is not a rating; read loosely, the finding would need no answer.
    finding = {**REVIEW["findings"][1], "rating": "Hold"}
    review = {**REVIEW, "findings": [finding]}
    found = calls.problems(signal_dir(tmp_path, review=review))
    assert any("Hold" in p for p in found), found


def test_a_version_is_judged_as_an_m3_record(tmp_path):
    """A re-vet's record, results/vetting/<name>/r<N>/, is the signal's record (decision 0041): its call names the
    signal, and the bar reads the files in the version's directory."""
    m3 = signal_dir(tmp_path, call=HELD)
    assert calls.problems(signal_dir(m3, name="r2")) == []
    assert (
        calls.problems(signal_dir(m3, name="r3", call=KILLED, outcomes={"odd_even": "fail"})) == []
    )
    assert calls.version(m3 / "r2") == 2 and calls.version(m3) is None
    assert calls.signal_name(m3 / "r2") == NAME
    # A call naming the version's directory, not the signal, is refused.
    [problem] = calls.problems(signal_dir(m3, name="r4", call=edit(PASSED, f'"{NAME}"', '"r4"')))
    assert problem == f"call.toml is for r4, not {NAME}"
    # The version's own files decide: a pass on a version whose literature search is inconclusive is refused,
    # whatever the M3 record holds.
    found = calls.problems(signal_dir(m3, name="r5", literature="inconclusive"))
    assert any("the literature search is inconclusive" in p for p in found)
    # r1 is not a version: the M3 record is the first.
    assert calls.version(tmp_path / "r1") is None and calls.version(tmp_path / "r12") == 12
    # A version's refusals name the signal, not its directory.
    assert calls.problems(signal_dir(m3, name="r6", call=None)) == [f"no call.toml in {NAME}"]
    found = calls.problems(signal_dir(m3, name="r7", call=PROMOTED, **SPOC))
    assert f"promotion is for second-list rows; {NAME} is a candidate" in found
    (m3 / "r8").mkdir()
    (m3 / "r8" / "call.toml").write_text(HELD)
    assert calls.problems(m3 / "r8") == [f"no checks.json beside the call in {NAME}"]


def test_no_call_is_a_problem(tmp_path):
    assert calls.problems(signal_dir(tmp_path, call=None)) == [f"no call.toml in {NAME}"]


NOTE = '[[note]]\nfinding = "F2"\ndate = 2026-10-26\ntext = "The magnitudes give 0.358."\n'


def test_notes_on_the_review_sit_beside_their_finding(tmp_path):
    path = tmp_path / "review-notes.toml"
    path.write_text(NOTE)
    [note] = calls.load_notes(path, REVIEW)["F2"]
    assert note["text"] == "The magnitudes give 0.358." and str(note["date"]) == "2026-10-26"


@pytest.mark.parametrize(
    "text, message",
    [
        (NOTE.replace('"F2"', '"F9"'), "'F9', which is not a finding"),
        (NOTE.replace("2026-10-26", '"soon"'), "TOML date"),
        (NOTE + 'author = "me"\n', "exactly date, finding, text"),
        (NOTE.replace('"The magnitudes give 0.358."', '" "'), "no text"),
        ("[notes]\n", "unknown key(s) notes"),
    ],
)
def test_a_notes_file_that_breaks_the_schema_is_refused(tmp_path, text, message):
    path = tmp_path / "review-notes.toml"
    path.write_text(text)
    with pytest.raises(calls.CallError, match=re.escape(message)):
        calls.load_notes(path, REVIEW)


# A TOI on the signal's own star at twice its period, listed after its claim with every disposition PC, as claims.json
# lists a row decision 0042 excepts. ExoFOP shows it as PLANET_AT_THE_PERIOD.
LATER_TOI = {
    "source": "TOI",
    "name": "TOI-9999.01",
    "tic": 44926986,
    "period": EPHEMERIS["period"] * 2,
    "first_listed": "2027-03-01",
    "dispositions": ["PC"],
}
LATER_CTOI = {**LATER_TOI, "source": "CTOI", "name": "CTOI-44926986.02"}
# Novelty's own fail on that TOI, as the vetting run records it.
FAILED = {"outcomes": {"novelty": "fail"}}


def rerun(outcome: str, reason: str, category: str | None = None) -> dict:
    """Novelty as `vetting claims` runs it again without the rows decision 0042 excepts."""
    return {
        "check": "novelty",
        "outcome": outcome,
        "reason": reason,
        "evidence": {} if category is None else {"category": category},
    }


PASSES = rerun("pass", "no known object matches")


def claimed(path: Path, excepted: list[dict], novelty: dict | None, kept: list[dict] = ()) -> Path:
    """The record at `path` with claims.json beside it, as `vetting claims` writes it."""
    record = {
        "signal": {"name": NAME, "tic": 44926986},
        "vetting_run": "20261101T000000Z-vetting-run-abc1234-0001",
        "literature_run": "20261101T010000Z-vetting-literature-abc1234-0001",
        "claim": {"date": "2026-10-28", "record": "https://doi.org/10.5281/zenodo.23745923"},
        "exofop_status": "ok",
        "excepted": excepted,
        "kept": list(kept),
        "novelty": novelty,
    }
    (path / "claims.json").write_text(json.dumps(record))
    return path


def test_a_pass_stands_on_a_novelty_fail_0042_excepts(tmp_path):
    # The TOI fails novelty and shows on ExoFOP at the period: both bars refuse the pass.
    found = calls.problems(signal_dir(tmp_path / "a", planets=[PLANET_AT_THE_PERIOD], **FAILED))
    assert "novelty is fail: novelty fail" in found
    assert any(p.startswith("ExoFOP lists TOI 9999.01") for p in found), found
    # Listed after the claim, it is excepted, and novelty without it passes.
    path = signal_dir(tmp_path / "b", planets=[PLANET_AT_THE_PERIOD], **FAILED)
    assert calls.problems(claimed(path, [LATER_TOI], PASSES)) == []


def test_a_pass_on_a_kept_listing_is_refused(tmp_path):
    # TFOPWG's FP carries someone else's evidence about the signal: the row is kept and nothing is run again.
    kept = {"source": "TOI", "name": "TOI-9999.01", "reason": "disposition FP, not PC"}
    path = signal_dir(tmp_path, planets=[PLANET_AT_THE_PERIOD], **FAILED)
    found = calls.problems(claimed(path, [], None, kept=[kept]))
    assert "novelty is fail: novelty fail" in found
    assert any(p.startswith("ExoFOP lists TOI 9999.01") for p in found), found


def test_a_rerun_at_known_to_spoc_passes_a_promoted_row_and_blocks_a_shortlisted_one(tmp_path):
    # Without the later TOI, the SPOC TCE from the same data still matches.
    spoc = rerun("inconclusive", "matches only SPOC TCE or ExoMiner rows", "known_to_spoc")

    def found(name, call, kind):
        path = signal_dir(tmp_path / name, call=call, kind=kind, **FAILED)
        return calls.problems(claimed(path, [LATER_TOI], spoc))

    assert found("a", PROMOTED, "second") == []
    # The refusal names the rerun: checks.json still holds novelty's own fail.
    assert found("b", PASSED, "candidate") == [
        "novelty, run again under decision 0042, is inconclusive: matches only SPOC TCE or ExoMiner rows"
    ]


def test_a_claims_json_the_bar_cannot_read_raises(tmp_path):
    # An exception is never a pass: a claims.json that excepts a listing with no rerun, or one that isn't JSON, stops
    # the bar for a pass and for a kill alike.
    on_novelty = edit(KILLED, '["odd_even"]', '["novelty"]')
    for name, call in (("a", PASSED), ("b", on_novelty)):
        path = claimed(signal_dir(tmp_path / name, call=call, **FAILED), [LATER_TOI], None)
        with pytest.raises(calls.CallError, match="excepts a listing but holds no rerun"):
            calls.problems(path)
        (path / "claims.json").write_text('{"excepted": [')
        with pytest.raises(json.JSONDecodeError):
            calls.problems(path)


def bar_2(path: Path, planets: list[dict], excepted: list[dict]) -> list[str]:
    """The problems of a pass whose novelty fail decision 0042 lifts, with ExoFOP's `planets` beside it."""
    return calls.problems(claimed(signal_dir(path, planets=planets, **FAILED), excepted, PASSES))


def test_a_planet_parameter_row_under_an_excepted_toi_does_not_block_bar_2(tmp_path):
    # Each of the TOI's rows names it in `toi` and its star's listing in `name` (pin P2).
    uploaded = {
        **PLANET_AT_THE_PERIOD,
        "provenance": "Planet Parameters (User uploaded)",
        "period": EPHEMERIS["period"],
    }
    assert bar_2(tmp_path / "a", [PLANET_AT_THE_PERIOD, uploaded], [LATER_TOI]) == []
    other = {**PLANET_AT_THE_PERIOD, "toi": "TOI 9998.01", "name": "TIC 44926986.02"}
    [problem] = bar_2(tmp_path / "b", [PLANET_AT_THE_PERIOD, other], [LATER_TOI])
    assert problem.startswith("ExoFOP lists TOI 9998.01 (TIC 44926986.02)")
    # A TOI's row is read by its `toi` alone: a `name` that is an excepted CTOI's lets nothing through.
    [problem] = bar_2(tmp_path / "c", [other], [LATER_CTOI])
    assert problem.startswith("ExoFOP lists TOI 9998.01 (TIC 44926986.02)")


def test_a_planet_parameter_row_under_an_excepted_ctoi_does_not_block_bar_2(tmp_path):
    # A CTOI never made a TOI has its uploaded row under its own name, with no TOI (pin P2).
    row = {
        **PLANET_AT_THE_PERIOD,
        "provenance": "Planet Parameters (User uploaded)",
        "name": "TIC 44926986.02",
        "toi": None,
    }
    assert bar_2(tmp_path / "a", [row], [LATER_CTOI]) == []
    # Any other name still blocks: another CTOI, the excepted TOI's number as a CTOI's, and names that read as no
    # listing.
    for i, name in enumerate(("TIC 44926986.03", "TIC 9999.01", "HIP 8152 b", None)):
        [problem] = bar_2(tmp_path / f"b{i}", [{**row, "name": name}], [LATER_CTOI, LATER_TOI])
        assert problem.startswith(f"ExoFOP lists {name} ("), problem


def test_a_kill_cannot_rest_on_a_novelty_fail_the_rerun_does_not_repeat(tmp_path):
    on_novelty = edit(KILLED, '["odd_even"]', '["novelty"]')

    def found(name, *claims):
        path = signal_dir(tmp_path / name, call=on_novelty, **FAILED)
        return calls.problems(claimed(path, *claims) if claims else path)

    assert found("a") == []
    # Nothing excepted: the fail stands.
    assert found("b", [], None) == []
    # Run again, it still fails on a row decision 0042 keeps, a neighbour's say: the kill stands on it.
    assert found("c", [LATER_TOI], rerun("fail", "matches TOI TOI-9997.01")) == []
    for name, again in (
        ("d", PASSES),
        ("e", rerun("inconclusive", "matches only SPOC TCE or ExoMiner rows", "known_to_spoc")),
    ):
        [problem] = found(name, [LATER_TOI], again)
        assert problem.endswith("(failed checks and confirmed findings: F2)"), problem


@pytest.mark.parametrize(
    "change",
    [
        {},
        *(change for change, _ in REFUSED),
        FAILED,
        {"planets": [PLANET_AT_THE_PERIOD], **FAILED},
        {"call": PROMOTED, "kind": "second", **SPOC},
        {"call": KILLED, "outcomes": {"odd_even": "fail"}},
        {"call": edit(KILLED, '["odd_even"]', '["novelty"]'), **FAILED},
        {"call": KILLED},
        {"call": HELD},
    ],
)
def test_without_claims_json_the_bar_is_unchanged(tmp_path, change):
    # A claims.json that excepts nothing leaves every call where a record without one leaves it.
    kept = {
        "source": "TOI",
        "name": "TOI-9999.01",
        "reason": "first listed 2026-01-05, not after the claim date 2026-10-28",
    }
    without = calls.problems(signal_dir(tmp_path / "a", **change))
    path = claimed(signal_dir(tmp_path / "b", **change), [], None, kept=[kept])
    assert calls.problems(path) == without
