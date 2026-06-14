from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from hubble_tension import policy
from hubble_tension.runtime import LOCK_COLLISION_EXIT_CODE, RunResult, RuntimeSupervisor


def test_fresh_start_initializes_state_and_attempt_one(tmp_path: Path) -> None:
    output = StringIO()
    result = _run(tmp_path, output)
    state = _state(tmp_path)

    assert result.exit_code == 0
    assert result.status == "ready"
    assert state["active_attempt_id"] == "attempt-000001"
    assert state["active_branch_id"] == "branch-000000"
    assert state["active_test_id"] == "test-000000"
    assert state["checkpoint_count"] >= 2
    assert "[HT-LAB attempt=attempt-000001 branch=branch-000000 test=test-000000 stage=start]" in (
        output.getvalue()
    )
    assert (tmp_path / "runs" / "run-000001" / "lab.log").exists()
    db_path = tmp_path / "lab_state.sqlite3"
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        event_count = connection.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
        checkpoint_count = connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        runtime_status = connection.execute(
            "SELECT status FROM runtime_state WHERE state_key = 'default'"
        ).fetchone()[0]
        attempt_status = connection.execute(
            "SELECT status FROM attempts WHERE attempt_id = 'attempt-000001'"
        ).fetchone()[0]
        run_status = connection.execute(
            "SELECT status FROM runs WHERE run_id = 'run-000001'"
        ).fetchone()[0]
    assert event_count >= 2
    assert checkpoint_count >= 2
    assert runtime_status == "ready"
    assert attempt_status == "ready"
    assert run_status == "ready"


def test_interrupted_run_resumes_from_checkpoint(tmp_path: Path) -> None:
    _run(tmp_path)
    result = _run(tmp_path)
    state = _state(tmp_path)

    assert result.resumed
    assert result.status == "ready"
    assert state["resume_count"] == 1
    assert state["checkpoint_count"] >= 4


def test_process_lock_collision_reports_active_paths(tmp_path: Path) -> None:
    _run(tmp_path)
    state = _state(tmp_path)
    lock_payload = {
        "pid": os.getpid(),
        "run_id": state["active_run_id"],
        "state_path": str(tmp_path / "runtime_state.json"),
        "log_path": str(tmp_path / "runs" / "run-000001" / "lab.log"),
    }
    (tmp_path / "lock.json").write_text(json.dumps(lock_payload), encoding="utf-8")
    output = StringIO()

    result = _run(tmp_path, output)

    assert result.exit_code == LOCK_COLLISION_EXIT_CODE
    assert result.lock_collision
    assert "active_run_id=run-000001" in output.getvalue()
    assert f"state_path={tmp_path / 'runtime_state.json'}" in output.getvalue()
    assert f"log_path={tmp_path / 'runs' / 'run-000001' / 'lab.log'}" in output.getvalue()


def test_stale_process_lock_is_removed_and_run_recovers(tmp_path: Path) -> None:
    _run(tmp_path)
    stale_lock_payload = {
        "pid": 999_999_999,
        "run_id": "run-000001",
        "state_path": str(tmp_path / "runtime_state.json"),
        "log_path": str(tmp_path / "runs" / "run-000001" / "lab.log"),
    }
    (tmp_path / "lock.json").write_text(json.dumps(stale_lock_payload), encoding="utf-8")

    result = _run(tmp_path)

    assert result.exit_code == 0
    assert not result.lock_collision
    assert not (tmp_path / "lock.json").exists()


def test_budget_exhaustion_checkpoints_and_enters_configured_status(tmp_path: Path) -> None:
    result = _run(tmp_path, env={"HT_LAB_FORCE_BUDGET_EXHAUSTED": "1"})
    state = _state(tmp_path)
    latest = json.loads((tmp_path / "checkpoints" / "latest.json").read_text(encoding="utf-8"))

    assert result.status == "generation_budget_failed"
    assert state["status"] == "generation_budget_failed"
    assert state["budget_exhausted_reason"] == "forced_budget_exhausted"
    assert latest["reason"] == "budget_exhausted"


def test_token_budget_hard_stop_uses_configured_generation_status(tmp_path: Path) -> None:
    result = _run(tmp_path, env={"HT_LAB_GENERATED_TOKENS_ATTEMPT": "400001"})
    state = _state(tmp_path)

    assert result.status == "generation_budget_failed"
    assert state["budget_exhausted_reason"] == "generated_tokens_per_attempt"
    assert state["budget_usage"]["generated_tokens_per_attempt"] == 400001
    assert state["budget_limits"]["hard_generated_tokens_per_attempt"] == 400000


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({"HT_LAB_FAKE_CPU_PERCENT": "80.1"}, "cpu_percent"),
        ({"HT_LAB_FAKE_WALL_TIME_MINUTES": "45.1"}, "wall_time_minutes"),
        ({"HT_LAB_ACTIVE_SOLVER_JOBS": "2"}, "active_solver_jobs"),
        ({"HT_LAB_FAKE_STORAGE_GB": "20.1"}, "storage_gb"),
        ({"HT_LAB_ACTIVE_LAB_RUNS": "2"}, "active_lab_runs"),
    ],
)
def test_budget_pause_caps_checkpoint_without_prompt(
    tmp_path: Path,
    env: dict[str, str],
    reason: str,
) -> None:
    result = _run(tmp_path, env=env)
    state = _state(tmp_path)

    assert result.status == "budget_paused"
    assert state["status"] == "budget_paused"
    assert state["budget_exhausted_reason"] == reason
    assert state["budget_usage"]
    assert state["budget_limits"]


def test_stop_file_checkpoints_without_review_gate(tmp_path: Path) -> None:
    _run(tmp_path)
    stop_path = tmp_path / "runs" / "run-000001" / "STOP"
    stop_path.write_text("stop\n", encoding="utf-8")

    result = _run(tmp_path)
    state = _state(tmp_path)
    latest = json.loads((tmp_path / "checkpoints" / "latest.json").read_text(encoding="utf-8"))

    assert result.status == "stopped"
    assert state["stop_requested"] is True
    assert state["stop_reason"] == "stop_file"
    assert latest["reason"] == "stop_file"


def test_signal_stop_request_checkpoints_without_review_gate(tmp_path: Path) -> None:
    output = StringIO()
    supervisor = RuntimeSupervisor(
        state_dir=tmp_path,
        env={
            "HT_LAB_DISABLE_AUTONOMOUS_LOOP": "1",
            "HT_LAB_DRY_RUN": "1",
        },
        stream=output,
    )
    supervisor.request_stop("signal:SIGTERM")

    result = supervisor.run()
    state = _state(tmp_path)
    latest = json.loads((tmp_path / "checkpoints" / "latest.json").read_text(encoding="utf-8"))

    assert result.status == "stopped"
    assert state["stop_reason"] == "signal:SIGTERM"
    assert latest["reason"] == "signal:SIGTERM"
    assert "stage=stop" in output.getvalue()


def test_stable_candidate_restart_prints_non_claim_summary(tmp_path: Path) -> None:
    candidate = json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    (tmp_path / "stable_candidate.json").write_text(
        json.dumps(candidate),
        encoding="utf-8",
    )
    output = StringIO()

    result = _run(tmp_path, output)
    state = _state(tmp_path)

    assert result.status == "stable_candidate_recorded"
    assert state["status"] == "stable_candidate_recorded"
    assert policy.NON_CLAIM_TEXT in output.getvalue()
    assert "CANDIDATE PASSED ALL CONFIGURED GATES" in output.getvalue()


def test_stable_candidate_restart_does_not_pass_unreplicated_timeout(tmp_path: Path) -> None:
    candidate = json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    candidate["replication_status"] = "unreplicated_timeout"
    (tmp_path / "stable_candidate.json").write_text(
        json.dumps(candidate),
        encoding="utf-8",
    )
    output = StringIO()

    result = _run(tmp_path, output)

    assert result.status == "ready"
    assert "CANDIDATE PASSED ALL CONFIGURED GATES" not in output.getvalue()
    assert "Replication: passed_independent_path" not in output.getvalue()


def test_lazy_integrations_surface_pending_and_sandbox_status(tmp_path: Path) -> None:
    result = _run(tmp_path, env={"HT_LAB_SANDBOX_RUNTIME": "definitely-missing-runtime"})
    state = _state(tmp_path)

    assert result.status == "ready"
    assert state["integrations"]["python_dependencies"] == "available"
    assert state["integrations"]["sandbox"] == "sandbox_unavailable"
    assert state["integrations"]["agents"] == "integration_pending"
    assert state["integrations"]["datasets"] == "integration_pending"
    assert state["integrations"]["solver_packages"] == "integration_pending"


def test_missing_python_dependency_checkpoints_bootstrap_status(tmp_path: Path) -> None:
    result = _run(tmp_path, env={"HT_LAB_FAKE_MISSING_PYTHON_DEP": "1"})
    state = _state(tmp_path)
    latest = json.loads((tmp_path / "checkpoints" / "latest.json").read_text(encoding="utf-8"))

    assert result.status == "bootstrap_needed"
    assert state["integrations"]["python_dependencies"] == "bootstrap_needed"
    assert state["bootstrap_blocker"] == "python_dependencies_missing"
    assert latest["reason"] == "python_dependencies_missing"


def test_required_missing_sandbox_checkpoints_structured_status(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        env={
            "HT_LAB_REQUIRE_SANDBOX": "1",
            "HT_LAB_SANDBOX_RUNTIME": "definitely-missing-runtime",
        },
    )
    state = _state(tmp_path)
    latest = json.loads((tmp_path / "checkpoints" / "latest.json").read_text(encoding="utf-8"))

    assert result.status == "sandbox_unavailable"
    assert state["status"] == "sandbox_unavailable"
    assert latest["reason"] == "sandbox_unavailable"


def test_required_missing_solver_probe_checkpoints_bootstrap_status(tmp_path: Path) -> None:
    solver_prefix = tmp_path / "missing-solvers"
    result = _run(
        tmp_path,
        env={
            "HT_LAB_REQUIRE_SOLVERS": "1",
            "HT_SOLVER_PREFIX": str(solver_prefix),
        },
    )
    state = _state(tmp_path)
    latest = json.loads((tmp_path / "checkpoints" / "latest.json").read_text(encoding="utf-8"))

    assert result.status == "bootstrap_solver_unavailable"
    assert state["integrations"]["solver_packages"] == "bootstrap_solver_unavailable"
    assert state["solver_environment"]["missing_sources"] == ["class", "hyrec2"]
    assert state["bootstrap_blocker"] == "bootstrap_solver_unavailable"
    assert latest["reason"] == "bootstrap_solver_unavailable"


def test_non_dry_monitor_loop_exits_on_stop_file(tmp_path: Path) -> None:
    output = StringIO()
    results: list[RunResult] = []
    supervisor = RuntimeSupervisor(
        state_dir=tmp_path,
        env={
            "HT_LAB_DISABLE_AUTONOMOUS_LOOP": "1",
            "HT_LAB_IDLE_INTERVAL_SECONDS": "0.05",
        },
        stream=output,
    )
    thread = threading.Thread(target=lambda: results.append(supervisor.run()))

    thread.start()
    try:
        _wait_for(lambda: "stage=monitor" in output.getvalue())
        (tmp_path / "runs" / "run-000001" / "STOP").write_text("stop\n", encoding="utf-8")
        thread.join(timeout=3)
    finally:
        if thread.is_alive():
            supervisor.request_stop("test_cleanup")
            thread.join(timeout=3)

    state = _state(tmp_path)
    assert not thread.is_alive()
    assert results[0].status == "stopped"
    assert state["stop_reason"] == "stop_file"
    assert "stage=monitor" in output.getvalue()
    assert "stage=stop" in output.getvalue()


def _run(
    state_dir: Path,
    output: StringIO | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    runtime_env = {
        "HT_LAB_DISABLE_AUTONOMOUS_LOOP": "1",
        "HT_LAB_DRY_RUN": "1",
    }
    if env:
        runtime_env.update(env)
    supervisor = RuntimeSupervisor(
        state_dir=state_dir,
        env=runtime_env,
        stream=output if output is not None else StringIO(),
    )
    return supervisor.run()


def _state(state_dir: Path) -> dict[str, Any]:
    payload = json.loads((state_dir / "runtime_state.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not satisfied before timeout")
