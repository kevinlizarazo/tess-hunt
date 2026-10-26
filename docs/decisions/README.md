# Decisions

One file per decision, `NNNN-short-title.md`, numbered in order and never renumbered or deleted. A decision that
replaces an earlier one links it, and the earlier file gets a "Superseded by" line.

Each file has Date, Status (Proposed, Accepted, Superseded), Context, Decision and Evidence. Evidence links to unit
tests or to generated files under `results/`; numbers are not typed by hand.

Changing anything under `criteria/` after results exist needs an entry here first, approved by the maintainer.

Some records, docstrings and comments use labels from the build. A "Task N" (or "Task N Step M") is a step of the
milestone's implementation plan, which is kept outside the repository. A "Ruling" (Ruling G, Ruling AX and so on) is
a choice the controller, the Claude session that ran the plan, made during the build; it binds once the maintainer
accepts it, and each record that cites one states it in full and says when it was accepted. A "pin" (P2, P3) is a
probe made before the build to settle a fact the plan relied on. "PF" numbers are findings of M2's final review, and
"F" numbers in a vetting record are its review's findings. "M3 design, section N" points to the milestone's design,
also kept outside the repository, from which [docs/design.md](../design.md) was amended.
