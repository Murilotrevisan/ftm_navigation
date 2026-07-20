# The build & host-unit-test container

**Scope: builds firmware and runs host unit tests. It does not touch the
boards.** No device mapping, no `--privileged`. Flashing and E2E run on
Windows, which already has ESP-IDF v5.5.2 — keeping hardware on the host
avoids USB passthrough into WSL entirely (`usbipd-win`, device forwarding,
re-attaching after every replug), complexity that would buy reproducibility
for a step that is already reproducible.

Full rationale and the job/where table: `docs/CONTAINER.md`.

## Files

| File | Purpose |
| --- | --- |
| `Dockerfile` | `FROM espressif/idf:v5.5.2` + Ruby/Ceedling + gcovr. **The tag is pinned deliberately** — floating to `latest` would change the IDF version out from under the measurements in `docs/HARDWARE_FINDINGS.md` |
| `docker-compose.yml` | repo bind mount, persistent ccache volume, UID mapping. Contains no `devices:` and no `privileged:` — `tests/tools/test_host_suites_need_no_hardware.py` asserts that mechanically |
| `entrypoint.sh` | sources `/opt/esp/idf/export.sh`, then `exec "$@"`. **LF line endings, enforced by `.gitattributes`** — CRLF here fails with a confusing "not found" |

## Usage

Always through `tools/dev.ps1`, which routes each subcommand to the right side:

```powershell
.\tools\dev.ps1 setup        # build the image, print tool versions
.\tools\dev.ps1 build        # firmware  -> build_container/firmware
.\tools\dev.ps1 test-host    # L1a + L1b
.\tools\dev.ps1 coverage     # gcovr     -> build_container/coverage
.\tools\dev.ps1 shell        # interactive shell, repo at /project
```

Raw equivalent, if you need it:

```powershell
docker compose -f docker\docker-compose.yml run --rm dev bash tools/dev.sh test-host
```

## Two things that will bite

**`bash -lc` breaks in this image — use `bash -c`.** The login shell re-sources
the IDF export and swallows the rest of the command, so every command after
the first silently does nothing. This cost an hour to find once already.

**Container build output goes to `build_container/`, never `build/`.** A
`build/` produced by Windows CMake contains Windows absolute paths and fails
inside Linux in a confusing way. Every `idf.py` invocation in `tools/dev.sh`
passes `-B build_container/<name>` and a matching `SDKCONFIG`, so the two
never meet.

## File ownership

The compose file exposes `FTM_UID`/`FTM_GID` (default `0`), and `tools/dev.sh`
is the place to export them when running under Linux/WSL, where a root-owned
build directory is a genuine nuisance.

**On Docker Desktop for Windows this is not what protects you.** The bind
mount is drvfs: the container runs as root, but every file it creates surfaces
on the host owned by the Windows user. Verified on this machine —
container-side `ls -ln` shows `0 0`, while host-side `Get-Acl` reports
`MURILOTREVISAN\murilo`. The UID mapping is kept for the Linux path, not
because Windows needs it.
