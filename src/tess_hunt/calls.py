"""The maintainer's call on a vetted signal, and the "passed" bar `vetting publish` holds it to (M3 design, section
4.9; decision 0028). A call is passed, killed or held; it rests on named checks and review findings and holds no
numbers of its own."""

import datetime as dt
import json
import tomllib
from pathlib import Path

from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.provenance import repo_root

OUTCOMES = ("passed", "killed", "held")
SENTENCES = ("not_a_binary", "not_another_star", "not_an_artefact_or_known")
LENSES = ("on_star", "planet", "real_new")
RATINGS = ("kill", "hold", "note")
KEYS = {
    "signal",
    "outcome",
    "date",
    "reasons",
    "rests_on",
    "criteria",
    "deciding_evidence",
    "promotion",
    "answers",
    "sentences",
    "hits_read",
}


class CallError(ValueError):
    pass


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def load_review(path: Path) -> dict:
    """review.json, as the review workflow writes it (M3 design, section 4.8). A rating or lens read loosely could
    leave a finding nobody must answer, so anything off the schema raises."""
    try:
        review = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CallError(f"review.json: {exc}") from None
    errors = [
        f"review.json has no {k}"
        for k in ("signal", "model", "date", "findings", "hits_flagged", "summary")
        if k not in review
    ]
    if not errors and not (
        isinstance(review["findings"], list)
        and all(
            isinstance(f, dict) and isinstance(f.get("refuters"), list) for f in review["findings"]
        )
    ):
        errors.append("review.json's findings are a list, each with a list of refuters")
    if errors:
        raise CallError("; ".join(errors))
    ids = [f.get("id") for f in review["findings"]]
    if len(set(ids)) != len(ids):
        errors.append(f"review.json repeats a finding id: {ids}")
    for f in review["findings"]:
        missing = [
            k for k in ("id", "lens", "rating", "claim", "evidence", "refuters") if k not in f
        ]
        if missing:
            errors.append(f"finding {f.get('id')} has no {', '.join(missing)}")
            continue
        if f["lens"] not in LENSES:
            errors.append(
                f"finding {f['id']}: lens {f['lens']!r} is not one of {', '.join(LENSES)}"
            )
        if f["rating"] not in RATINGS:
            errors.append(
                f"finding {f['id']}: rating {f['rating']!r} is not one of {', '.join(RATINGS)}"
            )
        if not all(
            isinstance(r.get("refuted"), bool) and _text(r.get("reason")) for r in f["refuters"]
        ):
            errors.append(
                f"finding {f['id']}: each refuter needs refuted (true or false) and a reason"
            )
    if not _strings(review["hits_flagged"]):
        errors.append("review.json's hits_flagged is not a list of ids")
    if errors:
        raise CallError("; ".join(errors))
    return review


def confirmed(review: dict) -> list[str]:
    """The findings rated kill or hold that no refuter refuted. One no refuter has answered yet stands."""
    return [
        f["id"]
        for f in review["findings"]
        if f["rating"] in ("kill", "hold") and not any(r["refuted"] for r in f["refuters"])
    ]


def pixels(signal_dir: Path, checks: dict) -> dict | None:
    """The pixel check the record holds for the signal: for a second-list row the one `vetting second-list` ran
    (pixels.json), since triage runs its own only on novelty passes (M3 design, section 4.10; Ruling U); for any other
    signal, triage's, in checks.json."""
    if checks["signal"]["kind"] == "second":
        return _json(signal_dir / "pixels.json")
    return checks["pixels"]


def _names(signal_dir: Path) -> set[str]:
    """What a call may rest on: the checks in the record and the review's findings."""
    checks = _json(signal_dir / "checks.json")
    if checks is None:
        raise CallError(f"no checks.json beside the call in {signal_dir.name}")
    names = {c["check"] for c in checks["checks"]} | {"neighbours"}
    if pixels(signal_dir, checks) is not None:
        names.add("pixels")
    for name in ("triceratops", "literature"):
        if (signal_dir / f"{name}.json").is_file():
            names.add(name)
    if (signal_dir / "review.json").is_file():
        names |= {f["id"] for f in load_review(signal_dir / "review.json")["findings"]}
    return names


def load(path: Path) -> dict:
    """call.toml, checked against its schema: the keys each outcome needs, and `rests_on` naming checks or findings
    the record beside it holds. Raises CallError."""
    try:
        call = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise CallError(f"call.toml: {exc}") from None
    errors = []
    unknown = sorted(set(call) - KEYS)
    if unknown:
        errors.append(f"call.toml has unknown key(s) {', '.join(unknown)}")
    for key, what in (("signal", "the signal's name"), ("reasons", "the reasons in words")):
        if not _text(call.get(key)):
            errors.append(f"call.toml needs {key}, {what}")
    if call.get("outcome") not in OUTCOMES:
        errors.append(f"outcome {call.get('outcome')!r} is not one of {', '.join(OUTCOMES)}")
    # A TOML datetime is a dt.date too; the call is dated by day.
    if not isinstance(call.get("date"), dt.date) or isinstance(call.get("date"), dt.datetime):
        errors.append("date must be a TOML date (2026-10-28)")
    for key in ("rests_on", "criteria"):
        if not _strings(call.get(key)):
            errors.append(f"call.toml needs {key}, a list of names")
    call.setdefault("answers", {})
    call.setdefault("sentences", {})
    call.setdefault("deciding_evidence", None)
    call.setdefault("promotion", None)
    if not (isinstance(call["answers"], dict) and all(_text(v) for v in call["answers"].values())):
        errors.append("[answers] gives each finding id an answer in words")
    if not isinstance(call["sentences"], dict):
        errors.append("[sentences] is a table of the three sentences")
        call["sentences"] = {}
    if call["promotion"] is not None and not _text(call["promotion"]):
        errors.append("promotion, when given, names the TCE matched and the reason")
    if "hits_read" in call and not _strings(call["hits_read"]):
        errors.append("hits_read is a list of the flagged hits' ids")
    outcome = call.get("outcome")
    if outcome == "held" and not _text(call["deciding_evidence"]):
        errors.append("a held call needs deciding_evidence: what would decide it")
    if outcome == "passed":
        missing = [s for s in SENTENCES if not _text(call["sentences"].get(s))]
        if missing:
            errors.append(f"a passed call needs [sentences] {', '.join(missing)}")
        # Ruling R: written out even when empty, so a pass can't skip the reading by leaving it out.
        if "hits_read" not in call:
            errors.append(
                "a passed call needs hits_read, the flagged hits read (an empty list when none)"
            )
    if errors:
        raise CallError("; ".join(errors))
    call.setdefault("hits_read", [])
    known = _names(path.parent)
    strange = [n for n in call["rests_on"] if n not in known]
    if strange:
        raise CallError(
            f"rests_on names {', '.join(strange)}, which is neither a check in the record nor a review finding"
        )
    return call


def _failures(checks: dict, triceratops: dict | None, pixel: dict | None) -> set[str]:
    failed = {c["check"] for c in checks["checks"] if c["outcome"] == "fail"}
    # A pixel fail kills a signal as it would have in triage (M3 design, section 4.10).
    for name, record in (("triceratops", triceratops), ("pixels", pixel)):
        if record is not None and record["outcome"] == "fail":
            failed.add(name)
    return failed


def _match_rule(signal_dir: Path) -> tuple[tuple[float, ...], float, float]:
    """The vetting run's own period tolerance and harmonics, from the criteria files its provenance names, each
    checked against the sha256 it recorded."""
    provenance = _json(signal_dir / "provenance-checks.json")
    if provenance is None:
        raise CallError("no provenance-checks.json: the vetting run's criteria are unknown")
    loaded = []
    for used in provenance["criteria"][:2]:
        path = repo_root() / used["file"]
        if not path.is_file() or load_criteria(path).sha256 != used["sha256"]:
            raise CallError(
                f"{used['file']} changed since the vetting run; its period tolerance is unknown"
            )
        loaded.append(load_criteria(path))
    search, vet = loaded
    return (
        tuple(vet["novelty"]["harmonics"]),
        search["match"]["sigma_p"],
        search["match"]["sigma_t"],
    )


def _exofop_at_the_period(signal_dir: Path, checks: dict, literature: dict) -> list[str]:
    """Bar 2: ExoFOP shows nothing at the period (Ruling Q), matched on period alone at the novelty harmonics."""
    planets = literature["search"]["exofop"].get("planets")
    if planets is None:
        return [
            "the literature record keeps no ExoFOP planet periods (it predates decision 0028); search again"
        ]
    try:
        harmonics, sigma_p, sigma_t = _match_rule(signal_dir)
    except CallError as exc:
        return [str(exc)]
    eph = Ephemeris(**checks["ephemeris"])
    out = []
    for p in planets:
        if p["period"] is None:
            continue
        ratio = ephemeris_match(
            eph, Ephemeris(p["period"], float("nan"), float("nan")), harmonics, sigma_p, sigma_t
        )
        if ratio is not None:
            label = f"{p['toi']} ({p['name']})" if p["toi"] else p["name"]
            out.append(
                f"ExoFOP lists {label} ({p['provenance']}) at {p['period']:.6g} d, which matches the signal's "
                f"period at ratio {ratio:g}"
            )
    return out


def _pass_problems(signal_dir: Path, call: dict, checks: dict, review: dict | None) -> list[str]:
    out = []
    kind = checks["signal"]["kind"]
    promotion = call["promotion"]
    if promotion is not None and kind != "second":
        out.append(f"promotion is for second-list rows; {signal_dir.name} is a {kind}")
    for c in checks["checks"]:
        if c["outcome"] == "pass":
            continue
        # Bar 2: a promoted second-list row's novelty stays inconclusive as known_to_spoc (decision 0013).
        promoted = (
            c["check"] == "novelty"
            and kind == "second"
            and promotion is not None
            and c["outcome"] == "inconclusive"
            and c["evidence"].get("category") == "known_to_spoc"
        )
        if not promoted:
            out.append(f"{c['check']} is {c['outcome']}: {c['reason']}")
    # Triage passed every other signal's pixel check before shortlisting it; a second-list row's is the second list's.
    if kind == "second":
        pixel = pixels(signal_dir, checks)
        if pixel is None:
            out.append(
                "no pixels.json: a second-list row's pass needs the second list's pixel check"
            )
        elif pixel["outcome"] != "pass":
            out.append(f"the pixel check is {pixel['outcome']}: {pixel['reason']}")
    triceratops = _json(signal_dir / "triceratops.json")
    if triceratops is None:
        out.append("no triceratops.json: a pass needs TRICERATOPS's")
    elif triceratops["outcome"] != "pass":
        out.append(f"TRICERATOPS is {triceratops['outcome']}: {triceratops['reason']}")
    literature = _json(signal_dir / "literature.json")
    if literature is None:
        out.append("no literature.json: a pass needs a complete literature search")
    else:
        if literature["outcome"] != "pass":
            out.append(f"the literature search is {literature['outcome']}: {literature['reason']}")
        out += _exofop_at_the_period(signal_dir, checks, literature)
    if review is None:
        out.append("no review.json: a pass needs the review, every confirmed finding answered")
        return out
    found = confirmed(review)
    out += [
        f"confirmed finding {f} has no answer in [answers]"
        for f in found
        if f not in call["answers"]
    ]
    out += [
        f"[answers] names {a}, which is not a confirmed finding"
        for a in call["answers"]
        if a not in found
    ]
    out += [
        f"flagged hit {h} is not in hits_read"
        for h in review["hits_flagged"]
        if h not in call["hits_read"]
    ]
    return out


def problems(signal_dir: Path) -> list[str]:
    """Why the call in `signal_dir` claims more than the record beside it supports; empty when it stands. A pass
    needs the "passed" bar; a kill rests on a failed check or a confirmed finding; a hold names what would decide
    it."""
    path = signal_dir / "call.toml"
    if not path.is_file():
        return [f"no call.toml in {signal_dir.name}"]
    try:
        call = load(path)
        review = (
            load_review(signal_dir / "review.json")
            if (signal_dir / "review.json").is_file()
            else None
        )
    except CallError as exc:
        return [str(exc)]
    checks = _json(signal_dir / "checks.json")
    out = []
    if call["signal"] != signal_dir.name:
        out.append(f"call.toml is for {call['signal']}, not {signal_dir.name}")
    if checks["evidence_only"]:
        out.append("checks.json is an evidence-only vet, which never makes a call")
    if checks["criteria_version"] not in call["criteria"]:
        out.append(
            f"call.toml's criteria name {', '.join(call['criteria'])}, not {checks['criteria_version']}, the "
            "criteria the checks ran under"
        )
    if call["outcome"] == "killed":
        found = set(confirmed(review)) if review else set()
        tric = _json(signal_dir / "triceratops.json")
        grounds = _failures(checks, tric, pixels(signal_dir, checks)) | found
        if not grounds & set(call["rests_on"]):
            listed = ", ".join(sorted(grounds)) or "none in this record"
            out.append(
                f"a kill rests on a failed check or a confirmed finding; rests_on names {', '.join(call['rests_on'])}"
                f" (failed checks and confirmed findings: {listed})"
            )
    elif call["outcome"] == "passed":
        out += _pass_problems(signal_dir, call, checks, review)
    return out
