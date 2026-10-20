"""The dossier: one signal's record rendered for the maintainer's call and for the public record (M3 design, section
4.7; decision 0028). It reads only the files in the signal's directory. The template is filled with `substitute` and
each value is read by its key, so a value the record lacks raises instead of rendering (docs/design.md, section
5.5)."""

import json
from pathlib import Path
from string import Template

from astropy.time import Time

from tess_hunt import calls

PAGE = Template("""\
# $title

$status

## Signal and star

$star

## Checks

$checks

## On the star?

$on_star

## A planet rather than a binary?

$planet

## Real and new?

$real_new

## Next TESS looks

$looks

## Plots

$plots

## Catalogued rows on the star

$catalogued

## Literature hits

$hits

## With the timing-suspect sectors (evidence only)

$suspect

## Review

$review

## Call

$call
""")
README = Template("""\
# Vetting

One row per published signal the maintainer has called passed, killed or held, whose call stands on its record
([decision 0028](../../docs/decisions/0028-outcomes-and-calls.md)). Each directory holds the signal's dossier
(`dossier.md`), the call (`call.toml`), the review (`review.json`) and the run files the dossier is rendered from;
[../README.md](../README.md) describes each file. A passed signal is a planet candidate, not a confirmed planet.

| Signal | Outcome | Date | Reason |
|---|---|---|---|
$rows
""")
KINDS = {
    "candidate": "a shortlisted candidate",
    "second": "a second-list row (a SPOC TCE that never became a TOI)",
    "control": "a known-planet control",
    "negative_control": "a negative control",
}
LENSES = {"on_star": "on the star", "planet": "a planet", "real_new": "real and new"}
SENTENCES = {
    "not_a_binary": "Not a binary on the star",
    "not_another_star": "Not another star's light",
    "not_an_artefact_or_known": "Not an artefact or a known object",
}
PLOTS = {
    "transits.png": "Each transit, against hours from its predicted mid-time",
    "folds.png": "The fold in each season and each product family",
    "odd_even.png": "Odd and even transits side by side",
    "phase.png": "The whole orbit, with phase 0.5 and LEO-Vetter's ModShift secondary marked",
    "centroids.png": "Triage's centroid offset per sector, with the neighbours that could host the signal",
}
# A second-list row's centroid plot: the second list draws it from its own pixel check, beside pixels.json, since the
# vetting run's centroids.png drew triage's record, which holds no offsets for the row.
SECOND_LIST_CENTROIDS = (
    "pixels.png",
    "The second list's pixel check: each sector's centroid offset, with the neighbours that could host the signal",
)
# The products that publish CROWDSAP; QLP publishes none.
CROWDSAP = ("SPOC", "TESS-SPOC")
# Whose pixel check the centroid table shows, keyed by whether the signal is a second-list row: its name, its owner
# at the head of a sentence, and who judged the offset. Triage never ran its check on a second-list row; the second
# list ran it as triage runs it (decision 0028).
PIXEL_CHECK = {
    False: ("triage's pixel check", "Triage's", "triage"),
    True: ("the second list's pixel check", "The second list's", "the second list's check"),
}


def _json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def _f(value, fmt: str) -> str:
    """A number from the record, or "missing" where the record holds null for it."""
    return "missing" if value is None else format(value, fmt)


def _ppm(fraction) -> str:
    return "missing" if fraction is None else f"{fraction * 1e6:.0f}"


def _cell(text) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows])


def _list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _words(values: list) -> str:
    values = [str(v) for v in values]
    if len(values) < 2:
        return "".join(values)
    return ", ".join(values[:-1]) + " and " + values[-1]


class Record:
    """The files in a signal's directory, each read once."""

    def __init__(self, path: Path):
        self.path = path
        self.name = path.name
        self.checks = json.loads((path / "checks.json").read_text())
        self.provenance = {
            role: _json(path / f"provenance-{role}.json")
            for role in (
                "checks",
                "triceratops",
                "literature",
                "checks-with-suspect",
                "second-list",
            )
        }
        self.pixels = calls.pixels(path, self.checks)
        self.triceratops = _json(path / "triceratops.json")
        self.literature = _json(path / "literature.json")
        self.suspect = _json(path / "checks-with-suspect.json")
        has_review = (path / "review.json").is_file()
        self.review = calls.load_review(path / "review.json") if has_review else None
        self.call = calls.load(path / "call.toml") if (path / "call.toml").is_file() else None

    def check(self, name: str) -> dict:
        return next(c for c in self.checks["checks"] if c["check"] == name)

    def said(self, name: str) -> str:
        c = self.check(name)
        return f"{c['outcome']}, {c['reason']}"

    def absent(self, role: str, what: str) -> str:
        """Why the record holds no `role` file: no run given, or a run that did not judge this signal."""
        provenance = self.provenance[role]
        if provenance is None:
            return f"No {what} run was given."
        return f"{what} run {provenance['run_id']} did not judge this signal."

    @property
    def second(self) -> bool:
        """A second-list row, whose pixel check is the second list's: triage never ran its own on it."""
        return self.checks["signal"]["kind"] == "second"

    def no_pixels(self) -> str:
        """Why the record holds no pixel check."""
        return (
            self.absent("second-list", "second-list")
            if self.second
            else self.checks["triage_reason"]
        )


def _title(r: Record) -> str:
    return f"{r.name}: TIC {r.checks['star']['tic']}"


def _status(r: Record) -> str:
    if r.call is None:
        return "Draft: no call yet. Rendered from the files in this directory (decision 0028)."
    return (
        f"Call: **{r.call['outcome']}** on {r.call['date']}. Rendered from the files in this directory "
        "(decision 0028)."
    )


def _names(r: Record) -> list[str]:
    star = r.checks["star"]
    source_id = star["dr3_source_id"]
    names = [f"TIC {star['tic']}"]
    if source_id is not None:
        names.append(f"Gaia DR3 {source_id}")
    if r.literature is not None:
        names += r.literature["search"]["names"]
    return list(dict.fromkeys(names))


def _runs(r: Record) -> str:
    out = []
    for role, label in (
        ("checks", "vetting"),
        ("triceratops", "TRICERATOPS"),
        ("literature", "literature"),
        ("checks-with-suspect", "evidence-only vetting"),
        ("second-list", "second list"),
    ):
        p = r.provenance[role]
        if p is not None:
            kind = "production" if p["production"] else "not production"
            out.append(f"{label} {p['run_id']} (commit {p['git']['commit'][:7]}, {kind})")
    return "; ".join(out)


def _crowdsap(r: Record) -> str:
    out, none = [], []
    for sector, source in sorted(r.checks["sources"].items(), key=lambda s: int(s[0])):
        if source["provenance"] in CROWDSAP:
            out.append(f"S{sector} {_f(source['crowdsap'], '.3f')}")
        else:
            none.append(f"S{sector} ({source['provenance']})")
    if none:
        out.append(f"none published for {', '.join(none)}")
    return "; ".join(out)


def _star(r: Record) -> str:
    c, star = r.checks, r.checks["star"]
    eph = c["ephemeris"]
    families = "; ".join(
        f"{name.upper()} family: {_words(s)}" for name, s in sorted(c["families"].items())
    )
    dropped = _words(c["dropped_suspect"]) or "none"
    criteria = ", ".join(Path(x["file"]).stem for x in r.provenance["checks"]["criteria"])
    rows = [
        ["Signal", f"{r.name}, {KINDS[c['signal']['kind']]}"],
        ["Names", ", ".join(_names(r))],
        [
            "Ephemeris (the search's box)",
            f"period {eph['period']:.6f} d, epoch BTJD {eph['t0']:.4f}, duration {eph['duration']:.4f} d "
            f"({eph['duration'] * 24:.2f} h), depth {_ppm(eph['depth'])} ppm",
        ],
        [
            "Star (TIC)",
            f"Teff {_f(star['teff'], '.0f')} K, radius {_f(star['rad'], '.2f')} solar radii, "
            f"Tmag {_f(star['tmag'], '.2f')}",
        ],
        [
            "RUWE (Gaia DR3)",
            f"missing, because {star['dr3_reason']}"
            if star["ruwe"] is None
            else f"{star['ruwe']:.2f}",
        ],
        ["CROWDSAP", _crowdsap(r)],
        ["Sectors vetted", f"{families}; left out as timing-suspect: {dropped}"],
        ["Criteria", criteria],
        ["Runs", _runs(r)],
    ]
    return _table(["", ""], rows)


def _checks(r: Record) -> str:
    rows = [[c["check"], c["outcome"], c["reason"]] for c in r.checks["checks"]]
    nb = r.checks["neighbours"]
    rows.append(["neighbours", nb["outcome"], nb["reason"]])
    if r.pixels is None:
        rows.append(["pixels", "not run", r.no_pixels()])
    else:
        rows.append(["pixels", r.pixels["outcome"], r.pixels["reason"]])
    for role, what, record in (
        ("triceratops", "TRICERATOPS", r.triceratops),
        ("literature", "literature", r.literature),
    ):
        if record is None:
            rows.append([role, "not run", r.absent(role, what)])
        else:
            rows.append([role, record["outcome"], record["reason"]])
    if not r.second:
        pixel_check = "triage's pixel check"
    elif r.pixels is None:
        pixel_check = "triage's pixel check, which triage did not run on this row (it runs only on novelty passes)"
    else:
        pixel_check = (
            "triage's pixel check as the second list ran it on this row "
            "(triage runs it only on novelty passes)"
        )
    note = (
        f"{r.checks['criteria_version']}'s checks first, then the neighbour table (evidence, never a fail), "
        f"{pixel_check}, TRICERATOPS and the literature search."
    )
    return note + "\n\n" + _table(["Check", "Outcome", "Reason"], rows)


def _centroids(r: Record) -> str:
    pixels = r.pixels
    if pixels is None:
        return f"Centroids: no pixel evidence ({r.no_pixels()})."
    label, owner, judge = PIXEL_CHECK[r.second]
    # A pixel check triage never ran (novelty or the flux tests did not pass) measured no sector.
    sectors = sorted(pixels["evidence"].get("sectors", []), key=lambda s: s["sector"])
    if not sectors:
        return (
            f"Centroids: {label} is {pixels['outcome']} ({pixels['reason']}); no sector measured."
        )
    suspect = set(r.checks["dropped_suspect"])
    # Triage judges the best-quality sector's offset (pixels.pixel_check); the row holding that offset is its sector.
    # A NaN offset is null in the record and matches no row.
    judged_offset = pixels["evidence"]["offset_qual_arcsec"]
    judged = [
        s["sector"]
        for s in sectors
        if judged_offset is not None and s["offset_arcsec"] == judged_offset
    ]
    rows = []
    for s in sectors:
        notes = []
        if s["sector"] in suspect:
            notes.append("timing-suspect: vet-v3 leaves it out")
        if s["sector"] in judged:
            notes.append(f"the offset {judge} judged")
        rows.append(
            [s["sector"], _f(s["offset_arcsec"], ".1f"), _f(s["quality"], ".2f"), "; ".join(notes)]
        )
    if len(judged) == 1:
        sector = judged[0]
        source = (
            f"{owner} {pixels['outcome']} rests on the best-quality sector's offset, S{sector}'s"
            + (
                ", from a timing-suspect sector that vet-v3 leaves out."
                if sector in suspect
                else "."
            )
        )
    else:
        source = (
            f"{owner} {pixels['outcome']} rests on the best-quality sector's offset, which no single row below "
            "reports."
        )
    return (
        f"Centroids, from {label} ({pixels['outcome']}, {pixels['reason']}): the difference-image "
        f"centroid's offset from the target in each sector. {source}\n\n"
        + _table(["Sector", "Offset (arcsec)", "Quality", "Note"], rows)
    )


def _neighbours(r: Record) -> str:
    nb = r.checks["neighbours"]
    evidence = nb["evidence"]
    head = f"Neighbours ({nb['outcome']}): {nb['reason']}."
    # A neighbour table that was never built has no possible hosts to list.
    hosts = evidence.get("possible_hosts")
    if not hosts:
        return head
    # The cross-check of design 4.4: the TRICERATOPS star matched to each host, and the depth it gave that star.
    weighed = r.triceratops and r.triceratops["evidence"]["hosts"]
    matched = {h["source_id"]: h for h in weighed} if weighed else None
    header = ["Star", "Separation (arcsec)", "Eclipse needed"]
    if matched is not None:
        header += ["TRICERATOPS's star (distance)", "Its depth"]
    rows = []
    for h in sorted(hosts, key=lambda h: h["sep_arcsec"]):
        needed = "missing" if h["required_depth"] is None else f"{100 * h['required_depth']:.3g}%"
        row = [f"Gaia DR3 {h['source_id']}", _f(h["sep_arcsec"], ".1f"), needed]
        if matched is not None:
            m = matched[h["source_id"]]
            if m["tic"] is None:
                row += [f'none matched (nearest {_f(m["distance_arcsec"], ".1f")}")', "none"]
            else:
                row += [
                    f'TIC {m["tic"]} ({_f(m["distance_arcsec"], ".1f")}")',
                    # TRICERATOPS can stop after building its star list and before calc_depths.
                    "not computed" if m["tdepth"] is None else f"{100 * m['tdepth']:.3g}%",
                ]
        rows.append(row)
    return (
        f"{head} Each Gaia DR3 star that could make the dip, with the eclipse depth it would need, scaled from "
        f"the depth in {evidence['depth_from']} ({_ppm(evidence['depth'])} ppm) as if all its light fell in "
        "the aperture"
        + (
            ", and the TRICERATOPS star matched to it with the distance between them at the TIC's epoch"
            if matched is not None
            else ""
        )
        + ":\n\n"
        + _table(header, rows)
    )


def _spread(evidence: dict, name: str) -> str:
    mean, sd = evidence[f"{name}_mean"], evidence[f"{name}_sd"]
    runs = len(evidence[name])
    out = f"mean {name.upper()} {_f(mean, '.3g')}"
    if sd is not None:
        out += f" (sd {sd:.2g})"
    return f"{out} over {runs} run(s) of {evidence['draws']} draws"


def _triceratops_on_star(r: Record) -> str:
    t = r.triceratops
    if t is None:
        return f"TRICERATOPS: {r.absent('triceratops', 'TRICERATOPS')}"
    e = t["evidence"]
    fold = {"fit_prior": "the density-prior fit's", "signal": "the signal's"}[
        t["ephemeris_from"]["ephemeris"]
    ]
    # Every field run() records is in the record, a run that raised included; None is a step TRICERATOPS never
    # reached (tricera.RUN_FIELDS), so each sentence says only what the record shows.
    if e["exposure_s"] is not None:
        data = f"took sectors {_words(e['sectors'])} at {e['exposure_s']:g} s"
        if e["points"] is not None:
            data += f" and folded them on {fold} ephemeris"
    elif e["groups"] is None:
        # `run` records the groups first, so only a raise leaves them out.
        data = f"raised before it chose its data: {e['raised']}"
    else:
        data = "found no cadence group to run on"
    lines = [f"TRICERATOPS ({t['outcome']}) {data}."]
    if e["fpp"]:
        lines.append(f"It gave a {_spread(e, 'nfpp')}.")
        if e["raised"] is not None:
            lines.append(
                f"Then it raised, after {len(e['fpp'])} of {e['runs']} calc_probs run(s): {e['raised']}."
            )
    elif e["raised"] is not None:
        # A raise before the cadence group is already the first sentence.
        if e["groups"] is not None:
            lines.append(f"It raised before any calc_probs run finished: {e['raised']}.")
    elif e["stopped"] is not None:
        lines.append(f"It stopped before calc_probs: {e['stopped']}.")
    else:
        lines.append(f"It made no calc_probs run: {t['reason']}.")
    nb = r.checks["neighbours"]
    hosts = nb["evidence"].get("possible_hosts")
    if hosts is None:
        lines.append("No neighbour table was built, so whether a possible host exists is unknown.")
    elif not hosts and nb["outcome"] == "pass":
        lines.append("The neighbour table lists no possible host for it to weigh.")
    elif not hosts:
        # A star the table could not judge is never marked possible, so an empty list is not "none to weigh".
        lines.append(
            f"The neighbour table lists no possible host, but it could not judge every star: {nb['reason']}."
        )
    elif e["missing_hosts"] is None:
        lines.append("It built no star list, so no possible host was matched to it.")
    else:
        missing = ", ".join(f"Gaia DR3 {s}" for s in e["missing_hosts"])
        # A host in the star list is weighed only by a calc_probs run that finished.
        if e["fpp"]:
            lines.append(f"Possible hosts it did not weigh: {missing or 'none'}.")
        elif missing:
            lines.append(
                f"Possible hosts not in its star list: {missing}. No calc_probs run weighed any star."
            )
        else:
            lines.append(
                "Every possible host is in its star list, and no calc_probs run weighed them."
            )
        zero = e["hosts_tdepth_zero"]
        if zero:
            matched = {h["source_id"]: h["tic"] for h in e["hosts"]}
            listed = ", ".join(f"Gaia DR3 {s} (TIC {matched[s]})" for s in zero)
            lines.append(
                f"It gave zero depth to {listed}: its apertures take too little of "
                f"{'that star' if len(zero) == 1 else 'each one'}'s light to make the dip. "
                "Evidence for the review, not a blocker (decision 0026)."
            )
    return " ".join(lines)


def _on_star(r: Record) -> str:
    star = r.checks["star"]
    # A failed archive query, which a re-run fixes, must read apart from a star Gaia DR3 gives no RUWE.
    ruwe = (
        f"RUWE missing (Gaia DR3), because {star['dr3_reason']}."
        if star["ruwe"] is None
        else f"RUWE {star['ruwe']:.2f} (Gaia DR3)."
    )
    return "\n\n".join(
        [
            _centroids(r),
            _neighbours(r),
            _triceratops_on_star(r),
            f"{ruwe} A high RUWE points to an unresolved companion, which TRICERATOPS's priors don't condition "
            "on; above vet-v3's limit, or without a RUWE, TRICERATOPS is inconclusive.",
        ]
    )


def _modshift(r: Record) -> str:
    m = r.checks["modshift"]
    if m is None:
        return f"no ModShift evidence ({r.checks['triage_reason']})"
    return (
        f"the strongest secondary is {_f(m['sig_sec'], '.3g')} sigma at phase {_f(m['phs_sec'], '.3g')}, depth "
        f"{_ppm(m['dep_sec'])} ppm; primary {_f(m['sig_pri'], '.3g')} sigma, tertiary "
        f"{_f(m['sig_ter'], '.3g')} sigma at phase {_f(m['phs_ter'], '.3g')}, positive {_f(m['sig_pos'], '.3g')} "
        f"sigma at phase {_f(m['phs_pos'], '.3g')}; Fred {_f(m['Fred'], '.3g')}"
    )


def _others(r: Record) -> str:
    others = r.checks["other_signals"]
    if others is None:
        return f"not known ({r.checks['triage_reason']})"
    if not others:
        return "none"
    return "; ".join(
        f"rank {o['rank']} at {o['period']:.4f} d (period ratio {o['period_ratio']:.3g}, SDE {o['sde']:.1f})"
        for o in others
    )


def _radius(r: Record) -> str:
    check = r.check("radius")
    flat = check["evidence"].get("rp_rearth") if check["outcome"] != "inconclusive" else None
    text = (
        f"Radius: {r.said('radius')}. Rp is {_f(flat, '.2f')} Earth radii from the flat-prior fit"
    )
    prior = r.checks["fit_prior"]
    if prior is None:
        text += f"; there is no density-prior fit ({r.checks['fit_prior_reason']})"
    elif prior["rp_rearth"] is None:
        text += "; the density-prior fit gives none (the TIC gives no stellar radius)"
    else:
        rp = prior["rp_rearth"]
        text += (
            f" and {rp['median']:.2f} (16th to 84th percentile {rp['p16']:.2f} to {rp['p84']:.2f}) from the "
            "density-prior fit"
        )
    return text + "; the radius check reads the flat-prior fit."


def _summary(value: dict, fmt: str) -> str:
    return f"{value['median']:{fmt}} (-{value['minus']:{fmt}}, +{value['plus']:{fmt}})"


def _fit_prior(r: Record) -> str:
    prior = r.checks["fit_prior"]
    if prior is None:
        return f"Density-prior fit: none ({r.checks['fit_prior_reason']})."
    rp = prior["rp_rearth"]
    radius = (
        "no Rp (the TIC gives no stellar radius)"
        if rp is None
        else f"Rp {rp['median']:.2f} Earth radii (16th to 84th percentile {rp['p16']:.2f} to {rp['p84']:.2f})"
    )
    eph = prior["ephemeris"]
    return (
        "Density-prior fit (the TIC density as a prior), whose parameters M4 uses: "
        f"{radius}, b {_summary(prior['b'], '.2f')}, a/R* {_summary(prior['a_rs'], '.2f')}, period "
        f"{eph['period']['median']:.6f} d (sd {eph['period']['sd']:.2g}), t0 BTJD {eph['t0']['median']:.4f} "
        f"(sd {eph['t0']['sd']:.2g} d)."
    )


def _planet(r: Record) -> str:
    shape = r.check("shape")
    b = shape["evidence"].get("b_median") if shape["outcome"] != "inconclusive" else None
    items = [
        f"Odd and even transits: {r.said('odd_even')}.",
        f"Secondary at phase 0.5: {r.said('secondary')}.",
        f"Secondary at any phase (LEO-Vetter's ModShift, from triage): {_modshift(r)}.",
        f"The search's other signals on the star: {_others(r)}.",
        f"Shape (flat-prior fit): {r.said('shape')}; median b {_f(b, '.2f')}.",
        f"Density (flat-prior fit): {r.said('density')}.",
        _radius(r),
        _fit_prior(r),
    ]
    if r.triceratops is None:
        items.append(f"TRICERATOPS: {r.absent('triceratops', 'TRICERATOPS')}")
    elif r.triceratops["evidence"]["fpp"]:
        items.append(
            f"TRICERATOPS ({r.triceratops['outcome']}): {_spread(r.triceratops['evidence'], 'fpp')}."
        )
    else:
        items.append(
            f"TRICERATOPS ({r.triceratops['outcome']}): no calc_probs run finished, so no FPP."
        )
    return _list(items)


def _exofop(r: Record) -> str:
    if r.literature is None:
        return f"ExoFOP: {r.absent('literature', 'literature')}"
    x = r.literature["search"]["exofop"]
    if x["status"] != "ok":
        return f"ExoFOP: not read ({x['error']})."
    period = r.checks["ephemeris"]["period"]
    tois = (
        ", ".join(f"{t['toi']} ({t.get('disp_tfop') or 'no disposition'})" for t in x["tois"])
        or "none"
    )
    ctois = (
        ", ".join(f"{t['ctoi']} ({t.get('cdisp') or 'no disposition'})" for t in x["ctois"])
        or "none"
    )
    planets = [
        (f"{p['toi']} ({p['name']})" if p["toi"] else p["name"])
        + f", {p['provenance']}: "
        + (
            "no period"
            if p["period"] is None
            else f"{p['period']:.6g} d, {p['period'] / period:.3g} times ours"
        )
        for p in x["planets"]
    ]
    comments = [f"{c['object']}: {c['comment']}" for c in x["comments"]]
    lines = [
        f"ExoFOP, read live: TOIs {tois}; CTOIs {ctois}; confirmed planets "
        f"{x['confirmed_planets'] or 'none'}."
    ]
    if planets:
        lines.append("Planet parameters on ExoFOP:\n\n" + _list(planets))
    if comments:
        lines.append("Comments on ExoFOP:\n\n" + _list(comments))
    return "\n\n".join(lines)


def _real_new(r: Record) -> str:
    novelty = r.check("novelty")
    tce = novelty["evidence"].get("tce_matches") or []
    tce += novelty["evidence"].get("tce_period_matches") or []
    items = [
        f"Signal present: {r.said('signal_present')}.",
        f"Held-out seasons: {r.said('holdout')}.",
        f"Sector depths: {r.said('sector_depth')}.",
        f"Novelty, against the catalog snapshot: {r.said('novelty')}."
        + (
            f" SPOC TCE or ExoMiner rows at the period: {', '.join(t['name'] for t in tce)}."
            if tce
            else ""
        ),
    ]
    if r.literature is None:
        items.append(f"Literature: {r.absent('literature', 'literature')}")
    else:
        lit = r.literature
        [ads] = lit["search"]["sources"]["ads"].values()
        # Only a search ADS answered has a note.
        note = f" {ads['note']}" if ads.get("note") else ""
        items.append(
            f"Literature by name ({', '.join(lit['search']['names'])}) and NASA ADS: {lit['outcome']}, "
            f"{lit['reason']}.{note} The hits are listed below."
        )
    return _list(items) + "\n\n" + _exofop(r)


def _utc(btjd: float) -> str:
    return Time(btjd + 2457000.0, format="jd", scale="tdb").utc.strftime("%Y-%m-%d %H:%M")


def _two_minute(r: Record) -> str:
    sources = r.checks["sources"]
    spoc = sorted(
        int(s)
        for s, source in sources.items()
        if source["provenance"] == "SPOC" and source["cadence_s"] <= 120.0
    )
    if spoc:
        return f"In the sectors fetched, the star had SPOC 2-min data in sectors {_words(spoc)}."
    products: dict[str, set[float]] = {}
    for source in sources.values():
        products.setdefault(source["provenance"], set()).add(source["cadence_s"])
    listed = "; ".join(
        f"{name} at {_words([f'{c:g}' for c in sorted(cadences, reverse=True)])} s"
        for name, cadences in sorted(products.items())
    )
    return f"In the sectors fetched, the star never had SPOC 2-min data ({listed})."


def _ddt(r: Record) -> str:
    upcoming = r.checks["upcoming_sectors"]
    rule = (
        "2-min data and the DDT ask (M3 design, section 4.5): which stars get 2-min data in a sector is decided per "
        "cycle, so tess-point can't say whether these sectors will have it. " + _two_minute(r)
    )
    if not upcoming:
        return (
            rule
            + " With no upcoming TESS look there is no DDT ask; M4 decides this signal's route."
        )
    if r.call is None:
        return rule + (
            " If passed, M4 makes the DDT ask for 2-min data when the next look is full-frame images only. If held on "
            "the transit's shape, it may on the maintainer's call; held on blending, or killed, it does not, since "
            "2-min data come from the same pixels."
        )
    outcome = r.call["outcome"]
    if outcome == "passed":
        return (
            rule
            + " Passed: M4 makes the DDT ask for 2-min data if the next look is full-frame images only."
        )
    if outcome == "held":
        return rule + (
            " Held: the DDT ask applies only on the maintainer's call and only when the deciding evidence is the "
            "transit's shape; a hold on blending does not go, since 2-min data come from the same pixels. Deciding "
            f"evidence: {r.call['deciding_evidence']}"
        )
    return rule + " Killed: no DDT ask."


def _looks(r: Record) -> str:
    c = r.checks
    upcoming = c["upcoming_sectors"]
    if upcoming is None:
        return f"No upcoming sectors in this record ({c['windows_reason']})."
    parts = [
        f"tess-point places the star in sectors {_words(upcoming)}."
        if upcoming
        else "tess-point places the star in no upcoming sector."
    ]
    windows = c["windows"]
    if windows is None:
        parts.append(f"No predicted windows: {c['windows_reason']}.")
    elif upcoming:
        dated = [w for w in windows if "epoch" in w]
        sigmas = list(dated[0]["half_width_minutes"]) if dated else []
        rows = [
            [
                w["sector"],
                w["epoch"],
                f"{w['mid_btjd']:.3f}",
                _utc(w["mid_btjd"]),
                f"{w['sd_minutes']:.1f}",
                *(f"{w['half_width_minutes'][s]:.1f}" for s in sigmas),
            ]
            for w in dated
        ]
        duration = c["window_duration"]
        source = "the density-prior fit" if duration["from"] == "fit_prior" else "the signal"
        parts.append(
            "No sector with known dates holds a predicted transit."
            if not dated
            else "Each transit predicted in those sectors, from the density-prior fit's posterior (epochs count periods "
            f"from its t0); duration {duration['days']:.4f} d from {source}:\n\n"
            + _table(
                ["Sector", "Epoch", "Mid (BTJD)", "Mid (UTC)", "sd (min)"]
                + [f"{s} sigma half-width (min)" for s in sigmas],
                rows,
            )
        )
        unknown = [w["sector"] for w in windows if w.get("dates") == "unknown"]
        empty = [s for s in upcoming if s not in {w["sector"] for w in windows}]
        if unknown:
            parts.append(f"Dates not yet known for sector(s) {_words(unknown)}.")
        if empty:
            parts.append(f"No transit predicted in sector(s) {_words(empty)}.")
    parts.append(_ddt(r))
    return "\n\n".join(parts)


def _plots(r: Record) -> str:
    found = [
        (f"plots/{name}", caption)
        for name, caption in PLOTS.items()
        if (r.path / "plots" / name).is_file() and not (r.second and name == "centroids.png")
    ]
    if r.second and (r.path / SECOND_LIST_CENTROIDS[0]).is_file():
        found.append(SECOND_LIST_CENTROIDS)
    if not found:
        return "No plots in this record."
    return "\n\n".join(f"{caption}:\n\n![{caption}]({path})" for path, caption in found)


def _catalogued(r: Record) -> str:
    cat = r.checks["catalogued"]
    ours = cat["transits"]
    if not cat["rows"]:
        return "No catalogued row on this star."
    rows = []
    for row in cat["rows"]:
        masked = (
            "yes" if row["masked"] else "no, it is the signal" if row["matches_signal"] else "no"
        )
        if row["overlaps"] is None:
            overlap = "no epoch in the catalog"
        else:
            overlap = f"{len(row['overlaps'])} of {len(ours)}" + (
                f": {', '.join(str(n) for n in row['overlaps'])}" if row["overlaps"] else ""
            )
        rows.append(
            [row["source"], row["kind"], row["name"], _f(row["period"], ".5f"), masked, overlap]
        )
    note = (
        f"Every catalogued row on the star in the snapshot. vet-v3 masks only the kinds the search masks (decision "
        "0021); the rest stay unmasked. A row overlaps a transit of ours, numbered by epoch from the signal's t0, "
        f"when its mask window ({cat['mask_width_durations']:g} of its durations, or of "
        f"{cat['fallback_duration_days']:g} d where the catalog gives none) meets it. {len(ours)} transits of "
        "ours have data."
    )
    return (
        note
        + "\n\n"
        + _table(
            ["Source", "Kind", "Name", "Period (d)", "Masked", "Transits of ours it overlaps"], rows
        )
    )


def _paper_id(hit: dict) -> str:
    ids = [
        f"doi {hit['doi']}" if hit["doi"] else None,
        f"arXiv {hit['arxiv']}" if hit["arxiv"] else None,
    ]
    return ", ".join(i for i in ids if i) or ", ".join(hit["ids"])


def _hits(r: Record) -> str:
    if r.literature is None:
        return r.absent("literature", "literature")
    hits = r.literature["evidence"]["hits"]
    rows = [[h["title"], _paper_id(h), ", ".join(h["found_by"])] for h in hits]
    text = f"{len(hits)} paper(s) from the searches that answered, one row per paper."
    broad = r.literature["evidence"]["too_broad"]
    if broad:
        text += f" Too broad to list: {'; '.join(broad)}."
    return text + ("\n\n" + _table(["Title", "Id", "Found by"], rows) if rows else "")


def _suspect(r: Record) -> str:
    if r.suspect is None:
        return "No evidence-only run was given."
    with_them = {c["check"]: c for c in r.suspect["checks"]}
    rows = [
        [
            c["check"],
            c["outcome"],
            with_them[c["check"]]["outcome"],
            with_them[c["check"]]["reason"],
        ]
        for c in r.checks["checks"]
    ]
    added = _words(r.checks["dropped_suspect"]) or "none"
    return (
        "The same vet with the timing-suspect sectors kept in (decision 0022). It is shown for comparison and never "
        f"used for the call. Sectors it adds: {added}.\n\n"
        + _table(["Check", "Without them", "With them", "Reason with them"], rows)
    )


def render_review(review: dict) -> str:
    """The review's findings, each with its lens, rating and both refuters' verdicts (M3 design, section 4.8)."""
    confirmed = set(calls.confirmed(review))
    parts = [
        f"Reviewer {review['model']}, {review['date']}. {review['summary']}",
        "A finding rated kill or hold is confirmed when no refuter refuted it; a note gets no refuters.",
    ]
    for f in review["findings"]:
        head = f"### {f['id']} ({LENSES[f['lens']]}, {f['rating']})"
        if f["rating"] != "note":
            head += ": confirmed" if f["id"] in confirmed else ": refuted"
        verdicts = [
            f"Refuter {i}: {'refuted' if v['refuted'] else 'did not refute'}. {v['reason']}"
            for i, v in enumerate(f["refuters"], 1)
        ]
        body = f"Claim: {f['claim']}\n\nEvidence: {f['evidence']}"
        if verdicts:
            body += "\n\n" + _list(verdicts)
        elif f["rating"] != "note":
            body += "\n\nNo refuter has answered yet."
        parts.append(f"{head}\n\n{body}")
    flagged = ", ".join(review["hits_flagged"]) or "none"
    parts.append(f"Literature hits flagged for the maintainer to read: {flagged}.")
    return "\n\n".join(parts)


def _call(r: Record) -> str:
    call = r.call
    if call is None:
        return "No call yet."
    findings = {f["id"] for f in r.review["findings"]} if r.review else set()
    rests = ", ".join(f"{n} (finding)" if n in findings else n for n in call["rests_on"])
    lines = [
        f"Outcome: **{call['outcome']}**, {call['date']}.",
        f"Reasons: {call['reasons']}",
        f"Rests on: {rests or 'nothing named'}.",
        f"Criteria: {', '.join(call['criteria'])}.",
    ]
    if call["deciding_evidence"]:
        lines.append(f"Deciding evidence: {call['deciding_evidence']}")
    if call["promotion"]:
        lines.append(f"Promotion: {call['promotion']}")
    if call["answers"]:
        lines.append(
            "Answers to confirmed findings:\n\n"
            + _list([f"{k}: {v}" for k, v in call["answers"].items()])
        )
    if call["sentences"]:
        lines.append(
            "In one sentence each:\n\n"
            + _list(
                [
                    f"{SENTENCES[k]}: {call['sentences'][k]}"
                    for k in SENTENCES
                    if k in call["sentences"]
                ]
            )
        )
    if call["outcome"] == "passed":
        lines.append(f"Flagged hits read: {', '.join(call['hits_read']) or 'none were flagged'}.")
    return "\n\n".join(lines)


def render(signal_dir: Path) -> str:
    """The dossier for the signal whose record is in `signal_dir`: page one (the signal and the star, every check,
    the three questions, the next TESS looks), then the plots, the catalogued rows, the literature hits, the
    evidence-only vet, the review and the call."""
    r = Record(signal_dir)
    return PAGE.substitute(
        title=_title(r),
        status=_status(r),
        star=_star(r),
        checks=_checks(r),
        on_star=_on_star(r),
        planet=_planet(r),
        real_new=_real_new(r),
        looks=_looks(r),
        plots=_plots(r),
        catalogued=_catalogued(r),
        hits=_hits(r),
        suspect=_suspect(r),
        review="No review yet." if r.review is None else render_review(r.review),
        call=_call(r),
    )


def _not_listed(path: Path) -> list[str]:
    """Why the signal directory at `path` is not a published record whose call stands; empty when it is."""
    # publish writes dossier.md last of the record's files, so a directory without it was never published.
    if not ((path / "checks.json").is_file() and (path / "dossier.md").is_file()):
        return ["not published: a call with no record beside it"]
    return calls.problems(path)


def listed(
    vetting_root: Path, staged: Path | None = None
) -> tuple[list[Path], dict[str, list[str]]]:
    """The signal directories the README lists (a published record whose call stands), and why each other
    directory holding a call is left out. `staged` stands in for the directory of its name, so `vetting publish`
    renders the README before it copies anything."""
    dirs = {call.parent.name: call.parent for call in vetting_root.glob("*/call.toml")}
    if staged is not None:
        dirs[staged.name] = staged
    shown, left = [], {}
    for name in sorted(dirs):
        why = _not_listed(dirs[name])
        if why:
            left[name] = why
        else:
            shown.append(dirs[name])
    return shown, left


def readme(vetting_root: Path, staged: Path | None = None) -> str:
    """results/vetting/README.md: one row per published signal whose call stands, from the call files."""
    rows = []
    for path in listed(vetting_root, staged)[0]:
        call = calls.load(path / "call.toml")
        rows.append(
            f"| [{path.name}]({path.name}/dossier.md) | {call['outcome']} | {call['date']} | "
            f"{_cell(call['reasons'])} |"
        )
    return README.substitute(rows="\n".join(rows))
