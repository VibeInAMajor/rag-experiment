import { afterEach, describe, expect, it, vi } from "vitest";
import { createWorkbenchApiClient } from "./client";
import { contractRevision } from "./contracts";
import {
  decodeActiveChunkPage,
  decodeCapabilities,
  decodeDocumentDetail,
  decodeDocumentPage,
  decodeIngestionJob,
} from "./decode";

const meta = {
  contract_revision: contractRevision,
  request_id: "request-1",
  trace_id: "trace-1",
};
const scope = {
  ...meta,
  workspace_id: "development",
  corpus_revision: "corpus-1",
};
const document = {
  source_id: "source-1",
  title: "<script>inert</script>",
  media_type: "text/plain",
  status: "ready",
  active_version_id: "version-1",
  chunk_count: 1,
  updated_at: "2026-11-23T10:00:00+00:00",
};
const detail = {
  ...scope,
  ...document,
  warnings: [],
  original_content_available: false,
};
const chunk = {
  chunk_id: "chunk-1",
  order: 0,
  content: "<img onerror=alert(1)>",
  content_hash: "a".repeat(64),
  section_path: [],
  metadata: { line_start: 1 },
};
const chunkPage = {
  ...scope,
  source_id: "source-1",
  source_version_id: "version-1",
  items: [chunk],
  next_cursor: null,
};
const upload = {
  ...scope,
  source_id: "source-1",
  source_version_id: "version-1",
  job_id: "job-1",
  outcome: "created",
  status: "completed",
  chunk_count: 1,
  stages: [
    { stage: "parsing", duration_ms: 1 },
    { stage: "chunking", duration_ms: 2 },
    { stage: "publication", duration_ms: 3 },
  ],
  replayed: false,
};
const job = {
  ...meta,
  workspace_id: "development",
  job_id: "job-1",
  source_id: "source-1",
  source_version_id: "version-1",
  reserved_version_id: "version-1",
  status: "completed",
  stage: "completed",
  retryable: false,
  error_code: null,
  chunk_count: 1,
  outcome: "created",
  created_at: document.updated_at,
  updated_at: document.updated_at,
  finished_at: document.updated_at,
  stages: upload.stages,
};
const caps = {
  ...meta,
  backend_revision: "backend-1",
  deployment_mode: "single_workspace_dev",
  service_state: "running",
  profiles: [],
  features: {
    documents: true,
    search: false,
    upload: true,
    document_details: true,
    jobs: true,
  },
  dependencies: { database: { status: "empty" } },
  pdf_ingestion: {
    available: false,
    text_layer: false,
    page_provenance: false,
    table_rows: false,
    original_evidence: false,
    ocr: false,
    visual_understanding: false,
    visual_detection_coverage: "unverified",
    max_bytes: 8388608,
    max_pages: 32,
  },
};

function json(
  value: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": "request-1",
      ...headers,
    },
  });
}
function setup(value: unknown = upload, status = 201) {
  const fetchImpl = vi
    .fn<typeof fetch>()
    .mockImplementation(async () => json(value, status));
  return { client: createWorkbenchApiClient({ fetchImpl }), fetchImpl };
}
function operation(
  file = new File(["hello"], "example.txt", { type: "text/plain" }),
) {
  return { file, idempotencyKey: "same-operation-key" };
}
afterEach(() => vi.useRealTimers());

describe("live document runtime contracts", () => {
  it("retains all capability fields and fails closed for missing or malformed required flags", () => {
    expect(decodeCapabilities(caps).features).toEqual(caps.features);
    expect(decodeCapabilities(caps).pdf_ingestion).toEqual(caps.pdf_ingestion);
    for (const value of [undefined, null, "true", 1]) {
      expect(() =>
        decodeCapabilities({
          ...caps,
          features: { ...caps.features, upload: value },
        }),
      ).toThrow();
      expect(() =>
        decodeCapabilities({ ...caps, pdf_ingestion: value }),
      ).toThrow();
    }
    for (const override of [
      { ocr: true },
      { max_bytes: 1 },
      { max_pages: 33 },
      { available: true },
    ])
      expect(() =>
        decodeCapabilities({
          ...caps,
          pdf_ingestion: { ...caps.pdf_ingestion, ...override },
        }),
      ).toThrow();
  });

  it("accepts empty pages, optional metadata, inert content and omitted/null page", () => {
    expect(
      decodeDocumentPage(
        { ...scope, items: [], next_cursor: null },
        "development",
      ).items,
    ).toEqual([]);
    expect(
      decodeDocumentDetail(
        { ...detail, parser: null, source_bytes: 0 },
        "development",
        "source-1",
      ).source_bytes,
    ).toBe(0);
    expect(
      decodeActiveChunkPage(chunkPage, "development", "source-1").items[0],
    ).not.toHaveProperty("source_version_id");
    expect(
      decodeActiveChunkPage(
        { ...chunkPage, items: [{ ...chunk, page: null }] },
        "development",
        "source-1",
      ).items[0].page,
    ).toBeNull();
    expect(
      decodeIngestionJob(job, "development", "job-1").reserved_version_id,
    ).toBe("version-1");
    expect(
      decodeIngestionJob(
        {
          ...job,
          status: "failed",
          stage: "publishing",
          outcome: null,
          source_version_id: null,
        },
        "development",
        "job-1",
      ).stage,
    ).toBe("publishing");
  });

  it.each([
    { updated_at: "yesterday" },
    { updated_at: "2026-02-30T10:00:00Z" },
    { chunk_count: -1 },
    { language_policy: "auto" },
    { original_content_available: true },
    { source_bytes: 1.2 },
    { parser: { bad: Infinity } },
  ])("rejects malformed details %#", (override) => {
    expect(() =>
      decodeDocumentDetail(
        { ...detail, ...override },
        "development",
        "source-1",
      ),
    ).toThrow();
  });

  it("validates workspace, source, version, revision and duplicate/order boundaries", () => {
    expect(() =>
      decodeDocumentPage(
        { ...scope, items: [document, document], next_cursor: null },
        "development",
      ),
    ).toThrow();
    expect(() => decodeDocumentDetail(detail, "foreign", "source-1")).toThrow();
    expect(() =>
      decodeDocumentDetail(detail, "development", "source-2"),
    ).toThrow();
    expect(() =>
      decodeDocumentDetail(detail, "development", "source-1", {
        expectedVersionId: "stale",
      }),
    ).toThrow();
    expect(() =>
      decodeActiveChunkPage(chunkPage, "development", "source-1", {
        expectedCorpusRevision: "stale",
      }),
    ).toThrow();
    expect(() =>
      decodeActiveChunkPage(
        { ...chunkPage, items: [{ ...chunk, order: -1 }] },
        "development",
        "source-1",
      ),
    ).toThrow();
    expect(() =>
      decodeActiveChunkPage(
        { ...chunkPage, items: [{ ...chunk, content_hash: undefined }] },
        "development",
        "source-1",
      ),
    ).toThrow();
    expect(() =>
      decodeIngestionJob(
        { ...job, updated_at: "2025-01-01T00:00:00Z" },
        "development",
        "job-1",
      ),
    ).toThrow();
    expect(() => decodeIngestionJob(job, "development", "other-job")).toThrow();
  });
});

describe("shared document transport", () => {
  it("passes real FormData with a browser boundary and accepts created 201", async () => {
    const { client, fetchImpl } = setup();
    expect(
      await client.uploadDocument("development", operation()),
    ).toMatchObject({ outcome: "created", replayed: false });
    const init = fetchImpl.mock.calls[0][1]!;
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe(
      "same-operation-key",
    );
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    expect(init.method).toBe("POST");
  });

  it("preserves the supplied key and exact replacement fields for replay", async () => {
    const { client, fetchImpl } = setup(
      { ...upload, outcome: "updated", replayed: true },
      200,
    );
    const body = {
      ...operation(),
      sourceId: "source-1",
      expectedActiveVersionId: "version-1",
    };
    await client.uploadDocument("development", body);
    await client.uploadDocument("development", body);
    for (const call of fetchImpl.mock.calls) {
      expect(new Headers(call[1]?.headers).get("Idempotency-Key")).toBe(
        body.idempotencyKey,
      );
      const form = call[1]?.body as FormData;
      expect(form.get("source_id")).toBe("source-1");
      expect(form.get("expected_active_version_id")).toBe("version-1");
    }
  });

  it("uses the qualified MIME when the operating system supplies no file type", async () => {
    const { client, fetchImpl } = setup();
    const file = new File(["print('hello')"], "example.py");
    await client.uploadDocument("development", operation(file));
    const sent = (fetchImpl.mock.calls[0][1]?.body as FormData).get("file");
    expect(sent).toBeInstanceOf(File);
    expect((sent as File).type).toBe("text/x-python");
    expect(await (sent as File).text()).toBe(await file.text());
    expect(file.type).toBe("");
  });

  it.each([
    [200, { outcome: "created", replayed: false }],
    [201, { outcome: "created", replayed: true }],
    [201, { outcome: "updated" }],
    [202, {}],
    [201, { stages: [{ stage: "parsing", duration_ms: -1 }] }],
    [201, { stages: [{ stage: "parsing", duration_ms: null }] }],
  ])(
    "rejects contradictory upload HTTP/body %s %#",
    async (status, override) => {
      const { client } = setup({ ...upload, ...override }, status);
      await expect(
        client.uploadDocument("development", operation()),
      ).rejects.toMatchObject({ kind: "protocol" });
    },
  );

  it("supports created replay 200 and validates all GET endpoint contexts", async () => {
    const { client, fetchImpl } = setup({ ...upload, replayed: true }, 200);
    expect(
      (await client.uploadDocument("development", operation())).replayed,
    ).toBe(true);
    fetchImpl.mockResolvedValueOnce(
      json({ ...scope, items: [document], next_cursor: "signed.cursor" }),
    );
    await client.listDocuments("development", {
      limit: 1,
      cursor: "signed.cursor",
      expectedCorpusRevision: "corpus-1",
    });
    expect(fetchImpl.mock.calls.at(-1)?.[0]).toBe(
      "/api/v1/workspaces/development/documents?limit=1&cursor=signed.cursor",
    );
    fetchImpl.mockResolvedValueOnce(json(detail));
    await client.getDocumentDetail("development", "source-1");
    fetchImpl.mockResolvedValueOnce(json(chunkPage));
    await client.listActiveChunks("development", "source-1", {
      expectedVersionId: "version-1",
    });
    fetchImpl.mockResolvedValueOnce(json(job));
    await client.getIngestionJob("development", "job-1");
    fetchImpl.mockResolvedValueOnce(json(job, 201));
    await expect(
      client.getIngestionJob("development", "job-1"),
    ).rejects.toMatchObject({ kind: "protocol" });
    await expect(
      client.listDocuments("development", { limit: 101 }),
    ).rejects.toMatchObject({ code: "INVALID_PAGE_LIMIT" });
    await expect(
      client.listDocuments("development", { cursor: "x".repeat(513) }),
    ).rejects.toMatchObject({ kind: "protocol" });
    await expect(
      client.getDocumentDetail("../foreign", "source-1"),
    ).rejects.toMatchObject({ kind: "protocol" });
  });

  it("enforces qualified formats, MIME aliases and per-format caps before fetching", async () => {
    const { client, fetchImpl } = setup();
    for (const file of [
      new File(["x"], "bad.csv"),
      new File(["x"], "bad.txt", { type: "application/pdf" }),
      new File([new Uint8Array(1048577)], "large.py"),
      new File(["x"], "file.pdf", { type: "application/pdf" }),
    ])
      await expect(
        client.uploadDocument("development", operation(file)),
      ).rejects.toMatchObject({ kind: "configuration" });
    await expect(
      client.uploadDocument("development", {
        ...operation(),
        sourceId: "source-1",
      }),
    ).rejects.toMatchObject({ code: "INVALID_UPDATE_FIELDS" });
    await expect(
      client.uploadDocument("development", {
        ...operation(),
        idempotencyKey: "short",
      }),
    ).rejects.toMatchObject({ code: "INVALID_IDEMPOTENCY_KEY" });
    expect(fetchImpl).not.toHaveBeenCalled();
    await client.uploadDocument("development", {
      ...operation(
        new File([new Uint8Array(8388608)], "file.pdf", {
          type: "application/pdf",
        }),
      ),
      pdfAvailable: true,
    });
    await expect(
      client.uploadDocument("development", {
        ...operation(
          new File([new Uint8Array(8388609)], "file.pdf", {
            type: "application/pdf",
          }),
        ),
        pdfAvailable: true,
      }),
    ).rejects.toMatchObject({ code: "CONTENT_LIMIT_EXCEEDED" });
    for (const [name, type] of [
      ["file.py", "text/x-python"],
      ["file.md", "text/x-markdown"],
      ["file.markdown", "text/plain"],
    ])
      await client.uploadDocument(
        "development",
        operation(new File(["x"], name, { type })),
      );
  });

  it.each([400, 404, 409, 413, 415, 429, 503, 504])(
    "retains error job correlation for HTTP %s",
    async (status) => {
      const { client } = setup(
        {
          ...meta,
          error: {
            code: "INGESTION_FAILED",
            message: "Safe error",
            retryable: true,
            http_status: status,
            job_id: "job-1",
          },
        },
        status,
      );
      await expect(
        client.uploadDocument("development", operation()),
      ).rejects.toMatchObject({
        httpStatus: status,
        jobId: "job-1",
        requestId: "request-1",
        traceId: "trace-1",
      });
    },
  );

  it("rejects malformed content type and request correlation", async () => {
    const { client, fetchImpl } = setup();
    fetchImpl.mockResolvedValueOnce(
      json(upload, 201, { "Content-Type": "text/html" }),
    );
    await expect(
      client.uploadDocument("development", operation()),
    ).rejects.toMatchObject({ kind: "protocol" });
    fetchImpl.mockResolvedValueOnce(
      json(upload, 201, { "X-Request-ID": "wrong" }),
    );
    await expect(
      client.uploadDocument("development", operation()),
    ).rejects.toMatchObject({ kind: "protocol" });
  });

  it("uses the dedicated 240s upload deadline and local abort without inventing server IDs", async () => {
    vi.useFakeTimers();
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockImplementation(() => new Promise(() => {}));
    const client = createWorkbenchApiClient({ fetchImpl });
    const pending = client.uploadDocument("development", operation());
    const rejected = expect(pending).rejects.toMatchObject({
      kind: "timeout",
      jobId: undefined,
      traceId: undefined,
    });
    await vi.advanceTimersByTimeAsync(239999);
    expect(fetchImpl.mock.calls[0][1]?.signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await rejected;
    const controller = new AbortController();
    const stopped = client.uploadDocument("development", operation(), {
      signal: controller.signal,
    });
    controller.abort();
    await expect(stopped).rejects.toMatchObject({
      kind: "cancelled",
      jobId: undefined,
    });
    fetchImpl.mockRejectedValueOnce(new TypeError("offline"));
    await expect(
      client.uploadDocument("development", operation()),
    ).rejects.toMatchObject({ code: "NETWORK_ERROR", jobId: undefined });
    expect(() =>
      createWorkbenchApiClient({ uploadTimeoutMs: 240001 }),
    ).toThrow();
  });
});
