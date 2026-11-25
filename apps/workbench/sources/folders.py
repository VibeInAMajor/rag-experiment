"""Display folder aggregates over persisted source records, independent of upload attempts."""

from collections.abc import Sequence
from typing import Literal

from apps.workbench.contracts.schemas import FolderState
from apps.workbench.persistence.models import DocumentRecord


def document_folder_states(records: Sequence[DocumentRecord]) -> dict[str, list[FolderState]]:
    """Return ancestor states per source using all records before HTTP pagination."""
    aggregates: dict[tuple[str, str], FolderState] = {}
    ancestors: dict[str, list[tuple[str, str]]] = {}
    for record in records:
        location = record.upload_location
        if location is None:
            continue
        parts = location.path.split("/")[:-1]
        keys = [(location.group_id, "/".join(parts[: depth + 1])) for depth in range(len(parts))]
        ancestors[record.source_id] = keys
        for key in keys:
            previous = aggregates.get(key)
            count = (previous.file_count if previous else 0) + 1
            ready = (previous.ready_count if previous else 0) + int(record.status == "ready")
            status: Literal["ready", "processing", "error"] = (
                "error"
                if record.status == "error" or previous is not None and previous.status == "error"
                else "ready"
                if ready == count
                else "processing"
            )
            aggregates[key] = FolderState(file_count=count, ready_count=ready, status=status)
    return {source_id: [aggregates[key] for key in keys] for source_id, keys in ancestors.items()}
