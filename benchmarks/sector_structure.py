"""The sector structure the null's scramble splits, per light-curve provenance and sector: how many stars, the median
span in days, and the median and largest number of internal gaps longer than half a day, on a random sample of the
cached light curves.

Usage, from the repository root (reads the light-curve cache under $TESS_HUNT_DATA):
    uv run python benchmarks/sector_structure.py > results/benchmarks/sector-structure-<date>.txt
"""

import numpy as np
import pandas as pd

from tess_hunt.config import lc_dir
from tess_hunt.lightcurve import LightCurve

SAMPLE, SEED, GAP_DAYS = 500, 0, 0.5

paths = sorted(lc_dir().glob("*.npz"))
size = min(SAMPLE, len(paths))
print(
    f"# {size} of the {len(paths)} cached light curves, drawn with numpy default_rng({SEED}); "
    f"gaps longer than {GAP_DAYS} d"
)
rows = []
for path in np.random.default_rng(SEED).choice(paths, size=size, replace=False):
    lc = LightCurve.load(path)
    for sector in np.unique(lc.sector):
        t = np.sort(lc.time[lc.sector == sector])
        rows.append(
            {
                "sector": int(sector),
                "provenance": lc.sources[str(int(sector))]["provenance"],
                "span_days": t[-1] - t[0],
                "gaps_over_half_day": int((np.diff(t) > GAP_DAYS).sum()),
            }
        )
table = (
    pd.DataFrame(rows)
    .groupby(["provenance", "sector"])
    .agg(
        stars=("span_days", "size"),
        span_days=("span_days", "median"),
        gaps_median=("gaps_over_half_day", "median"),
        gaps_max=("gaps_over_half_day", "max"),
    )
)
print(table.round(1).to_string())
