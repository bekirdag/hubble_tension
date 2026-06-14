from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import cast

from hubble_tension.schemas.operations import (
    ExternalEvidenceRecord,
    ExternalRerunRequest,
    ExternalTransitionProposal,
    ReportExternalStatus,
    TransitionTargetStatus,
)
from hubble_tension.state import ReportRecord


def infer_external_status(
    evidence: Iterable[ExternalEvidenceRecord],
) -> TransitionTargetStatus:
    relations = {record.relation for record in evidence}
    if relations & {"refutes", "constrains", "contradicts_required_observable"}:
        return "externally_refuted"
    if relations & {"superseding_dataset", "superseding_likelihood"}:
        return "superseded"
    if relations & {"independent_support", "reproduces_prediction"}:
        return "externally_supported"
    return "unchecked"


def propose_external_transition(
    *,
    report_id: str,
    current_external_status: ReportExternalStatus = "unchecked",
    evidence: Iterable[ExternalEvidenceRecord] = (),
    confidence: float = 0.0,
    reason: str | None = None,
    candidate_id: str | None = None,
    hypothesis_id: str | None = None,
    target_external_status: TransitionTargetStatus | None = None,
) -> ExternalTransitionProposal:
    evidence_tuple = tuple(evidence)
    target = target_external_status or infer_external_status(evidence_tuple)
    proposal_id = _proposal_id(report_id, target, evidence_tuple)
    return ExternalTransitionProposal(
        proposal_id=proposal_id,
        report_id=report_id,
        target_external_status=target,
        current_external_status=current_external_status,
        confidence=confidence,
        reason=reason or f"external literature monitor proposed {target}",
        evidence=evidence_tuple,
        candidate_id=candidate_id,
        hypothesis_id=hypothesis_id,
        rerun_required=target != "unchecked",
    )


def monitor_external_status_for_reports(
    reports: Sequence[ReportRecord],
    evidence_by_report_id: Mapping[str, Iterable[ExternalEvidenceRecord]],
    *,
    confidence: float = 0.75,
) -> tuple[ExternalTransitionProposal, ...]:
    proposals: list[ExternalTransitionProposal] = []
    for report in sorted(reports, key=lambda item: item.report_id):
        evidence_tuple = tuple(evidence_by_report_id.get(report.report_id, ()))
        if not evidence_tuple:
            continue
        target_status = infer_external_status(evidence_tuple)
        if target_status == report.external_status:
            continue
        proposals.append(
            propose_external_transition(
                report_id=report.report_id,
                current_external_status=_report_external_status(report.external_status),
                evidence=evidence_tuple,
                confidence=confidence,
                reason="external-status monitor found cited literature or dataset change",
                candidate_id=report.candidate_id,
                hypothesis_id=report.hypothesis_id,
                target_external_status=target_status,
            )
        )
    return tuple(proposals)


def automated_transition_decision(
    proposal: ExternalTransitionProposal,
    *,
    min_confidence: float = 0.5,
) -> ExternalTransitionProposal:
    if proposal.target_external_status == "unchecked":
        return proposal.model_copy(
            update={
                "decision": "accepted",
                "decision_reason": "no cited external change; report remains unchecked",
                "rerun_required": False,
            }
        )
    if proposal.confidence >= min_confidence:
        return proposal.model_copy(
            update={
                "decision": "accepted",
                "decision_reason": "automated evidence rule passed confidence threshold",
                "rerun_required": True,
            }
        )
    return proposal.model_copy(
        update={
            "decision": "rejected",
            "decision_reason": "automated evidence rule below confidence threshold",
            "rerun_required": False,
        }
    )


def rerun_request_from_transition(
    proposal: ExternalTransitionProposal,
) -> ExternalRerunRequest | None:
    if proposal.decision != "accepted" or not proposal.rerun_required:
        return None
    evidence_ids = tuple(record.evidence_id for record in proposal.evidence)
    rerun_id = _rerun_id(proposal.proposal_id, evidence_ids)
    return ExternalRerunRequest(
        rerun_id=rerun_id,
        proposal_id=proposal.proposal_id,
        report_id=proposal.report_id,
        candidate_id=proposal.candidate_id,
        hypothesis_id=proposal.hypothesis_id,
        target_external_status=proposal.target_external_status,
        reason="accepted external-status transition requires automated rerun",
        evidence_ids=evidence_ids,
        status="queued",
        metadata_json={"decision_reason": proposal.decision_reason},
    )


def _proposal_id(
    report_id: str,
    target: str,
    evidence: tuple[ExternalEvidenceRecord, ...],
) -> str:
    evidence_ids = "|".join(record.evidence_id for record in evidence) or "no-evidence"
    digest = hashlib.sha256(f"{report_id}|{target}|{evidence_ids}".encode())
    return f"external-{digest.hexdigest()[:16]}"


def _rerun_id(proposal_id: str, evidence_ids: tuple[str, ...]) -> str:
    evidence_text = "|".join(evidence_ids)
    digest = hashlib.sha256(f"{proposal_id}|{evidence_text}".encode())
    return f"external-rerun-{digest.hexdigest()[:16]}"


def _report_external_status(status: str) -> ReportExternalStatus:
    if status in {
        "not_submitted",
        "unchecked",
        "externally_refuted",
        "externally_supported",
        "superseded",
    }:
        return cast(ReportExternalStatus, status)
    return "unchecked"
