from __future__ import annotations

from typing import Any

from pydantic import Field

from hubble_tension.schemas.base import StrictBaseModel
from hubble_tension.schemas.types import RuntimeStatus


class RuntimeState(StrictBaseModel):
    status: RuntimeStatus
    active_attempt_id: str | None = None
    active_branch_id: str | None = None
    active_test_id: str | None = None
    active_run_id: str | None = None
    active_run_dir: str | None = None
    active_hypothesis_id: str | None = None
    started_at: str | None = None
    stable_candidate_id: str | None = None
    last_lab_head_decision_id: str | None = None
    last_metric_packet_id: str | None = None
    last_checkpoint_at: str | None = None
    lock_owner: str | None = None
    bootstrap_blocker: str | None = None
    state_path: str | None = None
    log_path: str | None = None
    checkpoint_count: int = Field(default=0, ge=0)
    resume_count: int = Field(default=0, ge=0)
    stop_requested: bool = False
    stop_reason: str | None = None
    integrations: dict[str, str] = Field(default_factory=dict)
    lab_head: dict[str, str | bool] = Field(default_factory=dict)
    lab_loop: dict[str, Any] = Field(default_factory=dict)
    solver_environment: dict[str, Any] = Field(default_factory=dict)
    budget_usage: dict[str, int | float | str | bool] = Field(default_factory=dict)
    budget_limits: dict[str, int | float | str | bool] = Field(default_factory=dict)
    budget_exhausted_reason: str | None = None
    updated_at: str = Field(min_length=1)
