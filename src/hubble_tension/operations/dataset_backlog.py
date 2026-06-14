from __future__ import annotations

from collections.abc import Mapping

from hubble_tension.schemas.operations import DatasetBacklogItem

FAILED_STATUSES = ("failed", "missing", "crashed", "timeout")
INCONCLUSIVE_STATUSES = ("inconclusive", "not_run", "unavailable")


def dataset_backlog_from_statuses(
    *,
    source_ref: str,
    dataset_statuses: Mapping[str, str],
) -> tuple[DatasetBacklogItem, ...]:
    items: list[DatasetBacklogItem] = []
    for dataset_id, status in sorted(dataset_statuses.items()):
        normalized = status.lower()
        if any(marker in normalized for marker in FAILED_STATUSES):
            items.append(
                _item(
                    dataset_id=dataset_id,
                    status=status,
                    source_kind="failed_screen",
                    source_ref=source_ref,
                    priority=10,
                )
            )
        elif any(marker in normalized for marker in INCONCLUSIVE_STATUSES):
            items.append(
                _item(
                    dataset_id=dataset_id,
                    status=status,
                    source_kind="inconclusive_screen",
                    source_ref=source_ref,
                    priority=20,
                )
            )
    return tuple(items)


def _item(
    *,
    dataset_id: str,
    status: str,
    source_kind: str,
    source_ref: str,
    priority: int,
) -> DatasetBacklogItem:
    return DatasetBacklogItem(
        backlog_id=f"dataset-backlog-{source_ref}-{dataset_id}",
        dataset_id=dataset_id,
        reason=f"{dataset_id} status {status} requires integration follow-up",
        source_kind=source_kind,
        source_ref=source_ref,
        priority=priority,
        metadata_json={"dataset_status": status},
    )
