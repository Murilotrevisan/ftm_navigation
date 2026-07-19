"""Hold two FTM consoles open while driving responder/initiator sessions."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
import time

try:
    from .console import ConsoleTimeout, LineSplitter, SerialConsole
except ImportError:  # direct script execution
    from console import ConsoleTimeout, LineSplitter, SerialConsole


SESSION_TERMINATORS = (
    " meters",
    "FTM procedure failed!",
    "FTM procedure timed out!",
    "Failed to start FTM session",
    "No matching AP found",
)


@dataclass(frozen=True)
class DirectionRun:
    responder_port: str
    initiator_port: str
    ssid: str
    transcript: str
    elapsed_s: float


class TwoBoardBench:
    def __init__(
        self,
        first_port: str,
        second_port: str,
        *,
        log_dir: Path | None = None,
        prompt_timeout: float = 15.0,
    ) -> None:
        self.first_port = first_port
        self.second_port = second_port
        self.log_dir = log_dir
        self.prompt_timeout = prompt_timeout
        self._stack: ExitStack | None = None
        self._boards: dict[str, SerialConsole] = {}

    def __enter__(self) -> "TwoBoardBench":
        self._stack = ExitStack()
        try:
            for port in (self.first_port, self.second_port):
                log_path = self.log_dir / f"{port}.log" if self.log_dir else None
                self._boards[port] = self._stack.enter_context(
                    SerialConsole(port, log_path=log_path)
                )
            for port, board in self._boards.items():
                require_prompt(board, port=port, timeout=self.prompt_timeout)
        except BaseException:
            self._stack.close()
            self._stack = None
            self._boards.clear()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._stack is not None:
            self._stack.close()
        self._stack = None
        self._boards.clear()

    def run_direction(
        self,
        *,
        responder_port: str,
        initiator_port: str,
        sessions: int,
        ssid: str,
        session_timeout: float = 12.0,
        responder_offset_cm: int | None = None,
    ) -> DirectionRun:
        if sessions < 1:
            raise ValueError("sessions must be at least 1")
        responder = self._boards[responder_port]
        initiator = self._boards[initiator_port]
        started = time.monotonic()

        ap_mark = responder.mark()
        responder.send(f"ap {ssid}")
        responder.wait_for("Starting SoftAP with FTM Responder support", timeout=5.0, since=ap_mark)
        responder.wait_for("ftm>", timeout=5.0, since=ap_mark)

        if responder_offset_cm is not None:
            offset_mark = responder.mark()
            responder.send(f"ftm -R --offset={responder_offset_cm}")
            responder.wait_for("ftm>", timeout=5.0, since=offset_mark)

        run_mark = initiator.mark()
        for _ in range(sessions):
            session_mark = initiator.mark()
            initiator.send(f"ftm -I -s {ssid}")
            initiator.wait_for_any(
                SESSION_TERMINATORS,
                timeout=session_timeout,
                since=session_mark,
            )
            # Let the line terminator and next prompt reach the reader before
            # taking a transcript snapshot or issuing the next command.
            time.sleep(0.1)

        return DirectionRun(
            responder_port=responder_port,
            initiator_port=initiator_port,
            ssid=ssid,
            transcript=initiator.text_since(run_mark),
            elapsed_s=time.monotonic() - started,
        )


def require_prompt(board: SerialConsole, *, port: str, timeout: float) -> None:
    try:
        board.wait_for("ftm>", timeout=timeout)
    except ConsoleTimeout as exc:
        raise ConsoleTimeout(
            f"{port}: board never reached the 'ftm>' prompt within {timeout:.1f}s; "
            "check that USB-Serial-JTAG console support is enabled"
        ) from exc


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responder-port", default="COM3")
    parser.add_argument("--initiator-port", default="COM4")
    parser.add_argument("--sessions", type=int, default=8)
    parser.add_argument("--ssid", default="FTM_BENCH")
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--transcript", type=Path, help="write the initiator run transcript")
    parser.add_argument("--responder-offset", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    with TwoBoardBench(
        args.responder_port,
        args.initiator_port,
        log_dir=args.log_dir,
    ) as bench:
        run = bench.run_direction(
            responder_port=args.responder_port,
            initiator_port=args.initiator_port,
            sessions=args.sessions,
            ssid=args.ssid,
            responder_offset_cm=args.responder_offset,
        )
    print(run.transcript, end="")
    if args.transcript:
        args.transcript.parent.mkdir(parents=True, exist_ok=True)
        args.transcript.write_text(run.transcript, encoding="utf-8")
    print(f"\nCompleted {args.sessions} sessions in {run.elapsed_s:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
