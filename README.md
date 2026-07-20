# FTM Indoor Positioning

A 3D indoor positioning bench built from ESP32-C3 boards using Wi-Fi FTM
(Fine Timing Measurement). One initiator measures its distance to several
stationary anchors; distances plus known anchor positions give a position fix.

**Start at [`docs/PLAN.md`](docs/PLAN.md).** It is the index for everything else.

## Quick orientation

| I want to… | Read |
| --- | --- |
| Understand the project and its phases | [`docs/PLAN.md`](docs/PLAN.md) |
| Work on a phase (agents start here) | [`docs/AGENT_BRIEF.md`](docs/AGENT_BRIEF.md) |
| Know what the hardware actually does | [`docs/HARDWARE_FINDINGS.md`](docs/HARDWARE_FINDINGS.md) — normative |
| Build or run tests | [`docs/CONTAINER.md`](docs/CONTAINER.md), [`tests/README.md`](tests/README.md) |
| Check a board is healthy | [`tools/bench_firmware/README.md`](tools/bench_firmware/README.md) |

## Common commands

```powershell
.\tools\dev.ps1 setup        # build the container image (once)
.\tools\dev.ps1 venv         # create .venv and install test deps (once)

.\tools\dev.ps1 build        # bench firmware, in the container
.\tools\dev.ps1 test-host    # L1a + L1b unit tests, no hardware needed
.\tools\dev.ps1 coverage     # gcovr report
.\tools\dev.ps1 e2e          # end-to-end across both boards
```

Builds and host unit tests run in a Linux container; flashing and anything
touching the boards runs on Windows in the project venv. `dev.ps1` routes each
subcommand to the right side.

## Status

Phases 0 (container and test infrastructure) and 1 (bench validation firmware)
are merged. See the phase table in [`docs/PLAN.md`](docs/PLAN.md) for what is
next, and [`docs/reports/`](docs/reports/) for what each completed phase
actually delivered.
