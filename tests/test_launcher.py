from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_root_launcher_runs_without_prompts(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    env["HT_LAB_STATE_DIR"] = str(tmp_path)
    env["HT_LAB_DRY_RUN"] = "1"
    env["HT_LAB_DISABLE_AUTONOMOUS_LOOP"] = "1"
    result = subprocess.run(
        ["./hubble_tension.sh"],
        check=True,
        capture_output=True,
        env=env,
        input=b"",
        timeout=10,
    )

    output = result.stdout.decode()
    expected_prefix = (
        "[HT-LAB attempt=attempt-000001 branch=branch-000000 test=test-000000 stage=start]"
    )
    assert expected_prefix in output
    assert "stage=dry_run" in output
    assert (tmp_path / "runtime_state.json").exists()
    assert result.stderr == b""


def test_root_launcher_prefers_repo_venv_when_python_unset(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHON", None)
    env["HT_LAB_STATE_DIR"] = str(tmp_path)
    env["HT_LAB_DRY_RUN"] = "1"
    env["HT_LAB_DISABLE_AUTONOMOUS_LOOP"] = "1"
    result = subprocess.run(
        ["./hubble_tension.sh"],
        check=True,
        capture_output=True,
        env=env,
        input=b"",
        timeout=10,
    )

    output = result.stdout.decode()
    assert "stage=dry_run" in output
    assert (tmp_path / "runtime_state.json").exists()
    assert result.stderr == b""


def test_root_launcher_starts_default_autonomous_stub_loop(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    env["HT_LAB_STATE_DIR"] = str(tmp_path)
    env["HT_LAB_DRY_RUN"] = "1"
    env["HT_LAB_CORPUS_SOURCE"] = "mock"
    env["HT_LAB_HEAD_AGENT"] = "stub"
    result = subprocess.run(
        ["./hubble_tension.sh"],
        check=True,
        capture_output=True,
        env=env,
        input=b"",
        timeout=10,
    )

    output = result.stdout.decode()
    assert "stage=observe" in output
    assert "stage=restart" in output
    assert "stage=phase5" in output
    assert (
        tmp_path / "runs" / "run-000001" / "generated_models" / "stub_zoroto_model.py"
    ).exists()
    assert result.stderr == b""
