from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BudgetConfig:
    generated_tokens_per_hypothesis: int
    generated_tokens_per_attempt: int
    hard_stop_multiplier: int
    active_lab_runs: int
    generated_code_sandboxes: int
    solver_jobs: int
    lab_head_requests: int
    max_sustained_cpu_percent: int
    min_free_ram_gb: int
    max_lab_state_storage_gb: int
    screening_attempt_minutes: int
    promising_candidate_validation_hours: int
    l7_posterior_attempt_hours: int
    l7_total_candidate_hours: int
    hard_generation_stop_status: str
    l7_timeout_status: str


@dataclass(frozen=True)
class LabHeadFallbackConfig:
    allow_healthy_local_agents: bool
    prompt_on_unavailable: bool
    unavailable_status: str


@dataclass(frozen=True)
class LabHeadProvenanceConfig:
    require_agent_id: bool
    require_agent_version_hash: bool
    require_prompt_template_id: bool
    require_prompt_template_hash: bool


@dataclass(frozen=True)
class LabHeadConfig:
    version: int
    adapter: str
    agent: str
    execution: str
    fallback: LabHeadFallbackConfig
    provenance: LabHeadProvenanceConfig


def read_budget_config(path: Path) -> BudgetConfig:
    """Load the Phase 1 runtime budget contract."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Budget config must be a mapping: {path}")

    generated_tokens = _mapping(payload, "generated_tokens")
    concurrency = _mapping(payload, "concurrency")
    hardware = _mapping(payload, "hardware")
    wall_time = _mapping(payload, "wall_time")
    status = _mapping(payload, "status")

    return BudgetConfig(
        generated_tokens_per_hypothesis=_int(generated_tokens, "per_hypothesis"),
        generated_tokens_per_attempt=_int(generated_tokens, "per_attempt"),
        hard_stop_multiplier=_int(generated_tokens, "hard_stop_multiplier"),
        active_lab_runs=_int(concurrency, "active_lab_runs"),
        generated_code_sandboxes=_int(concurrency, "generated_code_sandboxes"),
        solver_jobs=_int(concurrency, "solver_jobs"),
        lab_head_requests=_int(concurrency, "lab_head_requests"),
        max_sustained_cpu_percent=_int(hardware, "max_sustained_cpu_percent"),
        min_free_ram_gb=_int(hardware, "min_free_ram_gb"),
        max_lab_state_storage_gb=_int(hardware, "max_lab_state_storage_gb"),
        screening_attempt_minutes=_int(wall_time, "screening_attempt_minutes"),
        promising_candidate_validation_hours=_int(
            wall_time, "promising_candidate_validation_hours"
        ),
        l7_posterior_attempt_hours=_int(wall_time, "l7_posterior_attempt_hours"),
        l7_total_candidate_hours=_int(wall_time, "l7_total_candidate_hours"),
        hard_generation_stop_status=_str(status, "hard_generation_stop"),
        l7_timeout_status=_str(status, "l7_timeout"),
    )


def read_lab_head_config(path: Path, env: Mapping[str, str] | None = None) -> LabHeadConfig:
    """Load the automated lab-head binding contract."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Lab-head config must be a mapping: {path}")

    runtime_env = env or {}
    fallback = _mapping(payload, "fallback")
    provenance = _mapping(payload, "provenance")
    configured_agent = runtime_env.get("HT_LAB_HEAD_AGENT") or _str(payload, "agent")
    configured_adapter = runtime_env.get("HT_LAB_HEAD_ADAPTER") or _str(payload, "adapter")

    return LabHeadConfig(
        version=_int(payload, "version"),
        adapter=configured_adapter,
        agent=configured_agent,
        execution=_str(payload, "execution"),
        fallback=LabHeadFallbackConfig(
            allow_healthy_local_agents=_bool(fallback, "allow_healthy_local_agents"),
            prompt_on_unavailable=_bool(fallback, "prompt_on_unavailable"),
            unavailable_status=_str(fallback, "unavailable_status"),
        ),
        provenance=LabHeadProvenanceConfig(
            require_agent_id=_bool(provenance, "require_agent_id"),
            require_agent_version_hash=_bool(provenance, "require_agent_version_hash"),
            require_prompt_template_id=_bool(provenance, "require_prompt_template_id"),
            require_prompt_template_hash=_bool(provenance, "require_prompt_template_hash"),
        ),
    )


def _mapping(payload: Mapping[object, object], key: str) -> Mapping[object, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Budget config section must be a mapping: {key}")
    return value


def _int(payload: Mapping[object, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Budget config value must be an integer: {key}")
    return value


def _str(payload: Mapping[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Budget config value must be a non-empty string: {key}")
    return value


def _bool(payload: Mapping[object, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Config value must be a boolean: {key}")
    return value
