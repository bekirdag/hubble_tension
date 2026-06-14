from __future__ import annotations

from typing import Literal

WildnessLevel = Literal["W0", "W1", "W2", "W3", "W4", "W5"]

CandidateStatus = Literal[
    "screening_only_local_prior",
    "promising_internal",
    "adversarial_validation",
    "stable_internal_candidate",
    "externally_refuted",
    "externally_supported",
]

ReplicationStatus = Literal[
    "not_run",
    "passed_independent_path",
    "failed_independent_path",
    "unreplicated_timeout",
]

ReplicationScope = Literal[
    "not_recorded",
    "background_only",
    "compressed_observable",
    "full_supported_family",
]

AdversarialStatus = Literal[
    "not_run",
    "running",
    "passed_registered_gate",
    "failed_registered_gate",
    "inconclusive_adversarial_budget",
]

RuntimeStatus = Literal[
    "bootstrap_needed",
    "ready",
    "running",
    "stopped",
    "budget_paused",
    "sandbox_unavailable",
    "integration_pending",
    "lab_head_unavailable",
    "generator_quarantine",
    "bootstrap_solver_unavailable",
    "generation_budget_failed",
    "inconclusive_timeout",
    "inconclusive_posterior",
    "stable_candidate_recorded",
]

Decision = Literal[
    "implement",
    "revise",
    "archive",
    "tune",
    "branch",
    "backtrack",
    "abandon",
    "promote",
    "report",
]

Uncertainty = Literal["low", "medium", "high"]
