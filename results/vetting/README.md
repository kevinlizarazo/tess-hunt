# Vetting

One row per published signal the maintainer has called passed, killed or held, whose call stands on its record
([decision 0028](../../docs/decisions/0028-outcomes-and-calls.md)). Each directory holds the signal's dossier
(`dossier.md`), the call (`call.toml`), the review (`review.json`) and the run files the dossier is rendered from;
[../README.md](../README.md) describes each file. A passed signal is a planet candidate, not a confirmed planet.

| Signal | Outcome | Date | Reason |
|---|---|---|---|
| [103312990-1](103312990-1/dossier.md) | held | 2026-10-22 | Nothing kills it: the dip is in every season at a steady depth, shows no binary signature on the target, and is not known. It can't pass because the public data can't place it on HD 297321: a nearby eclipsing binary within an arcminute is not excluded, Gaia sees an unresolved companion that no public data identify, and only one season can test the held-out check. |
| [399023421-1](399023421-1/dossier.md) | held | 2026-10-22 | Every vet-v3 check, the pixel check and the literature search pass, and nothing on the target looks like a binary. TRICERATOPS can't place the dip on the target: three faint background stars a few arcseconds away could make it with deep eclipses, and TESS's pixels can't separate them from the target. |
| [44926986-1](44926986-1/dossier.md) | killed | 2026-10-22 | Not new: eumemic's public all-sky candidate list holds this signal at the same period and epoch, added before tess-hunt made any public claim. TRICERATOPS also fails it, on a planet on the bound companion TIC 44926982, which TESS's pixels can't separate from the target. |
| [48010903-1](48010903-1/dossier.md) | killed | 2026-10-22 | An eccentric eclipsing binary of stars, not a planet: the real period is longer than the search's, and the search's second signal on the star is the binary's secondary eclipse, too deep and too long for any planet. The shape and radius checks fail too, on a fit that sits near the grazing line, so they are the weaker grounds. The next-look windows in this dossier use the search's period, not the binary's. |
