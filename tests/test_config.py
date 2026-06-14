from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text())
    assert isinstance(data, dict)
    return data


def test_project_phase_marker_tracks_phase14_release_readiness() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())

    assert data["tool"]["hubble_tension"]["phase"] == "14"


def test_budget_defaults_are_pinned() -> None:
    budgets = _load_yaml("config/budgets.yaml")

    assert budgets["cloud_spend_usd_per_day"] == 0
    assert budgets["generated_tokens"]["per_hypothesis"] == 20_000
    assert budgets["generated_tokens"]["per_attempt"] == 200_000
    assert budgets["generated_tokens"]["hard_stop_multiplier"] == 2
    assert budgets["concurrency"]["active_lab_runs"] == 1
    assert budgets["concurrency"]["generated_code_sandboxes"] == 1
    assert budgets["concurrency"]["solver_jobs"] == 1
    assert budgets["concurrency"]["lab_head_requests"] == 1
    assert budgets["hardware"]["max_sustained_cpu_percent"] == 80
    assert budgets["hardware"]["min_free_ram_gb"] == 4
    assert budgets["hardware"]["max_lab_state_storage_gb"] == 20
    assert budgets["wall_time"]["screening_attempt_minutes"] == 45
    assert budgets["wall_time"]["promising_candidate_validation_hours"] == 2
    assert budgets["wall_time"]["l7_posterior_attempt_hours"] == 12
    assert budgets["wall_time"]["l7_total_candidate_hours"] == 48
    assert budgets["status"]["hard_generation_stop"] == "generation_budget_failed"
    assert budgets["status"]["l7_timeout"] == "inconclusive_posterior"


def test_lab_head_config_never_prompts_for_missing_agent() -> None:
    lab_head = _load_yaml("config/lab_head.yaml")

    assert lab_head["adapter"] == "mcoda"
    assert lab_head["agent"] == "codex55"
    assert lab_head["execution"] == "local_only"
    assert lab_head["fallback"]["prompt_on_unavailable"] is False
    assert lab_head["fallback"]["unavailable_status"] == "lab_head_unavailable"
    assert lab_head["provenance"]["require_prompt_template_hash"] is True


def test_ci_runs_policy_tests_without_mcoda_dependency() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert 'python-version: "3.13"' in workflow
    assert "python -m pytest tests/test_policy.py" in workflow
    assert "mcoda" not in workflow.lower()
