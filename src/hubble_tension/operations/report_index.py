from __future__ import annotations

import json
from collections.abc import Iterable

from hubble_tension.schemas.operations import ReportIndexEntry
from hubble_tension.state import ReportRecord


def build_report_index_entry(report: ReportRecord) -> ReportIndexEntry:
    metadata_text = json.dumps(report.metadata_json, sort_keys=True)
    parts = (
        report.report_id,
        report.report_path,
        report.external_status,
        report.title or "",
        report.hypothesis_id or "",
        report.candidate_id or "",
        metadata_text,
    )
    return ReportIndexEntry(
        report_id=report.report_id,
        report_path=report.report_path,
        external_status=report.external_status,  # type: ignore[arg-type]
        title=report.title,
        hypothesis_id=report.hypothesis_id,
        candidate_id=report.candidate_id,
        metadata_json=report.metadata_json,
        search_text=" ".join(parts).lower(),
    )


def search_report_entries(
    entries: Iterable[ReportIndexEntry],
    query: str,
) -> tuple[ReportIndexEntry, ...]:
    terms = tuple(term for term in query.lower().split() if term)
    if not terms:
        return tuple()
    return tuple(
        entry
        for entry in sorted(entries, key=lambda item: item.report_id)
        if all(term in entry.search_text for term in terms)
    )
