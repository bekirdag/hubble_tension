from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

NOVELTY_GATING_WEIGHT: Final[float] = 0.0

SCREENING_ONLY_LOCAL_PRIOR: Final[str] = "screening_only_local_prior"
ADVERSARIAL_VALIDATION: Final[str] = "adversarial_validation"
STABLE_INTERNAL_CANDIDATE: Final[str] = "stable_internal_candidate"
PROMISING_INTERNAL: Final[str] = "promising_internal"
EXTERNALLY_REFUTED: Final[str] = "externally_refuted"
EXTERNALLY_SUPPORTED: Final[str] = "externally_supported"

REQUIRED_REPLICATION_STATUS: Final[str] = "passed_independent_path"
REQUIRED_ADVERSARIAL_STATUS: Final[str] = "passed_registered_gate"
ACCEPTED_STABLE_REPLICATION_SCOPES: Final[tuple[str, ...]] = (
    "compressed_observable",
    "full_supported_family",
)

NON_CLAIM_TEXT: Final[str] = "NOT A SCIENTIFIC CLAIM"
CONFIGURED_GATES_TEXT: Final[str] = "HT-LAB: CANDIDATE PASSED ALL CONFIGURED GATES"
NOT_PASSED_CONFIGURED_GATES_TEXT: Final[str] = "HT-LAB: CANDIDATE HAS NOT PASSED CONFIGURED GATES"

GENERATED_CODE_ALLOWED_ROOTS: Final[tuple[str, ...]] = (
    "src/hubble_tension/generated_models/",
    "experiments/runs/",
)

PROHIBITED_REVIEW_GATES: Final[tuple[str, ...]] = (
    "human_approval_required",
    "manual_review_required",
    "human_science_review_required",
)

CANDIDATE_STATUS_LABELS: Final[tuple[str, ...]] = (
    SCREENING_ONLY_LOCAL_PRIOR,
    PROMISING_INTERNAL,
    ADVERSARIAL_VALIDATION,
    STABLE_INTERNAL_CANDIDATE,
    EXTERNALLY_REFUTED,
    EXTERNALLY_SUPPORTED,
)

RUNTIME_STATUS_LABELS: Final[tuple[str, ...]] = (
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
)

SCIENTIFIC_STATUS_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        SCREENING_ONLY_LOCAL_PRIOR: "Screening-only local prior",
        PROMISING_INTERNAL: "Promising internal candidate",
        ADVERSARIAL_VALIDATION: "Adversarial validation",
        STABLE_INTERNAL_CANDIDATE: "Stable internal candidate",
        EXTERNALLY_REFUTED: "Externally refuted",
        EXTERNALLY_SUPPORTED: "Externally supported",
    }
)

PROMOTION_REQUIREMENTS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        PROMISING_INTERNAL: (
            "metric_packet_present",
            "no_hard_constraint_failure",
        ),
        ADVERSARIAL_VALIDATION: (
            "replication_status:passed_independent_path",
            "datasets_passed_json:not_empty",
        ),
        STABLE_INTERNAL_CANDIDATE: (
            "replication_status:passed_independent_path",
            "replication_scope:compressed_observable_or_full_supported_family",
            "adversarial_status:passed_registered_gate",
            "non_claim_banner_required",
        ),
    }
)

CORE_STATE_TRANSITIONS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "bootstrap_needed": (
            "ready",
            "lab_head_unavailable",
            "sandbox_unavailable",
            "integration_pending",
        ),
        "ready": ("running", "budget_paused"),
        "running": (
            "stopped",
            "budget_paused",
            "generator_quarantine",
            "generation_budget_failed",
            "inconclusive_timeout",
            "stable_candidate_recorded",
        ),
        "stopped": ("ready",),
        "budget_paused": ("ready", "inconclusive_posterior"),
        "stable_candidate_recorded": (),
    }
)


def gate_score(data_fit_score: float, novelty_score: float) -> float:
    """Return the gate score with novelty explicitly excluded."""

    return data_fit_score + (NOVELTY_GATING_WEIGHT * novelty_score)


def candidate_passed_configured_gates(candidate: Mapping[str, object]) -> bool:
    """Check the Phase 0 stable-candidate policy contract."""

    return (
        candidate.get("candidate_status") == STABLE_INTERNAL_CANDIDATE
        and candidate.get("replication_status") == REQUIRED_REPLICATION_STATUS
        and replication_scope_can_support_stable(candidate)
        and candidate.get("adversarial_status") == REQUIRED_ADVERSARIAL_STATUS
    )


def replication_scope_can_support_stable(candidate: Mapping[str, object]) -> bool:
    """Return true when replication scope is broad enough for stable status."""

    return candidate.get("replication_scope") in ACCEPTED_STABLE_REPLICATION_SCOPES


def status_label(status: str) -> str:
    """Return the configured scientific label for a status."""

    return SCIENTIFIC_STATUS_LABELS.get(status, status)


def promotion_requirements_for(target_status: str) -> tuple[str, ...]:
    """Return immutable promotion requirements for the target status."""

    return PROMOTION_REQUIREMENTS.get(target_status, ())


def can_promote_to(candidate: Mapping[str, object], target_status: str) -> bool:
    """Evaluate the Phase 0 promotion guardrails that can run without solvers."""

    if target_status == STABLE_INTERNAL_CANDIDATE:
        return candidate_passed_configured_gates(candidate)

    if target_status == ADVERSARIAL_VALIDATION:
        datasets = candidate.get("datasets_passed_json", {})
        return (
            candidate.get("replication_status") == REQUIRED_REPLICATION_STATUS
            and isinstance(datasets, Mapping)
            and any(bool(passed) for passed in datasets.values())
        )

    if target_status == PROMISING_INTERNAL:
        datasets = candidate.get("datasets_passed_json", {})
        return isinstance(datasets, Mapping) and any(bool(passed) for passed in datasets.values())

    return False


def is_allowed_generated_code_path(path: str) -> bool:
    """Return true when generated code targets a controlled generated path."""

    normalized = path.replace("\\", "/")
    return any(normalized.startswith(root) for root in GENERATED_CODE_ALLOWED_ROOTS)


def render_stable_candidate_banner(candidate: Mapping[str, object]) -> str:
    """Render a non-claim candidate banner from candidate row state."""

    gate_text = (
        CONFIGURED_GATES_TEXT
        if candidate_passed_configured_gates(candidate)
        else NOT_PASSED_CONFIGURED_GATES_TEXT
    )
    concept = candidate.get("concept_name", "unknown")
    attempt = candidate.get("attempt_id", "unknown")
    branch = candidate.get("branch_id", "unknown")
    report = candidate.get("report_path", "not_recorded")
    datasets = candidate.get("datasets_passed_json", {})
    replication_status = candidate.get("replication_status", "not_run")
    replication_scope = candidate.get("replication_scope", "not_recorded")
    adversarial_status = candidate.get("adversarial_status", "not_run")
    candidate_status = candidate.get("candidate_status", "unknown")

    return "\n".join(
        [
            "============================================================",
            gate_text,
            NON_CLAIM_TEXT,
            "============================================================",
            f"Concept: {concept}",
            f"Attempt: {attempt}",
            f"Branch: {branch}",
            f"Report: {report}",
            f"Datasets passed: {datasets}",
            f"Adversarial validation: {adversarial_status}",
            f"Replication: {replication_status}",
            f"Replication scope: {replication_scope}",
            f"Status: {candidate_status}",
            "============================================================",
        ]
    )


class StableCandidateBanner:
    """Render restart summaries from candidate row state."""

    @staticmethod
    def render(candidate_row: Mapping[str, object]) -> str:
        return render_stable_candidate_banner(candidate_row)
