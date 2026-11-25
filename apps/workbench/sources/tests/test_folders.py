"""Folder readiness reflects persisted documents, including records beyond an HTTP page."""

from apps.workbench.contracts.schemas import UploadLocation
from apps.workbench.persistence.models import DocumentRecord
from apps.workbench.sources.folders import document_folder_states


def test_unpublished_attempts_do_not_prevent_folder_readiness() -> None:
    """An original selection of five files can contain just one persisted Ready document."""
    document = DocumentRecord(
        source_id="source",
        title="notes.txt",
        media_type="text/plain",
        status="ready",
        active_version_id="version",
        chunk_count=1,
        updated_at="2026-11-25T12:00:00Z",
        upload_location=UploadLocation(group_id="selection", path="corpus/sub/notes.txt", folder_totals=[5, 3]),
    )
    states = document_folder_states([document])
    assert [state.model_dump() for state in states["source"]] == [
        {"file_count": 1, "ready_count": 1, "status": "ready"},
        {"file_count": 1, "ready_count": 1, "status": "ready"},
    ]
    failed = document.model_copy(update={"source_id": "failed", "status": "error"})
    complete = document_folder_states([document, failed])
    assert complete["source"][0].model_dump() == {"file_count": 2, "ready_count": 1, "status": "error"}
    assert complete["failed"][1].status == "error"
