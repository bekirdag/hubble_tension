"""Adversarial validation namespace for Phase 12."""

from hubble_tension.adversarial.checks import (
    CHECK_TYPE_ALTERNATE_DATASET_SPLIT,
    CHECK_TYPE_CALIBRATION_SUITE_RERUN,
    CHECK_TYPE_LIKELIHOOD_CRASH_AUDIT,
    CHECK_TYPE_NEUTRAL_SCORE_AUDIT,
    CHECK_TYPE_OUT_OF_PRIOR_AUDIT,
    CHECK_TYPE_PRIOR_ART_REFUTATION_SEARCH,
    CHECK_TYPE_STRICTER_TOLERANCE_RERUN,
    MIN_DISTINCT_ATTEMPTS,
    MIN_REGISTERED_CHECKS,
    MIN_REQUIRED_CHECK_TYPES,
    REGISTERED_ADVERSARIAL_CHECKS,
    RegisteredAdversarialCheck,
    build_adversarial_queue,
    evaluate_adversarial_gate,
    phase12_registered_gate_attempts,
    registered_check_ids,
)

__all__ = [
    "CHECK_TYPE_ALTERNATE_DATASET_SPLIT",
    "CHECK_TYPE_CALIBRATION_SUITE_RERUN",
    "CHECK_TYPE_LIKELIHOOD_CRASH_AUDIT",
    "CHECK_TYPE_NEUTRAL_SCORE_AUDIT",
    "CHECK_TYPE_OUT_OF_PRIOR_AUDIT",
    "CHECK_TYPE_PRIOR_ART_REFUTATION_SEARCH",
    "CHECK_TYPE_STRICTER_TOLERANCE_RERUN",
    "MIN_DISTINCT_ATTEMPTS",
    "MIN_REGISTERED_CHECKS",
    "MIN_REQUIRED_CHECK_TYPES",
    "REGISTERED_ADVERSARIAL_CHECKS",
    "RegisteredAdversarialCheck",
    "build_adversarial_queue",
    "evaluate_adversarial_gate",
    "phase12_registered_gate_attempts",
    "registered_check_ids",
]
