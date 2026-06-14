from __future__ import annotations

from collections.abc import Sequence

from hubble_tension.schemas.operations import (
    DatasetBacklogItem,
    ExternalTransitionProposal,
    OperatorDigest,
)
from hubble_tension.state import ReportRecord


def build_operator_digest(
    *,
    digest_id: str,
    reports: Sequence[ReportRecord],
    transitions: Sequence[ExternalTransitionProposal],
    backlog: Sequence[DatasetBacklogItem],
) -> OperatorDigest:
    accepted = sum(1 for proposal in transitions if proposal.decision == "accepted")
    content = (
        f"reports={len(reports)}; external_transitions={len(transitions)}; "
        f"accepted_transitions={accepted}; dataset_backlog={len(backlog)}"
    )
    return OperatorDigest(
        digest_id=digest_id,
        digest_type="periodic_operations",
        content=content,
        report_count=len(reports),
        transition_count=len(transitions),
        backlog_count=len(backlog),
        requires_acknowledgement=False,
    )
