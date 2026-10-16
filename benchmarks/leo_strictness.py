"""LEO-Vetter's outcomes, in a published triage run, on the signals that match a catalogued eclipsing binary or a
catalogued planet candidate, and the tests it failed most often.

Each signal's ephemeris and LEO-Vetter outcome come from the run's published signals.csv. The catalogued objects a
signal matches, with their kind and harmonic ratio, come from novelty's own matching (check_novelty with the run's
criteria), rerun here because signals.csv names only the first match. That needs the run's catalog snapshot
(known.parquet) and targets table (the stars' positions) from $TESS_HUNT_DATA. Neither is published: the script checks
both against the hashes in the run's provenance.json and stops unless every signal's novelty outcome and reason come
out as signals.csv has them.

Usage, from the repository root:
    uv run python benchmarks/leo_strictness.py results/triage/<run id> > results/triage/leo-strictness-<date>.txt
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from tess_hunt.config import data_dir, load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.novelty import check_novelty
from tess_hunt.provenance import sha256_file

run = Path(sys.argv[1])
provenance = json.loads((run / "provenance.json").read_text())
argv = provenance["argv"]


def argument(flag: str) -> Path:
    return Path(argv[argv.index(flag) + 1].replace("$TESS_HUNT_DATA", str(data_dir())))


def checked(name: str, path: Path) -> Path:
    if sha256_file(path) != provenance["inputs"][name]["sha256"]:
        raise SystemExit(f"{path.name} is not the {name} file {provenance['run_id']} read")
    return path


crit = {}
for entry in provenance["criteria"]:
    loaded = load_criteria(entry["file"])
    if loaded.sha256 != entry["sha256"]:
        raise SystemExit(f"{entry['file']} has changed since {provenance['run_id']}")
    crit[Path(entry["file"]).stem] = loaded
novelty, match = crit["triage-v1"]["novelty"], crit["search-v2"]["match"]
snapshot = argument("--catalogs")
checked("catalog_manifest", snapshot / "manifest.json")
known = pd.read_parquet(checked("known", snapshot / "known.parquet"))
stars = pd.read_parquet(checked("targets", argument("--targets"))).set_index("tic")
signals = pd.read_csv(run / "signals.csv", float_precision="round_trip", keep_default_na=False)

rows = []
for s in signals.to_dict("records"):
    tic = int(s["tic"])
    result = check_novelty(
        tic,
        float(stars.at[tic, "ra"]),
        float(stars.at[tic, "dec"]),
        Ephemeris(float(s["period"]), float(s["t0"]), float(s["duration"]), float(s["depth"])),
        known,
        novelty["neighbour_arcmin"],
        tuple(novelty["harmonics"]),
        match["sigma_p"],
        match["sigma_t"],
        inconclusive_kinds=tuple(novelty["inconclusive_kinds"]),
    )
    if (str(result.outcome), result.reason) != (s["novelty"], s["novelty_reason"]):
        raise SystemExit(f"TIC {tic} rank {s['rank']}: novelty differs from signals.csv")
    matches = result.evidence.get("matches", [])
    eb = any(m["kind"] == "eb" for m in matches)
    candidate = not eb and any(m["kind"] == "candidate" and m["ratio"] == 1.0 for m in matches)
    rows.append({"eb": eb, "candidate": candidate, "leo": s["leo_flux"]})
table = pd.DataFrame(rows)

harmonics = ", ".join(f"{h:.4g}" for h in novelty["harmonics"])
sources = ", ".join(sorted(set(known.loc[known["kind"] == "candidate", "source"])))
print(f"# LEO-Vetter on catalogued objects, triage run {provenance['run_id']}")
print(
    f"# {len(signals)} signals at or above SDE {provenance['threshold']['value']:.2f}, from its signals.csv."
)
print(
    "# A match is novelty's (period and epoch, criteria/triage-v1.toml [novelty]) to a catalogued object on the"
    f" signal's star or within {novelty['neighbour_arcmin']:g}' of it."
)
print(
    f"# EB match: the signal matches a catalogued eclipsing binary (kind eb) at any ratio ({harmonics})."
)
print(
    f"# Candidate match: it matches a catalogued planet candidate (kind candidate: {sources}) at the"
    " candidate's own period (ratio 1), and has no EB match."
)
print(
    f"# Matches rerun on snapshot {snapshot.name} and the run's targets table (both unpublished; sha256 as in"
    " provenance.json); every novelty outcome and reason agrees with signals.csv."
)
print()
print("match       signals  LEO pass  LEO fail  LEO inconclusive")
for name in ("eb", "candidate"):
    leo = table.loc[table[name], "leo"]
    counts = [int(leo.eq(o).sum()) for o in ("pass", "fail", "inconclusive")]
    label = "EB" if name == "eb" else "candidate"
    print(f"{label:<10} {len(leo):>8} {counts[0]:>9} {counts[1]:>9} {counts[2]:>17}")
print()
failed = Counter(
    test.strip()
    for reason in signals.loc[signals["leo_flux"].eq("fail"), "leo_reason"]
    for test in reason.split(":", 1)[1].split(",")
)
print(
    f"LEO-Vetter tests failed, in signals (of {int(signals['leo_flux'].eq('fail').sum())} that failed):"
)
for test, n in failed.most_common():
    print(f"{test:<20} {n:>6}")
