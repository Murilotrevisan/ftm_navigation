# L1b — ESP-IDF `linux` target (Unity) → `components/services/`

| | |
| --- | --- |
| **Runs where** | Container |
| **Command** | `.\tools\dev.ps1 test-host` |
| **Duration** | ~35 s cold (CMake configure dominates), ~5 s warm |
| **Hardware** | None, ever |

Run only this level, or the binary on its own:

```powershell
.\tools\dev.ps1 shell
# inside the container:
bash tools/dev.sh test-l1b
./build_container/host_idf/host_idf_tests.elf ; echo "exit=$?"
```

## Scope

`components/services/` **only**. `domain/` belongs to `tests/host_ceedling/`
(`docs/TESTING.md` §2).

Why IDF's own build rather than a second Ceedling project: `services/` lives
inside the IDF component system, so building it this way exercises the **real
component dependency graph and the real Kconfig wiring** — including the
role-strategy source selection — which a standalone Ceedling project cannot
see. The binary is native: no board, no emulator.

## The trap this harness is built around

ESP-IDF's linux target **keeps its scheduler running after `UNITY_END()`**.
Without an explicit `exit(failures)` the binary never terminates, so a failing
suite **hangs instead of failing** — which looks like a stuck machine rather
than a broken build (`docs/CONTAINER.md` §7).

`main/test_harness_smoke.c` calls `exit(failures)`, making the exit code the
failure count. That claim is checked rather than trusted:

```powershell
.\tools\dev.ps1 test-host-selfcheck
```

builds the suite with `-DFTM_TEST_SELFCHECK_FAIL`, which compiles in one
deliberately failing test, and asserts that the run **exits non-zero within a
timeout**. A zero exit or a timeout there means the harness is broken and
every "pass" it has ever reported is meaningless.

## The files

| File | Contents |
| --- | --- |
| `main/test_harness_smoke.c` | entry point, `UNITY_BEGIN/END`, the mandatory `exit()`, and the self-check test |
| `main/test_ftm_quality.c` | `ftm_quality` — the observed hardware failures from `docs/HARDWARE_FINDINGS.md`, notably the **clamp signature** (`valid=2, total=30` while the session reports *success*) and the 0.8 boundary either side (24/30 usable, 23/30 not) |

Adding a module test: add `main/test_<module>.c` with a
`register_<module>_tests(void)` that `RUN_TEST`s its cases, list it in
`main/CMakeLists.txt`, and call it from `app_main`.
