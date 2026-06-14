from __future__ import annotations

import os
import shutil
import signal
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

from hubble_tension import __version__, policy
from hubble_tension.lab.agents import select_lab_head
from hubble_tension.lab.stub_loop import StubLabLoop
from hubble_tension.runtime.config import (
    BudgetConfig,
    read_budget_config,
    read_lab_head_config,
)
from hubble_tension.runtime.locks import FileLock, LockCollisionError
from hubble_tension.runtime.logging import LabLogger, LogContext
from hubble_tension.runtime.state import JsonObject, RuntimeStore, utc_now
from hubble_tension.schemas.runtime import RuntimeState
from hubble_tension.solvers import solver_package_status
from hubble_tension.state import StateStore

DEFAULT_STATE_DIR = ".hubble_tension_state"
FRESH_ATTEMPT_ID = "attempt-000001"
FRESH_BRANCH_ID = "branch-000000"
FRESH_TEST_ID = "test-000000"
FRESH_RUN_ID = "run-000001"
LOCK_COLLISION_EXIT_CODE = 2
BYTE_PER_GB = 1024**3


@dataclass(frozen=True)
class BudgetCheck:
    status: str
    reason: str


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    status: str
    state_path: Path
    log_path: Path
    run_id: str
    resumed: bool = False
    lock_collision: bool = False


class RuntimeSupervisor:
    """Phase 1 runtime supervisor for no-argument local operation."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
        stream: TextIO | None = None,
    ) -> None:
        self.repo_root = repo_root if repo_root is not None else _repo_root()
        self.env = env if env is not None else os.environ
        configured_state_dir = self.env.get("HT_LAB_STATE_DIR")
        self.state_dir = (
            state_dir
            if state_dir is not None
            else Path(configured_state_dir)
            if configured_state_dir
            else self.repo_root / DEFAULT_STATE_DIR
        )
        if not self.state_dir.is_absolute():
            self.state_dir = self.repo_root / self.state_dir
        self.store = RuntimeStore(self.state_dir)
        self.sql_store = StateStore(self.state_dir / "lab_state.sqlite3")
        self.stream = stream
        self.stop_requested = False
        self.stop_reason: str | None = None

    def request_stop(self, reason: str) -> None:
        self.stop_requested = True
        self.stop_reason = reason

    def run(self) -> RunResult:
        self.store.ensure()
        budget_config = read_budget_config(self.repo_root / "config" / "budgets.yaml")
        raw_state = self.store.load_state()
        resumed = raw_state is not None
        state = self._prepare_state(raw_state)
        self._prepare_run_paths(state)
        self._refresh_integrations(state)

        run_id = _state_str(state, "active_run_id", FRESH_RUN_ID)
        log_path = self.store.log_path_for(run_id)
        lock_payload = {
            "created_at": utc_now(),
            "log_path": str(log_path),
            "owner": "hubble_tension.runtime.supervisor",
            "pid": os.getpid(),
            "run_id": run_id,
            "state_path": str(self.store.state_path),
        }

        try:
            with FileLock(self.store.lock_path, lock_payload):
                self.sql_store.initialize()
                return self._run_locked(state, budget_config, resumed, log_path)
        except LockCollisionError as exc:
            collision = exc.collision
            print(
                "[HT-LAB lock-collision] "
                f"active_run_id={collision.run_id} "
                f"state_path={collision.state_path} "
                f"log_path={collision.log_path}",
                file=self.stream if self.stream is not None else sys.stdout,
                flush=True,
            )
            return RunResult(
                exit_code=LOCK_COLLISION_EXIT_CODE,
                status="running",
                state_path=self.store.state_path,
                log_path=Path(collision.log_path),
                run_id=collision.run_id,
                resumed=resumed,
                lock_collision=True,
            )

    def _run_locked(
        self,
        state: JsonObject,
        budget_config: BudgetConfig,
        resumed: bool,
        log_path: Path,
    ) -> RunResult:
        logger = LabLogger(log_path, stream=self.stream)
        context = _log_context(state)
        with self._signal_handlers():
            bootstrap_blocker = _optional_state_str(state, "bootstrap_blocker")
            if bootstrap_blocker is None:
                state["status"] = "running"
            if resumed:
                state["resume_count"] = int(state.get("resume_count", 0)) + 1
            self._save_checkpoint(state, "resume" if resumed else "fresh_start")
            logger.emit(
                context,
                "start",
                (
                    f"runtime supervisor version {__version__} "
                    f"{'resuming from checkpoint' if resumed else 'initialized attempt 1'}"
                ),
            )

            if bootstrap_blocker is not None:
                self._save_checkpoint(state, bootstrap_blocker)
                logger.emit(
                    context,
                    "bootstrap",
                    f"{bootstrap_blocker}; checkpointed bootstrap status",
                )
                return self._result(state, resumed=resumed)

            stable_candidate = self.store.load_stable_candidate()
            if stable_candidate is not None and policy.candidate_passed_configured_gates(
                stable_candidate
            ):
                state["status"] = "stable_candidate_recorded"
                state["stable_candidate_id"] = str(stable_candidate.get("candidate_id", "unknown"))
                self._save_checkpoint(state, "stable_candidate_recorded")
                logger.emit(
                    context,
                    "stable_candidate",
                    "configured gates already passed; default search is paused",
                )
                print(
                    policy.render_stable_candidate_banner(stable_candidate),
                    file=self.stream if self.stream is not None else sys.stdout,
                    flush=True,
                )
                return self._result(state, resumed=resumed)

            budget_check = self._budget_check(state, budget_config)
            if budget_check is not None:
                self._checkpoint_budget_exhaustion(state, budget_check, logger, context)
                return self._result(state, resumed=resumed)

            stop_reason = self._stop_reason(state)
            if stop_reason is not None:
                state["status"] = "stopped"
                state["stop_requested"] = True
                state["stop_reason"] = stop_reason
                self._save_checkpoint(state, stop_reason)
                logger.emit(
                    context,
                    "stop",
                    f"checkpointed stop request from {stop_reason}",
                )
                return self._result(state, resumed=resumed)

            logger.emit(context, "integrations", self._integration_summary(state))
            if self._phase5_loop_requested():
                lab_head = select_lab_head(
                    config=read_lab_head_config(
                        self.repo_root / "config" / "lab_head.yaml",
                        self.env,
                    ),
                    prompt_dir=self.repo_root / "prompts",
                    env=self.env,
                )
                if not lab_head.available:
                    state["status"] = lab_head.status
                    state["bootstrap_blocker"] = lab_head.status
                    self._save_checkpoint(state, lab_head.status)
                    logger.emit(
                        context,
                        "bootstrap",
                        f"{lab_head.status}; checkpointed lab-head bootstrap status",
                    )
                    return self._result(state, resumed=resumed)
                result = StubLabLoop(
                    repo_root=self.repo_root,
                    run_dir=Path(_state_str(state, "active_run_dir", str(self.state_dir))),
                    state_store=self.sql_store,
                    lab_head=lab_head,
                    logger=logger,
                    context=context,
                    env=self.env,
                ).run_once(state)
                self._save_checkpoint(state, "phase5_stub_cycle_complete")
                logger.emit(
                    context,
                    "phase5",
                    (
                        "stub lab cycle checkpointed "
                        f"hypothesis={result.hypothesis_id} decision={result.decision_id}"
                    ),
                )
                if self.env.get("HT_LAB_DRY_RUN") == "1":
                    return self._result(state, resumed=resumed)

            if self.env.get("HT_LAB_DRY_RUN") == "1":
                logger.emit(context, "dry_run", "test control requested one supervisor cycle")
                state["status"] = "ready"
                self._save_checkpoint(state, "ready")
                return self._result(state, resumed=resumed)

            state["status"] = "ready"
            self._save_checkpoint(state, "ready")
            logger.emit(
                context,
                "monitor",
                "supervisor monitor active; waiting for autonomous lab phases and stop signals",
            )
            return self._monitor_until_exit(
                state,
                budget_config,
                logger,
                context,
                resumed=resumed,
            )

    def _monitor_until_exit(
        self,
        state: JsonObject,
        budget_config: BudgetConfig,
        logger: LabLogger,
        context: LogContext,
        *,
        resumed: bool,
    ) -> RunResult:
        idle_interval = self._idle_interval_seconds()
        while True:
            budget_check = self._budget_check(state, budget_config)
            if budget_check is not None:
                self._checkpoint_budget_exhaustion(state, budget_check, logger, context)
                return self._result(state, resumed=resumed)

            stable_candidate = self.store.load_stable_candidate()
            if stable_candidate is not None and policy.candidate_passed_configured_gates(
                stable_candidate
            ):
                state["status"] = "stable_candidate_recorded"
                state["stable_candidate_id"] = str(stable_candidate.get("candidate_id", "unknown"))
                self._save_checkpoint(state, "stable_candidate_recorded")
                logger.emit(
                    context,
                    "stable_candidate",
                    "configured gates passed during monitor loop; default search is paused",
                )
                print(
                    policy.render_stable_candidate_banner(stable_candidate),
                    file=self.stream if self.stream is not None else sys.stdout,
                    flush=True,
                )
                return self._result(state, resumed=resumed)

            stop_reason = self._stop_reason(state)
            if stop_reason is not None:
                state["status"] = "stopped"
                state["stop_requested"] = True
                state["stop_reason"] = stop_reason
                self._save_checkpoint(state, stop_reason)
                logger.emit(
                    context,
                    "stop",
                    f"checkpointed stop request from {stop_reason}",
                )
                return self._result(state, resumed=resumed)

            time.sleep(idle_interval)

    def _idle_interval_seconds(self) -> float:
        configured = self.env.get("HT_LAB_IDLE_INTERVAL_SECONDS")
        if configured is None:
            return 5.0
        try:
            interval = float(configured)
        except ValueError:
            return 5.0
        return max(0.05, interval)

    def _prepare_state(self, raw_state: JsonObject | None) -> JsonObject:
        now = utc_now()
        if raw_state is None:
            return {
                "active_attempt_id": FRESH_ATTEMPT_ID,
                "active_branch_id": FRESH_BRANCH_ID,
                "active_run_id": FRESH_RUN_ID,
                "active_test_id": FRESH_TEST_ID,
                "budget_exhausted_reason": None,
                "budget_limits": {},
                "budget_usage": {},
                "bootstrap_blocker": None,
                "checkpoint_count": 0,
                "integrations": {},
                "lab_head": {},
                "lab_loop": {},
                "solver_environment": {},
                "last_checkpoint_at": None,
                "last_lab_head_decision_id": None,
                "last_metric_packet_id": None,
                "lock_owner": None,
                "resume_count": 0,
                "started_at": now,
                "stable_candidate_id": None,
                "status": "bootstrap_needed",
                "stop_reason": None,
                "stop_requested": False,
                "updated_at": now,
            }
        state = dict(raw_state)
        state.setdefault("active_attempt_id", FRESH_ATTEMPT_ID)
        state.setdefault("active_branch_id", FRESH_BRANCH_ID)
        state.setdefault("active_test_id", FRESH_TEST_ID)
        state.setdefault("active_run_id", FRESH_RUN_ID)
        state.setdefault("budget_exhausted_reason", None)
        state.setdefault("budget_limits", {})
        state.setdefault("budget_usage", {})
        state.setdefault("bootstrap_blocker", None)
        state.setdefault("checkpoint_count", 0)
        state.setdefault("integrations", {})
        state.setdefault("lab_head", {})
        state.setdefault("lab_loop", {})
        state.setdefault("solver_environment", {})
        state.setdefault("last_lab_head_decision_id", None)
        state.setdefault("last_metric_packet_id", None)
        state.setdefault("resume_count", 0)
        state.setdefault("started_at", now)
        state.setdefault("stable_candidate_id", None)
        state.setdefault("stop_reason", None)
        state.setdefault("stop_requested", False)
        state["updated_at"] = now
        return state

    def _prepare_run_paths(self, state: JsonObject) -> None:
        run_id = _state_str(state, "active_run_id", FRESH_RUN_ID)
        run_dir = self.store.run_dir_for(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        state["active_run_dir"] = str(run_dir)
        state["state_path"] = str(self.store.state_path)
        state["log_path"] = str(self.store.log_path_for(run_id))

    def _refresh_integrations(self, state: JsonObject) -> None:
        sandbox_runtime = self.env.get("HT_LAB_SANDBOX_RUNTIME", "podman")
        sandbox_status = "available" if shutil.which(sandbox_runtime) else "sandbox_unavailable"
        python_status = self._python_dependency_status()
        solver_probe = solver_package_status(repo_root=self.repo_root, env=self.env)
        loop_requested = self._phase5_loop_requested()
        lab_head = (
            select_lab_head(
                config=read_lab_head_config(
                    self.repo_root / "config" / "lab_head.yaml",
                    self.env,
                ),
                prompt_dir=self.repo_root / "prompts",
                env=self.env,
            )
            if loop_requested
            else None
        )
        integrations = {
            "agents": lab_head.status if lab_head is not None else "integration_pending",
            "datasets": "integration_pending",
            "likelihood_packages": "integration_pending",
            "python_dependencies": python_status,
            "scale_out_workers": "integration_pending",
            "solver_packages": solver_probe.status,
            "web_services": "integration_pending",
            "sandbox": sandbox_status,
        }
        state["integrations"] = integrations
        state["solver_environment"] = solver_probe.as_state()
        state["lab_head"] = lab_head.as_state() if lab_head is not None else {
            "available": False,
            "status": "integration_pending",
        }
        state["bootstrap_blocker"] = None
        if python_status == "bootstrap_needed":
            state["status"] = "bootstrap_needed"
            state["bootstrap_blocker"] = "python_dependencies_missing"
            return
        sandbox_required = self.env.get("HT_LAB_REQUIRE_SANDBOX") == "1"
        if sandbox_status == "sandbox_unavailable" and sandbox_required:
            state["status"] = "sandbox_unavailable"
            state["bootstrap_blocker"] = "sandbox_unavailable"
            return
        if (
            self.env.get("HT_LAB_REQUIRE_SOLVERS") == "1"
            and solver_probe.status == "bootstrap_solver_unavailable"
        ):
            state["status"] = "bootstrap_solver_unavailable"
            state["bootstrap_blocker"] = "bootstrap_solver_unavailable"
            return
        if lab_head is not None and not lab_head.available:
            state["status"] = lab_head.status
            state["bootstrap_blocker"] = lab_head.status

    def _phase5_loop_requested(self) -> bool:
        if self.env.get("HT_LAB_DISABLE_AUTONOMOUS_LOOP") == "1":
            return False
        configured = self.env.get("HT_LAB_ENABLE_PHASE5_LOOP")
        if configured is not None:
            return configured == "1"
        return True

    def _python_dependency_status(self) -> str:
        if self.env.get("HT_LAB_FAKE_MISSING_PYTHON_DEP") == "1":
            return "bootstrap_needed"
        required_modules = ("pydantic", "yaml")
        return (
            "available"
            if all(find_spec(module_name) is not None for module_name in required_modules)
            else "bootstrap_needed"
        )

    def _budget_check(
        self,
        state: JsonObject,
        budget_config: BudgetConfig,
    ) -> BudgetCheck | None:
        usage = self._budget_usage(state)
        limits = self._budget_limits(budget_config)
        state["budget_usage"] = usage
        state["budget_limits"] = limits

        if self.env.get("HT_LAB_FORCE_BUDGET_EXHAUSTED") == "1":
            return BudgetCheck(
                status=budget_config.hard_generation_stop_status,
                reason="forced_budget_exhausted",
            )
        if usage["generated_tokens_per_attempt"] > limits["hard_generated_tokens_per_attempt"]:
            return BudgetCheck(
                status=budget_config.hard_generation_stop_status,
                reason="generated_tokens_per_attempt",
            )
        if (
            usage["generated_tokens_per_hypothesis"]
            > limits["hard_generated_tokens_per_hypothesis"]
        ):
            return BudgetCheck(
                status=budget_config.hard_generation_stop_status,
                reason="generated_tokens_per_hypothesis",
            )
        if usage["cpu_percent"] > limits["max_sustained_cpu_percent"]:
            return BudgetCheck(status="budget_paused", reason="cpu_percent")
        if usage["wall_time_minutes"] > limits["screening_attempt_minutes"]:
            return BudgetCheck(status="budget_paused", reason="wall_time_minutes")
        if usage["active_solver_jobs"] > limits["solver_jobs"]:
            return BudgetCheck(status="budget_paused", reason="active_solver_jobs")
        if usage["storage_gb"] > limits["max_lab_state_storage_gb"]:
            return BudgetCheck(status="budget_paused", reason="storage_gb")
        if usage["active_lab_runs"] > limits["active_lab_runs"]:
            return BudgetCheck(status="budget_paused", reason="active_lab_runs")
        return None

    def _budget_usage(self, state: Mapping[str, Any]) -> dict[str, float]:
        return {
            "active_lab_runs": self._env_int("HT_LAB_ACTIVE_LAB_RUNS", 1),
            "active_solver_jobs": self._env_int("HT_LAB_ACTIVE_SOLVER_JOBS", 0),
            "cpu_percent": self._env_float("HT_LAB_FAKE_CPU_PERCENT", 0.0),
            "generated_tokens_per_attempt": self._env_int(
                "HT_LAB_GENERATED_TOKENS_ATTEMPT",
                int(state.get("generated_tokens_per_attempt", 0)),
            ),
            "generated_tokens_per_hypothesis": self._env_int(
                "HT_LAB_GENERATED_TOKENS_HYPOTHESIS",
                int(state.get("generated_tokens_per_hypothesis", 0)),
            ),
            "storage_gb": self._env_float(
                "HT_LAB_FAKE_STORAGE_GB",
                self._state_storage_gb(),
            ),
            "wall_time_minutes": self._env_float(
                "HT_LAB_FAKE_WALL_TIME_MINUTES",
                self._wall_time_minutes(state),
            ),
        }

    def _budget_limits(self, budget_config: BudgetConfig) -> dict[str, float]:
        return {
            "active_lab_runs": budget_config.active_lab_runs,
            "hard_generated_tokens_per_attempt": (
                budget_config.generated_tokens_per_attempt * budget_config.hard_stop_multiplier
            ),
            "hard_generated_tokens_per_hypothesis": (
                budget_config.generated_tokens_per_hypothesis * budget_config.hard_stop_multiplier
            ),
            "max_lab_state_storage_gb": budget_config.max_lab_state_storage_gb,
            "max_sustained_cpu_percent": budget_config.max_sustained_cpu_percent,
            "screening_attempt_minutes": budget_config.screening_attempt_minutes,
            "solver_jobs": budget_config.solver_jobs,
        }

    def _checkpoint_budget_exhaustion(
        self,
        state: JsonObject,
        budget_check: BudgetCheck,
        logger: LabLogger,
        context: LogContext,
    ) -> None:
        state["status"] = budget_check.status
        state["budget_exhausted_reason"] = budget_check.reason
        self._save_checkpoint(state, "budget_exhausted")
        logger.emit(
            context,
            "budget",
            (
                f"budget exhausted by {budget_check.reason}; "
                f"checkpointed and entered {budget_check.status}"
            ),
        )

    def _wall_time_minutes(self, state: Mapping[str, Any]) -> float:
        started_at = _optional_state_str(state, "started_at")
        if started_at is None:
            return 0.0
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        return max(0.0, (datetime.now(UTC) - started).total_seconds() / 60)

    def _state_storage_gb(self) -> float:
        total_bytes = 0
        for path in self.store.state_dir.rglob("*"):
            if path.is_file():
                total_bytes += path.stat().st_size
        return total_bytes / BYTE_PER_GB

    def _env_int(self, key: str, default: int) -> int:
        value = self.env.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _env_float(self, key: str, default: float) -> float:
        value = self.env.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    def _stop_reason(self, state: JsonObject) -> str | None:
        if self.stop_requested:
            return self.stop_reason or "signal"
        run_id = _state_str(state, "active_run_id", FRESH_RUN_ID)
        if self.store.stop_path_for(run_id).exists():
            return "stop_file"
        return None

    def _save_checkpoint(self, state: JsonObject, reason: str) -> None:
        state["checkpoint_count"] = int(state.get("checkpoint_count", 0)) + 1
        state["last_checkpoint_at"] = utc_now()
        state["updated_at"] = state["last_checkpoint_at"]
        RuntimeState.model_validate(state)
        self.store.save_state(state)
        self.store.write_checkpoint(state, reason)
        self.store.append_event(
            {
                "attempt_id": state.get("active_attempt_id"),
                "branch_id": state.get("active_branch_id"),
                "event": "checkpoint",
                "reason": reason,
                "recorded_at": state["last_checkpoint_at"],
                "status": state.get("status"),
                "test_id": state.get("active_test_id"),
            }
        )
        self.sql_store.record_state_transition(
            status=_state_str(state, "status", "ready"),
            reason=reason,
            state=state,
            attempt_id=_optional_state_str(state, "active_attempt_id"),
            branch_id=_optional_state_str(state, "active_branch_id"),
            test_id=_optional_state_str(state, "active_test_id"),
            run_id=_optional_state_str(state, "active_run_id"),
            checkpoint_required=True,
        )

    def _result(self, state: JsonObject, *, resumed: bool) -> RunResult:
        return RunResult(
            exit_code=0,
            status=_state_str(state, "status", "ready"),
            state_path=self.store.state_path,
            log_path=Path(
                _state_str(state, "log_path", str(self.store.log_path_for(FRESH_RUN_ID)))
            ),
            run_id=_state_str(state, "active_run_id", FRESH_RUN_ID),
            resumed=resumed,
        )

    def _integration_summary(self, state: Mapping[str, Any]) -> str:
        integrations = state.get("integrations", {})
        if not isinstance(integrations, Mapping):
            return "integration status unavailable"
        parts = [f"{key}={value}" for key, value in sorted(integrations.items())]
        return "integration status: " + ", ".join(parts)

    @contextmanager
    def _signal_handlers(self) -> Iterator[None]:
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        previous_int = signal.getsignal(signal.SIGINT)
        previous_term = signal.getsignal(signal.SIGTERM)

        def handler(signum: int, frame: FrameType | None) -> None:
            del frame
            self.request_stop(f"signal:{signal.Signals(signum).name}")

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
        try:
            yield
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _state_str(state: Mapping[str, Any], key: str, fallback: str) -> str:
    value = state.get(key)
    if isinstance(value, str) and value:
        return value
    return fallback


def _optional_state_str(state: Mapping[str, Any], key: str) -> str | None:
    value = state.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _log_context(state: Mapping[str, Any]) -> LogContext:
    return LogContext(
        attempt_id=_state_str(state, "active_attempt_id", FRESH_ATTEMPT_ID),
        branch_id=_state_str(state, "active_branch_id", FRESH_BRANCH_ID),
        test_id=_state_str(state, "active_test_id", FRESH_TEST_ID),
    )
