# Recorded bench transcripts

These files are raw recordings from the physical ESP32-C3 boards on 2026-07-19.
They are not synthesised fixtures. Their serial CR/CRLF terminators were
normalized to LF and prompt-only trailing spaces were trimmed for stable text
fixtures; measurement and diagnostic content is unchanged.

- `pass_capture/`: COM3 (`14:63:93:8d:98:74`) responder and COM4
  (`14:63:93:8d:96:e4`) initiator, boards in the fixed 1.00 m fixture, eight
  sessions. Captured by `validate_board.py --skip-flash --sessions 8`.
- `clamp_capture/low_valid.txt`: the same physical placement and roles, eight
  sessions after setting the real responder T1 offset to `+450 cm`. Captured by
  `two_board.py --sessions 8 --responder-offset 450`. It contains low-valid
  successful reports and explicit firmware failures.
- `clamp_capture/initiator.txt`: four `+600 cm` sessions, all explicit firmware
  failures. It is retained as the worst end of the same real clamp sweep.

`COM4-initiator.log` is the bounded transcript consumed by the passing-decision
test. The clamp tests consume the bounded `initiator.txt` recording.
