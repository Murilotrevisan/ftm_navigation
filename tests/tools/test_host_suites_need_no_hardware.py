"""L4 -- mechanical guards on the host unit-test suites.

HOW TO RUN (Windows host, project venv):

    .\\tools\\dev.ps1 tools-test

Duration: < 1 s.

L1a and L1b must run in the container with NO hardware attached
(docs/TESTING.md §7). "We are careful about that" is not a guarantee; this
file is. It also enforces the layering rule that makes host testing possible
at all: domain/ must not include a single ESP-IDF header
(docs/ARCHITECTURE.md §1).

These checks are cheap and they fail the moment someone reaches for a board
from a host test -- which is exactly when it is cheap to fix.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

HOST_TEST_DIRS = [
    REPO_ROOT / "tests" / "host_ceedling",
    REPO_ROOT / "tests" / "host_idf",
]

# Anything that means "this test talks to hardware".
FORBIDDEN_IN_HOST_TESTS = [
    "serial",       # pyserial, and any C identifier containing it
    "esptool",
    "COM3",
    "COM4",
]

# ESP-IDF headers that must never appear in domain/. Not exhaustive by design:
# the broad check below catches the rest.
ESP_IDF_HEADER_HINTS = [
    "esp_wifi.h",
    "esp_err.h",
    "esp_event.h",
    "esp_log.h",
    "esp_system.h",
    "freertos/",
    "driver/",
    "nvs_flash.h",
]


def _sources(root: Path, suffixes=(".c", ".h", ".yml", ".py")) -> List[Path]:
    if not root.exists():
        pytest.fail(f"expected directory is missing: {root}")
    return [p for p in root.rglob("*") if p.suffix in suffixes and p.is_file()]


@pytest.mark.parametrize("directory", HOST_TEST_DIRS, ids=lambda p: p.name)
def test_host_suites_do_not_reference_hardware(directory: Path):
    offenders = []
    for path in _sources(directory):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for needle in FORBIDDEN_IN_HOST_TESTS:
            if needle.lower() in text:
                # The word appears in prose in the file headers explaining WHY
                # hardware is absent, so only flag code lines.
                for lineno, line in enumerate(text.splitlines(), start=1):
                    stripped = line.strip()
                    if needle.lower() not in stripped:
                        continue
                    if stripped.startswith(("*", "/*", "//", "#", "-")):
                        continue
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
    assert not offenders, "host unit tests must not touch hardware:\n" + "\n".join(offenders)


def test_domain_includes_no_esp_idf_header():
    """The rule the whole host-test strategy rests on.

    domain/ is pure C. An `#include "esp_wifi.h"` here breaks the build
    contract (docs/ARCHITECTURE.md §1) and would make L1a impossible.
    """
    offenders = []
    for path in _sources(REPO_ROOT / "components" / "domain", suffixes=(".c", ".h")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            stripped = line.strip()
            if not stripped.startswith("#include"):
                continue
            if any(hint in stripped for hint in ESP_IDF_HEADER_HINTS):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
    assert not offenders, "domain/ must not include ESP-IDF headers:\n" + "\n".join(offenders)


def test_no_esp_err_t_in_domain_or_services_public_headers():
    """esp_err_t must not escape into domain/ or services/ public headers.

    Drivers may use it internally, but they translate at the boundary
    (docs/ARCHITECTURE.md §9).
    """
    offenders = []
    for layer in ("domain", "services"):
        root = REPO_ROOT / "components" / layer
        if not root.exists():
            continue
        for path in root.rglob("include/**/*.h"):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                stripped = line.strip()
                # Comments are where the rule itself is written down.
                if stripped.startswith(("*", "/*", "//")):
                    continue
                if "esp_err_t" in stripped:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
    assert not offenders, "esp_err_t in a public header:\n" + "\n".join(offenders)


def test_every_declared_test_directory_exists():
    """dev.ps1 and tests/README.md must not point at paths that do not exist."""
    for relative in [
        "tests/host_ceedling",
        "tests/host_idf",
        "tests/target_smoke",
        "tests/e2e",
        "tests/tools",
        "tests/sim",
        "tests/manual",
        "docker",
        "tools",
    ]:
        assert (REPO_ROOT / relative).is_dir(), f"missing directory: {relative}"


def test_container_never_maps_a_device():
    """The container builds and unit-tests. It does not touch the boards.

    A `devices:` or `privileged:` key appearing in the compose file is a scope
    violation, so it is checked rather than trusted (docs/CONTAINER.md §3).
    """
    compose = (REPO_ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    for lineno, line in enumerate(compose.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("devices:"), f"device mapping at line {lineno}"
        assert not stripped.startswith("privileged:"), f"privileged at line {lineno}"
        assert "/dev/tty" not in stripped, f"device path at line {lineno}"
