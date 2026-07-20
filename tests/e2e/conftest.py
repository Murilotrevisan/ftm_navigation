"""L3 E2E fixtures -- two DUTs, resolved BY MAC, never by port number.

HOW TO RUN (Windows host, project venv -- never the container):

    .\\tools\\dev.ps1 e2e

Duration: ~40 s for the smoke suite, most of it flashing.

Design notes that are not obvious:

* **Boards are resolved by MAC** (docs/CONTAINER.md §6). Ports re-enumerate,
  and flashing the wrong role onto the wrong board produces a system that
  looks broken in a very confusing way. ``tools/board_ports.py`` owns the
  lookup; ``tools/boards.json`` owns the mapping.

* **A missing board fails, it never skips and never hangs.** Resolution
  happens once in ``pytest_configure``, before any test runs, and raises
  ``pytest.UsageError`` naming the role and MAC that is absent. A fixture that
  quietly skips would turn "the hardware is unplugged" into a green run.

* **Both ports are held open for the whole session.** Opening a serial port
  resets the board, so a per-step open would destroy a responder's AP state
  mid-test (docs/CONTAINER.md §7).

* pytest-embedded separates per-DUT option values with ``|``, so the ports are
  passed as ``COM3|COM4`` in the fixed order of ``ROLES``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))

import board_ports  # noqa: E402  (needs the sys.path line above)

# DUT order. dut[0] is the responder, dut[1] the initiator -- asserted by
# test_harness_smoke.py so the ordering cannot silently invert.
ROLES = ("responder", "initiator")

# The known-good app both boards are flashed with. Built in the container:
#     .\tools\dev.ps1 target-build
APP_PATH = _REPO_ROOT / "tests" / "target_smoke"
BUILD_DIR = _REPO_ROOT / "build_container" / "target_smoke"


_RESOLVED_KEY = pytest.StashKey[dict]()


def _e2e_selected(config: pytest.Config) -> bool:
    """True when this invocation is going to run E2E tests.

    This conftest is only loaded when something under tests/e2e/ is collected,
    so the default is yes -- `pytest tests`, `pytest tests/e2e` and
    `pytest tests -m "not manual"` must all resolve the boards. Guarding on
    the argument text instead was a bug: `-m "not manual"` mentions neither
    "e2e" nor the directory, so resolution was skipped and the DUT fixtures
    then ran unconfigured, as a single board.

    The one exception is an explicit `-m "not e2e"`, which is how a
    hardware-less runner deselects this level (docs/TESTING.md §7). Probing
    for boards there would defeat the point of deselecting it.
    """
    markexpr = " ".join((config.getoption("markexpr", default="") or "").split())
    if "not e2e" in markexpr:
        return False
    # `-m manual` selects only the operator-driven level, which likewise has
    # no use for the E2E boards.
    return markexpr != "manual"


def pytest_configure(config: pytest.Config) -> None:
    """Resolve roles to ports before collection, and wire pytest-embedded.

    Doing this here rather than in a fixture means a missing board is a
    configuration error reported once, not a per-test failure or a skip.
    """
    if not _e2e_selected(config):
        return

    if not BUILD_DIR.exists():
        raise pytest.UsageError(
            f"no build at {BUILD_DIR}. Build it first (in the container):\n"
            f"    .\\tools\\dev.ps1 target-build"
        )

    try:
        resolved = board_ports.resolve(list(ROLES))
    except board_ports.BoardNotFound as exc:
        raise pytest.UsageError(
            f"E2E needs both boards attached.\n{exc}\n"
            f"Roles and their MACs are defined in tools/boards.json "
            f"(normative copy: docs/CONTAINER.md §6)."
        ) from exc

    ports = "|".join(resolved[role] for role in ROLES)

    config.option.count = len(ROLES)
    config.option.port = ports
    config.option.embedded_services = "|".join(["esp,idf"] * len(ROLES))
    config.option.app_path = "|".join([str(APP_PATH)] * len(ROLES))
    config.option.build_dir = "|".join([str(BUILD_DIR)] * len(ROLES))

    config.stash[_RESOLVED_KEY] = resolved


@pytest.fixture(scope="session")
def board_map(request: pytest.FixtureRequest) -> dict:
    """role -> port, as resolved at configuration time."""
    return request.config.stash[_RESOLVED_KEY]


@pytest.fixture()
def responder(dut):
    """dut[0]. Named so tests read as roles rather than as indices."""
    return dut[0]


@pytest.fixture()
def initiator(dut):
    """dut[1]."""
    return dut[1]
