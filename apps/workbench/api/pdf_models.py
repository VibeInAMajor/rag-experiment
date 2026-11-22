"""Provider-neutral PDF geometry and bounded extraction records."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PdfLimits(BaseModel):
    """Deployment ceilings; untrusted documents cannot choose resource budgets."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    max_bytes: int = Field(default=8_388_608, gt=0, le=8_388_608)
    max_pages: int = Field(default=32, gt=0, le=32)
    max_characters: int = Field(default=1_048_576, gt=0, le=1_048_576)
    max_blocks: int = Field(default=4096, gt=0, le=4096)
    max_cells: int = Field(default=32_768, gt=0, le=32_768)
    wall_seconds: int = Field(default=180, gt=0, le=180)
    memory_bytes: int = Field(default=6_442_450_944, gt=0, le=6_442_450_944)
    cpu_seconds: int = Field(default=640, gt=0, le=640)


class PdfBox(BaseModel):
    """Top-left-origin PDF point coordinates, never inferred physical page numbers."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    left: float = Field(ge=0, le=14_400)
    top: float = Field(ge=0, le=14_400)
    right: float = Field(gt=0, le=14_400)
    bottom: float = Field(gt=0, le=14_400)

    @model_validator(mode="after")
    def _ordered(self) -> "PdfBox":
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Invalid PDF geometry")
        return self


class PdfCell(BaseModel):
    """One observed cell, including explicit row/column span and header roles."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    text: str = Field(max_length=32_768)
    row_start: int = Field(ge=0, le=8192)
    row_end: int = Field(gt=0, le=8192)
    column_start: int = Field(ge=0, le=64)
    column_end: int = Field(gt=0, le=64)
    column_header: bool = False
    row_header: bool = False


class PdfBlock(BaseModel):
    """An ordered text/heading/caption or structured table on exactly one verified page."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    block_id: str = Field(min_length=1, max_length=128)
    page: int = Field(ge=1, le=32)
    kind: Literal["text", "heading", "caption", "table"]
    text: str = Field(max_length=1_048_576)
    bbox: PdfBox
    heading_path: tuple[str, ...] = Field(default=(), max_length=6)
    caption: str | None = Field(default=None, max_length=2048)
    cells: tuple[PdfCell, ...] = Field(default=(), max_length=32_768)
    row_count: int = Field(default=0, ge=0, le=8192)
    column_count: int = Field(default=0, ge=0, le=64)
    warning_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _table_bounds(self) -> "PdfBlock":
        if self.kind == "table":
            if not self.cells or self.row_count < 2 or self.column_count < 2:
                raise ValueError("Unqualified PDF table")
            coverage: set[tuple[int, int]] = set()
            for cell in self.cells:
                if not (
                    0 <= cell.row_start < cell.row_end <= self.row_count
                    and 0 <= cell.column_start < cell.column_end <= self.column_count
                ):
                    raise ValueError("Invalid PDF cell range")
                for row in range(cell.row_start, cell.row_end):
                    for column in range(cell.column_start, cell.column_end):
                        if (row, column) in coverage:
                            raise ValueError("Overlapping PDF cells")
                        coverage.add((row, column))
            if len(coverage) != self.row_count * self.column_count:
                raise ValueError("Incomplete PDF cells")
        elif self.cells or self.row_count or self.column_count:
            raise ValueError("Table data on PDF text")
        if any(len(heading) > 512 for heading in self.heading_path):
            raise ValueError("Oversized PDF heading")
        return self


class PdfPage(BaseModel):
    """An actual extractor page, including pages with no retrievable text."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    number: int = Field(ge=1, le=32)
    width: float = Field(gt=0, le=14_400)
    height: float = Field(gt=0, le=14_400)
    coordinate_frame: Literal["top-left-unrotated-mediabox-points"] = "top-left-unrotated-mediabox-points"


class PdfVisualRegion(BaseModel):
    """Observed geometry only; captions do not imply diagram or chart understanding."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    region_id: str = Field(min_length=1, max_length=128)
    page: int = Field(ge=1, le=32)
    bbox: PdfBox
    kind: Literal["unprocessed_visual"] = "unprocessed_visual"
    caption: str | None = Field(default=None, max_length=2048)
    heading_path: tuple[str, ...] = Field(default=(), max_length=6)
    processing_status: Literal["incomplete"] = "incomplete"
    evidence_status: Literal["visual_evidence_unavailable"] = "visual_evidence_unavailable"


class PdfDocument(BaseModel):
    """A serializable app-owned extraction snapshot with content-free resource measurements."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pages: tuple[PdfPage, ...] = Field(min_length=1, max_length=32)
    blocks: tuple[PdfBlock, ...] = Field(min_length=1, max_length=4096)
    warning_codes: tuple[str, ...] = ()
    parser_seconds: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)
    cpu_seconds: float = Field(ge=0)
    assets_revision: str = Field(min_length=1, max_length=128)
    visual_regions: tuple[PdfVisualRegion, ...] = Field(default=(), max_length=4096)
    visual_detection_coverage: Literal["unverified"] = "unverified"
    visual_processing_status: Literal["incomplete"] = "incomplete"
    original_evidence_status: Literal["unavailable"] = "unavailable"
    processing_revision: Literal["pdf-layout-evidence-r1"] = "pdf-layout-evidence-r1"

    @model_validator(mode="after")
    def _page_bounds(self) -> "PdfDocument":
        if [page.number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("Invalid PDF page sequence")
        if len({block.block_id for block in self.blocks}) != len(self.blocks):
            raise ValueError("Duplicate PDF blocks")
        if sum(len(block.text) for block in self.blocks) > PdfLimits().max_characters:
            raise ValueError("Oversized PDF extraction")
        if sum(len(block.cells) for block in self.blocks) > PdfLimits().max_cells:
            raise ValueError("Oversized PDF cell allocation")
        regions: tuple[PdfBlock | PdfVisualRegion, ...] = (*self.blocks, *self.visual_regions)
        for block in regions:
            if block.page > len(self.pages):
                raise ValueError("Unverified PDF page")
            page = self.pages[block.page - 1]
            if block.bbox.right > page.width + 1 or block.bbox.bottom > page.height + 1:
                raise ValueError("PDF block outside page")
        return self
