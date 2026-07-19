"""Serial console driver that keeps one board open for an entire session."""

from __future__ import annotations

import argparse
import codecs
from pathlib import Path
import sys
import threading
import time
from typing import Iterable


class ConsoleTimeout(TimeoutError):
    """Raised when expected console output does not arrive before a deadline."""


class LineSplitter:
    """Split arbitrary byte chunks into decoded lines without losing fragments."""

    def __init__(self) -> None:
        self._pending = bytearray()

    def feed(self, data: bytes) -> list[str]:
        self._pending.extend(data)
        lines: list[str] = []
        while True:
            newline = self._pending.find(b"\n")
            if newline < 0:
                return lines
            raw = bytes(self._pending[:newline])
            del self._pending[: newline + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            lines.append(raw.decode("utf-8", errors="replace"))

    def flush(self) -> str | None:
        if not self._pending:
            return None
        raw = bytes(self._pending)
        self._pending.clear()
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        return raw.decode("utf-8", errors="replace")


class SerialConsole:
    """Own a serial port and continuously retain its decoded output."""

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        log_path: Path | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.log_path = log_path
        self._serial = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._text = ""
        self._reader_error: BaseException | None = None
        self._log = None

    def __enter__(self) -> "SerialConsole":
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "pyserial is required; run this tool from the project venv"
            ) from exc

        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = self.log_path.open("w", encoding="utf-8", newline="")
        self._serial = serial.Serial(
            self.port,
            self.baudrate,
            timeout=0.1,
            write_timeout=2.0,
        )
        # USB-Serial-JTAG uses these lines for automatic boot/reset control.
        # PySerial's asserted defaults can otherwise leave an ESP32-C3 silent.
        self._serial.dtr = False
        self._serial.rts = False
        self._reader = threading.Thread(
            target=self._read_forever,
            name=f"serial-{self.port}",
            daemon=True,
        )
        self._reader.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._reader is not None:
            self._reader.join(timeout=2.0)
        if self._serial is not None:
            self._serial.close()
        if self._log is not None:
            self._log.close()

    def _read_forever(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while not self._stop.is_set():
                assert self._serial is not None
                data = self._serial.read(self._serial.in_waiting or 1)
                if data:
                    self._append(decoder.decode(data))
            tail = decoder.decode(b"", final=True)
            if tail:
                self._append(tail)
        except BaseException as exc:  # surfaced to the caller by wait_for_any
            with self._condition:
                self._reader_error = exc
                self._condition.notify_all()

    def _append(self, text: str) -> None:
        with self._condition:
            self._text += text
            if self._log is not None:
                self._log.write(text)
                self._log.flush()
            self._condition.notify_all()

    def mark(self) -> int:
        with self._condition:
            return len(self._text)

    def text_since(self, mark: int = 0) -> str:
        with self._condition:
            return self._text[mark:]

    def send(self, command: str) -> None:
        if self._serial is None:
            raise RuntimeError(f"{self.port}: console is not open")
        self._serial.write((command.rstrip("\r\n") + "\r\n").encode("utf-8"))
        self._serial.flush()

    def wait_for(
        self,
        pattern: str,
        *,
        timeout: float,
        since: int = 0,
    ) -> str:
        matched, text = self.wait_for_any((pattern,), timeout=timeout, since=since)
        assert matched == pattern
        return text

    def wait_for_any(
        self,
        patterns: Iterable[str],
        *,
        timeout: float,
        since: int = 0,
    ) -> tuple[str, str]:
        choices = tuple(patterns)
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                text = self._text[since:]
                for pattern in choices:
                    if pattern in text:
                        return pattern, text
                if self._reader_error is not None:
                    raise RuntimeError(
                        f"{self.port}: serial reader stopped: {self._reader_error}"
                    ) from self._reader_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    wanted = ", ".join(repr(item) for item in choices)
                    raise ConsoleTimeout(
                        f"{self.port}: timed out after {timeout:.1f}s waiting for {wanted}"
                    )
                self._condition.wait(remaining)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Windows serial port, e.g. COM3")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--log", type=Path, help="raw UTF-8 transcript path")
    parser.add_argument("--prompt-timeout", type=float, default=15.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    with SerialConsole(args.port, baudrate=args.baudrate, log_path=args.log) as board:
        board.wait_for("ftm>", timeout=args.prompt_timeout)
        print(f"{args.port}: ready; enter commands, Ctrl-Z then Enter to quit")
        for command in sys.stdin:
            mark = board.mark()
            board.send(command)
            try:
                print(board.wait_for("ftm>", timeout=30.0, since=mark), end="")
            except ConsoleTimeout as exc:
                print(exc, file=sys.stderr)
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
