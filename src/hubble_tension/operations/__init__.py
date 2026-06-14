"""Continuous operations helpers for Phase 13."""

from hubble_tension.operations.dataset_backlog import dataset_backlog_from_statuses
from hubble_tension.operations.digests import build_operator_digest
from hubble_tension.operations.external_status import (
    automated_transition_decision,
    infer_external_status,
    monitor_external_status_for_reports,
    propose_external_transition,
    rerun_request_from_transition,
)
from hubble_tension.operations.maintenance import (
    build_report_regeneration_result,
    cleanup_stale_scratch,
    compact_state_storage,
)
from hubble_tension.operations.report_index import build_report_index_entry, search_report_entries
from hubble_tension.operations.scaleout import default_scale_out_profile

__all__ = [
    "automated_transition_decision",
    "build_operator_digest",
    "build_report_regeneration_result",
    "build_report_index_entry",
    "cleanup_stale_scratch",
    "compact_state_storage",
    "dataset_backlog_from_statuses",
    "default_scale_out_profile",
    "infer_external_status",
    "monitor_external_status_for_reports",
    "propose_external_transition",
    "rerun_request_from_transition",
    "search_report_entries",
]
