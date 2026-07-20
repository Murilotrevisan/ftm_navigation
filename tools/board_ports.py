"""Resolve boards by MAC address, never by port number.

Ports re-enumerate unpredictably (docs/CONTAINER.md §6), so every consumer --
``tools/dev.ps1 flash`` and ``tests/e2e/conftest.py`` alike -- goes through
this module rather than hardcoding COM3/COM4. The role -> MAC mapping lives in
``tools/boards.json``.

Runs on the Windows host inside the project venv. Needs ``pyserial`` and
``esptool``; both are pinned in ``requirements-test.txt``.

Reading a MAC opens the serial port, which RESETS the board. That is harmless
before flashing or before a test starts, but it is the reason discovery
happens once up front rather than per step: a responder's AP state would not
survive a mid-test port open.

CLI:
    python tools/board_ports.py --list            # every attached ESP board
    python tools/board_ports.py --role responder  # print that role's port
    python tools/board_ports.py --require-all     # exit 2 unless all roles present
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Espressif USB-Serial-JTAG. These boards expose only the built-in bridge --
# VID 303A / PID 1001 (docs/HARDWARE_FINDINGS.md §1).
ESPRESSIF_VID = 0x303A

_MAC_RE = re.compile(r"MAC:\s*((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BOARDS_JSON = _REPO_ROOT / "tools" / "boards.json"


class BoardNotFound(RuntimeError):
    """A role's board is not attached. Deliberately loud, never a skip."""


def load_roles() -> Dict[str, str]:
    """role -> normalised MAC, from tools/boards.json."""
    # utf-8-sig, not utf-8: PowerShell's Set-Content writes a BOM by default,
    # and a BOM makes json.loads fail with a message that says nothing about
    # which file is at fault. Learned the hard way in Phase 0.
    data = json.loads(_BOARDS_JSON.read_text(encoding="utf-8-sig"))
    return {role: spec["mac"].lower() for role, spec in data["roles"].items()}


def esp_ports() -> List[str]:
    """Every attached Espressif USB-Serial-JTAG port, e.g. ['COM3', 'COM4']."""
    from serial.tools import list_ports  # imported lazily: venv-only dependency

    return sorted(p.device for p in list_ports.comports() if p.vid == ESPRESSIF_VID)


def read_mac(port: str, timeout: float = 30.0) -> Optional[str]:
    """Base MAC of the chip on `port`, or None if it could not be read.

    No firmware is required -- this talks to the ROM loader.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "esptool", "--port", port, "read_mac"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    matches = _MAC_RE.findall(proc.stdout)
    if matches:
        return matches[-1].lower()

    # Say WHY, on stderr. A silent None here surfaces later as the misleading
    # "board not attached" when the board is in fact attached but busy.
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    reason = tail[-1] if tail else f"esptool exited {proc.returncode} with no output"
    print(f"WARNING: could not read a MAC from {port}: {reason}", file=sys.stderr)
    return None


def discover() -> Dict[str, str]:
    """MAC -> port for every attached board that answers."""
    found: Dict[str, str] = {}
    for port in esp_ports():
        try:
            mac = read_mac(port)
        except subprocess.TimeoutExpired:
            mac = None
        if mac:
            found[mac] = port
    return found


def resolve(roles: Optional[List[str]] = None) -> Dict[str, str]:
    """role -> port for the requested roles.

    Raises BoardNotFound listing exactly which role and MAC is missing, and
    what *was* attached. A missing board must produce a clear failure, never a
    silent skip and never a hang.
    """
    wanted = load_roles()
    if roles is not None:
        unknown = [r for r in roles if r not in wanted]
        if unknown:
            raise BoardNotFound(
                f"unknown role(s) {unknown}; tools/boards.json defines {sorted(wanted)}"
            )
        wanted = {r: wanted[r] for r in roles}

    attached = discover()
    resolved = {role: attached[mac] for role, mac in wanted.items() if mac in attached}

    missing = {role: mac for role, mac in wanted.items() if mac not in attached}
    if missing:
        detail = ", ".join(f"{role} (MAC {mac})" for role, mac in sorted(missing.items()))
        seen = ", ".join(f"{mac} on {port}" for mac, port in sorted(attached.items())) or "none"
        raise BoardNotFound(
            f"board not attached for: {detail}. "
            f"Espressif boards currently attached: {seen}. "
            f"Check the USB cable and that no other program holds the port."
        )
    return resolved


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list attached boards as JSON")
    group.add_argument("--role", help="print the port for this role")
    group.add_argument(
        "--require-all",
        action="store_true",
        help="print role->port JSON; exit 2 if any role is missing",
    )
    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps(discover(), indent=2))
        return 0

    try:
        if args.role:
            print(resolve([args.role])[args.role])
        else:
            print(json.dumps(resolve(), indent=2))
    except BoardNotFound as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
