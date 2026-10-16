"""How far transit-diffImage's pixel times sit from TESScut's barycentric times, and how many in-transit cadences
that moves, per difference image (transit-diffImage's own in-transit rule on both time sets).

transit-diffImage's bundled SPICE ephemeris ends on 2020-10-26, so for later sectors it cannot correct its pixel times
to the barycentre. The script reads every imageData_*.pickle under a directory of transit-diffImage's difference
images, such as the --basetemp of a pixel control run (tests/test_pixels.py::test_real_nearby_eb_controls).

Usage, from the repository root:
    uv run python benchmarks/pixel_timing.py <image directory> > results/triage/pixel-timing-<date>.txt
"""

import pickle
import sys
from pathlib import Path

import numpy as np

IN_TRANSIT_FRACTION = 0.9


def in_transit(t, planet) -> set:
    half = IN_TRANSIT_FRACTION * planet["durationHours"] / 24.0 / 2.0
    epochs = np.unique(np.round((t - planet["epoch"]) / planet["period"]).astype(int))
    centres = [c for c in planet["epoch"] + epochs * planet["period"] if t.min() <= c <= t.max()]
    near = [np.abs(t - t[np.abs(t - c).argmin()]) < half for c in centres]
    return set(np.flatnonzero(np.any(near, axis=0))) if near else set()


paths = sorted(Path(sys.argv[1]).rglob("imageData_*.pickle"))
print(
    f"# {len(paths)} difference images; in transit: within {IN_TRANSIT_FRACTION / 2:g} durations of the cadence "
    "nearest a transit centre; pixel times against TESScut's times"
)
for path in paths:
    _, _, pixel, _, _, _, planet = pickle.load(path.open("rb"))
    tdi, tesscut = np.asarray(pixel["time"]), np.asarray(pixel["rawTime"])
    valid = np.asarray(pixel["validBarycentricCorrection"], dtype=bool).mean()
    shift = np.nanmax(np.abs(tdi - tesscut)) * 1440.0
    a, b = in_transit(tdi, planet), in_transit(tesscut, planet)
    print(
        f"{path.parent.name} S{pixel['sector']}: valid correction {valid:.2f}, max shift {shift:.2f} min, "
        f"duration {planet['durationHours']:.2f} h, in-transit cadences {len(b)}, moved {len(a ^ b)}"
    )
