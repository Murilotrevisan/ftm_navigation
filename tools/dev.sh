#!/usr/bin/env bash
# Container-side task runner.
#
# Two ways in:
#   - tools/dev.ps1 (Windows) invokes this inside the container for every
#     container-side subcommand. That is the normal path.
#   - Directly, from inside WSL/Linux or an interactive container shell.
#
# Everything here runs in Linux and touches no hardware. Hardware subcommands
# live in tools/dev.ps1 and run in the Windows venv (docs/CONTAINER.md).
#
# MUST keep LF line endings; .gitattributes enforces it. CRLF makes this fail
# with a confusing "not found".
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/build_container"
FIRMWARE_DIR="${REPO_ROOT}/tools/bench_firmware"
CEEDLING_DIR="${REPO_ROOT}/tests/host_ceedling"
HOST_IDF_DIR="${REPO_ROOT}/tests/host_idf"
COVERAGE_DIR="${BUILD_DIR}/coverage"

# Container build output is kept out of any host `build/`: a build/ produced by
# Windows CMake carries Windows absolute paths and fails inside Linux in a
# confusing way (docs/CONTAINER.md §3).
IDF_BUILD_DIR="${BUILD_DIR}/firmware"
IDF_TEST_BUILD_DIR="${BUILD_DIR}/host_idf"
IDF_SELFCHECK_BUILD_DIR="${BUILD_DIR}/host_idf_selfcheck"
TARGET_SMOKE_BUILD_DIR="${BUILD_DIR}/target_smoke"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

in_container() { [ -d /opt/esp/idf ]; }

require_idf() {
    if ! command -v idf.py >/dev/null 2>&1; then
        if [ -f /opt/esp/idf/export.sh ]; then
            # shellcheck disable=SC1091
            . /opt/esp/idf/export.sh >/dev/null 2>&1
        else
            echo "ERROR: idf.py not on PATH and /opt/esp/idf/export.sh not found." >&2
            echo "       This subcommand must run inside the container." >&2
            exit 1
        fi
    fi
}

# --- firmware -----------------------------------------------------------

cmd_build() {
    require_idf
    say "Bench firmware build (esp32c3) -> ${IDF_BUILD_DIR}"
    cd "${FIRMWARE_DIR}"
    idf.py -B "${IDF_BUILD_DIR}" \
           -D SDKCONFIG="${IDF_BUILD_DIR}/sdkconfig" \
           set-target esp32c3 build
}

cmd_target_build() {
    require_idf
    say "L2 target smoke app build (esp32c3) -> ${TARGET_SMOKE_BUILD_DIR}"
    cd "${REPO_ROOT}/tests/target_smoke"
    idf.py -B "${TARGET_SMOKE_BUILD_DIR}" \
           -D SDKCONFIG="${TARGET_SMOKE_BUILD_DIR}/sdkconfig" \
           set-target esp32c3 build
}

# --- host unit tests ----------------------------------------------------

cmd_test_l1a() {
    say "L1a  Ceedling (Unity + CMock)  ->  components/domain"
    cd "${CEEDLING_DIR}"
    ceedling test:all
}

cmd_test_l1b() {
    require_idf
    say "L1b  ESP-IDF linux target      ->  components/services"
    cd "${HOST_IDF_DIR}"
    idf.py -B "${IDF_TEST_BUILD_DIR}" \
           -D SDKCONFIG="${IDF_TEST_BUILD_DIR}/sdkconfig" \
           --preview set-target linux build
    say "L1b  running ${IDF_TEST_BUILD_DIR}/host_idf_tests.elf"
    # The binary exits with its failure count (see the file header on why that
    # exit() is not optional), so `set -e` fails the run for us.
    "${IDF_TEST_BUILD_DIR}/host_idf_tests.elf"
}

cmd_test_host() {
    cmd_test_l1a
    cmd_test_l1b
    say "L1a + L1b PASS"
}

# Proves the L1b harness reports failure rather than exiting 0 or hanging.
# Expected to FAIL -- a zero exit code here means the harness is broken.
cmd_test_host_selfcheck() {
    require_idf
    say "L1b harness self-check (a deliberate failure -- expected to FAIL)"
    cd "${HOST_IDF_DIR}"
    idf.py -B "${IDF_SELFCHECK_BUILD_DIR}" \
           -D SDKCONFIG="${IDF_SELFCHECK_BUILD_DIR}/sdkconfig" \
           -D "CMAKE_C_FLAGS=-DFTM_TEST_SELFCHECK_FAIL" \
           --preview set-target linux build >/dev/null

    set +e
    timeout 120 "${IDF_SELFCHECK_BUILD_DIR}/host_idf_tests.elf"
    local rc=$?
    set -e

    if [ "${rc}" -eq 124 ]; then
        echo "SELF-CHECK FAILED: the binary hung instead of failing (timeout)." >&2
        echo "  Cause is almost always a missing exit() after UNITY_END()." >&2
        return 1
    fi
    if [ "${rc}" -eq 0 ]; then
        echo "SELF-CHECK FAILED: a failing test exited 0. Failures are invisible." >&2
        return 1
    fi
    say "self-check OK: failing test -> exit code ${rc}, no hang"
}

# --- coverage -----------------------------------------------------------

cmd_coverage() {
    say "Coverage (gcovr) over L1a -> ${COVERAGE_DIR}"
    cd "${CEEDLING_DIR}"
    ceedling gcov:all

    rm -rf "${COVERAGE_DIR}"
    mkdir -p "${COVERAGE_DIR}"

    # --root must be the Ceedling project directory, NOT the repo root: the
    # coverage data records source paths relative to the directory the
    # compiler ran in, and gcovr resolves them from --root. Pointing it at the
    # repo root yields "Cannot open source file test/..." and, with errors
    # ignored, a report reading lines-valid="0" -- which looks like a pass
    # (docs/CONTAINER.md §7).
    gcovr --root "${CEEDLING_DIR}" \
          --filter "${REPO_ROOT}/components/domain/" \
          --print-summary \
          --html-details "${COVERAGE_DIR}/index.html" \
          --xml-pretty --xml "${COVERAGE_DIR}/coverage.xml" \
          "${BUILD_DIR}/ceedling/gcov/out"

    # A 0 % report is a wiring failure, not a pass. Fail loudly on one.
    local lines_valid
    lines_valid=$(sed -n 's/.*lines-valid="\([0-9]*\)".*/\1/p' \
                  "${COVERAGE_DIR}/coverage.xml" | head -1)
    if [ -z "${lines_valid}" ] || [ "${lines_valid}" -eq 0 ]; then
        echo "ERROR: coverage report contains zero lines -- gcovr is not seeing" >&2
        echo "       the coverage data. This is a wiring failure, not 0 % coverage." >&2
        return 1
    fi

    say "coverage report OK: ${lines_valid} lines measured"
    echo "  HTML: build_container/coverage/index.html"
    echo "  XML : build_container/coverage/coverage.xml"
    echo
    echo "Coverage is REPORTED, NOT GATED (docs/TESTING.md §2, PHASE_0 decisions)."
}

# --- housekeeping -------------------------------------------------------

cmd_clean() {
    say "Removing ${BUILD_DIR}"
    rm -rf "${BUILD_DIR}"
}

usage() {
    cat <<'EOF'
Usage: tools/dev.sh <command>

Container-side commands (no hardware, ever):
  build                 build bench firmware for esp32c3 -> build_container/firmware
  target-build          build the L2 smoke app for esp32c3
  test-host             L1a (Ceedling) + L1b (IDF linux target)
  test-host-selfcheck   prove the L1b harness fails loudly instead of hanging
  coverage              gcovr over L1a                   -> build_container/coverage
  clean                 delete build_container/

Hardware commands (flash, e2e, manual) live in tools/dev.ps1 and run on the
Windows host in the project venv. See docs/CONTAINER.md.
EOF
}

case "${1:-}" in
    build)               cmd_build ;;
    target-build)        cmd_target_build ;;
    test-host)           cmd_test_host ;;
    test-l1a)            cmd_test_l1a ;;
    test-l1b)            cmd_test_l1b ;;
    test-host-selfcheck) cmd_test_host_selfcheck ;;
    coverage)            cmd_coverage ;;
    clean)               cmd_clean ;;
    ""|-h|--help|help)   usage ;;
    *) echo "Unknown command: $1" >&2; echo >&2; usage >&2; exit 2 ;;
esac
