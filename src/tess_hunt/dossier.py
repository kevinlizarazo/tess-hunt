"""The dossier: one signal's record rendered for the maintainer's call and for the public record (M3 design, section
4.7; decision 0028). It reads only the files in the signal's directory. The template is filled with `substitute` and
each value is read by its key, so a value the record lacks raises instead of rendering (docs/design.md, section
5.5)."""

import json
import re
from pathlib import Path
from string import Template

from tess_hunt import calls
from tess_hunt.predict import seen_utc
from tess_hunt.provenance import scrub, unname

PAGE = Template("""\
# $title

$status$changes

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
(`dossier.md`), the call (`call.toml`), the review (`review.json`), the review's scripts and outputs
(`review-scripts.tar.gz`) and the run files the dossier is rendered from; [../README.md](../README.md) describes each
file. A passed signal is a planet candidate, not a confirmed planet.

| Signal | Outcome | Date | Reason |
|---|---|---|---|
$rows

## Reading the reviews

Each review (`review.json`, quoted in `dossier.md`) cites its evidence by the names it had on the machine the reviews
ran on: scratch directories, draft records and shell variables holding run ids. This key says what each stands for.

- `/tmp/t13/<name>/` was the review's scratch directory. Its scripts and their small outputs are in
  `<name>/review-scripts.tar.gz`, under `t13/<name>/`, with a `MANIFEST.txt` listing each file left out and why (fetched
  from a service, 1 MB (1,000,000 bytes) or over, a copy of a published file, and so on). `/tmp/t13/` itself, the
  scripts every review shared, is in [review-scripts.tar.gz](review-scripts.tar.gz), under `t13/`: among them
  `heavy.sh`, which ran each memory-heavy command one at a time once 6 GB were free and under a 6 GB cap, `assemble.py`,
  which made `review.json` from a review workflow's output, and `compare_runs.py` and `cmp_control_vet.py`, which
  compared runs for decisions 0034 and 0036. `/tmp/pixel-diag/` was the pixel check's diagnosis, published as
  [pixel-check-diagnosis-2026-10-20-scripts.tar.gz](../benchmarks/pixel-check-diagnosis-2026-10-20-scripts.tar.gz).
- "The brief" is the review brief every reviewer and refuter was given: [review-brief.md](review-brief.md). "M3
  design, section N" in it and in the reviews is the milestone's design, kept outside the repository, from which
  [docs/design.md](../../docs/design.md) was amended. The brief's `/mnt/c/code/docs/tess-hunt-m3-design.md` and the
  reviews' `C:\\code\\docs\\tess-hunt-m3-design.md` are both that private design on the maintainer's machine (the
  dossiers show it as `tess-hunt-m3-design.md`); it is not published, and the public spec is
  [docs/design.md](../../docs/design.md).
- `~` is the maintainer's home directory and `$$TESS_HUNT_DATA` the data directory (by default `~/.cache/tess-hunt`);
  `~/code/tess-hunt` is the maintainer's checkout of this repository. A run id names a directory under
  `$$TESS_HUNT_DATA/runs/`. `review.json` keeps every other path as the review wrote it; `dossier.md` shows a path
  elsewhere on the maintainer's machine by its file name alone.
- "The maintainer" in the reviews, the brief and the tarballs stands where they gave the maintainer's name, rewritten
  by the same step that rewrites the home directory
  ([decision 0038](../../docs/decisions/0038-literature-trim-and-username-scrub.md)).
- `drafts/m3/<name>/` and `drafts/m3-r2/<name>/`, under `$$TESS_HUNT_DATA`, are draft records `tess-hunt vetting
  dossier` laid out: `drafts/m3` from the first runs (`VET_RUN`, `VET_SUSPECT_RUN`, `TRIC_RUN`, `LIT_RUN`,
  `SECOND_RUN`), `drafts/m3-r2` from the reruns after decisions 0034 to 0036 (`VET2_RUN`, `VET2_SUSPECT_RUN`,
  `TRIC2_RUN`, `TRIC3A_RUN`, `TRIC3B_RUN`, `LIT3_RUN`, `SECOND2_RUN`). Each published record holds its runs' files as
  `drafts/m3-r2` held them, and its `provenance-*.json` files name its runs.
- The shell variables, set by files under `$$TESS_HUNT_DATA/logs/` that are not published, each hold a run id (or,
  for `SNAP3`, a catalog snapshot under `$$TESS_HUNT_DATA/catalogs/`):

| Variable | Run | What it is |
|---|---|---|
| `SEARCH_RUN` | [`20261014T205855Z-search-fe29585-cdf2`](../benchmarks/20261014T205855Z-search-fe29585-cdf2) | M2's production search |
| `THRESHOLD_RUN` | [`20261014T175116Z-threshold-0d6748e-40ac`](../benchmarks/20261014T175116Z-threshold-0d6748e-40ac) | M2's detection threshold |
| `TRIAGE_RUN` | [`20261015T155441Z-triage-7b12e25-3f57`](../triage/20261015T155441Z-triage-7b12e25-3f57) | M2's triage, with LEO-Vetter and the pixel check |
| `SNAP3` | `2026-10-17T142814Z` | the catalog snapshot novelty used (not published) |
| `CONTROLS_RUN` | [`20261020T082333Z-benchmark-controls-16418d2-f45a`](../benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a) | vet-v3's controls |
| `VET_RUN` | `20261020T010149Z-vetting-run-62882b5-c3ee` | vet-v3 on the 19 signals, first run |
| `VET_SUSPECT_RUN` | `20261020T011247Z-vetting-run-62882b5-d92b` | the same with the timing-suspect sectors kept in, evidence only |
| `SECOND_RUN` | `20261020T012658Z-vetting-second-list-62882b5-3fca` | the second list, first run |
| `TRIC_RUN` | `20261020T013408Z-vetting-triceratops-62882b5-e092` | TRICERATOPS, first run |
| `LIT_RUN` | `20261020T091938Z-vetting-literature-2315775-066c` | the literature search, first run |
| `VET2_RUN` | `20261020T174317Z-vetting-run-61b5944-2d70` | vet-v3 on the 19 signals, rerun after decisions 0034 and 0035 |
| `VET2_SUSPECT_RUN` | `20261020T175536Z-vetting-run-61b5944-7f4e` | its evidence-only twin |
| `SECOND2_RUN` | [`20261020T180844Z-vetting-second-list-61b5944-7096`](../benchmarks/20261020T180844Z-vetting-second-list-61b5944-7096) | the second list, rerun |
| `TRIC2_RUN` | `20261020T181658Z-vetting-triceratops-61b5944-1bbf` | TRICERATOPS on the rerun, before decision 0036 |
| `LIT3_RUN` | `20261021T001540Z-vetting-literature-61b5944-07de` | the literature search on the rerun |
| `TRIC3A_RUN` | `20261021T044850Z-vetting-triceratops-cd4e7a2-07c3` | TRICERATOPS on the five promoted second-list rows, after decision 0036 |
| `TRIC3B_RUN` | `20261021T194348Z-vetting-triceratops-cd4e7a2-7821` | TRICERATOPS on 399023421-1, 296819076-1, 103312990-1 and 44926986-1, after decision 0036 |

Five benchmark notes and three tarballs under `../benchmarks/`, published on 2026-10-20 and 21 before the scrub of
[decision 0038](../../docs/decisions/0038-literature-trim-and-username-scrub.md), still give the maintainer's home
directory in full. Read it as `~`, its `.cache/tess-hunt` as `$$TESS_HUNT_DATA`, and its `code/tess-hunt-run` as a
second checkout of this repository.
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
# The directories of a path on a Windows drive, or on one WSL mounts, as the reviews ran from Windows.
MACHINE_DIRS = re.compile(r"(?:\b[A-Za-z]:[\\/]|/mnt/[a-z]/)(?:[^\\/\s\"'`()]+[\\/])*")
# The decision records the dossier cites, linked from results/vetting/<name>/dossier.md.
DECISIONS = {
    "0021": "0021-vet-masks-search-kinds.md",
    "0022": "0022-vet-without-timing-suspect-sectors.md",
    "0026": "0026-triceratops.md",
    "0028": "0028-outcomes-and-calls.md",
    "0037": "0037-quoted-text-in-the-dossier.md",
    "0038": "0038-literature-trim-and-username-scrub.md",
    "0039": "0039-ddt-for-held-signals.md",
    "0040": "0040-predictions-for-held-signals.md",
    "0041": "0041-revets-as-versions.md",
}
# Each novelty evidence list of catalog rows a signal matched.
NOVELTY_MATCHES = ("matches", "period_matches", "objects", "tce_matches", "tce_period_matches")
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


def _scrub(text: str) -> str:
    """Quoted text as the dossier shows it, with no machine path (docs/design.md, section 6.2) and no maintainer's
    name: the data and home directories as tess-hunt's scrub writes them, the name as `unname` writes it, and a path
    elsewhere on the machine by its file name alone."""
    return MACHINE_DIRS.sub("", unname(scrub(text)))


def _decision(number: str, vetting: str = "../") -> str:
    """A link to a decision record from a dossier `vetting` below results/vetting/."""
    return f"[decision {number}]({vetting}../../docs/decisions/{DECISIONS[number]})"


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
        self.name = calls.signal_name(path)
        self.version = calls.version(path)
        # The relative path from the dossier to results/vetting/: a version sits a level deeper.
        self.vetting = "../../" if self.version else "../"
        self.checks = json.loads((path / "checks.json").read_text())
        self.provenance = {
            role: _json(path / f"provenance-{role}.json")
            for role in (
                "checks",
                "triceratops",
                "literature",
                "checks-with-suspect",
                "second-list",
                "titles",
                "merge",
                "prereg",
            )
        }
        # A version's dossier says what changed since the record before it, from that record's checks alone.
        self.before = self.before_provenance = None
        if self.version:
            previous = path.parent if self.version == 2 else path.parent / f"r{self.version - 1}"
            self.before = json.loads((previous / "checks.json").read_text())
            self.before_provenance = json.loads((previous / "provenance-checks.json").read_text())
        self.merge = _json(path / "merge.json")
        self.prereg = _json(path / "prereg.json")
        self.pixels = calls.pixels(path, self.checks)
        self.triceratops = _json(path / "triceratops.json")
        self.literature = _json(path / "literature.json")
        self.suspect = _json(path / "checks-with-suspect.json")
        has_review = (path / "review.json").is_file()
        self.review = calls.load_review(path / "review.json") if has_review else None
        self.call = calls.load(path / "call.toml") if (path / "call.toml").is_file() else None
        notes = path / "review-notes.toml"
        self.notes = calls.load_notes(notes, self.review) if self.review and notes.is_file() else {}

    def decision(self, number: str) -> str:
        return _decision(number, self.vetting)

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
    version = f" r{r.version}" if r.version else ""
    return f"{r.name}{version}: TIC {r.checks['star']['tic']}"


def _status(r: Record) -> str:
    source = (
        f"Rendered from the files in this directory ({r.decision('0028')}); the review and the call are quoted, not "
        f"rendered ({r.decision('0037')})."
    )
    if r.version:
        source += (
            " What changed since the record before it is read from that record's `checks.json`."
        )
    if r.call is None:
        return f"Draft: no call yet. {source}"
    return f"Call: **{r.call['outcome']}** on {r.call['date']}. {source}"


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
        ("titles", "titles"),
        ("merge", "revet fetch"),
        ("prereg", "preregistered test"),
    ):
        p = r.provenance[role]
        if p is not None:
            kind = "production" if p["production"] else "not production"
            out.append(f"{label} {p['run_id']} (commit {p['git']['commit'][:7]}, {kind})")
    return "; ".join(out)


def _triage(r: Record) -> str:
    """The triage run whose ModShift and pixel evidence the vetting run read, and the criteria it judged under."""
    made = r.provenance["checks"]
    if made["triage_run"] is None:
        return "none: the vetting run read no triage run"
    # A vetting run made before M4's deferred minors recorded no triage criteria file.
    used = made["inputs"].get("triage_criteria")
    if used is None:
        return f"triage run {made['triage_run']} (the vetting run recorded no criteria file for it)"
    return f"triage run {made['triage_run']}, under {Path(used['file']).stem}"


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
        ["Triage", _triage(r)],
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
    # A record made before decision 0034 doesn't name its centre: every such table ran from the TIC position.
    centre = evidence.get("centre", "TIC position, J2000")
    return (
        f"{head} Each Gaia DR3 star that could make the dip, with its separation from the target "
        f"({centre}) and the eclipse depth it would need, scaled from the depth in "
        f"{evidence['depth_from']} ({_ppm(evidence['depth'])} ppm) as if all its light fell in the aperture"
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
    # A star the table could not judge is never marked possible, so its list can leave a host out.
    unjudged = f"it could not judge every star: {nb['reason']}"
    if hosts and nb["outcome"] != "pass":
        lines.append(f"The neighbour table lists possible hosts, but {unjudged}.")
    if hosts is None:
        lines.append("No neighbour table was built, so whether a possible host exists is unknown.")
    elif not hosts and nb["outcome"] == "pass":
        lines.append("The neighbour table lists no possible host for it to weigh.")
    elif not hosts:
        lines.append(f"The neighbour table lists no possible host, but {unjudged}.")
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
                f"Evidence for the review, not a blocker ({r.decision('0026')})."
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
    flat = check["evidence"]["rp_rearth"] if check["outcome"] != "inconclusive" else None
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
    b = shape["evidence"]["b_median"] if shape["outcome"] != "inconclusive" else None
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
    # ExoFOP's comments stay ExoFOP's contributors' words and are not shown (decision 0038).
    lines = [
        f"ExoFOP, read live: TOIs {tois}; CTOIs {ctois}; confirmed planets "
        f"{x['confirmed_planets'] or 'none'}."
    ]
    if planets:
        lines.append("Planet parameters on ExoFOP:\n\n" + _list(planets))
    return "\n\n".join(lines)


def _prereg(r: Record) -> str:
    """The preregistered test of the new season (decision 0040), from prereg.json, for the line beside vet-v3's own
    held-out result."""
    p = r.prereg
    head = (
        f"The preregistered test of the new season ({r.decision('0040')}), package {p['package']}, as of "
        f"{p['as_of']}: "
    )
    if p["result"] == "pending":
        said = f"pending: {p['reason']}."
    elif p["result"] == "untested":
        said = f"untested ({p['status']}): {p['reason']}."
    else:
        tension = f"tension {p['tension']:.2f} sigma" if "tension" in p else p["tension_skipped"]
        said = (
            f"{p['result']} ({p['status']}): depth {_ppm(p['depth'])} ppm (error {_ppm(p['err'])} ppm, {p['n']} "
            f"cadences in the cores), {p['sigma']:.2f} sigma, expected SNR {p['expected_snr']:.2f}, {tension}."
        )
    made = r.provenance["prereg"]
    if made is not None and made["vetting_run"] != r.provenance["checks"]["run_id"]:
        said += (
            f" Carried unchanged from {_vetted_by(r, made['vetting_run'])}, which judged it (vetting run "
            f"{made['vetting_run']}): decision 0040 judges a signal once."
        )
    return (
        head
        + said
        + " It judges only the new season, against the prediction published before that season; vet-v3's held-out "
        "check above holds out each season in turn and refits on the rest."
    )


def _vetted_by(r: Record, vetting_run: str) -> str:
    """The record beside this one that `vetting_run` vetted, by name."""
    signal = r.path.parent if r.version else r.path
    versions = sorted((p for p in signal.glob("r*") if calls.version(p)), key=calls.version)
    for path in (signal, *versions):
        made = _json(path / "provenance-checks.json")
        if made is not None and made["run_id"] == vetting_run:
            return "the M3 record" if path == signal else path.name
    return "an earlier version"


def _real_new(r: Record) -> str:
    novelty = r.check("novelty")
    tce = novelty["evidence"].get("tce_matches") or []
    tce += novelty["evidence"].get("tce_period_matches") or []
    items = [
        f"Signal present: {r.said('signal_present')}.",
        f"Held-out seasons: {r.said('holdout')}.",
        *([_prereg(r)] if r.prereg is not None else []),
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
        f"2-min data and the DDT ask ({r.decision('0026')}): which stars get 2-min data in a sector is decided per "
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
            "the transit's shape, it may on the maintainer's call; held on blending it does not, since 2-min data "
            "come from the same pixels; killed, it does not."
        )
    outcome = r.call["outcome"]
    if outcome == "passed":
        return (
            rule
            + " Passed: M4 makes the DDT ask for 2-min data if the next look is full-frame images only."
        )
    if outcome == "held":
        return rule + (
            " Held: the DDT ask applies only on the maintainer's call and only when 2-min data would supply its "
            "deciding evidence: the transit's shape, or a season no public light curve will otherwise cover; a hold "
            "on blending does not go, since 2-min data come from the same pixels "
            f"({r.decision('0039')}). Deciding evidence: {r.call['deciding_evidence']}"
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
        # A 1-sigma half-width is the sd column again.
        sigmas = [s for s in (dated[0]["half_width_minutes"] if dated else []) if float(s) != 1]
        rows = [
            [
                w["sector"],
                w["epoch"],
                f"{w['mid_btjd']:.3f}",
                seen_utc(w["mid_btjd"], c["star"]["ra"], c["star"]["dec"]),
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
            f"from its t0); duration {duration['days']:.4f} d from {source}. Mid (UTC) is when the transit is seen "
            "from Earth: the barycentric time less the light's travel time toward the star:\n\n"
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
    # Before `vetting run` caught each plot's failure, one that raised discarded the vet, so a record that names no
    # failed plot drew every one.
    failed = r.checks.get("plot_errors", {})
    shown = []
    for name, caption in PLOTS.items():
        # A second-list row's centroid plot is the second list's, below.
        if r.second and name == "centroids.png":
            continue
        if (r.path / "plots" / name).is_file():
            shown.append(f"{caption}:\n\n![{caption}](plots/{name})")
        elif name in failed:
            shown.append(f"{caption}: not drawn ({failed[name]}).")
    if r.second:
        name, caption = SECOND_LIST_CENTROIDS
        if (r.path / name).is_file():
            shown.append(f"{caption}:\n\n![{caption}]({name})")
        elif r.pixels is None:
            shown.append(f"Centroids: no plot ({r.no_pixels()}).")
        else:
            # A second-list run made before the second list drew its own plot.
            run = r.provenance["second-list"]["run_id"]
            shown.append(
                f"Centroids: no plot (second-list run {run} drew none beside its pixels.json)."
            )
    if not shown:
        return "No plots in this record."
    return "\n\n".join(shown)


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
        "Every catalogued row on the star in the snapshot. vet-v3 masks only the kinds the search masks "
        f"({r.decision('0021')}); the rest stay unmasked. A row overlaps a transit of ours, numbered by epoch from "
        "the signal's t0, "
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
    rows = [[h["title"] or "", _paper_id(h), ", ".join(h["found_by"])] for h in hits]
    text = f"{len(hits)} paper(s) from the searches that answered, one row per paper. " + (
        "Titles come only from open sources: the search's own arXiv, OpenAlex and Zenodo hits, else OpenAlex's "
        "record for the paper's DOI; a paper none of them titles has a blank title "
        f"({r.decision('0038')})."
        if "trim" in r.literature
        else "Titles as the searches gave them, ADS's among them; a published record keeps only open sources' "
        f"titles ({r.decision('0038')})."
    )
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
        f"The same vet with the timing-suspect sectors kept in ({r.decision('0022')}). It is shown for comparison and "
        "never "
        f"used for the call. Sectors it adds: {added}.\n\n"
        + _table(["Check", "Without them", "With them", "Reason with them"], rows)
    )


def render_review(
    review: dict, notes: dict[str, list[dict]] | None = None, vetting: str = "../"
) -> str:
    """The review's findings, each with its lens, rating and both refuters' verdicts (M3 design, section 4.8), and
    beside a finding any note added on it under decision 0037 (review-notes.toml), marked as no part of the review.
    Its links lead from a dossier `vetting` below results/vetting/."""
    confirmed = set(calls.confirmed(review))
    notes = notes or {}
    parts = [
        f"Quoted from `review.json`, as the reviewer and the refuters wrote it: its numbers, paths and run names are "
        f"theirs, not rendered from the runs ({_decision('0037', vetting)}). [The vetting README]({vetting}README.md) "
        "says what its paths and run names stand for.",
        f"Reviewer {review['model']}, {review['date']}. {review['summary']}",
        "A finding rated kill or hold is confirmed when no refuter refuted it; a note gets no refuters.",
    ]
    for f in review["findings"]:
        head = f"### {f['id']} ({LENSES[f['lens']]}, {f['rating']})"
        if f["rating"] != "note":
            head += ": confirmed" if f["id"] in confirmed else ": refuted"
            # Confirmed only because nothing refuted it: the reader should not take it for tested.
            if not f["refuters"]:
                head += ", no refuter ran on it"
        verdicts = [
            f"Refuter {i}: {'refuted' if v['refuted'] else 'did not refute'}. {v['reason']}"
            for i, v in enumerate(f["refuters"], 1)
        ]
        body = f"Claim: {f['claim']}\n\nEvidence: {f['evidence']}"
        if verdicts:
            body += "\n\n" + _list(verdicts)
        elif f["rating"] != "note":
            body += "\n\nNo refuter ran on it."
        for note in notes.get(f["id"], []):
            body += (
                f"\n\n**Note added on {note['date']} under {_decision('0037', vetting)}, not part of the review or the "
                f"call:** {note['text']}"
            )
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
        f"Quoted from `call.toml`, the maintainer's words, not rendered from the runs ({r.decision('0037')}).",
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


def _sectors(sectors: list) -> str:
    return _words([f"S{s}" for s in sectors])


def _file(product: dict) -> str:
    return Path(product["s3_key"]).name


def _light_curve_changes(r: Record) -> str:
    """What the revet fetch run's merge record says changed in the light curve (decision 0041)."""
    sectors = r.merge[str(r.checks["tic"])]["sectors"]

    def listed(status: str, said) -> str:
        found = [
            said(int(s), x)
            for s, x in sorted(sectors.items(), key=lambda item: int(item[0]))
            if x["status"] == status
        ]
        return _words(found) or "none"

    added = listed("added", lambda s, x: f"S{s} ({x['fresh']['provenance']})")
    redelivered = listed(
        "redelivered",
        lambda s, x: (
            f"S{s} ({x['base']['provenance']}, {_file(x['base'])} replaced by {_file(x['fresh'])})"
        ),
    )
    kept = listed(
        "kept_m2",
        lambda s, x: f"S{s} ({x['base']['provenance']} kept, {x['fresh']['provenance']} not taken)",
    )
    return (
        f"The light curve, from revet fetch run {r.provenance['merge']['run_id']} (`merge.json`), keeps every sector of "
        f"the earlier one as it was fetched, but for these. Sectors added: {added}. Redelivered (a timing-suspect "
        f"product replaced by the same product's newer delivery): {redelivered}. Kept as first fetched though the new "
        f"fetch found another product: {kept}."
    )


def _post_dictions(r: Record) -> str | None:
    """Windows in sectors the light curve already holds: vet-v3 predicts from a fixed first sector, so a re-vet's
    windows there were not predictions."""
    held = {int(s) for s in r.checks["sources"]}
    post = sorted({w["sector"] for w in r.checks["windows"] or [] if "epoch" in w} & held)
    if not post:
        return None
    return (
        f"The windows for {_sectors(post)} under Next TESS looks are post-dictions, not predictions: this light curve "
        f"already holds {'that sector' if len(post) == 1 else 'those sectors'}."
    )


def _carried_pixels(r: Record, earlier: str) -> str | None:
    second = r.provenance["second-list"]
    if second is None or second["vetting_run"] == r.provenance["checks"]["run_id"]:
        return None
    return (
        f"The second list's pixel check is carried from {earlier}: second-list run {second['run_id']}, made from "
        f"vetting run {second['vetting_run']}, is not run again on a re-vet ({r.decision('0041')})."
    )


def _diff(before: list[str], now: list[str]) -> str:
    new = [x for x in dict.fromkeys(now) if x not in before]
    gone = [x for x in dict.fromkeys(before) if x not in now]
    parts = [
        f"{label}: {'; '.join(items)}" for label, items in (("new", new), ("gone", gone)) if items
    ]
    return "; ".join(parts) or "the same"


def _masked(checks: dict) -> list[str]:
    return [f"{m['period']:.5f} d (t0 BTJD {m['t0']:.4f})" for m in checks["masked"]]


def _rows(checks: dict) -> list[str]:
    return [
        f"{x['source']} {x['kind']} {x['name']} at {_f(x['period'], '.5f')} d"
        for x in checks["catalogued"]["rows"]
    ]


def _novelty_matches(checks: dict) -> list[str]:
    evidence = next(c for c in checks["checks"] if c["check"] == "novelty")["evidence"]
    return [
        f"{m['source']} {m['name']} at "
        + ("no period" if m.get("period") is None else f"{m['period']:.6g} d")
        + (f", ratio {m['ratio']:g}" if m.get("ratio") is not None else "")
        for key in NOVELTY_MATCHES
        for m in evidence.get(key) or []
    ]


def _snapshot(provenance: dict) -> str:
    """The catalog snapshot a vetting run read: recorded since decision 0041, in the arguments before it."""
    if "catalogs" in provenance:
        return provenance["catalogs"]
    argv = provenance["argv"]
    return Path(argv[argv.index("--catalogs") + 1]).name


def _snapshot_changes(r: Record, earlier: str) -> str:
    """The masked rows, catalogued rows and novelty matches that differ between the two versions' checks: what a
    fresh catalog snapshot changed, read without the snapshots."""
    before, now = r.before, r.checks
    old, new = (next(c for c in x["checks"] if c["check"] == "novelty") for x in (before, now))
    said = [f"{c['outcome']} ({c['reason']})" for c in (old, new)]
    novelty = (
        f"{said[1]} in both"
        if said[0] == said[1]
        else f"{said[0]} in {earlier}, {said[1]} in this version"
    )
    return (
        f"Against {earlier}'s `checks.json`, which vetted with catalog snapshot `{_snapshot(r.before_provenance)}` "
        f"(this version: `{_snapshot(r.provenance['checks'])}`):\n\n"
        + _list(
            [
                f"Masked rows: {_diff(_masked(before), _masked(now))}.",
                f"Catalogued rows on the star: {_diff(_rows(before), _rows(now))}.",
                f"Novelty: {novelty}.",
                f"Its matches: {_diff(_novelty_matches(before), _novelty_matches(now))}.",
            ]
        )
    )


def _changes(r: Record) -> str:
    """A version's record (decision 0041): the version before it, linked, and what changed since it."""
    if r.version is None:
        return ""
    earlier = "the M3 record" if r.version == 2 else f"r{r.version - 1}"
    link = "../dossier.md" if r.version == 2 else f"../r{r.version - 1}/dossier.md"
    parts = [
        f"Version {r.version} of this signal's record, a re-vet on newer data ({r.decision('0041')}). "
        f"[{earlier[0].upper()}{earlier[1:]}]({link}) stays as it was published.",
        _light_curve_changes(r),
        _post_dictions(r),
        _carried_pixels(r, earlier),
        _snapshot_changes(r, earlier),
    ]
    return f"\n\n## Changes since {earlier}\n\n" + "\n\n".join(p for p in parts if p)


def render(signal_dir: Path) -> str:
    """The dossier for the signal whose record is in `signal_dir`: page one (the signal and the star, every check,
    the three questions, the next TESS looks), then the plots, the catalogued rows, the literature hits, the
    evidence-only vet, the review and the call."""
    r = Record(signal_dir)
    return PAGE.substitute(
        title=_title(r),
        status=_status(r),
        changes=_changes(r),
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
        review="No review yet."
        if r.review is None
        else _scrub(render_review(r.review, r.notes, r.vetting)),
        call=_scrub(_call(r)),
    )


def _not_listed(path: Path) -> list[str]:
    """Why the signal directory at `path` is not a published record whose call stands; empty when it is."""
    # publish writes dossier.md last of the record's files, so a directory without it was never published.
    if not ((path / "checks.json").is_file() and (path / "dossier.md").is_file()):
        return ["not published: a call with no record beside it"]
    return calls.problems(path)


def _key(path: Path) -> str:
    """A record's path under results/vetting/: the signal's name, and for a version its directory under it."""
    return f"{path.parent.name}/{path.name}" if calls.version(path) else path.name


def listed(
    vetting_root: Path, staged: Path | None = None
) -> tuple[list[Path], dict[str, list[str]]]:
    """The record directories whose call stands (a published record: the M3 record or a version of it), by signal
    and version, and why each other directory holding a call is left out, by its path under `vetting_root`. `staged`
    stands in for the directory of its path, so `vetting publish` renders the README before it copies anything."""
    found = [
        call.parent
        for call in (*vetting_root.glob("*/call.toml"), *vetting_root.glob("*/r*/call.toml"))
        if call.parent.parent == vetting_root or calls.version(call.parent)
    ]
    dirs = {_key(path): path for path in found}
    if staged is not None:
        dirs[_key(staged)] = staged
    shown, left = [], {}
    for key in sorted(
        dirs, key=lambda k: (calls.signal_name(dirs[k]), calls.version(dirs[k]) or 1)
    ):
        why = _not_listed(dirs[key])
        if why:
            left[key] = why
        else:
            shown.append(dirs[key])
    return shown, left


def _published(path: Path) -> bool:
    return (path / "checks.json").is_file() and (path / "dossier.md").is_file()


def readme(vetting_root: Path, staged: Path | None = None) -> str:
    """results/vetting/README.md: one row per published signal, its latest version whose call stands, from the call
    files, with links to the versions before it (decision 0041)."""
    latest = {calls.signal_name(path): path for path in listed(vetting_root, staged)[0]}
    rows = []
    for name, path in latest.items():
        call = calls.load(path / "call.toml")
        version = calls.version(path)
        cell = f"[{name}]({name}/dossier.md)"
        if version:
            earlier = [("M3 record", name)] if _published(vetting_root / name) else []
            earlier += [
                (f"r{n}", f"{name}/r{n}")
                for n in range(2, version)
                if _published(vetting_root / name / f"r{n}")
            ]
            links = ", ".join(f"[{label}]({where}/dossier.md)" for label, where in earlier)
            cell = f"[{name} r{version}]({name}/r{version}/dossier.md)" + (
                f" (earlier: {links})" if links else ""
            )
        rows.append(f"| {cell} | {call['outcome']} | {call['date']} | {_cell(call['reasons'])} |")
    return README.substitute(rows="\n".join(rows))
