"""Compare a replayed injection run with the run it replays, as a Markdown report on stdout.

Usage: uv run python benchmarks/compare_replay.py OLD_CSV NEW_CSV > out.md
"""

import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["tic", "injection"]
SNR_EDGES = [0, 5, 7, 10, 15, 20, 50, np.inf]
SNR_RTOL = 1e-9
# NEW-row fields listed for each loss and gain, with decimals to print (None: print as is).
DETAIL = {
    "found_period": 5,
    "sde": 2,
    "rank": 0,
    "top_period": 5,
    "top_sde": 2,
    "n_bls": 0,
    "few_transits": 0,
    "budget_exhausted": None,
    "masked_fraction": 3,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flag(s: pd.Series) -> pd.Series:
    # Error rows leave NaN in bool columns, making them object columns where ~True is -2.
    return s.astype(str) == "True"


def num(v, decimals) -> str:
    if pd.isna(v):
        return "-"
    return str(v) if decimals is None else f"{v:.{decimals}f}"


def rate(s: pd.Series) -> str:
    return f"{s.mean():.3f}" if len(s) else "-"


def strip_dirs(text) -> str:
    # Exception messages can carry absolute paths, and the report must not.
    return re.sub(r"(?:[A-Za-z]:)?[\\/](?:[^\s'\"\\/]+[\\/])+", "", str(text))


def table(header, rows) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return "\n".join(lines)


def variable_tics(old: pd.DataFrame) -> set:
    """Stars whose two injections were both missed at the same, finite period."""
    out = set()
    for tic, g in old.groupby(level="tic"):
        p = g["found_period"]
        if (
            len(g) == 2
            and not flag(g["recovered"]).any()
            and np.isfinite(p).all()
            and p.iloc[0] == p.iloc[1]
        ):
            out.add(tic)
    return out


def recovery_table(mask, bins, before, after) -> str:
    rows = []
    for code, interval in enumerate(bins.cat.categories):
        sel = mask & (bins.cat.codes == code)
        label = f"[{interval.left:g}, {interval.right:g})"
        rows.append([label, int(sel.sum()), rate(before[sel]), rate(after[sel])])
    rows.append(["all", int(mask.sum()), rate(before[mask]), rate(after[mask])])
    return table(["bin", "n", "recovered before", "recovered after"], rows)


def changes_table(o: pd.DataFrame, n: pd.DataFrame) -> str:
    fields = n.reindex(columns=list(DETAIL))
    rows = []
    for (key, orow), (_, nrow) in zip(o.iterrows(), fields.iterrows(), strict=True):
        rows.append(
            [
                *key,
                num(orow["inj_period"], 4),
                num(orow["inj_rp_rearth"], 2),
                num(orow["expected_snr"], 2),
                *(num(nrow[c], d) for c, d in DETAIL.items()),
            ]
        )
    return table([*KEY, "inj_period", "inj_rp_rearth", "expected_snr", *DETAIL], rows)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: compare_replay.py OLD_CSV NEW_CSV")
    old_path, new_path = Path(sys.argv[1]), Path(sys.argv[2])
    old = pd.read_csv(old_path, float_precision="round_trip")
    new = pd.read_csv(new_path, float_precision="round_trip")
    old = old[(old["engine"] == "bls30") & (old["status"] == "ok")]
    # A row that failed before its search has no engine, and it still has to be reported.
    new = new[(new["engine"] == "bls30") | new["engine"].isna()]
    for name, df in (("OLD", old), ("NEW", new)):
        if df.duplicated(KEY).any():
            sys.exit(f"{name} has more than one bls30 row for some (tic, injection)")
    old_i = old.set_index(KEY).sort_index()
    new_i = new.set_index(KEY).sort_index()
    ok_i = new_i[new_i["status"] == "ok"]
    keys = old_i.index.intersection(ok_i.index).sort_values()
    o, n = old_i.loc[keys], ok_i.loc[keys]
    missing = old_i.index.difference(new_i.index)
    failed = new_i[new_i["status"] != "ok"]

    print(
        f"# Replay comparison: OLD {old_path.parent.name} (sha256 {sha256(old_path)}),"
        f" NEW {new_path.parent.name} (sha256 {sha256(new_path)})"
    )

    print("\n## Rows\n")
    counts = [
        ["OLD bls30 ok", len(old_i)],
        ["NEW bls30", len(new_i)],
        ["joined (NEW ok)", len(keys)],
        ["OLD missing from NEW", len(missing)],
        ["NEW not ok", len(failed)],
    ]
    print(table(["rows", "count"], counts))
    if len(missing):
        print("\n### OLD rows missing from NEW\n")
        print(table(KEY, [list(k) for k in missing]))
    if len(failed):
        print("\n### NEW rows not ok\n")
        errors = failed["error"] if "error" in failed else pd.Series(np.nan, index=failed.index)
        rows = [
            [*k, s, "-" if pd.isna(e) else strip_dirs(e)]
            for k, s, e in zip(failed.index, failed["status"], errors, strict=True)
        ]
        print(table([*KEY, "status", "error"], rows))

    print("\n## Same planets, same data\n")
    inj_cols = [c for c in old_i.columns if c.startswith("inj_")]
    o_inj, n_inj = o[inj_cols], n.reindex(columns=inj_cols)
    same = (o_inj == n_inj) | (o_inj.isna() & n_inj.isna())
    inj_bad = int((~same.all(axis=1)).sum())
    rel = (n["expected_snr"] - o["expected_snr"]).abs() / o["expected_snr"].abs()
    snr_bad = ~(rel <= SNR_RTOL)
    print(f"- pairs with any inj_* value different: {inj_bad} of {len(keys)}")
    print(
        f"- pairs with expected_snr relative difference above 1e-9: {int(snr_bad.sum())} of {len(keys)}"
    )
    if inj_bad:
        per_col = ", ".join(f"{c} {int(k)}" for c, k in (~same).sum().items() if k)
        print(f"\nMismatch: {inj_bad} pairs do not have the same inj_* values ({per_col}).")
    if snr_bad.any():
        print(
            f"\nMismatch: {int(snr_bad.sum())} pairs differ in expected_snr by more than 1e-9 relative.\n"
        )
        worst = rel[snr_bad].sort_values(ascending=False, na_position="first").index[:5]
        rows = [
            [
                *k,
                f"{o.at[k, 'expected_snr']:.12g}",
                f"{n.at[k, 'expected_snr']:.12g}",
                f"{rel[k]:.3e}",
            ]
            for k in worst
        ]
        print(
            table([*KEY, "expected_snr before", "expected_snr after", "relative difference"], rows)
        )

    before, after = flag(o["recovered"]), flag(n["recovered"])
    bins = pd.cut(o["expected_snr"], SNR_EDGES, right=False)
    print("\n## Recovery by expected SNR\n")
    print(recovery_table(pd.Series(True, index=o.index), bins, before, after))

    var = variable_tics(old_i)
    var_mask = pd.Series(o.index.get_level_values("tic").isin(var), index=o.index)
    print(
        f"\n## Recovery by expected SNR, variable stars: {len(var)} stars, {int(var_mask.sum())} injections\n"
    )
    print(recovery_table(var_mask, bins, before, after))

    for title, sel in (("Losses", before & ~after), ("Gains", ~before & after)):
        what = (
            "recovered before, missed after"
            if title == "Losses"
            else "missed before, recovered after"
        )
        print(f"\n## {title} ({what}; search fields from NEW): {int(sel.sum())}")
        if sel.any():
            print("\n" + changes_table(o[sel], n[sel]))

    print("\n## Runtime per search (s)\n")
    runtime = [
        [label, f"{r.median():.1f}", f"{r.quantile(0.9):.1f}"]
        for label, r in (("before", o["runtime_s"]), ("after", n["runtime_s"]))
    ]
    print(table(["run", "median", "p90"], runtime))

    print("\n## Retries (NEW)\n")
    if {"few_transits", "budget_exhausted"} <= set(n.columns):
        print(
            f"- used retries (few_transits > 0): {int((n['few_transits'] > 0).sum())} of {len(n)}"
        )
        print(f"- ran out (budget_exhausted): {int(flag(n['budget_exhausted']).sum())} of {len(n)}")
    else:
        print("- retries: not recorded")


if __name__ == "__main__":
    main()
