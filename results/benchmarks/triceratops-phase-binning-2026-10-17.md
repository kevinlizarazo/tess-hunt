# TRICERATOPS on phase-binned and unbinned input: the timing probe

A read-only probe made before the M3 build (pin P2, 2026-10-17 02:14 to 05:19 UTC), outside the pipeline. It gates
nothing; [decision 0026](../../docs/decisions/0026-triceratops.md) cites it for phase binning (Ruling G). Its script,
`probe/time_tric.py`, is in `triceratops-phase-binning-2026-10-17-scripts.tar.gz` beside this file, as it was kept
after the probe. The probe's command lines and output logs were not kept: they were in a scratch directory that is
gone. The numbers below are copied from the build's notes written at the time (its pins file), not regenerated.

**What it covers.** One star, TIC 146282666 (six SPOC 2-min sectors, 6,447 points within two durations of
mid-transit, 38 stars in TRICERATOPS's list, 9 with a depth above zero), and one seed for the unbinned run. Each
`calc_probs` ran on one core under `nice -n 10` and a memory cap, on a machine otherwise quiet. `time_tric.py` takes
the TIC, N, whether to run in parallel, the exposure in seconds, the sectors and the signals CSV, and folds within two
durations of mid-transit; with `BIN` set it averages the fold into phase bins one exposure wide, and `SEED` sets numpy's
seed before `calc_probs`.

| input | N | seed | time (s) | peak RSS | FPP | NFPP |
|---|---|---|---|---|---|---|
| unbinned | 1e5 | 0 | 958 | 575 MB | 0.0222 | 0.0128 |
| unbinned (the plan's input) | 1e6 | 0 | 9,727 | 646 MB | 0.0318 | 0.0131 |
| phase-binned to 120 s (540 points) | 1e6 | 0 | 984 | 646 MB | 0.0324 | 0.0152 |
| phase-binned | 1e6 | 1 | 1,007 | 646 MB | 0.0434 | 0.0183 |
| phase-binned | 1e6 | 2 | 1,004 | 646 MB | 0.0390 | 0.0163 |
| phase-binned | 1e6 | 3 | 1,004 | 646 MB | 0.0425 | 0.0170 |
| phase-binned | 1e6 | 4 | 1,007 | 646 MB | 0.0410 | 0.0139 |

**What it shows.** On the same draws (seed 0), binning cut the run from 9,727 s to 984 s and moved FPP by 0.0006 and
NFPP by 0.0021, both upward. The binned NFPP's standard deviation over seeds 0 to 4 is 0.0017, so the move is about
one run-to-run spread. The unbinned run was made once, with one seed, so its own spread was not measured, and no other
star was timed.
