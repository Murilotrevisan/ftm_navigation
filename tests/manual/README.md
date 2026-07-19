# L5 — Manual integration test (operator-driven)

**Empty on purpose. Populated in Phase 5/6.** Do not delete it — `dev.ps1
manual` and `tests/pytest.ini` reference this path.

| | |
| --- | --- |
| **Scope** | Physical movement of the initiator → distance tracks the movement |
| **Framework** | pytest, human in the loop |
| **Runs where** | Windows host, project venv |
| **Command** | `.\tools\dev.ps1 manual` |
| **Duration** | ~10 min, including operator time |
| **Marker** | `@pytest.mark.manual` — excluded from the autonomous run |

## Requirements the eventual test must meet (`docs/TESTING.md` §6)

- Numbered, unambiguous operator instructions ("place the initiator at 1 m,
  press ENTER; walk slowly to 5 m over ~30 s, press ENTER").
- Records continuously, **including during the movement**.
- Produces two artefacts: a PNG chart of distance vs. time with the phases
  annotated, and a **JSON summary** — per-phase mean, σ, sample count, valid
  ratio, RSSI, detected transitions.
- The JSON exists so an **AI can evaluate the run without seeing the chart**:
  did the measured distance track the commanded movement, monotonically,
  within tolerance?

Note `-s` is passed by `dev.ps1 manual`: without it pytest captures stdin and
the operator prompts never appear.
