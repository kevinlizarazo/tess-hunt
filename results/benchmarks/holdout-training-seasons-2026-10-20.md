# The held-out seasons' training seasons: what decision 0035 reaches

2026-10-20. Read-only, for Task 13's review of 441010857-1 (finding F1) and
[decision 0035](../../docs/decisions/0035-holdout-training-seasons.md). Nothing in the runs was changed. The screen is
the review's rules refuter's, at `/tmp/t13/441010857-1/refute-F1-rules/screen.py`; the other scripts were run from
`/tmp/t13b/`. Each script is quoted in full under [Scripts](#scripts), and each output in full in its section.

The runs, as `~/.cache/tess-hunt/logs/m3-vars.sh` names them:

- `VET_RUN`, `20261020T010149Z-vetting-run-62882b5-c3ee`: the 19 signals.
- `VET_SUSPECT_RUN`, `20261020T011247Z-vetting-run-62882b5-d92b`: its evidence-only twin, with the timing-suspect
  sectors kept in.
- `CONTROL_VET`, `20261017T155223Z-vetting-run-62882b5-4867`: the 24 controls.

## Answer

- **The screen** flags two signals in `VET_RUN`, each with both tested seasons trained on one season holding a
  transit by its count: 441010857-1 (holdout fail) and 438857197-1 (holdout pass). It counts a season's core cadences
  at its own refit ephemeris. It flags none of `CONTROL_VET`'s 24.
- **The fix** counts each season's cadences inside the whole transit at the check's input ephemeris. Run on each
  signal's inputs rebuilt as `vet_with_fits` builds them (section 2):
  - `VET_RUN`: 441010857-1 goes from fail to inconclusive. The other 18 are unchanged, 438857197-1 among them.
  - `VET_SUSPECT_RUN`: 441010857-1 goes from fail to inconclusive. The other 18 are unchanged.
  - `CONTROL_VET`: no outcome changes.
  - In all 62 records, every season whose status the fix leaves alone reproduces the run's `checks.json` field for
    field, by exact float equality, in the run shown. In the review's reruns, `VET_RUN`'s 277774870-1 printed
    `OTHER SEASONS DIFFER` in one pass of six, with its outcome and every season status unchanged; the field could not
    be pinned down (section 2).
- **438857197-1's S11 holds transits** (section 3). At 30-minute cadence it holds 8 cadences inside the transit and 4
  in the core after detrending, so a core count, under `min_points`, would leave it out. It pins the refit's period:
  trained with it, as the vet was, seasons 1 and 2 are predicted 0.09 h and 0.07 h from the flat fit, against a core
  half-width of 0.25 h, and show the transit at 8.3 and 7.0 sigma; trained without it, 8.88 h and 6.86 h off, at -0.5
  and -1.0 sigma.
- **Both windows on the three runs** (section 4). Counting the core would change 441010857-1 in `VET_RUN` and
  `VET_SUSPECT_RUN`, and 438857197-1 in `VET_RUN` (pass to inconclusive). Counting the whole transit changes only
  441010857-1, in both. Neither changes a control.
- **The four published single-signal vets** (vet-v1 and vet-v2) are not flagged by the screen's count (section 5).

## 1. The screen

`screen.py` reads each signal's holdout seasons from `checks.json`. A season holds a transit when its own held-out row
has n of 5 or more (vet-v3's `[holdout] min_points`), n being its core cadences at the ephemeris refit without it. For
each tested season (predicted or missed) it prints the season, its status, its training seasons and how many of them
hold a transit, and it flags a signal when a tested season trained on fewer than 2 that do. A signal with a tested
season has three seasons or more, so every one of its seasons reached the refit and has an n.

`python3 /tmp/t13/441010857-1/refute-F1-rules/screen.py "$VET_RUN"`:

```
103312990-1 inconclusive bearing [0, 1, 2] tested [(0, 'predicted', 2, 2)] 
146282666-1 inconclusive bearing [0, 1, 2] tested [(2, 'predicted', 2, 2)] 
164767175-1 inconclusive bearing [0, 1, 2, 3] tested [] 
173369850-1 pass bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'predicted', 4, 4), (4, 'predicted', 4, 4)] 
241522065-1 inconclusive bearing [] tested [] 
277774870-1 pass bearing [1, 2, 3] tested [(1, 'predicted', 3, 2), (2, 'predicted', 3, 2)] 
295140687-1 pass bearing [0, 1, 2] tested [(0, 'predicted', 2, 2), (1, 'predicted', 2, 2), (2, 'predicted', 2, 2)] 
296819076-1 inconclusive bearing [] tested [] 
322826591-1 fail bearing [0, 1, 2] tested [(0, 'missed', 2, 2), (1, 'missed', 2, 2), (2, 'predicted', 2, 2)] 
337885456-1 pass bearing [0, 1, 2] tested [(0, 'predicted', 2, 2), (1, 'predicted', 2, 2)] 
370977908-1 inconclusive bearing [0, 1, 2] tested [(1, 'predicted', 2, 2)] 
399023421-1 pass bearing [0, 1, 2] tested [(1, 'predicted', 2, 2), (2, 'predicted', 2, 2)] 
410399327-1 fail bearing [0, 1, 2, 3] tested [(0, 'missed', 3, 3), (1, 'missed', 3, 3)] 
423100454-1 pass bearing [0, 1, 2] tested [(0, 'predicted', 2, 2), (1, 'predicted', 2, 2), (2, 'predicted', 2, 2)] 
438857197-1 pass bearing [1, 2] tested [(1, 'predicted', 2, 1), (2, 'predicted', 2, 1)] <- one-bearing-season training
441010857-1 fail bearing [1, 2] tested [(1, 'missed', 2, 1), (2, 'predicted', 2, 1)] <- one-bearing-season training
44926986-1 pass bearing [1, 2, 3] tested [(1, 'predicted', 3, 2), (2, 'predicted', 3, 2)] 
458290782-1 fail bearing [0, 1, 2, 3] tested [(0, 'missed', 3, 3), (1, 'missed', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
48010903-1 pass bearing [0, 1, 2] tested [(0, 'predicted', 2, 2), (1, 'predicted', 2, 2)] 
```

`python3 /tmp/t13/441010857-1/refute-F1-rules/screen.py "$CONTROL_VET"`:

```
TOI-1052.01 pass bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'predicted', 4, 4), (4, 'predicted', 4, 4)] 
TOI-1058.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-107.01 pass bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'predicted', 4, 4), (4, 'predicted', 4, 4)] 
TOI-1097.02 inconclusive bearing [0, 1, 2] tested [(0, 'predicted', 2, 2)] 
TOI-1175.01 fail bearing [1, 2, 3, 4] tested [(1, 'missed', 4, 3), (2, 'predicted', 4, 3), (3, 'predicted', 4, 3), (4, 'predicted', 4, 3)] 
TOI-118.01 pass bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'predicted', 4, 4), (4, 'predicted', 4, 4)] 
TOI-1399.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-144.01 pass bearing [0, 1, 2, 3, 4, 5, 6, 7] tested [(0, 'predicted', 7, 7), (1, 'predicted', 7, 7), (2, 'predicted', 7, 7), (3, 'predicted', 7, 7), (4, 'predicted', 7, 7), (5, 'predicted', 7, 7), (6, 'predicted', 7, 7), (7, 'predicted', 7, 7)] 
TOI-188.01 pass bearing [0, 1, 2, 3, 4, 5] tested [(0, 'predicted', 5, 5), (1, 'predicted', 5, 5), (2, 'predicted', 5, 5), (3, 'predicted', 5, 5), (4, 'predicted', 5, 5), (5, 'predicted', 5, 5)] 
TOI-191.01 pass bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'predicted', 4, 4), (4, 'predicted', 4, 4)] 
TOI-2011.02 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-396.01 fail bearing [0, 1, 2, 3] tested [(0, 'missed', 3, 3), (1, 'missed', 3, 3), (2, 'missed', 3, 3), (3, 'missed', 3, 3)] 
TOI-396.03 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-411.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-4307.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-4320.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-451.02 inconclusive bearing [0, 1, 2] tested [] 
TOI-451.03 inconclusive bearing [0, 1, 2] tested [(0, 'missed', 2, 2)] 
TOI-576.01 fail bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'missed', 4, 4), (4, 'predicted', 4, 4)] 
TOI-652.01 pass bearing [0, 1, 2, 3, 4] tested [(0, 'predicted', 4, 4), (1, 'predicted', 4, 4), (2, 'predicted', 4, 4), (3, 'predicted', 4, 4), (4, 'predicted', 4, 4)] 
TOI-747.01 pass bearing [0, 1, 2] tested [(0, 'predicted', 2, 2), (1, 'predicted', 2, 2), (2, 'predicted', 2, 2)] 
TOI-755.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-763.02 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
TOI-826.01 pass bearing [0, 1, 2, 3] tested [(0, 'predicted', 3, 3), (1, 'predicted', 3, 3), (2, 'predicted', 3, 3), (3, 'predicted', 3, 3)] 
```

## 2. The fixed check on the runs' inputs

The screen counts core cadences at each season's own refit ephemeris; the fix counts cadences inside the whole transit
at the check's input ephemeris. `exact.py` runs the fixed `holdout` on each signal's vet-v3 inputs, rebuilt as
`vet_with_fits` builds them: the light curve (checked against the sha256 the run recorded), without its timing-suspect
sectors except in `VET_SUSPECT_RUN`, detrended around the run's `masked` transits, with red-noise errors; the criteria
files are checked against the run's sha256s. Each season prints its status, then
`(training_seasons, training_seasons_with_transits)`. Every season whose status did not change is compared with
`checks.json` field for field, the new count aside. The compare is exact float equality, so a rerun can differ in the
last bit. In the review's reruns of the command below, `VET_RUN`'s 277774870-1 printed
`pass == pass | OTHER SEASONS DIFFER` in one pass of six, with its outcome and every season status unchanged; it did not
recur in 14 more tries, so which field moved is not known. The block below is the run as made.

```sh
for r in VET_RUN CONTROL_VET; do echo "== $r"; /tmp/t13/heavy.sh uv run python /tmp/t13b/exact.py "${!r}"; done
echo "== VET_SUSPECT_RUN"
/tmp/t13/heavy.sh uv run python /tmp/t13b/exact.py "$VET_SUSPECT_RUN" --suspect; echo EXIT $?
```

```
== VET_RUN
103312990-1 inconclusive == inconclusive | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 underpowered (2, 2)
    season 2 untestable (2, 2)
146282666-1 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (2, 2)
    season 1 underpowered (2, 2)
    season 2 predicted (2, 2)
164767175-1 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (3, 3)
    season 1 underpowered (3, 3)
    season 2 underpowered (3, 3)
    season 3 underpowered (3, 3)
173369850-1 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
241522065-1 inconclusive == inconclusive | other seasons reproduce
    season 0 untestable (1, 1)
    season 1 untestable (1, 1)
277774870-1 pass == pass | other seasons reproduce
    season 0 no_predicted_transit_in_data (3, 3)
    season 1 predicted (3, 2)
    season 2 predicted (3, 2)
    season 3 untestable (3, 2)
295140687-1 pass == pass | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 predicted (2, 2)
    season 2 predicted (2, 2)
296819076-1 inconclusive == inconclusive | other seasons reproduce
    season 0 untestable (1, 1)
    season 1 untestable (1, 1)
322826591-1 fail == fail | other seasons reproduce
    season 0 missed (2, 2)
    season 1 missed (2, 2)
    season 2 predicted (2, 2)
337885456-1 pass == pass | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 predicted (2, 2)
    season 2 untestable (2, 2)
370977908-1 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (2, 2)
    season 1 predicted (2, 2)
    season 2 underpowered (2, 2)
399023421-1 pass == pass | other seasons reproduce
    season 0 underpowered (2, 2)
    season 1 predicted (2, 2)
    season 2 predicted (2, 2)
410399327-1 fail == fail | other seasons reproduce
    season 0 missed (3, 3)
    season 1 missed (3, 3)
    season 2 underpowered (3, 3)
    season 3 untestable (3, 3)
423100454-1 pass == pass | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 predicted (2, 2)
    season 2 predicted (2, 2)
438857197-1 pass == pass | other seasons reproduce
    season 0 no_predicted_transit_in_data (2, 2)
    season 1 predicted (2, 2)
    season 2 predicted (2, 2)
441010857-1 fail -> inconclusive | other seasons reproduce
    season 0 no_predicted_transit_in_data (2, 2)
    season 1 missed -> untestable (2, 1)
    season 2 predicted -> untestable (2, 1)
    reason: 0 season(s) could be tested; need 2
44926986-1 pass == pass | other seasons reproduce
    season 0 no_predicted_transit_in_data (3, 3)
    season 1 predicted (3, 2)
    season 2 predicted (3, 2)
    season 3 untestable (3, 2)
458290782-1 fail == fail | other seasons reproduce
    season 0 missed (3, 3)
    season 1 missed (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
48010903-1 pass == pass | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 predicted (2, 2)
    season 2 untestable (2, 2)
1 outcome(s) changed of 19
== CONTROL_VET
TOI-1052.01 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
TOI-1058.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-107.01 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
TOI-1097.02 inconclusive == inconclusive | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 underpowered (2, 2)
    season 2 underpowered (2, 2)
TOI-1175.01 fail == fail | other seasons reproduce
    season 0 no_predicted_transit_in_data (4, 4)
    season 1 missed (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
TOI-118.01 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
TOI-1399.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-144.01 pass == pass | other seasons reproduce
    season 0 predicted (7, 7)
    season 1 predicted (7, 7)
    season 2 predicted (7, 7)
    season 3 predicted (7, 7)
    season 4 predicted (7, 7)
    season 5 predicted (7, 7)
    season 6 predicted (7, 7)
    season 7 predicted (7, 7)
TOI-188.01 pass == pass | other seasons reproduce
    season 0 predicted (5, 5)
    season 1 predicted (5, 5)
    season 2 predicted (5, 5)
    season 3 predicted (5, 5)
    season 4 predicted (5, 5)
    season 5 predicted (5, 5)
TOI-191.01 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
TOI-2011.02 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-396.01 fail == fail | other seasons reproduce
    season 0 missed (3, 3)
    season 1 missed (3, 3)
    season 2 missed (3, 3)
    season 3 missed (3, 3)
TOI-396.03 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-411.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-4307.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 underpowered (3, 3)
    season 3 predicted (3, 3)
TOI-4320.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-451.02 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (2, 2)
    season 1 underpowered (2, 2)
    season 2 underpowered (2, 2)
TOI-451.03 inconclusive == inconclusive | other seasons reproduce
    season 0 missed (2, 2)
    season 1 underpowered (2, 2)
    season 2 underpowered (2, 2)
TOI-576.01 fail == fail | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 missed (4, 4)
    season 4 predicted (4, 4)
TOI-652.01 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
TOI-747.01 pass == pass | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 predicted (2, 2)
    season 2 predicted (2, 2)
TOI-755.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-763.02 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
TOI-826.01 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 predicted (3, 3)
0 outcome(s) changed of 24
== VET_SUSPECT_RUN
103312990-1 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 underpowered (3, 3)
    season 2 underpowered (3, 3)
    season 3 predicted (3, 3)
146282666-1 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (2, 2)
    season 1 underpowered (2, 2)
    season 2 predicted (2, 2)
164767175-1 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (3, 3)
    season 1 underpowered (3, 3)
    season 2 underpowered (3, 3)
    season 3 underpowered (3, 3)
173369850-1 pass == pass | other seasons reproduce
    season 0 predicted (4, 4)
    season 1 predicted (4, 4)
    season 2 predicted (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
241522065-1 pass == pass | other seasons reproduce
    season 0 predicted (2, 2)
    season 1 predicted (2, 2)
    season 2 untestable (2, 2)
277774870-1 fail == fail | other seasons reproduce
    season 0 no_predicted_transit_in_data (4, 3)
    season 1 predicted (4, 2)
    season 2 predicted (4, 2)
    season 3 missed (4, 2)
    season 4 no_predicted_transit_in_data (4, 3)
295140687-1 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 untestable (3, 3)
296819076-1 inconclusive == inconclusive | other seasons reproduce
    season 0 untestable (2, 2)
    season 1 underpowered (2, 2)
    season 2 missed (2, 2)
322826591-1 fail == fail | other seasons reproduce
    season 0 missed (3, 3)
    season 1 missed (3, 3)
    season 2 missed (3, 3)
    season 3 untestable (3, 3)
337885456-1 fail == fail | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 underpowered (3, 3)
    season 3 missed (3, 3)
370977908-1 inconclusive == inconclusive | other seasons reproduce
    season 0 underpowered (3, 3)
    season 1 predicted (3, 3)
    season 2 underpowered (3, 3)
    season 3 untestable (3, 3)
399023421-1 pass == pass | other seasons reproduce
    season 0 underpowered (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 untestable (3, 3)
410399327-1 fail == fail | other seasons reproduce
    season 0 missed (4, 4)
    season 1 missed (4, 4)
    season 2 underpowered (4, 4)
    season 3 predicted (4, 4)
    season 4 predicted (4, 4)
423100454-1 pass == pass | other seasons reproduce
    season 0 predicted (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 untestable (3, 3)
438857197-1 pass == pass | other seasons reproduce
    season 0 no_predicted_transit_in_data (3, 3)
    season 1 predicted (3, 3)
    season 2 predicted (3, 3)
    season 3 untestable (3, 3)
441010857-1 fail -> inconclusive | other seasons reproduce
    season 0 no_predicted_transit_in_data (3, 2)
    season 1 missed -> untestable (3, 1)
    season 2 predicted -> untestable (3, 1)
    season 3 no_predicted_transit_in_data (3, 2)
    reason: 0 season(s) could be tested; need 2
44926986-1 pass == pass | other seasons reproduce
    season 0 no_predicted_transit_in_data (4, 4)
    season 1 predicted (4, 3)
    season 2 predicted (4, 3)
    season 3 predicted (4, 3)
    season 4 underpowered (4, 3)
458290782-1 fail == fail | other seasons reproduce
    season 0 missed (4, 4)
    season 1 missed (4, 4)
    season 2 predicted (4, 4)
    season 3 underpowered (4, 4)
    season 4 missed (4, 4)
48010903-1 pass == pass | other seasons reproduce
    season 0 predicted (3, 2)
    season 1 predicted (3, 2)
    season 2 untestable (3, 2)
    season 3 no_predicted_transit_in_data (3, 3)
1 outcome(s) changed of 19
EXIT 0
```

## 3. 438857197-1's S11

`refit.py` rebuilds 438857197-1's inputs as `exact.py` does and refits each tested season with S11 in its training set,
as the vet did, and without it. Offsets are from the flat fit's transit time at the epoch nearest the season's middle.
S11 is TESS-SPOC at 30-minute cadence: `sources["11"]` in `VET_RUN`'s `checks.json` for 438857197-1 gives
`cadence_s` 1800.0.

`uv run python /tmp/t13b/refit.py`:

```
S11 after detrending: cadences inside the transit 8 in the core 4
flat fit P 3.659156 t0 1603.53907; core half-width 0.25 h
season 1 held out, trained with S11: P 3.659169, epoch 204 -0.09 h from the flat fit, held-out depth 1162 +- 140 ppm, 8.3 sigma, n 17
season 1 held out, trained without S11: P 3.657248, epoch 204 +8.88 h from the flat fit, held-out depth -72 +- 140 ppm, -0.5 sigma, n 17
season 2 held out, trained with S11: P 3.659160, epoch 397 +0.07 h from the flat fit, held-out depth 1106 +- 158 ppm, 7.0 sigma, n 47
season 2 held out, trained without S11: P 3.657675, epoch 397 -6.86 h from the flat fit, held-out depth -152 +- 155 ppm, -1.0 sigma, n 49
```

## 4. The core window or the whole transit

`variant.py` counts each season's cadences at the vet's ephemeris inside the core window (`core_fraction`) and inside
the whole transit, on the rebuilt, detrended light curve, and gives the holdout outcome each count would give: a
tested season becomes untestable when fewer than `min_training_seasons` of its training seasons hold `min_points` such
cadences. Making a season untestable changes no other season's status, so the outcome follows from the run's own
statuses. Under the whole-transit count its outcomes match section 2's.

```sh
for r in VET_RUN CONTROL_VET; do echo "== $r"; /tmp/t13/heavy.sh uv run python /tmp/t13b/variant.py "${!r}"; done
echo "== VET_SUSPECT_RUN"
/tmp/t13/heavy.sh uv run python /tmp/t13b/variant.py "$VET_SUSPECT_RUN" --suspect; echo EXIT $?
```

```
== VET_RUN
103312990-1 | inconclusive | core {0: 10, 1: 18, 2: 69} -> inconclusive | whole {0: 20, 1: 36, 2: 139} -> inconclusive 
146282666-1 | inconclusive | core {0: 134, 1: 136, 2: 559} -> inconclusive | whole {0: 269, 1: 270, 2: 1132} -> inconclusive 
164767175-1 | inconclusive | core {0: 134, 1: 180, 2: 346, 3: 170} -> inconclusive | whole {0: 264, 1: 359, 2: 684, 3: 316} -> inconclusive 
173369850-1 | pass | core {0: 8, 1: 54, 2: 160, 3: 163, 4: 395} -> pass | whole {0: 18, 1: 108, 2: 323, 3: 324, 4: 783} -> pass 
241522065-1 | inconclusive | core {0: 18, 1: 81} -> inconclusive | whole {0: 36, 1: 143} -> inconclusive 
277774870-1 | pass | core {0: 2, 1: 12, 2: 36, 3: 27} -> pass | whole {0: 4, 1: 24, 2: 72, 3: 54} -> pass 
295140687-1 | pass | core {0: 44, 1: 153, 2: 472} -> pass | whole {0: 88, 1: 301, 2: 942} -> pass 
296819076-1 | inconclusive | core {0: 32, 1: 153} -> inconclusive | whole {0: 65, 1: 300} -> inconclusive 
322826591-1 | fail | core {0: 360, 1: 335, 2: 108} -> fail | whole {0: 719, 1: 650, 2: 216} -> fail 
337885456-1 | pass | core {0: 33, 1: 306, 2: 249} -> pass | whole {0: 67, 1: 610, 2: 501} -> pass 
370977908-1 | inconclusive | core {0: 115, 1: 136, 2: 131} -> inconclusive | whole {0: 249, 1: 270, 2: 263} -> inconclusive 
399023421-1 | pass | core {0: 15, 1: 99, 2: 188} -> pass | whole {0: 30, 1: 198, 2: 375} -> pass 
410399327-1 | fail | core {0: 90, 1: 18, 2: 70, 3: 103} -> fail | whole {0: 180, 1: 31, 2: 151, 3: 195} -> fail 
423100454-1 | pass | core {0: 132, 1: 26, 2: 81} -> pass | whole {0: 267, 1: 54, 2: 162} -> pass 
438857197-1 | pass | core {0: 4, 1: 18, 2: 63} -> inconclusive | whole {0: 8, 1: 36, 2: 125} -> pass <- changes
441010857-1 | fail | core {0: 0, 1: 8, 2: 13} -> inconclusive | whole {0: 0, 1: 18, 2: 27} -> inconclusive <- changes
44926986-1 | pass | core {0: 0, 1: 9, 2: 34, 3: 27} -> pass | whole {0: 0, 1: 18, 2: 69, 3: 54} -> pass 
458290782-1 | fail | core {0: 10, 1: 36, 2: 80, 3: 90} -> fail | whole {0: 20, 1: 72, 2: 161, 3: 180} -> fail 
48010903-1 | pass | core {0: 45, 1: 18, 2: 27} -> pass | whole {0: 90, 1: 36, 2: 54} -> pass 
== CONTROL_VET
TOI-1052.01 | pass | core {0: 127, 1: 137, 2: 93, 3: 139, 4: 325} -> pass | whole {0: 242, 1: 276, 2: 185, 3: 279, 4: 649} -> pass 
TOI-1058.01 | pass | core {0: 212, 1: 211, 2: 211, 3: 424} -> pass | whole {0: 424, 1: 423, 2: 423, 3: 847} -> pass 
TOI-107.01 | pass | core {0: 360, 1: 400, 2: 334, 3: 333, 4: 334} -> pass | whole {0: 774, 1: 798, 2: 666, 3: 667, 4: 678} -> pass 
TOI-1097.02 | inconclusive | core {0: 9, 1: 127, 2: 32} -> inconclusive | whole {0: 17, 1: 255, 2: 66} -> inconclusive 
TOI-1175.01 | fail | core {0: 6, 1: 313, 2: 39, 3: 78, 4: 118} -> fail | whole {0: 10, 1: 626, 2: 78, 3: 157, 4: 255} -> fail 
TOI-118.01 | pass | core {0: 119, 1: 92, 2: 123, 3: 92, 4: 384} -> pass | whole {0: 242, 1: 184, 2: 245, 3: 185, 4: 768} -> pass 
TOI-1399.01 | pass | core {0: 51, 1: 589, 2: 359, 3: 899} -> pass | whole {0: 107, 1: 1168, 2: 701, 3: 1785} -> pass 
TOI-144.01 | pass | core {0: 252, 1: 498, 2: 454, 3: 126, 4: 335, 5: 1054, 6: 335, 7: 376} -> pass | whole {0: 519, 1: 992, 2: 913, 3: 250, 4: 670, 5: 2115, 6: 667, 7: 751} -> pass 
TOI-188.01 | pass | core {0: 385, 1: 469, 2: 173, 3: 431, 4: 186, 5: 482} -> pass | whole {0: 764, 1: 941, 2: 346, 3: 860, 4: 370, 5: 959} -> pass 
TOI-191.01 | pass | core {0: 128, 1: 129, 2: 129, 3: 129, 4: 191} -> pass | whole {0: 254, 1: 258, 2: 257, 3: 257, 4: 384} -> pass 
TOI-2011.02 | pass | core {0: 49, 1: 49, 2: 49, 3: 98} -> pass | whole {0: 99, 1: 98, 2: 98, 3: 196} -> pass 
TOI-396.01 | fail | core {0: 196, 1: 277, 2: 188, 3: 251} -> fail | whole {0: 390, 1: 554, 2: 429, 3: 503} -> fail 
TOI-396.03 | pass | core {0: 57, 1: 150, 2: 145, 3: 243} -> pass | whole {0: 114, 1: 318, 2: 290, 3: 480} -> pass 
TOI-411.01 | pass | core {0: 150, 1: 183, 2: 182, 3: 80} -> pass | whole {0: 272, 1: 359, 2: 365, 3: 156} -> pass 
TOI-4307.01 | pass | core {0: 528, 1: 461, 2: 112, 3: 667} -> pass | whole {0: 1051, 1: 925, 2: 246, 3: 1321} -> pass 
TOI-4320.01 | pass | core {0: 64, 1: 64, 2: 128, 3: 63} -> pass | whole {0: 128, 1: 128, 2: 256, 3: 125} -> pass 
TOI-451.02 | inconclusive | core {0: 548, 1: 277, 2: 464} -> inconclusive | whole {0: 1103, 1: 554, 2: 925} -> inconclusive 
TOI-451.03 | inconclusive | core {0: 230, 1: 47, 2: 117} -> inconclusive | whole {0: 459, 1: 120, 2: 233} -> inconclusive 
TOI-576.01 | fail | core {0: 157, 1: 157, 2: 209, 3: 237, 4: 158} -> fail | whole {0: 314, 1: 315, 2: 420, 3: 472, 4: 315} -> fail 
TOI-652.01 | pass | core {0: 159, 1: 128, 2: 128, 3: 224, 4: 312} -> pass | whole {0: 319, 1: 256, 2: 272, 3: 448, 4: 622} -> pass 
TOI-747.01 | pass | core {0: 951, 1: 541, 2: 1706} -> pass | whole {0: 1892, 1: 1069, 2: 3388} -> pass 
TOI-755.01 | pass | core {0: 228, 1: 259, 2: 324, 3: 549} -> pass | whole {0: 463, 1: 515, 2: 645, 3: 1101} -> pass 
TOI-763.02 | pass | core {0: 58, 1: 109, 2: 116, 3: 58} -> pass | whole {0: 116, 1: 195, 2: 217, 3: 116} -> pass 
TOI-826.01 | pass | core {0: 106, 1: 107, 2: 107, 3: 161} -> pass | whole {0: 214, 1: 214, 2: 214, 3: 321} -> pass 
== VET_SUSPECT_RUN
103312990-1 | pass | core {0: 10, 1: 18, 2: 69, 3: 36} -> pass | whole {0: 20, 1: 36, 2: 139, 3: 72} -> pass 
146282666-1 | inconclusive | core {0: 134, 1: 136, 2: 559} -> inconclusive | whole {0: 269, 1: 270, 2: 1132} -> inconclusive 
164767175-1 | inconclusive | core {0: 134, 1: 180, 2: 346, 3: 170} -> inconclusive | whole {0: 264, 1: 359, 2: 684, 3: 316} -> inconclusive 
173369850-1 | pass | core {0: 8, 1: 54, 2: 160, 3: 163, 4: 395} -> pass | whole {0: 18, 1: 108, 2: 323, 3: 324, 4: 783} -> pass 
241522065-1 | pass | core {0: 18, 1: 81, 2: 98} -> pass | whole {0: 36, 1: 143, 2: 199} -> pass 
277774870-1 | fail | core {0: 2, 1: 12, 2: 36, 3: 27, 4: 2} -> fail | whole {0: 4, 1: 24, 2: 72, 3: 54, 4: 4} -> fail 
295140687-1 | pass | core {0: 44, 1: 153, 2: 472, 3: 160} -> pass | whole {0: 88, 1: 301, 2: 942, 3: 307} -> pass 
296819076-1 | inconclusive | core {0: 32, 1: 153, 2: 508} -> inconclusive | whole {0: 65, 1: 300, 2: 1011} -> inconclusive 
322826591-1 | fail | core {0: 360, 1: 335, 2: 108, 3: 54} -> fail | whole {0: 719, 1: 650, 2: 216, 3: 108} -> fail 
337885456-1 | fail | core {0: 33, 1: 306, 2: 249, 3: 136} -> fail | whole {0: 67, 1: 610, 2: 501, 3: 276} -> fail 
370977908-1 | inconclusive | core {0: 115, 1: 136, 2: 131, 3: 117} -> inconclusive | whole {0: 249, 1: 270, 2: 263, 3: 234} -> inconclusive 
399023421-1 | pass | core {0: 15, 1: 99, 2: 188, 3: 420} -> pass | whole {0: 30, 1: 198, 2: 375, 3: 836} -> pass 
410399327-1 | fail | core {0: 90, 1: 18, 2: 70, 3: 103, 4: 53} -> fail | whole {0: 180, 1: 31, 2: 151, 3: 195, 4: 133} -> fail 
423100454-1 | pass | core {0: 132, 1: 26, 2: 81, 3: 80} -> pass | whole {0: 267, 1: 54, 2: 162, 3: 158} -> pass 
438857197-1 | pass | core {0: 4, 1: 18, 2: 63, 3: 76} -> pass | whole {0: 8, 1: 36, 2: 125, 3: 155} -> pass 
441010857-1 | fail | core {0: 0, 1: 8, 2: 13, 3: 0} -> inconclusive | whole {0: 0, 1: 18, 2: 27, 3: 0} -> inconclusive <- changes
44926986-1 | pass | core {0: 0, 1: 9, 2: 34, 3: 27, 4: 27} -> pass | whole {0: 0, 1: 18, 2: 69, 3: 54, 4: 54} -> pass 
458290782-1 | fail | core {0: 10, 1: 36, 2: 80, 3: 90, 4: 36} -> fail | whole {0: 20, 1: 72, 2: 161, 3: 180, 4: 72} -> fail 
48010903-1 | pass | core {0: 45, 1: 18, 2: 27, 3: 0} -> pass | whole {0: 90, 1: 36, 2: 54, 3: 0} -> pass 
EXIT 0
```

## 5. The published single-signal vets

The check's code serves every criteria version. `screen_vets.py` applies `screen.py`'s count to the four vets
published under `results/benchmarks/`, two under vet-v1 (`20261009T190108Z-vet-c7a2625-fe36`,
`20261009T191134Z-vet-c7a2625-ce0e`) and two under vet-v2 (`20261013T083805Z-vet-456ad38-309e`,
`20261013T083805Z-vet-456ad38-a1cf`). None is flagged.

`python3 /tmp/t13b/screen_vets.py results/benchmarks/*-vet-*`:

```
20261009T190108Z-vet-c7a2625-fe36 pass bearing [0, 1, 2, 3, 4, 5, 6, 7] tested [(0, 'predicted', 7, 7), (1, 'predicted', 7, 7), (2, 'predicted', 7, 7), (3, 'predicted', 7, 7), (4, 'predicted', 7, 7), (5, 'predicted', 7, 7), (6, 'predicted', 7, 7), (7, 'predicted', 7, 7)] 
20261009T191134Z-vet-c7a2625-ce0e pass bearing [0, 1, 2, 3, 4, 5] tested [(0, 'predicted', 5, 5), (1, 'predicted', 5, 5), (2, 'predicted', 5, 5), (3, 'predicted', 5, 5), (4, 'predicted', 5, 5), (5, 'predicted', 5, 5)] 
20261013T083805Z-vet-456ad38-309e pass bearing [0, 1, 2, 3, 4, 5, 6, 7] tested [(0, 'predicted', 7, 7), (1, 'predicted', 7, 7), (2, 'predicted', 7, 7), (3, 'predicted', 7, 7), (4, 'predicted', 7, 7), (5, 'predicted', 7, 7), (6, 'predicted', 7, 7), (7, 'predicted', 7, 7)] 
20261013T083805Z-vet-456ad38-a1cf pass bearing [0, 1, 2, 3, 4, 5] tested [(0, 'predicted', 5, 5), (1, 'predicted', 5, 5), (2, 'predicted', 5, 5), (3, 'predicted', 5, 5), (4, 'predicted', 5, 5), (5, 'predicted', 5, 5)] 
```

## Commands

Each ran from Git Bash inside `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-26.04 --cd /home/kevin/code/tess-hunt-13b --
bash -l -s`, on branch `t13b-holdout` with the fix in its working tree, after `. ~/.cache/tess-hunt/logs/m3-vars.sh`.
`/tmp/t13/heavy.sh` runs one memory-heavy command at a time under a 6 GB cap (its copy is in
`neighbour-epoch-reach-2026-10-20-scripts.tar.gz`, `t13/`). The screen ran under the system `python3` (3.14.4), the
others in the repo's environment (`uv sync --frozen`).

## Scripts

### screen.py

sha256 `9fb2517e34d10667255ca21c4073bb231e2f10e85dd4639aa9bbbf5c5aa7d1ff`

```python
import json, os, sys
run = sys.argv[1]
for name in sorted(os.listdir(f"{run}/signals")):
    d = json.load(open(f"{run}/signals/{name}/checks.json"))
    h = next(c for c in d["checks"] if c["check"] == "holdout")
    seasons = h["evidence"]["seasons"]
    bearing = {s["season"] for s in seasons if (s.get("n") or 0) >= 5}
    out = []
    for s in seasons:
        if s["status"] in ("predicted", "missed"):
            tb = len(bearing - {s["season"]})
            out.append((s["season"], s["status"], s["training_seasons"], tb))
    flag = any(tb < 2 for *_, tb in out)
    print(name, h["outcome"], "bearing", sorted(bearing), "tested", out, "<- one-bearing-season training" if flag else "")
```

### exact.py

sha256 `8001817acf240ee957ae7f156b9c08d3e6ace1bbc1d021b7eb7ad39f082f5dcf`

```python
"""Run this worktree's holdout (decision 0035) on each signal's vet-v3 inputs, rebuilt as vet_with_fits builds
them, and compare it with the run's checks.json. Usage: exact.py RUN [--suspect]"""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

from tess_hunt.checks.families import good_timestamps
from tess_hunt.checks.holdout import holdout
from tess_hunt.checks.photometry import red_noise_beta, with_red_noise
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.lightcurve import LightCurve

run = Path(sys.argv[1])
suspect = "--suspect" in sys.argv
prov = json.loads((run / "provenance.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


for name in ("vet-v3.toml", "search-v2.toml"):
    recorded = [c["sha256"] for c in prov["criteria"] if Path(c["file"]).name == name]
    assert recorded == [sha(f"criteria/{name}")], (name, recorded)
cs = load_criteria("criteria/search-v2.toml").values
cv = load_criteria("criteria/vet-v3.toml").values
core = cv["depth"]["core_fraction"]


def norm(o):
    if isinstance(o, dict):
        return {k: norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [norm(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(o) else float(o)
    return o


changed = 0
for d in sorted((run / "signals").iterdir()):
    chk = json.loads((d / "checks.json").read_text())
    tic = int(chk["tic"])
    assert sha(lc_dir() / f"{tic}.npz") == prov["inputs"][f"light_curve_{tic}"]["sha256"], d.name
    e = chk["ephemeris"]
    eph = Ephemeris(e["period"], e["t0"], e["duration"], e["depth"])
    lc = LightCurve.load(lc_dir() / f"{tic}.npz")
    if not suspect:
        lc = good_timestamps(lc)
    flat = detrend(lc, cs["detrend"], [Ephemeris(**m) for m in chk["masked"]])
    noisy = with_red_noise(flat, red_noise_beta(flat, eph, core * eph.duration, cv["red_noise"]))
    new = norm(holdout(noisy, eph, cv["holdout"], core, cv["families"]).to_dict())
    old = next(c for c in chk["checks"] if c["check"] == "holdout")
    rows = []
    same = True
    for a, b in zip(new["evidence"]["seasons"], old["evidence"]["seasons"], strict=True):
        a = dict(a)
        counts = (a["training_seasons"], a.pop("training_seasons_with_transits"))
        if a["status"] != b["status"]:
            rows.append(f"season {a['season']} {b['status']} -> {a['status']} {counts}")
        else:
            rows.append(f"season {a['season']} {a['status']} {counts}")
            # Families carry their label as a string either way; everything else must reproduce.
            same &= a == norm(b)
    moved = new["outcome"] != old["outcome"]
    changed += moved
    print(
        d.name,
        old["outcome"],
        "->" if moved else "==",
        new["outcome"],
        "| other seasons reproduce" if same else "| OTHER SEASONS DIFFER",
    )
    for r in rows:
        print("   ", r)
    if moved:
        print("    reason:", new["reason"])
print(f"{changed} outcome(s) changed of {len(list((run / 'signals').iterdir()))}")
```

### refit.py

sha256 `ae3fc22f9aeb434f282108a5e456cbebc3aa12fc007ec08ecbb4c706a11546cb`

```python
"""438857197-1: does S11 (4 core cadences after detrending) steer the held-out refits? Each held-out season
refit with S11 in its training set, as the vet did, and without it (read-only)."""
import json
import os

import numpy as np

from tess_hunt.checks.families import good_timestamps
from tess_hunt.checks.holdout import refit_ephemeris, season_labels
from tess_hunt.checks.photometry import box_depth, red_noise_beta, with_red_noise
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve

cs = load_criteria("criteria/search-v2.toml").values
cv = load_criteria("criteria/vet-v3.toml").values
core = cv["depth"]["core_fraction"]
chk = json.load(open(os.environ["VET_RUN"] + "/signals/438857197-1/checks.json"))
e = chk["ephemeris"]
eph = Ephemeris(e["period"], e["t0"], e["duration"], e["depth"])
lc = good_timestamps(LightCurve.load(lc_dir() / "438857197.npz"))
flat = detrend(lc, cs["detrend"], [Ephemeris(**m) for m in chk["masked"]])
noisy = with_red_noise(flat, red_noise_beta(flat, eph, core * eph.duration, cv["red_noise"]))
labels = season_labels(noisy.time, cv["holdout"]["season_gap_days"])
f = chk["fit"]
fit = Ephemeris(f["period"]["median"], f["t0"]["median"], eph.duration, eph.depth)
s11 = labels == 0
print("S11 after detrending: cadences inside the transit", int((in_transit(noisy.time, eph) & s11).sum()),
      "in the core", int((in_transit(noisy.time, eph, core) & s11).sum()))
print(f"flat fit P {fit.period:.6f} t0 {fit.t0:.5f}; core half-width {0.5 * core * eph.duration * 24:.2f} h")
for held in (1, 2):
    test = labels == held
    mid = np.median(noisy.time[test])
    k = round((mid - fit.t0) / fit.period)
    for name, train in (("with S11", labels != held), ("without S11", (labels != held) & (labels != 0))):
        p = refit_ephemeris(noisy.select(train), eph, cv["holdout"])
        d, err, n = box_depth(noisy.time[test], noisy.flux[test], noisy.flux_err[test], p, core)
        tc = fit.t0 + k * fit.period
        off = (p.t0 + round((tc - p.t0) / p.period) * p.period - tc) * 24
        print(f"season {held} held out, trained {name}: P {p.period:.6f}, epoch {k} {off:+.2f} h from the flat fit, "
              f"held-out depth {d * 1e6:.0f} +- {err * 1e6:.0f} ppm, {d / err:.1f} sigma, n {n}")
```

### screen_vets.py

sha256 `d58c9f96e0ba171a144bec564675b930e083185eae3b6a966ba1f249f27ba1a1`

```python
"""screen.py's count on the published single-signal vets, whose checks.json sits in the run directory itself.
Usage: screen_vets.py RUN_DIR..."""
import json
import sys

for run in sys.argv[1:]:
    d = json.load(open(f"{run}/checks.json"))
    h = next(c for c in d["checks"] if c["check"] == "holdout")
    seasons = h["evidence"]["seasons"]
    bearing = {s["season"] for s in seasons if (s.get("n") or 0) >= 5}
    out = []
    for s in seasons:
        if s["status"] in ("predicted", "missed"):
            tb = len(bearing - {s["season"]})
            out.append((s["season"], s["status"], s["training_seasons"], tb))
    flag = any(tb < 2 for *_, tb in out)
    print(run.rstrip("/").split("/")[-1], h["outcome"], "bearing", sorted(bearing), "tested", out, "<- one-bearing-season training" if flag else "")
```

### variant.py

sha256 `f1c10e9ef5624cb9dc62038caaf2f32daffaffb78fe406ab11583916d4b625c4`

```python
"""Each season's cadences at the vet's ephemeris inside the core window (core_fraction) and inside the whole
transit, on each signal's rebuilt vet-v3 inputs, and the holdout outcome each count would give: a tested
season untestable when fewer than min_training_seasons of its training seasons hold min_points cadences
(read-only). Usage: variant.py RUN [--suspect]"""
import json
import sys
from pathlib import Path

import numpy as np

from tess_hunt.checks.families import good_timestamps
from tess_hunt.checks.holdout import season_labels
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve

run = Path(sys.argv[1])
suspect = "--suspect" in sys.argv
cs = load_criteria("criteria/search-v2.toml").values
cv = load_criteria("criteria/vet-v3.toml").values
h = cv["holdout"]
core = cv["depth"]["core_fraction"]


def outcome(statuses):
    tested = [s for s in statuses if s in ("predicted", "missed")]
    if len(tested) < 2:
        return "inconclusive"
    return "fail" if "missed" in tested else "pass"


for d in sorted((run / "signals").iterdir()):
    chk = json.loads((d / "checks.json").read_text())
    e = chk["ephemeris"]
    eph = Ephemeris(e["period"], e["t0"], e["duration"], e["depth"])
    lc = LightCurve.load(lc_dir() / f"{int(chk['tic'])}.npz")
    if not suspect:
        lc = good_timestamps(lc)
    flat = detrend(lc, cs["detrend"], [Ephemeris(**m) for m in chk["masked"]])
    labels = season_labels(flat.time, h["season_gap_days"])
    seasons = np.unique(labels)
    counts = {
        rule: {int(s): int((in_transit(flat.time, eph, w) & (labels == s)).sum()) for s in seasons}
        for rule, w in (("core", core), ("whole", 1.0))
    }
    stored = next(c for c in chk["checks"] if c["check"] == "holdout")
    old = [s["status"] for s in stored["evidence"]["seasons"]]
    line = [d.name, stored["outcome"]]
    for rule, n in counts.items():
        bearing = {s for s, k in n.items() if k >= h["min_points"]}
        new = [
            "untestable"
            if st in ("predicted", "missed") and len(bearing - {i}) < h["min_training_seasons"]
            else st
            for i, st in enumerate(old)
        ]
        line.append(f"{rule} {n} -> {outcome(new)}")
    print(" | ".join(line), "<- changes" if len({p.rsplit(' ', 1)[-1] for p in line[2:]} | {stored['outcome']}) > 1 else "")
```
