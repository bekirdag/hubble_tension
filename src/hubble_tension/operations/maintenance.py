from __future__ import annotations

import hashlib
import shutil
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from hubble_tension.schemas.operations import MaintenanceJobResult, MaintenanceJobStatus

AUDIT_FILE_NAMES = {
    "lab_state.sqlite3",
    "runtime_state.json",
    "stable_candidate.json",
}
AUDIT_DIR_NAMES = {
    "checkpoints",
    "reports",
    "runs",
}
SCRATCH_NAMES = {
    "scratch",
    "tmp",
    "stale_scratch",
}


def cleanup_stale_scratch(
    state_dir: Path,
    *,
    dry_run: bool = False,
) -> MaintenanceJobResult:
    removed_paths: list[str] = []
    preserved_audit_records = 0
    for child in sorted(state_dir.iterdir()):
        if child.name in AUDIT_FILE_NAMES or child.name in AUDIT_DIR_NAMES:
            preserved_audit_records += 1
            continue
        if child.name not in SCRATCH_NAMES:
            continue
        removed_paths.append(str(child))
        if dry_run:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    status: MaintenanceJobStatus = "dry_run" if dry_run else "completed"
    return MaintenanceJobResult(
        job_id="maintenance-cleanup-stale-scratch",
        job_type="stale_scratch_cleanup",
        status=status,
        summary="removed stale scratch artifacts while preserving audit records",
        preserved_audit_records=preserved_audit_records,
        removed_paths=tuple(removed_paths),
    )


def compact_state_storage(
    db_path: Path,
    *,
    dry_run: bool = False,
) -> MaintenanceJobResult:
    status: MaintenanceJobStatus = "dry_run" if dry_run else "completed"
    if not dry_run:
        with sqlite3.connect(db_path) as connection:
            connection.execute("VACUUM")
    return MaintenanceJobResult(
        job_id="maintenance-storage-compaction",
        job_type="storage_compaction",
        status=status,
        summary="compacted SQLite state storage while preserving audit tables",
        preserved_audit_records=1 if db_path.exists() else 0,
        artifacts_json={"db_path": str(db_path), "dry_run": dry_run},
    )


def build_report_regeneration_result(
    report_ids: Iterable[str],
    *,
    dry_run: bool = False,
) -> MaintenanceJobResult:
    report_tuple = tuple(sorted(report_ids))
    digest = hashlib.sha256("|".join(report_tuple).encode()).hexdigest()[:16]
    status: MaintenanceJobStatus = "dry_run" if dry_run else "completed"
    return MaintenanceJobResult(
        job_id=f"maintenance-report-regeneration-{digest}",
        job_type="report_regeneration",
        status=status,
        summary="regenerated report index artifacts from durable report records",
        preserved_audit_records=len(report_tuple),
        artifacts_json={"report_ids": list(report_tuple), "dry_run": dry_run},
    )
