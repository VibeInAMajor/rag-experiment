"""Project verified PDF children into the shared preparation and persistence contract."""

import hashlib
from dataclasses import asdict
from time import perf_counter
from typing import TYPE_CHECKING, Any

from apps.workbench.chunking.chunking_profiles import (
    ChunkingDecision,
    ChunkingError,
    ChunkingErrorCode,
    PdfChunkingProfile,
)
from apps.workbench.parsing.parsing import SourceSpan

if TYPE_CHECKING:
    from apps.workbench.chunking.chunking import ChunkingInput, ExactModelCounter, ModelTokenAdmission, PreparedChunk


def prepare_pdf_chunks(
    source: "ChunkingInput",
    *,
    decision: ChunkingDecision[PdfChunkingProfile],
    admission: "ModelTokenAdmission | None",
    counter: "ExactModelCounter | None",
    started: float,
) -> tuple["PreparedChunk", ...]:
    """Reuse HybridChunker, common native admission and immutable version-scoped chunk identities."""
    from apps.workbench.chunking.chunking import PreparedChunk, _canonical_bytes, _fingerprint, _model_size
    from apps.workbench.chunking.chunking_adapters import count_tokens
    from apps.workbench.chunking.pdf.pdf_chunking_adapter import split_pdf_block

    parsed = source.parsed_document
    pdf = parsed.pdf_document
    if pdf is None:
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="PDF_PROJECTION_MISSING")
    fingerprint = _fingerprint(
        {
            "algorithm": "pdf-page-layout-children-r1",
            "source_sha256": parsed.source_sha256,
            "parser": (parsed.parser_id, parsed.parser_revision),
            "detector": parsed.detector_revision,
            "decision": asdict(decision),
            "model_admission": asdict(admission) if admission else None,
            "projection": pdf.model_dump(exclude={"parser_seconds", "cpu_seconds", "peak_memory_bytes"}),
        }
    )
    chunks: list[PreparedChunk] = []
    offset = 0
    prepared_bytes = 0
    for block in pdf.blocks:
        children = split_pdf_block(block, profile=decision.profile)
        for child in children:
            if len(chunks) >= decision.profile.max_chunks or perf_counter() - started > 30:
                raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PDF_PREPARATION_BUDGET")
            size = count_tokens(child.content)
            prepared_bytes += len(child.content.encode("utf-8"))
            if size > decision.profile.target_size or len(child.content) > 32_768 or prepared_bytes > 52_428_800:
                raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PDF_CHUNK_BUDGET")
            content_hash = hashlib.sha256(child.content.encode("utf-8")).hexdigest()
            metadata: dict[str, Any] = {
                "verified_document_type": "pdf_text_layer",
                "page_number": block.page,
                "page_start": block.page,
                "page_end": block.page,
                "bbox": block.bbox.model_dump(),
                "bbox_scope": "source_block",
                "coordinate_frame": pdf.pages[block.page - 1].coordinate_frame,
                "page_width": pdf.pages[block.page - 1].width,
                "page_height": pdf.pages[block.page - 1].height,
                "block_id": block.block_id,
                "block_kind": block.kind,
                "source_span_basis": "extracted_pdf_projection",
                "source_span_scope": "source_block" if block.kind == "table" else "original_excerpt",
                "source_block_sha256": hashlib.sha256(block.text.encode("utf-8")).hexdigest(),
                "original_excerpt": child.original_excerpt,
                "original_excerpt_sha256": hashlib.sha256(child.original_excerpt.encode("utf-8")).hexdigest(),
                "retrieval_sha256": content_hash,
                "table_aware": True,
                "visual_processing_status": pdf.visual_processing_status,
                "visual_detection_coverage": pdf.visual_detection_coverage,
                "original_evidence_status": pdf.original_evidence_status,
                "evidence_processing_revision": pdf.processing_revision,
                "parse_warning_codes": list(dict.fromkeys((*pdf.warning_codes, *block.warning_codes))),
            }
            if block.kind == "table":
                metadata.update(
                    {
                        "table_id": block.block_id,
                        "table_row_start": child.row_start,
                        "table_row_end": child.row_end,
                        "table_row_index_basis": "zero-based-half-open",
                        "table_header_repeated": True,
                        "table_headers": list(child.table_headers),
                        "table_caption": block.caption,
                        "original_cells": [cell.model_dump(exclude_defaults=True) for cell in child.original_cells],
                    }
                )
            identity = (source.workspace_id, source.source_id, source.source_version_id)
            chunk = PreparedChunk(
                workspace_id=source.workspace_id,
                source_id=source.source_id,
                source_version_id=source.source_version_id,
                chunk_id=_fingerprint((*identity, fingerprint, len(chunks), content_hash)),
                ordinal=len(chunks),
                content=child.content,
                content_hash=content_hash,
                source_span=SourceSpan(start=offset + child.source_start, end=offset + child.source_end),
                heading_path=block.heading_path,
                parent_structural_id=_fingerprint(
                    (*identity, pdf.processing_revision, fingerprint, block.page, block.heading_path)
                ),
                effective_size=size,
                overlap_tokens=child.overlap_tokens,
                processing_fingerprint=fingerprint,
                decision=decision,
                source_sha256=parsed.source_sha256,
                parser_id=parsed.parser_id,
                parser_revision=parsed.parser_revision,
                detector_revision=parsed.detector_revision,
                warning_codes=tuple(metadata["parse_warning_codes"]),
                length_model_token=_model_size(
                    child.content, heading_path=block.heading_path, admission=admission, counter=counter
                ),
                length_tiktoken_model_input=count_tokens(
                    admission.embedding_input(child.content, heading_path=block.heading_path)
                )
                if admission
                else None,
                model_counter_revision=admission.counter_revision if admission else None,
                pdf_metadata_json=_canonical_bytes(metadata),
                page=block.page,
            )
            chunk.metadata()
            chunks.append(chunk)
        offset += len(block.text) + 2
    if not chunks:
        raise ChunkingError(ChunkingErrorCode.EMPTY_INPUT)
    return tuple(chunks)
