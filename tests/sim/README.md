# Lsim — Simulation

**Empty on purpose. Populated in Phase 4/5.** Do not delete it as "unused" —
`tools/dev.ps1` and `tests/pytest.ini` both reference this path, and the
directory existing is what keeps the layout a standard rather than something
re-derived per phase.

| | |
| --- | --- |
| **Scope** | 3D trilateration with N ≥ 4 anchors, degenerate geometry, log replay |
| **Framework** | Ceedling (C logic) and pytest (`-m sim`, host replay) |
| **Runs where** | Container (C) / Windows venv (replay) |
| **Hardware** | None |

## Why it exists before it has contents

Only two boards exist, so a 3D fix cannot be produced on hardware at all
(`docs/PLAN.md` §5.7). The 3D maths is therefore developed and proven here —
against recorded real measurements with their real noise and drift, replayed
from `.ftmlog` captures — before any of it is compiled for the target
(`docs/PLAN.md` §4).

The simulation must cover, at minimum, the cases in `docs/TESTING.md` §4.3:
fewer than 4 anchors, coplanar and collinear anchors, duplicate positions,
inconsistent ranges, and numerical extremes. **A fabricated 3D fix below 4
usable anchors is a hard failure**, not a tolerance question.
