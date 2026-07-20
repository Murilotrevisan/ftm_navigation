"""Flash and autonomously validate both ESP32-C3 FTM boards."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys

try:
    from .console import ConsoleTimeout
    from .two_board import TwoBoardBench
except ImportError:  # direct script execution
    from console import ConsoleTimeout
    from two_board import TwoBoardBench


SUMMARY_RE = re.compile(
    r"FTM session ends with\s+(?P<valid>\d+)\s+valid readings out of\s+"
    r"(?P<total>\d+)(?:\s+readings received)?,\s+Avg raw RTT:\s+"
    r"(?P<rtt>-?\d+(?:\.\d+)?)\s+nSec,\s+"
    r"Avg RSSI:\s+(?P<rssi>-?\d+)"
)
DISTANCE_RE = re.compile(
    r"Estimated RTT\s+-\s+\d+\s+nSec,\s+Estimated Distance\s+-\s+"
    r"(?P<metres>\d+)\.(?P<centimetres>\d{2})\s+meters"
)
FRAME_RE = re.compile(
    r"ftm_station:\s*\|\s*\d+\s*\|\s*(?P<rtt>\d+|INVALID)\s*\|"
)
MAC_RE = re.compile(r"(?i)MAC(?: address)?:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})")


@dataclass
class Session:
    valid: int
    total: int
    rtt_raw_ns: float
    rssi_dbm: int
    distance_m: float | None = None

    @property
    def valid_ratio(self) -> float:
        return self.valid / self.total if self.total else 0.0


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    sessions: tuple[Session, ...]
    frame_rtt_ns: tuple[float, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Fingerprint:
    mac: str
    peer_mac: str
    role: str
    reference_distance_m: float
    sample_count: int
    mean_rtt_raw_ns: float
    stdev_rtt_raw_ns: float
    created_utc: str


def parse_transcript(text: str) -> tuple[list[Session], list[float]]:
    """Parse complete records and silently ignore unrelated or partial lines."""
    sessions: list[Session] = []
    pending_distance = 0
    frame_rtt_ns: list[float] = []

    for line in text.splitlines():
        summary = SUMMARY_RE.search(line)
        if summary:
            sessions.append(
                Session(
                    valid=int(summary.group("valid")),
                    total=int(summary.group("total")),
                    rtt_raw_ns=float(summary.group("rtt")),
                    rssi_dbm=int(summary.group("rssi")),
                )
            )
            continue

        distance = DISTANCE_RE.search(line)
        if distance:
            while pending_distance < len(sessions):
                session = sessions[pending_distance]
                pending_distance += 1
                if session.distance_m is None:
                    session.distance_m = int(distance.group("metres")) + (
                        int(distance.group("centimetres")) / 100.0
                    )
                    break
            continue

        frame = FRAME_RE.search(line)
        if frame and frame.group("rtt") != "INVALID":
            # wifi_ftm_report_entry_t.rtt is reported in picoseconds by ESP-IDF.
            frame_rtt_ns.append(int(frame.group("rtt")) / 1000.0)

    return sessions, frame_rtt_ns


def evaluate_transcript(
    text: str,
    *,
    expected_sessions: int,
    minimum_valid_ratio: float = 0.8,
    minimum_rssi_dbm: int = -100,
    maximum_rssi_dbm: int = -1,
) -> ValidationResult:
    sessions, frame_rtt_ns = parse_transcript(text)
    errors: list[str] = []
    warnings: list[str] = []

    if len(sessions) != expected_sessions:
        errors.append(
            f"expected {expected_sessions} successful sessions, parsed {len(sessions)}"
        )
    if "FTM procedure failed!" in text:
        errors.append("firmware reported an FTM session failure")
    if "FTM procedure timed out!" in text:
        errors.append("firmware reported an FTM session timeout")

    for index, session in enumerate(sessions, start=1):
        if session.total <= 0 or session.valid_ratio < minimum_valid_ratio:
            errors.append(
                f"session {index}: valid ratio {session.valid}/{session.total} "
                f"({session.valid_ratio:.3f}) is below {minimum_valid_ratio:.3f}"
            )
        if not minimum_rssi_dbm <= session.rssi_dbm <= maximum_rssi_dbm:
            errors.append(
                f"session {index}: RSSI {session.rssi_dbm} dBm is outside the "
                f"plausible range {minimum_rssi_dbm}..{maximum_rssi_dbm} dBm"
            )

    if sessions and not any(session.rtt_raw_ns > 0 for session in sessions):
        errors.append("all sessions reported zero raw RTT")

    measured_distances = [
        session.distance_m for session in sessions if session.distance_m is not None
    ]
    if sessions and len(measured_distances) != len(sessions):
        errors.append("one or more successful sessions had no distance result")
    elif measured_distances and all(distance == 0.0 for distance in measured_distances):
        errors.append(
            "boards too close? all reported distances are 0.00 m (FTM clamp condition)"
        )

    if sessions and not frame_rtt_ns:
        warnings.append("no per-frame RTT rows were parsed; check detailed report logging")

    return ValidationResult(
        passed=not errors,
        sessions=tuple(sessions),
        frame_rtt_ns=tuple(frame_rtt_ns),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def read_mac(port: str) -> str:
    command = [sys.executable, "-m", "esptool", "--port", port, "read_mac"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(f"{port}: esptool read_mac failed:\n{output.strip()}")
    match = MAC_RE.search(output)
    if not match:
        raise RuntimeError(f"{port}: could not parse MAC from esptool output:\n{output.strip()}")
    return match.group(1).lower()


def flash_board(port: str, *, project_dir: Path) -> None:
    wrapper = Path(__file__).with_name("idf.ps1")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(wrapper),
        "-C",
        str(project_dir),
        "-B",
        str(project_dir / "build_host"),
        "-p",
        port,
        "flash",
    ]
    completed = subprocess.run(command)
    if completed.returncode != 0:
        raise RuntimeError(f"{port}: firmware flash failed with exit {completed.returncode}")


def fingerprint_path(directory: Path, mac: str) -> Path:
    return directory / f"{mac.replace(':', '-')}.json"


def make_fingerprint(
    *,
    mac: str,
    peer_mac: str,
    role: str,
    frame_rtt_ns: tuple[float, ...],
) -> Fingerprint:
    if len(frame_rtt_ns) < 200:
        raise ValueError(
            f"fingerprint needs at least 200 frame samples, got {len(frame_rtt_ns)}"
        )
    return Fingerprint(
        mac=mac,
        peer_mac=peer_mac,
        role=role,
        reference_distance_m=1.0,
        sample_count=len(frame_rtt_ns),
        mean_rtt_raw_ns=statistics.fmean(frame_rtt_ns),
        stdev_rtt_raw_ns=statistics.stdev(frame_rtt_ns),
        created_utc=datetime.now(timezone.utc).isoformat(),
    )


def update_or_compare_fingerprint(
    fingerprint: Fingerprint,
    *,
    directory: Path,
) -> str:
    path = fingerprint_path(directory, fingerprint.mac)
    if not path.exists():
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(fingerprint), indent=2) + "\n", encoding="utf-8")
        return f"recorded baseline fingerprint {path}"

    baseline = Fingerprint(**json.loads(path.read_text(encoding="utf-8")))
    combined_standard_error = math.sqrt(
        (baseline.stdev_rtt_raw_ns**2 / baseline.sample_count)
        + (fingerprint.stdev_rtt_raw_ns**2 / fingerprint.sample_count)
    )
    threshold_ns = max(1.0, 3.0 * combined_standard_error)
    delta_ns = abs(fingerprint.mean_rtt_raw_ns - baseline.mean_rtt_raw_ns)
    if delta_ns > threshold_ns:
        return (
            f"WARNING: {fingerprint.mac} mean RTT diverged by {delta_ns:.3f} ns "
            f"(warning threshold {threshold_ns:.3f} ns)"
        )
    return (
        f"fingerprint stable for {fingerprint.mac}: mean delta {delta_ns:.3f} ns "
        f"(warning threshold {threshold_ns:.3f} ns)"
    )


def _print_result(port: str, result: ValidationResult) -> None:
    state = "PASS" if result.passed else "FAIL"
    print(
        f"{state} {port}: {len(result.sessions)} sessions, "
        f"{len(result.frame_rtt_ns)} per-frame RTT samples"
    )
    for error in result.errors:
        print(f"  ERROR: {error}")
    for warning in result.warnings:
        print(f"  WARNING: {warning}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-port", default="COM3")
    parser.add_argument("--second-port", default="COM4")
    parser.add_argument("--sessions", type=int, default=8)
    parser.add_argument("--skip-flash", action="store_true")
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument(
        "--fingerprint-dir",
        type=Path,
        default=Path(__file__).with_name("fingerprints"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.sessions < 1:
        print("FAIL: --sessions must be at least 1", file=sys.stderr)
        return 2

    project_dir = Path(__file__).resolve().parents[1] / "bench_firmware"
    ports = (args.first_port, args.second_port)
    try:
        macs = {port: read_mac(port) for port in ports}
        for port in ports:
            print(f"{port}: {macs[port]}")
        if not args.skip_flash:
            for port in ports:
                print(f"Flashing {port}...")
                flash_board(port, project_dir=project_dir)

        with TwoBoardBench(*ports, log_dir=args.log_dir) as bench:
            run = bench.run_direction(
                responder_port=ports[0],
                initiator_port=ports[1],
                sessions=args.sessions,
                ssid="FTM_BENCH",
            )

        if args.log_dir:
            args.log_dir.mkdir(parents=True, exist_ok=True)
            path = args.log_dir / f"{run.initiator_port}-initiator.log"
            path.write_text(run.transcript, encoding="utf-8")
        result = evaluate_transcript(
            run.transcript,
            expected_sessions=args.sessions,
        )
        _print_result(f"{ports[0]} responder + {ports[1]} initiator", result)
        if result.passed:
            for port, peer_port, role in (
                (ports[0], ports[1], "responder"),
                (ports[1], ports[0], "initiator"),
            ):
                try:
                    fingerprint = make_fingerprint(
                        mac=macs[port],
                        peer_mac=macs[peer_port],
                        role=role,
                        frame_rtt_ns=result.frame_rtt_ns,
                    )
                    print(
                        "  "
                        + update_or_compare_fingerprint(
                            fingerprint,
                            directory=args.fingerprint_dir,
                        )
                    )
                except ValueError as exc:
                    print(f"  WARNING: {exc}")

        print(
            "PASS: both boards validated in their assigned roles"
            if result.passed
            else "FAIL: board validation failed"
        )
        return 0 if result.passed else 1
    except (ConsoleTimeout, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
