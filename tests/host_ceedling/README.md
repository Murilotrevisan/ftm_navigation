# L1a — Ceedling (Unity + CMock) → `components/domain/`

| | |
| --- | --- |
| **Runs where** | Container. Ruby and Ceedling live in the image, **never on the PC** |
| **Command** | `.\tools\dev.ps1 test-host` |
| **Duration** | ~11 s cold, ~2 s warm |
| **Hardware** | None, ever |
| **Coverage** | `.\tools\dev.ps1 coverage` → `build_container/coverage/` |

Run only this level, or a single file:

```powershell
.\tools\dev.ps1 shell
# inside the container:
cd tests/host_ceedling && ceedling test:all
cd tests/host_ceedling && ceedling test:test_ftm_result_report.c
```

## Scope

`components/domain/` **only** — nothing else. `services/` belongs to
`tests/host_idf/` and a module tested in both suites drifts
(`docs/TESTING.md` §2).

Why Ceedling here: sub-second feedback on pure logic, which is where the
interesting worst-case behaviour lives (clamp, sign inversion, overflow,
degenerate geometry), and CMock generates C mocks **from the real headers**, so
a mock cannot silently drift from the interface it doubles.

## The files, and what they are examples of

| File | Demonstrates |
| --- | --- |
| `test_harness_smoke.c` | the plumbing works, independent of project code |
| `test_ftm_result.c` | real module; nominal, every enum value, out-of-range, negative, `INT32_MIN` |
| `test_ftm_result_report.c` | **CMock**: dependency mocked, tested when it succeeds *and* when it fails; NULL argument; buffer-too-small with a **canary byte** past the limit |

Copy `test_ftm_result_report.c` when adding a test with a mocked dependency —
it is the reference for the pattern.

## Ceedling 1.1.0 traps this project.yml already avoids

Configuration written from 0.x documentation fails, and all of these surface
only when the suite is actually executed (`docs/CONTAINER.md` §7):

| Symptom | Fix already applied |
| --- | --- |
| `:use_test_preprocessor is ':true' but must be one of ...` | 1.x wants the enum `:all` |
| `:defines must contain key / value pairs, not array` | 1.x wants a hash, `{}` |
| `Plugin 'stdout_pretty_tests_report' not found` | renamed to `report_tests_pretty_stdout` |
| `undefined reference to <fn>_ExpectAnyArgsAndReturn` | needs the `:expect_any_args` / `:return_thru_ptr` CMock plugins |
| `undefined reference` to a function that exists | Ceedling links the `.c` matching each **header the test includes** — keep one `.c` per public header |

## Coverage

Report generation is **not** delegated to Ceedling's gcov plugin: its gcovr
invocation scans from the working directory and cannot see an out-of-tree
build root, producing a report reading `lines-valid="0"` — which looks exactly
like a pass. `tools/dev.sh coverage` runs gcovr explicitly and **fails if the
line count is zero**.
