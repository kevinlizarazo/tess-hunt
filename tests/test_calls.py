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


@pytest.mark.parametrize(
    "change, message",
    [
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
    ],
)
def test_a_pass_the_evidence_does_not_support_is_refused(tmp_path, change, message):
    found = calls.problems(signal_dir(tmp_path, **change))
    assert found, change
    assert any(re.search(message, p) for p in found), found


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
