# L3 — E2E across both boards (autonomous)

| | |
| --- | --- |
| **Runs where** | **Windows host, project venv.** Never the container |
| **Command** | `.\tools\dev.ps1 e2e` |
| **Duration** | ~40 s, most of it flashing |
| **Hardware** | **Both boards**, permanently attached, fixed 1.00 m apart |

Prerequisite — build the app in the container first:

```powershell
.\tools\dev.ps1 target-build     # container
.\tools\dev.ps1 e2e              # host venv
```

## Boards are resolved by MAC, never by port number

Ports re-enumerate. `tools/boards.json` maps role → MAC (normative copy:
`docs/CONTAINER.md` §6) and `tools/board_ports.py` does the lookup, which is
the same code path `dev.ps1 flash` uses — so the E2E harness and the flasher
can never disagree about which board is which.

`conftest.py` resolves both roles **once, in `pytest_configure`**, before
collection. A missing board raises `pytest.UsageError` naming the role and the
MAC, and listing what *was* attached:

```
E2E needs both boards attached.
board not attached for: initiator (MAC 14:63:93:8d:96:e4). Espressif boards
currently attached: 14:63:93:8d:98:74 on COM3. Check the USB cable and that no
other program holds the port.
```

**A fixture that skips when hardware is missing is not acceptable here** — it
turns "the bench is unplugged" into a green run.

`dut[0]` is the responder and `dut[1]` the initiator, in the order of
`conftest.ROLES`. `test_roles_are_bound_to_the_expected_boards` asserts that
binding against the MAC each board prints at Wi-Fi start, so a silent role
swap fails loudly rather than producing measurements that mean something else.

## Writing a new E2E test

- Start the file with a **How to run** block (`docs/TESTING.md` §5).
- Assert on **both** DUTs.
- **Never assert a distance from a single reading.** `dist_est` is quantised
  to 15 cm, the observed spread at a fixed 1.2 m setup was 0.75–1.65 m, and
  there is real drift on a timescale of tens of seconds
  (`HARDWARE_FINDINGS.md` §3, §7, §8). Use a tolerance band over a minimum
  sample count — the suggested band is mean over ≥ 60 samples, 1.00 m ± 0.75 m,
  valid ratio ≥ 0.8 (§10) — and assert on the **valid/total ratio**, not only
  on the distance.
- Hold both ports open for the whole test: opening a port resets the board, so
  a per-step open destroys a responder's AP state (`docs/CONTAINER.md` §7).

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `PermissionError` / "Acesso negado" on a COM port | Another process holds it — an `idf.py monitor`, another agent's script, a previous run. The boards are a **shared, single-user resource**; only one session may drive them at a time |
| `UsageError: no build at build_container/target_smoke` | Run `.\tools\dev.ps1 target-build` first (in the container) |
| Board boots but no markers appear | Firmware missing `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` — boot logs still show, but the console is unreachable |
| Readings far outside the expected band | Check the fixture first: boards moved, clamp condition, wrong offset, or drift — in that order (`HARDWARE_FINDINGS.md` §10) |
