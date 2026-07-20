"""Regression tests for the Phase 0 runner / Phase 1 project layout."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_SH = REPO_ROOT / "tools" / "dev.sh"


def test_container_build_targets_the_moved_bench_firmware() -> None:
    script = DEV_SH.read_text(encoding="utf-8")
    match = re.search(
        r'^FIRMWARE_DIR="\$\{REPO_ROOT\}/([^"]+)"$', script, re.MULTILINE
    )

    assert match, "dev.sh must declare the firmware project relative to REPO_ROOT"
    project = REPO_ROOT / match.group(1)
    assert project == REPO_ROOT / "tools" / "bench_firmware"
    assert (project / "CMakeLists.txt").is_file()

    build_function = script.split("cmd_build() {", 1)[1].split("\n}", 1)[0]
    assert 'cd "${FIRMWARE_DIR}"' in build_function
