# 0032: The nearby-binary controls read inconclusive in TRICERATOPS, not fail; the pixel check catches them

- Date: 2026-10-20
- Status: Accepted (approved by the maintainer on 2026-10-19, after the controls' results were seen)

## Context

The M3 design (section 4.3) and the M3 plan's stop conditions (P6) expected TOI-1058.01 and TOI-1175.01, eclipsing
binaries 20.90" and 23.53" from their targets (decision 0025), to fail TRICERATOPS: mean NFPP over 0.1
([decision 0026](0026-triceratops.md)). TOI-1399.01, a nearby binary inside the pixel rule's 15", was to come out
anything but a pass.

The published controls run, `20261020T082333Z-benchmark-controls-16418d2-f45a`
([summary.md](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md), "the summary"
below, with its `controls.csv`), shows over ten runs each:

- TOI-1058.01: inconclusive, mean FPP 0.0334, mean NFPP 0.027 (sd 0.0217), between the pass bar (0.001) and the fail
  bar (0.1).
- TOI-1175.01: inconclusive on a RUWE blocker, "RUWE 1.48 > 1.4: an unresolved companion the priors don't condition
  on". Its mean NFPP, 0.0341 (sd 0.0096), is between the bars too, so it would be inconclusive without the blocker.
- TOI-1399.01: fail, mean NFPP 0.99, as required.

The controls rerun on the fixed code, `20261023T031548Z-benchmark-controls-cd4e7a2-ca9f`
([summary.md](../../results/benchmarks/20261023T031548Z-benchmark-controls-cd4e7a2-ca9f/summary.md),
[`controls.csv`](../../results/benchmarks/20261023T031548Z-benchmark-controls-cd4e7a2-ca9f/controls.csv)), gives the
same three outcomes. TOI-1058.01's means moved, to FPP 0.0288 and NFPP 0.0219 (sd 0.0132): the rerun dropped two flagged
TIC rows from its star list and read its field stars in another order ([0036](0036-triceratops-tic-duplicates.md), items
4 and 5). TOI-1175.01's mean NFPP stays 0.0341, and TOI-1399.01's reads 0.988.

The neighbour table lists 7 possible hosts for TOI-1058.01 and 13 for TOI-1175.01 (`possible_hosts` in
[`controls.csv`](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/controls.csv)). The network
test `test_nearby_eb_controls_show_a_possible_host` names each binary's Gaia DR3 source and finds it among the possible
hosts.

The build stopped at Task 11 Step 7 with these results and a recommendation to accept them. On 2026-10-19, after the
results were seen, the maintainer answered: "please go with your recommendations, keeping in mind i want integrity and
correctness." This record writes down that call. It is a call made on these results, not a rule set before them.

## Decision

- **Accepted as they stand.** TRICERATOPS can't pass either binary: its pass bar holds on them, and its fail bar
  doesn't reach them.
  - Both fail triage's pixel check, at 21.5" and 25.1" against its 15"
    ([pixel-controls-2026-10-16.txt](../../results/triage/pixel-controls-2026-10-16.txt)). A signal that fails it never
    reaches triage's shortlist, and every pass in vetting needs a pixel pass as well (Ruling W,
    [decision 0028](0028-outcomes-and-calls.md), accepted by the maintainer on 2026-10-22). Neither can come out
    passed.
  - What this means: a TRICERATOPS NFPP fail is not a reliable kill for a nearby binary 20" to 25" out. The pixel check
    catches those. Inside 15", where the pixel check can miss, TRICERATOPS caught the one control there is: TOI-1399.01
    passes the pixel check at 11.6" (the same file) and fails TRICERATOPS.
- **Not taken: a fail bar of NFPP over 0.01.** It would fail both binaries (0.027 and 0.0341). It would also sit just
  above two known planets, TOI-451.03 (mean NFPP 0.00808, sd 0.0092) and TOI-1097.02 (0.00643), from the summary and
  `controls.csv`. And TOI-1058.01's run-to-run sd (0.0217) is larger than its distance to that bar (0.027 less 0.01; in
  the rerun, 0.0132 against 0.0219 less 0.01), so its outcome would turn on the draws. It would also be a vet-v4 made
  after the results.
- **Open and unexplained.** TOI-1175.01's network test,
  `tests/test_tricera.py::test_nearby_eb_controls_fail_triceratops` (one run, on the catalog ephemeris in
  `benchmarks/pixel_controls.csv`), gave an NFPP near 1, inconclusive on the same RUWE blocker. Production, on the
  density-prior fit's ephemeris (0026's input), gave 0.0341 with an sd of 0.0096 over ten runs. The run-to-run spread
  can't account for that. The ephemeris is the likeliest cause, though the test also builds its light curve its own way;
  it was not diagnosed. Task 13's reviewers are told that TRICERATOPS's NFPP can move with the ephemeris.
- **The tests.** `test_nearby_eb_controls_fail_triceratops` is marked `xfail(strict=True, raises=AssertionError)`, its
  reason naming this record: the design's expectation stays visible, and if TOI-1058.01 starts to fail TRICERATOPS
  the strict mark reports it. TOI-1175.01 can't fail while its RUWE blocker (1.48 > 1.4) holds, so for it the strict
  mark watches nothing. `test_nearby_eb_controls_do_not_pass_triceratops` holds the standard accepted here. Both stay
  network and slow.

## Evidence

- The controls run's
  [summary.md](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md) and
  [`controls.csv`](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/controls.csv): the three
  controls' outcomes, FPP and NFPP means and sds, blockers and possible-host counts, and the two known planets' NFPP.
- The rerun's [summary.md](../../results/benchmarks/20261023T031548Z-benchmark-controls-cd4e7a2-ca9f/summary.md) and
  [`controls.csv`](../../results/benchmarks/20261023T031548Z-benchmark-controls-cd4e7a2-ca9f/controls.csv): the same
  outcomes on the fixed code, and TOI-1058.01's moved means.
- [results/triage/pixel-controls-2026-10-16.txt](../../results/triage/pixel-controls-2026-10-16.txt): the pixel
  check's offsets on the three nearby binaries.
- [tests/test_tricera.py](../../tests/test_tricera.py): `test_nearby_eb_controls_fail_triceratops` (expected to fail,
  strict), `test_nearby_eb_controls_do_not_pass_triceratops` and `test_toi_1399_does_not_pass_triceratops`, network,
  one run each.
- [tests/test_neighbours.py](../../tests/test_neighbours.py): `test_nearby_eb_controls_show_a_possible_host`, network.
- [tests/test_calls.py](../../tests/test_calls.py): `test_a_candidate_pass_needs_triages_pixel_pass` (Ruling W).
