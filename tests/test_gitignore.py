from __future__ import annotations

import subprocess

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "papers/example.pdf",
        "papers/nested/example.pdf",
        "experiments/run-1/artifact.json",
        "logs/lab.log",
        ".hubble_tension_state/runtime_state.json",
        ".hubble_tension_solvers/src/class/Makefile",
        ".venv/bin/python",
    ],
)
def test_local_artifacts_are_git_ignored(path: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], check=False)

    assert result.returncode == 0


def test_paper_bibliography_markdown_is_not_ignored() -> None:
    result = subprocess.run(["git", "check-ignore", "-q", "papers/README.md"], check=False)

    assert result.returncode == 1


def test_docdex_run_tests_config_is_not_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".docdex/run-tests.json"],
        check=False,
    )

    assert result.returncode == 1
