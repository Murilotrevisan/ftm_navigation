# Container — Build, Test and Flash

> **Spec, not yet built.** The container is Phase 0's first deliverable. One
> decision in §2 needs a human answer before it can be built.

The goal: **every build and every test runs inside a Linux container.** Nothing
installs into the Windows host toolchain. Agents run one command and get a
reproducible environment.

---

## 1. Base image

Build on Espressif's official image, pinned to the version already validated on
this hardware:

```dockerfile
FROM espressif/idf:v5.5.2
```

The repo already contains a `.devcontainer/` using `espressif/idf` — that is the
starting point, upgraded to a pinned tag and extended with the test toolchain.

**Do not float the tag.** `latest` would silently change the IDF version out
from under measurements recorded in `docs/HARDWARE_FINDINGS.md`.

### Installed inside the container

| Tool | Purpose |
| --- | --- |
| ESP-IDF v5.5.2 + toolchains | Build (from base image) |
| ESP-IDF **linux target** support | L1 host unit tests — see `docs/TESTING.md` §2 |
| Unity + CMock | Bundled in ESP-IDF at `components/unity`, `components/cmock` |
| Python 3 + pytest | L3/L4/L5 tests |
| `pytest-embedded`, `pytest-embedded-idf`, `pytest-embedded-serial-esp` | Multi-DUT E2E harness |
| `esptool.py` | Flashing (from base image) |
| matplotlib, numpy | Calibration/movement analysis |
| tkinter (`python3-tk`) | Phase 2 calibrator UI |
| gcovr | Host coverage (optional) |

**No Ruby, no Ceedling** — superseded, see `docs/TESTING.md` §2.

## 2. DECISION REQUIRED — USB access for flashing and E2E

A Linux container on Windows cannot see `COM3`/`COM4` by default. Docker Desktop
runs containers in a WSL2 VM, and USB devices are not forwarded automatically.

There is no way around this: **containerised flashing requires one extra tool on
the Windows host.**

### Option A — Container builds and unit-tests; Windows host flashes

- **Host installs:** container runtime only.
- Container produces `build/*.bin` into a mounted volume; a small PowerShell
  script on the host flashes with the ESP-IDF Python already present.
- **Limitation: E2E tests (L3/L5) run on the Windows host, not the container.**
  That is the most important test level, and it would sit outside the isolation
  you asked for. Agents would need a working Windows Python environment too —
  two environments to keep healthy.

### Option B — Container does everything, including flash and E2E *(recommended)*

- **Host installs:** container runtime **plus `usbipd-win`** (a ~5 MB Microsoft
  open-source tool).
- `usbipd` forwards each board's USB interface into WSL2, where the container
  sees them as `/dev/ttyACM0` and `/dev/ttyACM1`.
- Single environment. Agents run one command for every level, L1 through L5.
- **Cost:** `usbipd attach` must be re-run after a replug or reboot. Scriptable
  (`tools/attach_boards.ps1`), and the E2E harness should detect a missing
  device and print the exact fix-up command rather than hanging.

**Recommendation: Option B.** The whole point of the container is that agents
can run *all* tests autonomously and reproducibly; Option A leaves the E2E suite
outside it and creates a second environment to maintain.

### Also required either way: a container runtime

`docker` is **not currently installed** on this machine. WSL2 with Ubuntu **is**
already present and working.

| Choice | Notes |
| --- | --- |
| **Docker Desktop** | Simplest, integrates with WSL2. Check licence terms — free for personal/small business, paid for large orgs. |
| **Podman Desktop** | Rootless, no licence question, slightly rougher WSL2 USB story. |
| **Docker Engine inside the existing WSL2 Ubuntu** | Nothing installed on Windows proper; runs entirely inside the WSL distro you already have. Most faithful to "no changes on my PC", slightly more setup. |

> **Please answer: which container runtime, and Option A or B?** Everything else
> in this document is decided and does not need review.

## 3. Layout (Phase 0 deliverable)

```
docker/
├── Dockerfile              # FROM espressif/idf:v5.5.2 + test toolchain
├── docker-compose.yml      # volumes, device passthrough, user mapping
├── entrypoint.sh           # sources export.sh, drops to command
└── README.md               # -> points here
tools/
├── dev.ps1                 # Windows entry: dev.ps1 build|test|flash|shell
├── dev.sh                  # same, from inside WSL/Linux
└── attach_boards.ps1       # usbipd bind+attach for both boards (Option B)
```

### Key container requirements

- **Repo mounted, not copied**, so edits on Windows are visible immediately.
- **Build output must not collide with host builds.** Use a container-specific
  build directory (`build_container/`) — a `build/` produced by Windows CMake
  has Windows absolute paths and will fail confusingly inside Linux.
- **User mapping**: run as a non-root user matching the host UID so generated
  files are not root-owned.
- **ccache volume** persisted between runs; ESP-IDF builds are slow otherwise.
- Device passthrough for `/dev/ttyACM0` and `/dev/ttyACM1` (Option B).

## 4. Intended usage (what the README must document)

```powershell
# One-time
.\tools\dev.ps1 setup            # build the image

# Every session (Option B only)
.\tools\attach_boards.ps1        # forward both boards into WSL2

# Daily
.\tools\dev.ps1 build            # build firmware in container
.\tools\dev.ps1 test             # ALL autonomous tests (L1..L4)
.\tools\dev.ps1 test-host        # L1 only, no hardware needed
.\tools\dev.ps1 flash responder  # flash the COM3 board
.\tools\dev.ps1 flash initiator  # flash the COM4 board
.\tools\dev.ps1 e2e              # L3 end-to-end across both boards
.\tools\dev.ps1 manual           # L5 operator-driven movement test
.\tools\dev.ps1 shell            # interactive shell in the container
```

Every command must work from a clean checkout with no host-side ESP-IDF.

## 5. Board identity — do not trust port numbers

Ports enumerate in whatever order Windows/WSL feels like. `/dev/ttyACM0` is not
reliably the same physical board across reboots.

**Bind roles to MAC address, not port.** Known:

| Board | MAC | Intended role |
| --- | --- | --- |
| A | *(record during Phase 0)* | Responder / anchor |
| B | `14:63:93:8d:96:e4` | Initiator |

`dev.ps1 flash <role>` must resolve the role to a MAC, probe the attached
devices, and flash the right one — failing loudly if the expected board is
absent. Flashing the wrong role onto the wrong board silently produces a system
that looks broken in a very confusing way.

## 6. Traps

| Symptom | Cause |
| --- | --- |
| `export.sh` fails / tools missing | Entrypoint did not source `/opt/esp/idf/export.sh` |
| Build fails with Windows paths in errors | Host `build/` reused inside container — use `build_container/` |
| Files created as root on the host | Container UID not mapped to host user |
| `/dev/ttyACM*` missing | `usbipd attach` not run this session (Option B) |
| Serial writes time out, boot logs still appear | Firmware missing `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` — see `HARDWARE_FINDINGS.md` §1 |
| Shell script "not found" with a valid path | CRLF line endings — `.gitattributes` forces LF, verify it applied |
