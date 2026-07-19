"""L4 -- tests for host Python tooling. Plain pytest, no hardware.

HOW TO RUN (Windows host, project venv):

    .\\tools\\dev.ps1 tools-test

Duration: < 2 s.

This level exists for tools/ code -- the calibrator, the codegen and the log
analysis that later phases add. Phase 0's only host tool is
tools/board_ports.py, so that is what is covered here, without touching a
board: role resolution is tested against an injected discovery result rather
than against real hardware, so the failure paths (missing board, unknown role)
are deterministic instead of requiring someone to unplug a cable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import board_ports  # noqa: E402

RESPONDER_MAC = "14:63:93:8d:98:74"
INITIATOR_MAC = "14:63:93:8d:96:e4"


def test_boards_json_matches_the_normative_document():
    """tools/boards.json must agree with docs/CONTAINER.md §6.

    The document is normative; this file is the machine-readable copy. If they
    drift, `flash <role>` silently targets the wrong board.
    """
    roles = board_ports.load_roles()
    assert roles == {"responder": RESPONDER_MAC, "initiator": INITIATOR_MAC}

    container_md = (REPO_ROOT / "docs" / "CONTAINER.md").read_text(encoding="utf-8")
    for mac in roles.values():
        assert mac in container_md, f"{mac} is not in docs/CONTAINER.md"


def test_resolve_maps_roles_to_ports(monkeypatch):
    monkeypatch.setattr(
        board_ports, "discover", lambda: {RESPONDER_MAC: "COM3", INITIATOR_MAC: "COM4"}
    )
    assert board_ports.resolve() == {"responder": "COM3", "initiator": "COM4"}


def test_resolve_follows_the_mac_not_the_port_number(monkeypatch):
    """Ports re-enumerate. The role must follow the MAC wherever it lands."""
    monkeypatch.setattr(
        board_ports, "discover", lambda: {RESPONDER_MAC: "COM11", INITIATOR_MAC: "COM7"}
    )
    assert board_ports.resolve() == {"responder": "COM11", "initiator": "COM7"}


def test_missing_board_raises_and_names_the_role_and_mac(monkeypatch):
    """A missing board must fail loudly -- never skip, never default."""
    monkeypatch.setattr(board_ports, "discover", lambda: {RESPONDER_MAC: "COM3"})

    with pytest.raises(board_ports.BoardNotFound) as excinfo:
        board_ports.resolve()

    message = str(excinfo.value)
    assert "initiator" in message
    assert INITIATOR_MAC in message
    # The diagnostic must also say what WAS attached, or the operator cannot
    # tell "unplugged" from "wrong board".
    assert RESPONDER_MAC in message and "COM3" in message


def test_no_boards_at_all_raises(monkeypatch):
    monkeypatch.setattr(board_ports, "discover", lambda: {})

    with pytest.raises(board_ports.BoardNotFound) as excinfo:
        board_ports.resolve()
    assert "none" in str(excinfo.value)


def test_unknown_role_is_rejected(monkeypatch):
    monkeypatch.setattr(board_ports, "discover", lambda: {RESPONDER_MAC: "COM3"})

    with pytest.raises(board_ports.BoardNotFound) as excinfo:
        board_ports.resolve(["anchor_7"])
    assert "unknown role" in str(excinfo.value)


def test_mac_matching_is_case_insensitive(monkeypatch):
    """esptool prints lowercase; a hand-edited boards.json may not."""
    monkeypatch.setattr(
        board_ports, "discover", lambda: {RESPONDER_MAC.upper().lower(): "COM3"}
    )
    assert board_ports.resolve(["responder"]) == {"responder": "COM3"}


def test_read_mac_parses_esptool_output(monkeypatch):
    """esptool prints MAC twice (ROM, then stub); the last one is the answer."""

    class FakeProc:
        stdout = (
            "esptool.py v4.12.0\nMAC: 14:63:93:8D:98:74\n"
            "Uploading stub...\nMAC: 14:63:93:8d:98:74\n"
        )
        stderr = ""
        returncode = 0

    monkeypatch.setattr(board_ports.subprocess, "run", lambda *a, **k: FakeProc())
    assert board_ports.read_mac("COM3") == RESPONDER_MAC


def test_read_mac_returns_none_and_says_why(monkeypatch, capsys):
    """A board that does not answer must produce a reason, not a silent None.

    A silent None resurfaces later as "board not attached" for a board that is
    very much attached -- just busy.
    """

    class FakeProc:
        stdout = "esptool.py v4.12.0\n"
        stderr = "A fatal error occurred: Failed to connect to ESP32-C3\n"
        returncode = 2

    monkeypatch.setattr(board_ports.subprocess, "run", lambda *a, **k: FakeProc())

    assert board_ports.read_mac("COM9") is None
    assert "COM9" in capsys.readouterr().err


def test_boards_json_is_valid_json_with_the_expected_shape():
    data = json.loads((REPO_ROOT / "tools" / "boards.json").read_text(encoding="utf-8"))
    for role, spec in data["roles"].items():
        assert "mac" in spec, f"role {role} has no mac"
        assert len(spec["mac"].split(":")) == 6, f"role {role} has a malformed mac"
