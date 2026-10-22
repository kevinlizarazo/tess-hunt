# Vetting

One row per published signal the maintainer has called passed, killed or held, whose call stands on its record
([decision 0028](../../docs/decisions/0028-outcomes-and-calls.md)). Each directory holds the signal's dossier
(`dossier.md`), the call (`call.toml`), the review (`review.json`) and the run files the dossier is rendered from;
[../README.md](../README.md) describes each file. A passed signal is a planet candidate, not a confirmed planet.

| Signal | Outcome | Date | Reason |
|---|---|---|---|
| [44926986-1](44926986-1/dossier.md) | killed | 2026-10-22 | Not new: eumemic's public all-sky candidate list holds this signal at the same period and epoch, added before tess-hunt made any public claim. TRICERATOPS also fails it, on a planet on the bound companion TIC 44926982, which TESS's pixels can't separate from the target. |
