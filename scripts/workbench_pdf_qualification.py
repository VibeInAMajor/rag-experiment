"""Actual isolated PDF extraction and controlled lexical policy comparison, with explicit failures."""

import argparse
import hashlib
import json
import math
import os
import statistics
from collections import Counter
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import psycopg
import tiktoken

from apps.workbench.api.chunking_adapters import inspect_chunking_resources, split_prose
from apps.workbench.api.chunking_profiles import PdfChunkingProfile, structural_token_profile
from apps.workbench.api.parser_registry import ParsingError
from apps.workbench.api.pdf_chunking_adapter import split_pdf_block
from apps.workbench.api.pdf_models import PdfDocument
from apps.workbench.api.pdf_parser import extract_pdf
from scripts.workbench_pdf_fixtures import build_corpus


def _p95(values: list[float]) -> float | None:
    return sorted(values)[math.ceil(len(values) * 0.95) - 1] if values else None


def _controls(document: PdfDocument, policy: str) -> list[dict]:
    if policy == "page-alone":
        return [
            {
                "page": page.number,
                "text": "\n".join(block.text for block in document.blocks if block.page == page.number),
            }
            for page in document.pages
        ]
    if policy == "plain-recursive":
        text = "\n\n".join(block.text for block in document.blocks)
        # Baseline uses the same installed counter, without page/table structural boundaries.
        from apps.workbench.api.chunking_profiles import ChunkingDecision

        profile = replace(structural_token_profile(), target_size=768, overlap=0)
        decision = ChunkingDecision(
            profile=profile,
            strategy="prose_recursive",
            selection_reason="control",
            fallback_reasons=(),
            token_counter_revision=inspect_chunking_resources().token_counter_revision,
        )
        starts = []
        offset = 0
        for block in document.blocks:
            starts.append((offset, offset + len(block.text), block.page))
            offset += len(block.text) + 2
        return [
            {
                "page": next(page for start, end, page in starts if start <= span.start < end),
                "text": text[span.start : span.end],
            }
            for span in split_prose(text, decision=decision)
        ]
    target, overlap = (512, 64) if policy == "page-512-64" else (768, 64) if policy == "page-768-64" else (768, 0)
    profile = PdfChunkingProfile(target_size=target, overlap=overlap)
    return [
        {"page": block.page, "text": child.content}
        for block in document.blocks
        for child in split_pdf_block(block, profile=profile)
    ]


def _queries(name: str, document: PdfDocument) -> list[dict]:
    final_page = len(document.pages)
    if "table" in name or name == "numeric-units":
        queries = [
            {"query": "Station1R8", "pages": [1], "evidence": "1056"},
            {"query": f"Station{final_page}R1", "pages": [final_page], "evidence": str(final_page * 1000 + 7)},
        ]
        if name == "caption-table":
            queries.append({"query": "audited water output", "pages": [1], "evidence": "Station1R8"})
        if name == "cross-page-table":
            queries.append({"query": "Station1R8 Station2R8", "pages": [1, 2], "evidence": "Station2R8"})
        if name == "long-table":
            queries.append({"query": "Station1R1 Station1R30", "pages": [1], "evidence": "1210"})
        return queries
    if name == "two-columns":
        return [
            {"query": "Left section", "pages": [1], "evidence": "Left section observation"},
            {"query": "Right section", "pages": [1], "evidence": "Right section observation"},
        ]
    return [
        {"query": "PageMarker1", "pages": [1], "evidence": "PageMarker1"},
        {"query": f"PageMarker{final_page}", "pages": [final_page], "evidence": f"PageMarker{final_page}"},
    ]


def _audit_table_rows(name: str, document: PdfDocument) -> int:
    expected_rows = {"numeric-units": 8, "long-table": 30, "cross-page-table": 8, "caption-table": 15}.get(name)
    if expected_rows is None:
        return 0
    tables = [block for block in document.blocks if block.kind == "table"]
    if len(tables) != len(document.pages):
        raise RuntimeError("PDF table count differs from the independent fixture truth")
    audited = 0
    for table in tables:
        if table.row_count != expected_rows + 1 or table.column_count != 3:
            raise RuntimeError("PDF table dimensions differ from the independent fixture truth")
        grid = {(cell.row_start, cell.column_start): cell.text for cell in table.cells}
        if [grid[(0, column)] for column in range(3)] != ["Station", "Volume (litres)", "Quality code"]:
            raise RuntimeError("PDF column headers differ from the independent fixture truth")
        for row in range(1, expected_rows + 1):
            expected = [f"Station{table.page}R{row}", str(1000 * table.page + row * 7), f"QA{table.page}R{row}"]
            if [grid[(row, column)] for column in range(3)] != expected:
                raise RuntimeError("PDF numerical row/cell integrity mismatch")
            audited += 1
    return audited


def main() -> None:  # noqa: PLR0915 -- Extraction, controls and read-only SQL measurements are recorded together.
    """Persist content-free metrics and extraction snapshots; failed cases remain explicitly failed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("tasks/evidence/pdf-layout-2026-11-22/qualification"))
    parser.add_argument(
        "--resume", action="store_true", help="Reuse hashed extraction snapshots and their original measurements"
    )
    options = parser.parse_args()
    root = options.directory
    inputs = build_corpus(root / "inputs")
    encoding = tiktoken.get_encoding("o200k_base")
    policies = ("page-512-64", "page-768-0", "page-768-64", "page-alone", "plain-recursive")
    previous_report = (
        json.loads((root / "report.json").read_text()) if options.resume and (root / "report.json").is_file() else {}
    )
    previous_cases = {case["name"]: case for case in previous_report.get("cases", [])}
    report = {
        "corpus_kind": "reproducible non-sensitive qualification fixtures; separate real-source live proof required",
        "retrieval": "actual PostgreSQL simple FTS ts_rank_cd; 4096-token evidence budget; no answer generation",
        "cases": [],
        "policies": {},
        "queries": [],
    }
    documents = []
    for path in inputs:
        started = perf_counter()
        case = {"name": path.stem, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        try:
            cached = previous_cases.get(path.stem, {})
            snapshot = root / (path.stem + ".projection.json")
            if cached.get("status") == "passed" and cached.get("sha256") == case["sha256"] and snapshot.is_file():
                document = PdfDocument.model_validate_json(snapshot.read_bytes())
                if document.source_sha256 != case["sha256"]:
                    raise RuntimeError("Cached PDF input hash mismatch")
                case["extraction_artifact_reused"] = True
            else:
                document = extract_pdf(path.read_bytes())
            (root / (path.stem + ".projection.json")).write_text(document.model_dump_json(), encoding="utf-8")
            audited_rows = _audit_table_rows(path.stem, document)
            case.update(
                status="passed",
                pages=len(document.pages),
                tables=sum(b.kind == "table" for b in document.blocks),
                visual_regions=len(document.visual_regions),
                parser_seconds=document.parser_seconds,
                peak_memory_bytes=document.peak_memory_bytes,
                cpu_seconds=document.cpu_seconds,
                visual_processing_status=document.visual_processing_status,
                audited_table_body_rows=audited_rows,
                row_column_integrity="exact"
                if audited_rows
                else "not_audited"
                if any(block.kind == "table" for block in document.blocks)
                else "not_applicable",
            )
            documents.append((path.stem, document))
        except ParsingError as error:
            case.update(status="failed", code=error.code.value, elapsed_seconds=perf_counter() - started)
        report["cases"].append(case)
        (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(case), flush=True)
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not dsn:
        raise RuntimeError("An explicit local PostgreSQL app DSN is required; no metrics are fabricated")
    with psycopg.connect(dsn) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for policy in policies:
            children = []
            split_seconds = []
            duplicates = []
            ious = []
            for name, document in documents:
                started = perf_counter()
                chunks = _controls(document, policy)
                split_seconds.append(perf_counter() - started)
                previous = Counter()
                for ordinal, child in enumerate(chunks):
                    tokens = Counter(encoding.encode_ordinary(child["text"]))
                    intersection, union = sum((tokens & previous).values()), sum((tokens | previous).values())
                    if previous:
                        ious.append(intersection / union if union else 0)
                        duplicates.append(intersection / sum(tokens.values()) if tokens else 0)
                    previous = tokens
                    children.append(
                        {
                            "source": name,
                            "ordinal": ordinal,
                            "page": child["page"],
                            "text": child["text"],
                            "tokens": sum(tokens.values()),
                        }
                    )
            query_results = []
            latencies = []
            payload = json.dumps(children)
            for name, document in documents:
                for gold in _queries(name, document):
                    started = perf_counter()
                    rows = connection.execute(
                        "WITH corpus AS (SELECT * FROM jsonb_to_recordset(%s::jsonb) "
                        "AS c(source text,ordinal int,page int,text text,tokens int)), "
                        "q AS (SELECT plainto_tsquery('simple',%s) AS query) "
                        "SELECT source,ordinal,page,text,tokens,ts_rank_cd(to_tsvector('simple',text),query) AS score "
                        "FROM corpus,q WHERE to_tsvector('simple',text) @@ query "
                        "ORDER BY score DESC,source,ordinal LIMIT 10",
                        (payload, gold["query"]),
                    ).fetchall()
                    latencies.append(perf_counter() - started)
                    admitted = []
                    used = 0
                    for row in rows:
                        if used + row[4] <= 4096:
                            admitted.append(row)
                            used += row[4]
                    matches = [
                        row
                        for row in admitted
                        if row[0] == name and row[2] in gold["pages"] and gold["evidence"] in row[3]
                    ]
                    query_results.append(
                        dict(
                            source=name,
                            **gold,
                            recall5=any(row in matches for row in admitted[:5]),
                            recall10=bool(matches),
                            page_correct=bool(matches),
                            admitted_tokens=used,
                        )
                    )
            for failed in (case for case in report["cases"] if case["status"] == "failed"):
                for query in ("Left section", "Right section"):
                    query_results.append(
                        {
                            "source": failed["name"],
                            "query": query,
                            "recall5": False,
                            "recall10": False,
                            "page_correct": False,
                            "admitted_tokens": 0,
                            "parser_failure": failed["code"],
                        }
                    )
            parsed_times = [case["parser_seconds"] for case in report["cases"] if case["status"] == "passed"]
            report["policies"][policy] = {
                "child_count": len(children),
                "query_count": len(query_results),
                "recall_at_5": statistics.mean(float(q["recall5"]) for q in query_results),
                "recall_at_10": statistics.mean(float(q["recall10"]) for q in query_results),
                "page_citation_accuracy": statistics.mean(float(q["page_correct"]) for q in query_results),
                "adjacent_multiset_token_iou": statistics.mean(ious) if ious else 0,
                "adjacent_repeated_token_share": statistics.mean(duplicates) if duplicates else 0,
                "parse_plus_split_p95_seconds": _p95([a + b for a, b in zip(parsed_times, split_seconds, strict=True)]),
                "query_p95_seconds": _p95(latencies),
            }
            report["queries"].append({"policy": policy, "cases": query_results})
            (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"policies": report["policies"]}), flush=True)


if __name__ == "__main__":
    main()
