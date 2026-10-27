# Task 13 review brief (one signal per workflow)

You review one signal from tess-hunt milestone 3, a search for transiting planets in public TESS light curves. Your
job is to kill it. Find every reason the dip is not a planet on this star, not real, or not new. The review kills
nothing and passes nothing itself (M3 design, section 4.8). Each finding you report goes to the maintainer.
A finding that shows a check is wrong goes to a decision record, never to a quiet rerun.

The workflow names the signal (`<name>`, e.g. `399023421-1`) and says which brief applies:
- **Full brief:** the signal failed no check.
- **Short brief:** a check killed the signal. See "Signals a check killed" below.

## What you have (all read-only)

- **The draft dossier:** `~/.cache/tess-hunt/drafts/m3-r2/<name>/dossier.md`, with its plots and the run files it
  was rendered from in the same folder: `checks.json`, `checks-with-suspect.json`, `triceratops.json`,
  `literature.json`, `neighbours.csv`, `probs.csv` and the `provenance-*.json` files. Start here. (`drafts/m3/` holds
  the first drafts, from runs with the two defects below; don't review from them.)
- **The run directories.** `. ~/.cache/tess-hunt/logs/m3-vars.sh; . ~/.cache/tess-hunt/logs/m3-rerun-vars.sh`
  exports them. The signals' chain was rerun on 2026-10-20 after decisions 0034 (the neighbour table's epochs) and
  0035 (holdout's training seasons); the dossier comes from the rerun. TRICERATOPS was run again on 2026-10-21 after
  decision 0036 (it had weighed the TIC's DUPLICATE and ARTIFACT rows as stars):
  - `VET2_RUN`: vet-v3 on the 19 signals.
  - `VET2_SUSPECT_RUN`: the same with the timing-suspect sectors kept in. Evidence only.
  - `TRIC2_RUN`: TRICERATOPS on six signals, from before 0036. 146282666-1 and 164767175-1 keep it (their star
    lists held no flagged row).
  - `TRIC3A_RUN`: TRICERATOPS on the five promoted second-list rows, on 0036's code.
  - `TRIC3B_RUN`: TRICERATOPS on 399023421-1, 296819076-1, 103312990-1 and 44926986-1, on 0036's code (recorded when
    it finishes).
  - Run `20261021T025929Z-vetting-triceratops-61b5944-55f4` was stopped unfinished for 0036. It is not a record.
  - `LIT3_RUN`: literature by name, NASA ADS and ExoFOP.
  - `SECOND2_RUN`: the second list.
  - `VET_RUN`, `VET_SUSPECT_RUN`, `TRIC_RUN`, `LIT_RUN`, `SECOND_RUN`: the first runs. Compare with them if useful,
    never quote them as the signal's record.
  - `TRIAGE_RUN`: M2's triage, with LEO-Vetter and the pixel check.
  - `SNAP3`: the catalog snapshot novelty used.
  - `CONTROLS_RUN`: vet-v3's controls.
  - Each signal's light curves and fits are under `signals/<name>/` in its run.
- **The repo**, at `~/code/tess-hunt` (branch `milestone-3-vetting`):
  - `docs/design.md` is the project's design. M3's design, which section numbers such as 4.8 refer to, is outside
    the repo: `/mnt/c/code/docs/tess-hunt-m3-design.md`.
  - `docs/decisions/` holds the records. Read 0021 to 0028 and 0031 to 0036 at least.
  - `criteria/vet-v3.toml` holds the thresholds.
  - `results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md` is how vet-v3 did on 20 known
    planets and 4 negative controls.
  - `results/benchmarks/vet-v3-control-diagnosis-2026-10-17.md` diagnoses each control failure.
  - `.superpowers/sdd/tess-hunt-m3-plan/t11/pixel-diagnosis.md` diagnoses triage's pixel check: its four known-planet
    fails and the second list's six fails. It is published as
    `results/benchmarks/pixel-check-diagnosis-2026-10-20.md` with decision 0033; either copy will do.
  - The source is in `src/tess_hunt/`.

How to run things:
- From Git Bash: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-26.04 --cd ~/code/tess-hunt -- bash -l -s <<'EOF'
  ... EOF`.
- Use `uv run python` inside WSL, never `python` in Git Bash.
- Anything that loads light curves, images or fits runs through `/tmp/t13/heavy.sh <command> [args...]`. It runs
  one such command at a time across all review agents, waits for 6 GB free, and applies the 6 GB cap. Exit 75 means
  memory never came free: say so in your evidence rather than running it another way. Reading JSON, CSV and text
  files needs no wrapper.
- Scratch goes in `/tmp/t13/<name>/` only.

## Rules

- **Read-only.** Never write to the repo, a run directory or the drafts. Don't commit, push or dispatch subagents.
- **No outside contact.** Don't post to ExoFOP, TFOP, Zenodo or any person. Reading public pages is fine: ExoFOP,
  MAST, SIMBAD, arXiv, ADS's web UI. Never use or read the ADS token.
- **Numbers.** Every number in a finding comes from a run file or from a command you show. Give the path or the
  command, so a refuter can reproduce it.
- **Style.** Plain words, no em dashes.

## The three lenses, with the cases to test (design 4.8)

**On the star (`on_star`)**
- Blends with a Gaia neighbour: the neighbour table and the eclipse depth each neighbour would need. Since decision
  0034, `neighbours.csv`'s `sep_arcsec` runs from the target's own Gaia DR3 position at J2016.0; the check's
  evidence names its `centre`. TRICERATOPS makes its own star list and gives its own distances.
- The TOI-1399.01 miss: a nearby binary inside 15" that TRICERATOPS caught and the pixels didn't.
- Visual doubles, as 44926986 turned out to be (WDS J09474-3953A).
- Crowding: CROWDSAP per sector.
- QLP dilution.
- Centroid offsets per sector. Note which sector triage's pixel pass rests on, and whether that sector is
  timing-suspect.
- TRICERATOPS's NFPP and the stars it gave zero depth. Since decision 0036 it drops the TIC's DUPLICATE and ARTIFACT
  rows; `triceratops.json`'s `dropped_stars` lists them (the dossier doesn't, and runs before 0036 lack the field). A
  rerun repeats outcomes but not every digit: means moved by up to 3e-3 relative between identical runs (0036 item
  5), so don't read a finding into a difference that small.
- Decision 0032: TRICERATOPS's NFPP fail is not a reliable kill for a binary 20" to 25" out, and its NFPP can move
  with the ephemeris.

**A planet (`planet`)**
- An eclipsing binary on the target.
- An eccentric secondary away from phase 0.5: LEO-Vetter's ModShift, from triage.
- The EB pair at a period ratio the novelty harmonics don't list. Check the search's other signals on the star.
- V shape: the grazing fraction and b.
- Density against the TIC star, and the radius against the star.
- Decision 0031's causes that can fool a check on a real planet: a secondary that is the planet's own occultation, a
  density tension from eccentricity.

**Real and new (`real_new`)**
- Momentum dumps, scattered light, sector edges.
- One sector dominating the fold.
- The timing-suspect sectors S99 to S104 (QLP): vet-v3 leaves them out, and the evidence-only run shows them.
- Held-out seasons. Per 0031, holdout or sector_depth failures can come from TTVs or a partly covered transit.
- Novelty by name: the literature hits, ExoFOP and the catalog rows on the star (dossier's last tables).

## The literature hits

Screen every hit in `literature.json`, including ADS's. Flag any paper that names the star as a planet host, an
eclipsing binary, a variable or a member of a multiple system, or that reports a signal at or near this period. Put
flagged papers' ids (as the dossier prints them) in `hits_flagged`. A hit you dismiss gets a note finding only when
the reason isn't obvious from its title.

## Ratings

- **kill:** the evidence shows it is not a planet on this star, or it is known.
- **hold:** the public data can't decide, and you name what would decide it: 2-min data, high-resolution imaging,
  ground-based photometry, a QLP redelivery.
- **note:** worth the maintainer's eye, decides nothing.

Rate honestly. A weak kill wastes the refuters' time, and a missed one costs the maintainer's name.

## Signals a check killed (short brief)

One question: is the kill wrong? Look for:
- a bug in the check;
- an artefact the check misread;
- one of 0031's causes, which fool a check on a real planet: own occultation, eccentricity, TTVs, a partly covered
  transit, low SNR.

Report one finding per killed check. Rate it `kill` when the kill stands, and give the evidence. Rate it `hold` when
the kill looks wrong, and say why. Refuters run only on a `hold`.

## Output

Write one JSON file, `/tmp/t13/<name>/findings.json`:

```json
{
  "signal": "<name>",
  "summary": "two or three plain sentences: what you tested and what you found",
  "findings": [
    {"id": "F1", "lens": "on_star | planet | real_new", "rating": "kill | hold | note",
     "claim": "one sentence", "evidence": "what shows it: paths, numbers, commands"}
  ],
  "hits_flagged": ["<paper id>", "..."]
}
```

Ids run F1, F2 and so on. Then return only: the path, the number of findings by rating, and one line per kill or
hold. The controller adds the model, the date and the refuters' verdicts to make `review.json`.

## Refuters (two per kill or hold finding)

Each refuter gets the finding, this brief and the same read-only access, and writes
`{"refuted": true | false, "reason": "..."}`.
- **Refuter 1 reproduces it.** Rerun the numbers from the run files. Refute it if they don't hold.
- **Refuter 2 tests it against the rules.** Check the design, the decision records and the criteria: does the
  finding mean what it claims, and does the rating fit? Refute it if the finding misreads a rule or overstates its
  evidence.

Refute only on evidence. "I couldn't reproduce it" with the command you ran counts; "it seems unlikely" doesn't.
