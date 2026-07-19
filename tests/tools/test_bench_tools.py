from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_TOOLS = REPO_ROOT / "tools" / "bench"
sys.path.insert(0, str(BENCH_TOOLS))

from console import ConsoleTimeout, LineSplitter  # noqa: E402
from two_board import require_prompt  # noqa: E402
from validate_board import (  # noqa: E402
    evaluate_transcript,
    make_fingerprint,
    parse_transcript,
    update_or_compare_fingerprint,
)


FIXTURES = Path(__file__).with_name("fixtures") / "bench"
PASS_TRANSCRIPT = FIXTURES / "pass_capture" / "COM4-initiator.log"
CLAMP_TRANSCRIPT = FIXTURES / "clamp_capture" / "low_valid.txt"


def recorded(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_recorded_sessions_pass_decision_logic() -> None:
    result = evaluate_transcript(recorded(PASS_TRANSCRIPT), expected_sessions=8)

    assert result.passed
    assert len(result.sessions) == 8
    assert len(result.frame_rtt_ns) >= 200
    assert all(session.valid_ratio >= 0.8 for session in result.sessions)
    assert any(session.rtt_raw_ns > 0 for session in result.sessions)


def test_recorded_low_valid_ratio_fails() -> None:
    result = evaluate_transcript(recorded(CLAMP_TRANSCRIPT), expected_sessions=8)

    assert not result.passed
    assert min(session.valid_ratio for session in result.sessions) < 0.8
    assert any("valid ratio" in error for error in result.errors)


def test_recorded_zero_clamp_has_board_spacing_hint() -> None:
    result = evaluate_transcript(recorded(CLAMP_TRANSCRIPT), expected_sessions=8)

    assert not result.passed
    assert any("boards too close?" in error for error in result.errors)
    assert any("0.00 m" in error for error in result.errors)


def test_garbled_partial_serial_line_is_ignored_without_crash() -> None:
    source = recorded(PASS_TRANSCRIPT)
    damaged = source[: len(source) // 2] + "\ufffdpartial FTM sess"

    sessions, frame_rtt_ns = parse_transcript(damaged)

    assert sessions
    assert frame_rtt_ns


def test_missing_sessions_fail_clearly() -> None:
    result = evaluate_transcript("garbled only\ufffd", expected_sessions=2)

    assert not result.passed
    assert result.errors == ("expected 2 successful sessions, parsed 0",)


def test_prompt_timeout_is_clear_and_bounded() -> None:
    class NeverPrompt:
        def wait_for(self, pattern: str, *, timeout: float) -> str:
            raise ConsoleTimeout("simulated bounded wait")

    with pytest.raises(ConsoleTimeout, match="board never reached.*ftm>.*3.0s"):
        require_prompt(NeverPrompt(), port="COM9", timeout=3.0)


def test_line_splitter_handles_fragments_and_crlf() -> None:
    splitter = LineSplitter()

    assert splitter.feed(b"first\r") == []
    assert splitter.feed(b"\nsecond\nthird") == ["first", "second"]
    assert splitter.flush() == "third"
    assert splitter.flush() is None


def test_line_splitter_handles_split_utf8_and_replaces_invalid_bytes() -> None:
    splitter = LineSplitter()

    assert splitter.feed(b"caf\xc3") == []
    assert splitter.feed(b"\xa9\ninvalid:\xff\n") == ["caf\u00e9", "invalid:\ufffd"]


def test_fingerprint_requires_at_least_200_real_samples() -> None:
    with pytest.raises(ValueError, match="at least 200.*199"):
        make_fingerprint(
            mac="00:11:22:33:44:55",
            peer_mac="00:11:22:33:44:66",
            role="initiator",
            frame_rtt_ns=tuple(float(index) for index in range(199)),
        )


def test_fingerprint_is_recorded_then_compared(tmp_path: Path) -> None:
    samples = tuple(10.0 + ((index % 3) * 0.1) for index in range(200))
    baseline = make_fingerprint(
        mac="00:11:22:33:44:55",
        peer_mac="00:11:22:33:44:66",
        role="initiator",
        frame_rtt_ns=samples,
    )

    assert "recorded baseline fingerprint" in update_or_compare_fingerprint(
        baseline, directory=tmp_path
    )
    assert "fingerprint stable" in update_or_compare_fingerprint(
        baseline, directory=tmp_path
    )


def test_fingerprint_warns_on_significant_divergence(tmp_path: Path) -> None:
    samples = tuple(10.0 + ((index % 3) * 0.1) for index in range(200))
    baseline = make_fingerprint(
        mac="00:11:22:33:44:55",
        peer_mac="00:11:22:33:44:66",
        role="responder",
        frame_rtt_ns=samples,
    )
    update_or_compare_fingerprint(baseline, directory=tmp_path)
    divergent = replace(baseline, mean_rtt_raw_ns=baseline.mean_rtt_raw_ns + 5.0)

    message = update_or_compare_fingerprint(divergent, directory=tmp_path)

    assert message.startswith("WARNING:")
    assert "diverged" in message
