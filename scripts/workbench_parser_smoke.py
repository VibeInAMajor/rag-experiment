"""
Exercise the real parser over TCP in a temporary diagnostic Uvicorn process.

This is not an upload route in the main Workbench API or a storage integration test.
Run with Hatch from the repository root; source bodies stay out of evidence and logs.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlparse

import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from apps.workbench.parsing.parser_registry import ParsingError, UploadLimits
from apps.workbench.parsing.parsing import parse_source

_ROOT = Path(__file__).resolve().parents[1]
_ROUTE = "/diagnostic/parse"
_LIMIT = UploadLimits().max_bytes


async def _serve(ready_file: Path, *, qwen_tokenizer_dir: Path | None = None) -> None:
    from apps.workbench.chunking.chunking import ExactModelCounter

    model_counter: ExactModelCounter | None = None
    model_manifest: dict[str, Any] | None = None
    if qwen_tokenizer_dir is not None:
        from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter

        local_counter = await asyncio.to_thread(LocalQwenTokenCounter, qwen_tokenizer_dir)
        model_counter, model_manifest = local_counter, local_counter.manifest()
    token = secrets.token_urlsafe(32)
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.post("/diagnostic/stop")
    async def stop(request: Request) -> JSONResponse:
        if not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
            return JSONResponse(status_code=403, content={"code": "DIAGNOSTIC_ACCESS_DENIED"})
        server.should_exit = True
        return JSONResponse(content={"stopping": True})

    @app.post("/diagnostic/chunks")
    @app.post(_ROUTE)
    async def parse(request: Request) -> JSONResponse:
        if not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
            return JSONResponse(status_code=403, content={"code": "DIAGNOSTIC_ACCESS_DENIED"})
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > _LIMIT + 1:
                return JSONResponse(status_code=413, content={"code": "CONTENT_LIMIT_EXCEEDED"})
            body.extend(chunk)
        started = monotonic()
        try:
            parsed = await asyncio.to_thread(
                parse_source,
                bytes(body),
                safe_basename=request.headers.get("x-source-name", ""),
                declared_type=request.headers.get("content-type"),
            )
            chunk_payload: dict[str, Any] = {}
            if request.url.path == "/diagnostic/chunks":
                from apps.workbench.chunking.chunking import ChunkingInput, ModelTokenAdmission, prepare_chunks

                source = ChunkingInput(
                    parsed_document=parsed,
                    normalized_content=bytes(body).decode("utf-8-sig"),
                    workspace_id="development",
                    source_id="diagnostic",
                    source_version_id="diagnostic-v1",
                    language=request.headers.get("x-source-language", "en"),
                )
                admission = None
                if model_counter is not None:
                    admission = ModelTokenAdmission(
                        counter_revision=model_counter.counter_revision,
                        max_tokens=int(request.headers.get("x-model-token-budget", "32768")),
                        include_heading_path=True,
                    )
                chunks = await asyncio.to_thread(
                    prepare_chunks, source, model_admission=admission, model_counter=model_counter
                )
                chunk_payload["chunks"] = [asdict(chunk) for chunk in chunks]
        except ParsingError as error:
            return JSONResponse(
                status_code=413 if error.code.value == "CONTENT_LIMIT_EXCEEDED" else 422,
                content={"code": error.code.value, "reason": error.reason, "server_pid": os.getpid()},
            )
        except Exception as error:
            from apps.workbench.chunking.chunking_profiles import ChunkingError

            if not isinstance(error, ChunkingError):
                raise
            return JSONResponse(
                status_code=413 if error.code.value == "CONTENT_LIMIT_EXCEEDED" else 422,
                content={"code": error.code.value, "reason": error.reason, "server_pid": os.getpid()},
            )
        return JSONResponse(
            content={
                "parsed": asdict(parsed),
                "server_pid": os.getpid(),
                "duration_ms": round((monotonic() - started) * 1000, 3),
                **chunk_payload,
            }
        )

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, access_log=False, log_level="warning"))
    work = asyncio.create_task(server.serve())
    try:
        while not server.started:
            if work.done():
                await work
                raise RuntimeError("Diagnostic server did not start.")
            await asyncio.sleep(0.02)
        address = server.servers[0].sockets[0].getsockname()
        await asyncio.to_thread(
            ready_file.write_text,
            json.dumps({"port": address[1], "pid": os.getpid(), "token": token, "model_counter": model_manifest}),
            encoding="utf-8",
        )
        await work
    finally:
        server.should_exit = True
        await work


def _wait_ready(process: subprocess.Popen[bytes], ready_file: Path) -> dict[str, Any]:
    deadline = monotonic() + 20
    while monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Diagnostic process exited before readiness.")
        if ready_file.exists():
            try:
                ready = json.loads(ready_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                sleep(0.02)
                continue
            # Windows virtualenv executables may launch a second interpreter process.
            assert ready["pid"] != os.getpid()
            return ready
        sleep(0.05)
    raise TimeoutError("Diagnostic server readiness timed out.")


def _probe_main(client: httpx.Client) -> dict[str, Any]:
    live = client.get("/api/v1/health/live")
    ready = client.get("/api/v1/health/ready")
    capabilities = client.get("/api/v1/capabilities")
    documents = client.get("/api/v1/workspaces/development/documents?limit=1")
    for response in (live, ready, capabilities, documents):
        response.raise_for_status()
    payload = capabilities.json()
    return {
        "live_http": live.status_code,
        "ready_http": ready.status_code,
        "backend_revision": live.json()["backend_revision"],
        "features": payload["features"],
        "profiles": [profile["profile_id"] for profile in payload["profiles"]],
        "database": payload["dependencies"]["database"],
        "corpus_revision": documents.json()["corpus_revision"],
    }


def _stop_server(process: subprocess.Popen[bytes], ready: dict[str, Any] | None) -> None:
    if ready:
        try:
            with httpx.Client(timeout=5, trust_env=False) as client:
                client.post(
                    f"http://127.0.0.1:{ready['port']}/diagnostic/stop",
                    headers={"authorization": f"Bearer {ready['token']}"},
                ).raise_for_status()
        except httpx.HTTPError:
            logging.getLogger(__name__).warning("Diagnostic graceful shutdown failed; waiting before process cleanup.")
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            process.kill()
        process.wait(timeout=5)


def _assert_listener_closed(url: str) -> None:
    deadline = monotonic() + 10
    # Windows can take several seconds to report an actively refused loopback connection.
    with httpx.Client(timeout=5, trust_env=False) as client:
        while monotonic() < deadline:
            try:
                client.get(url + _ROUTE)
            except httpx.ConnectError:
                return
            sleep(0.05)
    raise RuntimeError("Diagnostic listener is still open after shutdown.")


def _send(client: httpx.Client, *, name: str, mime: str, content: bytes) -> httpx.Response:
    return client.post(_ROUTE, headers={"x-source-name": name, "content-type": mime}, content=content)


def _accepted(
    client: httpx.Client, *, label: str, name: str, mime: str, content: bytes, expected_format: str, pid: int
) -> dict[str, Any]:
    response = _send(client, name=name, mime=mime, content=content)
    assert response.status_code == 200, (label, response.status_code, response.json().get("code"))
    payload = response.json()
    assert payload["server_pid"] == pid and pid != os.getpid()
    parsed = payload["parsed"]
    assert parsed["format_id"] == expected_format
    assert parsed["source_sha256"] == sha256(content).hexdigest()
    assert parsed["contract_revision"] == "parsed-elements-v1"
    text = content.decode("utf-8-sig")
    previous = 0
    anchors = set()
    for index, element in enumerate(parsed["elements"]):
        start, end = element["source_span"]["start"], element["source_span"]["end"]
        assert previous <= start < end <= len(text)
        assert not text[previous:start].strip()
        assert element["text"] == text[start:end] and element["order"] == index
        assert element["parent_anchor"] is None or element["parent_anchor"] in anchors
        assert element["element_id"] not in anchors
        anchors.add(element["element_id"])
        previous = end
    assert parsed["elements"] and not text[previous:].strip()
    replay = _send(client, name=name, mime=mime, content=content)
    assert replay.status_code == 200 and replay.json()["server_pid"] == pid and replay.json()["parsed"] == parsed
    if label == "controlled-structure":
        headings = [element for element in parsed["elements"] if element["kind"] == "heading"]
        assert [element["heading_path"] for element in headings] == [["Огляд"], ["Огляд", "Деталі"]]
        assert {"CODE_FENCE_UNPARSED", "TABLE_UNPARSED"} <= set(parsed["warning_codes"])
        assert parsed["classification"]["has_protected_spans"]
    return {
        "case": label,
        "http_status": response.status_code,
        "bytes": len(content),
        "source_sha256": parsed["source_sha256"],
        "format_id": parsed["format_id"],
        "parser_id": parsed["parser_id"],
        "parser_revision": parsed["parser_revision"],
        "detector_revision": parsed["detector_revision"],
        "elements": len(parsed["elements"]),
        "kinds": dict(Counter(element["kind"] for element in parsed["elements"])),
        "warning_codes": parsed["warning_codes"],
        "server_duration_ms": payload["duration_ms"],
        "exact_spans_and_nonblank_coverage": True,
        "deterministic_replay": True,
    }


def _exercise(client: httpx.Client, *, pid: int, sample_dir: Path) -> dict[str, Any]:
    sample = (
        "# Огляд\r\n\r\nПривіт, світе! parser-runtime-content-canary.\r\n\r\n"
        "## Деталі\r\n\r\n| Назва | Значення |\r\n| --- | --- |\r\n| Тест | 42 |\r\n\r\n"
        "```python\r\n# Це не заголовок\r\nprint('not executed')\r\n```\r\n"
    )
    sample_file = sample_dir / "parser-runtime-filename-canary.md"
    sample_file.write_bytes(b"\xef\xbb\xbf" + sample.encode("utf-8"))
    positives = [
        (
            "repository-markdown",
            _ROOT / "docs-website/docs/architecture/content-aware-chunking-strategy.md",
            "text/markdown",
            "markdown",
        ),
        ("repository-text", _ROOT / "test/test_files/txt/doc_1.txt", "text/plain", "plain_text"),
        ("controlled-structure", sample_file, "text/markdown; charset=utf-8", "markdown"),
    ]
    accepted = [
        _accepted(
            client, label=label, name=path.name, mime=mime, content=path.read_bytes(), expected_format=fmt, pid=pid
        )
        for label, path, mime, fmt in positives
    ]
    accepted.append(
        _accepted(
            client,
            label="exact-one-mib",
            name="limit.txt",
            mime="text/plain",
            content=b"a" * _LIMIT,
            expected_format="plain_text",
            pid=pid,
        )
    )
    negatives = [
        ("disguised-pdf", "file.txt", "text/plain", b"%PDF-1.7\n", "FORMAT_MISMATCH"),
        (
            "unqualified-office",
            "file.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04",
            "PARSER_UNAVAILABLE",
        ),
        ("unknown-archive", "file.zip", "application/zip", b"PK\x03\x04", "UNSUPPORTED_FORMAT"),
        ("mime-conflict", "file.txt", "application/pdf", b"text", "FORMAT_MISMATCH"),
        ("traversal-name", "../file.txt", "text/plain", b"text", "FORMAT_MISMATCH"),
        ("invalid-utf8", "file.txt", "text/plain", b"\xffbroken", "FORMAT_MISMATCH"),
        ("empty-source", "file.md", "text/markdown", b" \n\t", "EMPTY_EXTRACTION"),
        ("over-one-mib", "file.txt", "text/plain", b"a" * (_LIMIT + 1), "CONTENT_LIMIT_EXCEEDED"),
        ("over-element-budget", "file.txt", "text/plain", b"a\n\n" * 4097, "CONTENT_LIMIT_EXCEEDED"),
    ]
    rejected = []
    for label, name, mime, content, code in negatives:
        response = _send(client, name=name, mime=mime, content=content)
        assert response.status_code == (413 if code == "CONTENT_LIMIT_EXCEEDED" else 422), label
        payload = response.json()
        assert payload["code"] == code and payload["server_pid"] == pid, label
        assert "parsed" not in payload
        rejected.append({"case": label, "http_status": response.status_code, "code": code, "reason": payload["reason"]})
    return {"accepted": accepted, "rejected": rejected, "http_parse_requests": len(accepted) * 2 + len(rejected)}


def _boundary_metrics(content: str, chunks: list[dict[str, Any]], *, language: str) -> dict[str, Any]:
    from apps.workbench.chunking import chunking_adapters as adapters
    from apps.workbench.chunking.chunking_profiles import ChunkingProfile, DocumentFeatures, resolve_profile
    from apps.workbench.parsing.parser_registry import ElementKind, FormatId

    def trim_end(position: int) -> int:
        while position > 0 and content[position - 1].isspace():
            position -= 1
        return position

    cuts = [trim_end(chunk["source_span"]["end"]) for chunk in chunks if chunk["source_span"]["end"] < len(content)]
    paragraphs = {trim_end(match.start()) for match in re.finditer(r"(?:\r\n|\r|\n)[ \t]*(?:\r\n|\r|\n)", content)}
    metrics: dict[str, Any] = {
        "internal_cuts": len(cuts),
        "cuts_at_paragraph_ends": sum(cut in paragraphs for cut in cuts),
        "source_tokens": adapters.count_tokens(content),
        "prepared_tokens": sum(chunk["effective_size"] for chunk in chunks),
        "word_counts": [len(chunk["content"].split()) for chunk in chunks],
    }
    if language in {"en", "ru"}:
        decision = resolve_profile(
            DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,), language=language),
            profile=ChunkingProfile(),
            resources=adapters.inspect_chunking_resources(),
        )
        sentence_splitter: Any = adapters._splitter(decision).nltk_tokenizer
        boundaries = {trim_end(sentence["end"]) for sentence in sentence_splitter.split_sentences(content)}
        metrics["cuts_at_nltk_sentence_ends"] = sum(cut in boundaries for cut in cuts)
    return metrics


def _model_budget_negatives(client: httpx.Client, cases: list[dict[str, Any]], *, pid: int) -> list[dict[str, Any]]:
    russian = next(case for case in cases if case["language"] == "ru")
    russian_content = "".join(part["text"] * part["repeat"] for part in russian["parts"])
    outcomes = []
    for label, text, budget, language in (
        ("real-qwen-one-token-overflow", "Real local Qwen admission includes its special token.", 1, "en"),
        ("real-qwen-500-token-russian-overflow", russian_content, 500, "ru"),
    ):
        response = client.post(
            "/diagnostic/chunks",
            content=text.encode("utf-8"),
            headers={
                "x-source-name": "budget.txt",
                "content-type": "text/plain",
                "x-model-token-budget": str(budget),
                "x-source-language": language,
            },
        )
        payload = response.json()
        assert response.status_code == 422 and payload["code"] == "MODEL_TOKEN_LIMIT_EXCEEDED"
        assert payload["server_pid"] == pid
        outcomes.append({"case": label, "http_status": 422, "code": payload["code"]})
    return outcomes


def _exercise_chunks(client: httpx.Client, *, pid: int, qwen_tokenizer_dir: Path | None = None) -> dict[str, Any]:
    from apps.workbench.chunking.chunking_adapters import count_tokens

    local_counter = None
    if qwen_tokenizer_dir is not None:
        from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter

        local_counter = LocalQwenTokenCounter(qwen_tokenizer_dir)

    manifest = json.loads(
        (_ROOT / "apps/workbench/chunking/tests/fixtures/chunking/manifest.json").read_text(encoding="utf-8")
    )
    outcomes = []
    requests_count = 0
    for case in manifest["cases"]:
        content = "".join(part["text"] * part["repeat"] for part in case["parts"])
        headers = {
            "x-source-name": case["filename"],
            "x-source-language": case["language"],
            "content-type": "text/markdown" if case["filename"].endswith(".md") else "text/plain",
        }
        response = client.post("/diagnostic/chunks", content=content.encode("utf-8"), headers=headers)
        requests_count += 1
        payload = response.json()
        assert payload["server_pid"] == pid
        if case.get("expected_error"):
            assert response.status_code == 422 and payload["code"] == case["expected_error"]
            outcomes.append({"case": case["case_id"], "http_status": response.status_code, "code": payload["code"]})
            continue
        assert response.status_code == 200, (case["case_id"], payload.get("code"))
        chunks = payload["chunks"]
        covered = 0
        for chunk in chunks:
            start, end = chunk["source_span"]["start"], chunk["source_span"]["end"]
            assert content[start:end] == chunk["content"] and not content[covered:start].strip()
            assert covered < end and chunk["effective_size"] == count_tokens(chunk["content"]) <= 500
            assert 0 <= chunk["overlap_tokens"] <= 50
            if local_counter is not None:
                context = " > ".join(chunk["heading_path"]) + "\n\n" if chunk["heading_path"] else ""
                assert chunk["length_model_token"] == local_counter.count_tokens(context + chunk["content"])
                assert chunk["model_counter_revision"] == local_counter.counter_revision
                assert chunk["length_tiktoken_model_input"] == count_tokens(context + chunk["content"])
            covered = end
        assert chunks and not content[covered:].strip()
        replay = client.post("/diagnostic/chunks", content=content.encode("utf-8"), headers=headers)
        requests_count += 1
        assert replay.status_code == 200 and replay.json()["chunks"] == chunks
        assert replay.json()["server_pid"] == pid
        outcomes.append(
            {
                "case": case["case_id"],
                "http_status": 200,
                "source_sha256": sha256(content.encode()).hexdigest(),
                "chunk_count": len(chunks),
                "length_tiktoken": [chunk["effective_size"] for chunk in chunks],
                "actual_overlap_tokens": [chunk["overlap_tokens"] for chunk in chunks],
                "length_model_token": [chunk["length_model_token"] for chunk in chunks],
                "length_tiktoken_model_input": [chunk["length_tiktoken_model_input"] for chunk in chunks],
                "model_minus_tiktoken_same_input": (
                    [chunk["length_model_token"] - chunk["length_tiktoken_model_input"] for chunk in chunks]
                    if local_counter is not None
                    else None
                ),
                "model_minus_tiktoken": (
                    [chunk["length_model_token"] - chunk["effective_size"] for chunk in chunks]
                    if local_counter is not None
                    else None
                ),
                "processing_fingerprint": chunks[0]["processing_fingerprint"],
                "decision": chunks[0]["decision"],
                "warning_codes": sorted({code for chunk in chunks for code in chunk["warning_codes"]}),
                "exact_source_coverage": True,
                "deterministic_replay": True,
                "server_duration_ms": payload["duration_ms"],
                "boundary_metrics": (
                    _boundary_metrics(content, chunks, language=case["language"])
                    if not case["filename"].endswith(".md")
                    else None
                ),
            }
        )
    for case, content in (
        ("oversized-fence", "```python\n" + "print(42)\n" * 600 + "```\n"),
        ("oversized-table", "| A | B |\n| --- | --- |\n" + "| cell | value |\n" * 600),
    ):
        response = client.post(
            "/diagnostic/chunks",
            content=content.encode(),
            headers={"x-source-name": "overflow.md", "content-type": "text/markdown"},
        )
        requests_count += 1
        payload = response.json()
        assert response.status_code == 413 and payload["code"] == "CONTENT_LIMIT_EXCEEDED"
        assert payload["reason"] == "PROTECTED_SPAN_OVERFLOW" and payload["server_pid"] == pid
        outcomes.append({"case": case, "http_status": 413, "code": payload["code"], "reason": payload["reason"]})
    for language in ("zh", "ja", "th"):
        response = client.post(
            "/diagnostic/chunks",
            content=b"This source does not select an unsupported locale.",
            headers={"x-source-name": "scope.txt", "content-type": "text/plain", "x-source-language": language},
        )
        requests_count += 1
        payload = response.json()
        assert response.status_code == 422 and payload["code"] == "UNSUPPORTED_LANGUAGE"
        assert payload["server_pid"] == pid
        outcomes.append({"case": f"unsupported-locale-{language}", "http_status": 422, "code": payload["code"]})
    if local_counter is not None:
        model_failures = _model_budget_negatives(client, manifest["cases"], pid=pid)
        outcomes.extend(model_failures)
        requests_count += len(model_failures)
    return {
        "chunking": {
            "outcomes": outcomes,
            "http_requests": requests_count,
            "model_token_counter_tested": local_counter is not None,
            "model_counter": local_counter.manifest() if local_counter is not None else None,
            "diagnostic_model_budget": 32768 if local_counter is not None else None,
            "served_tei_tokenizer_parity_tested": False,
        }
    }


def _run(*, main_url: str, evidence: Path, chunking: bool = False, qwen_tokenizer_dir: Path | None = None) -> None:
    report: dict[str, Any] = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "scope": "temporary-diagnostic-uvicorn-over-real-tcp",
        "main_api_parser_route_tested": False,
        "storage_ingestion_tested": False,
    }
    with httpx.Client(base_url=main_url, timeout=15, trust_env=False) as main_client:
        report["main_api_before"] = _probe_main(main_client)
        with tempfile.TemporaryDirectory(prefix="workbench-parser-smoke-") as temporary:
            folder = Path(temporary)
            ready_file = folder / "ready.json"
            log_file = folder / "server.log"
            with log_file.open("wb") as log:
                child_command = [sys.executable, "-m", "scripts.workbench_parser_smoke", "--serve", str(ready_file)]
                if qwen_tokenizer_dir is not None:
                    child_command.extend(["--qwen-tokenizer-dir", str(qwen_tokenizer_dir)])
                process = subprocess.Popen(
                    child_command,
                    cwd=_ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                ready = None
                try:
                    ready = _wait_ready(process, ready_file)
                    url = f"http://127.0.0.1:{ready['port']}"
                    report["diagnostic_server"] = {
                        "url": url,
                        "pid": ready["pid"],
                        "launcher_pid": process.pid,
                        "parent_pid": os.getpid(),
                    }
                    with httpx.Client(
                        base_url=url, timeout=15, trust_env=False, headers={"authorization": f"Bearer {ready['token']}"}
                    ) as client:
                        report.update(_exercise(client, pid=ready["pid"], sample_dir=folder))
                        if chunking:
                            report.update(
                                _exercise_chunks(client, pid=ready["pid"], qwen_tokenizer_dir=qwen_tokenizer_dir)
                            )
                finally:
                    _stop_server(process, ready)
                _assert_listener_closed(url)
                report["diagnostic_server_stopped"] = process.poll() is not None
                report["diagnostic_listener_closed"] = True
            diagnostic_log = log_file.read_text(encoding="utf-8")
            assert "parser-runtime-content-canary" not in diagnostic_log
            assert "parser-runtime-filename-canary" not in diagnostic_log
            assert "SECRET_FIXTURE_CONTENT" not in diagnostic_log
            report["log_content_and_filename_canaries_absent"] = True
            report["diagnostic_log"] = diagnostic_log
        report["main_api_after"] = _probe_main(main_client)
        assert report["main_api_before"] == report["main_api_after"]
        report["main_api_readiness_capabilities_and_corpus_unchanged"] = True
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "result": "passed",
                "http_parse_requests": report["http_parse_requests"],
                "http_chunking_requests": report.get("chunking", {}).get("http_requests", 0),
                "evidence": str(evidence),
            }
        )
    )


def main() -> None:
    """Run the local runtime smoke or its private owned child server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-url", default="http://127.0.0.1:8011")
    parser.add_argument("--evidence", type=Path, default=_ROOT / "tasks/evidence/parser-runtime-2026-11-22.json")
    parser.add_argument("--serve", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--chunking", action="store_true", help="Also exercise the verified parser-to-chunk pipeline.")
    parser.add_argument(
        "--qwen-tokenizer-dir", type=Path, help="Explicit local directory for the pinned Qwen tokenizer."
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.serve:
        asyncio.run(_serve(args.serve, qwen_tokenizer_dir=args.qwen_tokenizer_dir))
        return
    url = urlparse(args.main_url)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("The main API probe requires a local loopback HTTP URL.")
    if args.qwen_tokenizer_dir is not None and not args.chunking:
        parser.error("Local Qwen admission requires --chunking.")
    _run(
        main_url=args.main_url,
        evidence=args.evidence,
        chunking=args.chunking,
        qwen_tokenizer_dir=args.qwen_tokenizer_dir,
    )


if __name__ == "__main__":
    main()
