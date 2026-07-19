"""L3 E2E smoke test -- both boards boot the known-good app and pass on-target.

HOW TO RUN (Windows host, project venv):

    .\\tools\\dev.ps1 target-build     # container: build the app first
    .\\tools\\dev.ps1 e2e              # host venv: flash both boards and assert

Duration: ~40 s. Most of that is flashing two boards.

This is the reference E2E test every later one copies. What makes it a real
E2E test rather than a smoke-shaped placebo:

* it asserts on **both** DUTs, not just the first one to answer;
* it fails loudly when a board is missing (see conftest.py) instead of
  skipping;
* it asserts the on-target Unity result, not merely that some bytes arrived.

Note what it deliberately does NOT do: assert a distance. There is nothing
measuring distance yet, and per docs/HARDWARE_FINDINGS.md §8 and §10 such an
assertion needs a tolerance band over >= 60 samples -- a single reading would
flake against real drift. That test belongs to the phase that produces the
measurements.
"""

from __future__ import annotations

import pytest

BOOT_MARKER = "FTM_TARGET_SMOKE_BOOT"
PASS_MARKER = "FTM_TARGET_SMOKE_PASS"

pytestmark = pytest.mark.e2e


def test_both_boards_boot_the_app(dut):
    """Every DUT reaches the boot marker."""
    assert len(dut) == 2, f"expected 2 DUTs, got {len(dut)}"

    for index, board in enumerate(dut):
        board.expect_exact(BOOT_MARKER, timeout=30)


def test_both_boards_pass_their_on_target_tests(dut):
    """Every DUT reports a Unity run with zero failures.

    Asserting on the PASS marker rather than on 'no FAIL appeared' matters:
    absence of output is what a hung or unflashed board also looks like.
    """
    assert len(dut) == 2, f"expected 2 DUTs, got {len(dut)}"

    for board in dut:
        board.expect_exact(PASS_MARKER, timeout=30)
        board.expect_exact("failures=0", timeout=5)


def test_roles_are_bound_to_the_expected_boards(board_map, dut):
    """The role -> board binding is by MAC and it is the right way round.

    If responder and initiator ever swap, every distance measurement still
    "works" while meaning something different -- the kind of failure that is
    expensive to find later.
    """
    import json
    from pathlib import Path

    roles = json.loads(
        (Path(__file__).resolve().parents[2] / "tools" / "boards.json").read_text(
            encoding="utf-8"
        )
    )["roles"]

    assert set(board_map) == {"responder", "initiator"}
    assert board_map["responder"] != board_map["initiator"], "both roles on one port"

    # dut[0] is the responder by construction (conftest.ROLES); confirm the
    # serial port each DUT actually holds matches that role's resolved port.
    assert dut[0].serial.port == board_map["responder"]
    assert dut[1].serial.port == board_map["initiator"]

    # And that the resolved ports really carry the MACs we asked for: the
    # boot log prints the base MAC when Wi-Fi starts in STA mode.
    dut[0].expect_exact(roles["responder"]["mac"], timeout=30)
    dut[1].expect_exact(roles["initiator"]["mac"], timeout=30)
