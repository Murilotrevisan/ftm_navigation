# Tests — index

Every level, the exact command, **where it runs**, and how long it takes so a
slow suite is not mistaken for a hang.

Two rules decide where a test belongs:

1. **Builds and host unit tests run in the container. Anything touching the
   boards runs on Windows in the project venv** (`docs/CONTAINER.md`). The
   container has no device mapping and never touches hardware.
2. **Each module has exactly ONE authoritative host suite** (`docs/TESTING.md`
   §2). `domain/` is Ceedling's (L1a); `services/` is the ESP-IDF linux
   target's (L1b). Never test a module in both — duplicated suites drift, then
   disagree, and the disagreement gets settled by weakening whichever one is
   inconvenient.

---

## The levels

| Level | Scope | Command | Runs where | Duration | Hardware |
| --- | --- | --- | --- | --- | --- |
| **L1a** | `components/domain/` | `.\tools\dev.ps1 test-host` | Container | ~11 s cold, ~2 s warm | none |
| **L1b** | `components/services/` | `.\tools\dev.ps1 test-host` | Container | ~35 s cold, ~5 s warm | none |
| **L2** | on-target Unity | `.\tools\dev.ps1 target-build` then `.\tools\dev.ps1 flash <role>` | Build: container. Flash: venv | ~90 s build, ~15 s flash | 1 board |
| **L3** | E2E, both boards | `.\tools\dev.ps1 e2e` | Windows venv | ~40 s | **both boards** |
| **L4** | host Python tools | `.\tools\dev.ps1 tools-test` | Windows venv | < 2 s | none |
| **L5** | manual movement | `.\tools\dev.ps1 manual` | Windows venv | ~10 min + operator | both boards |
| **Lsim** | 3D / N≥4 anchors | *(Phase 4/5)* | Container / venv | — | none |

Coverage over L1a: `.\tools\dev.ps1 coverage` (container, ~16 s) →
`build_container/coverage/index.html` and `coverage.xml`.
**Coverage is reported, not gated** (`docs/TESTING.md` §2).

## Running everything

```powershell
.\tools\dev.ps1 test-host      # L1a + L1b   container, no hardware
.\tools\dev.ps1 coverage       #             container
.\tools\dev.ps1 tools-test     # L4          venv, no hardware
.\tools\dev.ps1 e2e            # L3          venv, both boards
```

Marker-based selection, from the repo root, for anything pytest owns:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -m "not manual"   # autonomous only
.\.venv\Scripts\python.exe -m pytest tests -m manual         # operator-driven only
```

`tests/pytest.ini` declares the markers `e2e`, `manual`, `slow` and `sim`, and
`--strict-markers` is on: a typo in a marker name is an error, not a silently
empty selection.

## Directory map

```
tests/
├── host_ceedling/   L1a  Ceedling (Unity + CMock)   -> components/domain
├── host_idf/        L1b  ESP-IDF linux target       -> components/services
├── target_smoke/    L2   on-target Unity app        -> the L2 template, and
│                         the known-good app L3 flashes
├── e2e/             L3   pytest-embedded, 2 DUTs by MAC, autonomous
├── tools/           L4   pytest for host Python tools
├── sim/             Lsim (Phase 4/5)
├── manual/          L5   (Phase 5/6)
├── pytest.ini       markers and selection
└── README.md        this file
```

## Things that will otherwise cost you an afternoon

| Symptom | Cause |
| --- | --- |
| Serial writes time out, but boot logs still appear | Firmware missing `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` (`HARDWARE_FINDINGS.md` §1) |
| FTM session never reports anything | `CONFIG_ESP_WIFI_FTM_ENABLE` is **`default n`** — set it explicitly (`HARDWARE_FINDINGS.md` §1) |
| L1b binary never exits | Missing `exit(failures)` after `UNITY_END()` — the linux target keeps its scheduler running |
| Coverage report shows 0 % | gcovr is not finding the coverage data. `dev.sh coverage` fails loudly on this rather than reporting a green 0 % |
| `PermissionError` / "Acesso negado" on a COM port | Another process holds it — an `idf.py monitor`, another test run, or another agent's bench script. The boards are a **shared, single-user resource** |
| Responder loses its AP state between steps | Opening a serial port resets the board; hold both ports for the whole test |
| `docker` not found in a fresh shell | PATH, not permissions. `dev.ps1` refreshes it from the registry automatically |
