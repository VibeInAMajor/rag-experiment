// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useLiveDocuments } from "./useLiveDocuments";
import { WorkbenchApiError } from "../api/client";
import type {
  ActiveChunkPageResponse,
  BackendCapabilities,
  DocumentDetail,
  DocumentPage,
  IngestionJobResponse,
  IngestionResponse,
} from "../api/contracts";
import {
  LiveDocumentsRequests,
  validateDocumentFile,
  type DocumentsClient,
  type LiveDocumentsContext,
} from "../domain/liveDocuments";

const meta = {
  contract_revision: "rag-api-v1.0" as const,
  request_id: "request-1",
  trace_id: "trace-1",
};
const capabilities: BackendCapabilities = {
  ...meta,
  backend_revision: "backend-1",
  deployment_mode: "single_workspace_dev",
  service_state: "running",
  profiles: [],
  features: {
    documents: true,
    search: true,
    upload: true,
    document_details: true,
    jobs: true,
  },
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
  dependencies: { database: { status: "ready", workspace_id: "workspace-1" } },
};
function page(
  source = "source-1",
  revision = "corpus-1",
  next: string | null = null,
): DocumentPage {
  return {
    ...meta,
    workspace_id: "workspace-1",
    corpus_revision: revision,
    items: source
      ? [
          {
            source_id: source,
            title: source,
            media_type: "text/plain",
            status: "ready",
            active_version_id: `${source}-v1`,
            chunk_count: 1,
            updated_at: "2026-11-23T12:00:00Z",
          },
        ]
      : [],
    next_cursor: next,
  };
}
function detail(
  source = "source-1",
  revision = "corpus-1",
  version = `${source}-v1`,
): DocumentDetail {
  return {
    ...meta,
    ...page(source, revision).items[0],
    source_id: source,
    workspace_id: "workspace-1",
    corpus_revision: revision,
    active_version_id: version,
    warnings: [],
    original_content_available: false,
  };
}
function chunks(
  source = "source-1",
  revision = "corpus-1",
  version = `${source}-v1`,
  next: string | null = null,
): ActiveChunkPageResponse {
  return {
    ...meta,
    workspace_id: "workspace-1",
    source_id: source,
    source_version_id: version,
    corpus_revision: revision,
    items: [
      {
        chunk_id: `${source}-chunk-1`,
        order: 0,
        content: "<script>inert source text</script>",
        content_hash: "hash-1",
        page: null,
        section_path: [],
        metadata: {},
      },
    ],
    next_cursor: next,
  };
}
function uploaded(): IngestionResponse {
  return {
    ...meta,
    workspace_id: "workspace-1",
    source_id: "uploaded-1",
    source_version_id: "uploaded-1-v1",
    job_id: "job-1",
    status: "completed",
    outcome: "created",
    chunk_count: 1,
    corpus_revision: "corpus-2",
    stages: [],
    replayed: false,
  };
}
function job(): IngestionJobResponse {
  return {
    ...meta,
    workspace_id: "workspace-1",
    job_id: "job-1",
    source_id: "uploaded-1",
    source_version_id: "uploaded-1-v1",
    reserved_version_id: "uploaded-1-v1",
    status: "completed",
    stage: "completed",
    retryable: false,
    error_code: null,
    chunk_count: 1,
    outcome: "created",
    created_at: "2026-11-23T12:00:00Z",
    updated_at: "2026-11-23T12:00:01Z",
    finished_at: "2026-11-23T12:00:01Z",
    stages: [],
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
async function settle() {
  for (let index = 0; index < 12; index++) await Promise.resolve();
}
function setup(overrides: Partial<DocumentsClient> = {}) {
  let context: LiveDocumentsContext = {
    mode: "live",
    workspaceId: "workspace-1",
    capabilities,
  };
  const client = {
    listDocuments: vi.fn(async () => page()),
    getDocumentDetail: vi.fn(async (_workspace: string, source: string) =>
      detail(source),
    ),
    listActiveChunks: vi.fn(async (_workspace: string, source: string) =>
      chunks(source),
    ),
    uploadDocument: vi.fn(async () => uploaded()),
    getIngestionJob: vi.fn(async () => job()),
    ...overrides,
  };
  const onPublished = vi.fn();
  const requests = new LiveDocumentsRequests(
    client,
    () => context,
    vi.fn(),
    onPublished,
  );
  return {
    requests,
    client,
    onPublished,
    setContext: (patch: Partial<LiveDocumentsContext>) => {
      context = { ...context, ...patch };
      requests.contextChanged();
    },
  };
}
const textFile = () =>
  new File(["trusted test bytes"], "source.txt", { type: "text/plain" });

describe("live document snapshot lifecycle", () => {
  it("loads persisted detail and version-enveloped chunks without Preview", async () => {
    const { requests, client } = setup();
    requests.start();
    await settle();
    expect(requests.state.status).toBe("ready");
    expect(requests.state.detail?.source_id).toBe("source-1");
    expect(requests.state.chunks[0].content).toBe(
      "<script>inert source text</script>",
    );
    expect(client.listDocuments).toHaveBeenCalledTimes(1);
    expect(client.listActiveChunks).toHaveBeenCalledWith(
      "workspace-1",
      "source-1",
      expect.objectContaining({
        expectedVersionId: "source-1-v1",
        expectedCorpusRevision: "corpus-1",
        limit: 50,
      }),
    );
  });
  it("reports real empty and unsupported states", async () => {
    const { requests, setContext } = setup({
      listDocuments: vi.fn(async () => page("")),
    });
    requests.start();
    await settle();
    expect(requests.state.status).toBe("empty");
    expect(requests.state.documents).toEqual([]);
    setContext({
      capabilities: {
        ...capabilities,
        features: { ...capabilities.features, documents: false },
      },
    });
    expect(requests.state.status).toBe("unavailable");
    expect(requests.state.chunks).toEqual([]);
  });
  it("aborts and ignores stale list success when transport ignores abort", async () => {
    const pending = deferred<DocumentPage>();
    const list = vi
      .fn()
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValue(page("", "corpus-2"));
    const { requests, setContext } = setup({ listDocuments: list });
    requests.start();
    const oldSignal = list.mock.calls[0][1].signal;
    setContext({ workspaceId: "workspace-2" });
    pending.resolve(page());
    await settle();
    expect(oldSignal.aborted).toBe(true);
    expect(requests.state.documents).toEqual([]);
    expect(requests.state.error?.code).toBe("DOCUMENT_SNAPSHOT_CHANGED");
  });
  it("does not resurrect data after stop and supports strict-mode restart", async () => {
    const old = deferred<DocumentPage>();
    const list = vi
      .fn()
      .mockReturnValueOnce(old.promise)
      .mockResolvedValue(page(""));
    const { requests } = setup({ listDocuments: list });
    requests.start();
    requests.stop(false);
    requests.start();
    await settle();
    old.resolve(page());
    await settle();
    expect(requests.state.status).toBe("empty");
    expect(requests.state.documents).toEqual([]);
  });
  it("never commits stale source detail or chunks under another selection", async () => {
    const pendingDetail = deferred<DocumentDetail>();
    const pendingChunks = deferred<ActiveChunkPageResponse>();
    const { requests } = setup({
      getDocumentDetail: vi
        .fn()
        .mockReturnValueOnce(pendingDetail.promise)
        .mockResolvedValue(detail("source-2")),
      listActiveChunks: vi.fn().mockReturnValue(pendingChunks.promise),
    });
    requests.start();
    await settle();
    await requests.selectSource(null);
    const selecting = requests.selectSource("source-2");
    await settle();
    pendingDetail.resolve(detail());
    pendingChunks.resolve(chunks("source-2"));
    await selecting;
    await settle();
    expect(requests.state.selectedSourceId).toBe("source-2");
    expect(requests.state.detail?.source_id).toBe("source-2");
    expect(requests.state.chunks[0].chunk_id).toBe("source-2-chunk-1");
  });
  it("drops stale chunk replies after mode, corpus or version switches", async () => {
    const pending = deferred<ActiveChunkPageResponse>();
    const { requests, setContext } = setup({
      listActiveChunks: vi.fn().mockReturnValue(pending.promise),
    });
    requests.start();
    await settle();
    setContext({ mode: "preview" });
    pending.resolve(chunks());
    await settle();
    expect(requests.state.status).toBe("idle");
    expect(requests.state.detail).toBeNull();
    expect(requests.state.chunks).toEqual([]);
  });
  it("appends signed pages with stable source deduplication", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(page("source-1", "corpus-1", "cursor-1"))
      .mockResolvedValueOnce({
        ...page("source-2"),
        items: [...page().items, ...page("source-2").items],
      });
    const { requests } = setup({ listDocuments: list });
    requests.start();
    await settle();
    await requests.loadMore();
    expect(requests.state.documents.map((item) => item.source_id)).toEqual([
      "source-1",
      "source-2",
    ]);
    expect(list.mock.calls[1][1]).toMatchObject({
      cursor: "cursor-1",
      expectedCorpusRevision: "corpus-1",
    });
  });
  it("invalid cursor discards old pages and restarts page one exactly once", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(page("source-1", "corpus-1", "expired"))
      .mockRejectedValueOnce(
        new WorkbenchApiError("expired", {
          kind: "http",
          code: "INVALID_CURSOR",
          httpStatus: 400,
        }),
      )
      .mockResolvedValueOnce(page("source-2", "corpus-2"));
    const { requests } = setup({
      listDocuments: list,
      getDocumentDetail: vi.fn(async (_w, source) =>
        detail(source, "corpus-2"),
      ),
      listActiveChunks: vi.fn(async (_w, source) => chunks(source, "corpus-2")),
    });
    requests.start();
    await settle();
    await requests.loadMore();
    expect(list).toHaveBeenCalledTimes(3);
    expect(list.mock.calls[2][1].cursor).toBeUndefined();
    expect(requests.state.documents.map((item) => item.source_id)).toEqual([
      "source-2",
    ]);
    expect(requests.state.notice).toContain("cursor expired");
  });
  it("rejects contradictory version and corpus envelopes", async () => {
    const { requests } = setup({
      listActiveChunks: vi.fn(async () =>
        chunks("source-1", "corpus-1", "wrong-version"),
      ),
    });
    requests.start();
    await settle();
    expect(requests.state.chunks).toEqual([]);
    expect(requests.state.chunksError?.code).toBe("DOCUMENT_SNAPSHOT_CHANGED");
  });
  it("restarts an invalid chunk cursor only once even if the next first page also fails", async () => {
    const listChunks = vi.fn().mockRejectedValue(
      new WorkbenchApiError("expired", {
        kind: "http",
        code: "INVALID_CURSOR",
        httpStatus: 400,
      }),
    );
    const { requests, client } = setup({ listActiveChunks: listChunks });
    requests.start();
    await settle();
    expect(listChunks).toHaveBeenCalledTimes(2);
    expect(client.listDocuments).toHaveBeenCalledTimes(2);
    expect(requests.state.chunks).toEqual([]);
    expect(requests.state.chunksError?.code).toBe("INVALID_CURSOR");
  });
  it("corpus context changes abort and reject old detail while transport ignores abort", async () => {
    const old = deferred<DocumentDetail>();
    const get = vi
      .fn()
      .mockReturnValueOnce(old.promise)
      .mockResolvedValue(detail("source-1", "corpus-2"));
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockResolvedValue(page("source-1", "corpus-2"));
    const { requests, setContext } = setup({
      getDocumentDetail: get,
      listDocuments: list,
      listActiveChunks: vi.fn(async () => chunks("source-1", "corpus-2")),
    });
    requests.start();
    await settle();
    const signal = get.mock.calls[0][2].signal;
    setContext({ corpusRevision: "corpus-2" });
    await settle();
    old.resolve(detail());
    await settle();
    expect(signal.aborted).toBe(true);
    expect(requests.state.detail?.corpus_revision).toBe("corpus-2");
  });
  it("a refresh of changed active version clears the previous chunk snapshot", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(detail())
      .mockResolvedValueOnce(detail("source-1", "corpus-1", "v2"));
    const listChunks = vi
      .fn()
      .mockResolvedValueOnce(chunks())
      .mockResolvedValueOnce(chunks("source-1", "corpus-1", "v2"));
    const { requests } = setup({
      getDocumentDetail: get,
      listActiveChunks: listChunks,
    });
    requests.start();
    await settle();
    const refreshing = requests.refreshSelected();
    expect(requests.state.chunks).toEqual([]);
    await refreshing;
    expect(requests.state.detail?.active_version_id).toBe("v2");
    expect(listChunks.mock.calls[1][2].expectedVersionId).toBe("v2");
  });
});

describe("upload operation identity and durable job status", () => {
  it("invalidates search immediately on publication even if navigation interrupts reconciliation", async () => {
    const reconciliation = deferred<DocumentPage>();
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockReturnValueOnce(reconciliation.promise);
    const { requests, setContext, onPublished } = setup({
      listDocuments: list,
    });
    requests.start();
    await settle();
    requests.chooseFile(textFile());
    const submitting = requests.submitUpload();
    await settle();
    expect(onPublished).toHaveBeenCalledExactlyOnceWith(uploaded());
    setContext({ enabled: false });
    reconciliation.resolve(page("uploaded-1", "corpus-2"));
    await submitting;
    expect(requests.state.documents).toEqual([]);
    expect(requests.state.upload.phase).toBe("succeeded");
    expect(onPublished).toHaveBeenCalledTimes(1);
  });
  it("retries unknown outcome with the exact same file and operation key, then reconciles all server resources", async () => {
    const file = textFile();
    const response = uploaded();
    const upload = vi
      .fn()
      .mockRejectedValueOnce(
        new WorkbenchApiError("timeout", { kind: "timeout", code: "TIMEOUT" }),
      )
      .mockResolvedValueOnce(response);
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(page("uploaded-1", "corpus-2"));
    const { requests, onPublished, client } = setup({
      uploadDocument: upload,
      listDocuments: list,
      getDocumentDetail: vi.fn(async (_w, source) =>
        detail(source, source === "uploaded-1" ? "corpus-2" : "corpus-1"),
      ),
      listActiveChunks: vi.fn(async (_w, source) =>
        chunks(source, source === "uploaded-1" ? "corpus-2" : "corpus-1"),
      ),
    });
    requests.start();
    await settle();
    requests.chooseFile(file);
    const key = requests.state.upload.idempotencyKey;
    await requests.submitUpload();
    expect(requests.state.upload.phase).toBe("unknown");
    expect(requests.state.upload.file).toBe(file);
    await requests.retryUpload();
    expect(upload.mock.calls.map((call) => call[1].idempotencyKey)).toEqual([
      key,
      key,
    ]);
    expect(upload.mock.calls[1][1].file).toBe(file);
    expect(requests.state.upload.response).toBe(response);
    expect(requests.state.upload.error).toBeUndefined();
    expect(requests.state.selectedSourceId).toBe("uploaded-1");
    expect(requests.state.detail?.active_version_id).toBe(
      response.source_version_id,
    );
    expect(requests.state.job?.job_id).toBe(response.job_id);
    expect(client.getIngestionJob).toHaveBeenCalledTimes(1);
    expect(onPublished).toHaveBeenCalledExactlyOnceWith(response);
  });
  it("prevents double submit and does not accept a late successful stopped POST", async () => {
    const pending = deferred<IngestionResponse>();
    const upload = vi.fn().mockReturnValue(pending.promise);
    const { requests, onPublished } = setup({ uploadDocument: upload });
    requests.start();
    await settle();
    requests.chooseFile(textFile());
    const attempt = requests.submitUpload();
    await requests.submitUpload();
    expect(upload).toHaveBeenCalledTimes(1);
    requests.stopUpload();
    pending.resolve(uploaded());
    await attempt;
    expect(requests.state.upload.phase).toBe("unknown");
    expect(requests.state.upload.response).toBeNull();
    expect(onPublished).not.toHaveBeenCalled();
  });
  it("binds replacement to loaded active version and preserves file/key/selection on conflict", async () => {
    const upload = vi.fn().mockRejectedValue(
      new WorkbenchApiError("changed", {
        kind: "http",
        code: "VERSION_CONFLICT",
        httpStatus: 409,
      }),
    );
    const { requests } = setup({ uploadDocument: upload });
    requests.start();
    await settle();
    const file = textFile();
    requests.chooseFile(file, true);
    const operation = requests.state.upload;
    await requests.submitUpload();
    expect(upload.mock.calls[0][1]).toMatchObject({
      sourceId: "source-1",
      expectedActiveVersionId: "source-1-v1",
    });
    expect(requests.state.upload.phase).toBe("conflict");
    expect(requests.state.upload.file).toBe(file);
    expect(requests.state.upload.idempotencyKey).toBe(operation.idempotencyKey);
    expect(requests.state.selectedSourceId).toBe("source-1");
    await requests.retryUpload();
    expect(upload).toHaveBeenCalledTimes(1);
  });
  it("retains failure job ID and fetches status only on explicit request", async () => {
    const { requests, client } = setup({
      uploadDocument: vi.fn().mockRejectedValue(
        new WorkbenchApiError("failed", {
          kind: "http",
          code: "PARSING_FAILED",
          httpStatus: 415,
          jobId: "job-1",
        }),
      ),
    });
    requests.start();
    await settle();
    requests.chooseFile(textFile());
    await requests.submitUpload();
    expect(requests.state.upload.phase).toBe("failed");
    expect(requests.state.upload.jobId).toBe("job-1");
    expect(client.getIngestionJob).not.toHaveBeenCalled();
    await requests.inspectJob();
    expect(requests.state.job?.reserved_version_id).toBe("uploaded-1-v1");
    expect(client.getIngestionJob).toHaveBeenCalledTimes(1);
  });
  it("retains same-scope unknown upload intent on navigation, clears private files on workspace change", async () => {
    const pending = deferred<IngestionResponse>();
    const { requests, setContext } = setup({
      uploadDocument: vi.fn().mockReturnValue(pending.promise),
    });
    requests.start();
    await settle();
    const file = textFile();
    requests.chooseFile(file);
    const attempt = requests.submitUpload();
    const key = requests.state.upload.idempotencyKey;
    setContext({ enabled: false });
    expect(requests.state.upload.phase).toBe("unknown");
    expect(requests.state.upload.file).toBe(file);
    expect(requests.state.upload.idempotencyKey).toBe(key);
    setContext({ workspaceId: "workspace-2" });
    expect(requests.state.upload.file).toBeNull();
    pending.resolve(uploaded());
    await attempt;
    expect(requests.state.upload.phase).toBe("idle");
  });
  it("fails closed before POST for disabled writes and conditional PDF", async () => {
    const { requests, client } = setup();
    requests.start();
    await settle();
    requests.chooseFile(
      new File(["%PDF-test"], "input.pdf", { type: "application/pdf" }),
    );
    await requests.submitUpload();
    expect(requests.state.upload.phase).toBe("failed");
    expect(client.uploadDocument).not.toHaveBeenCalled();
  });
});

describe("qualified advisory upload validation", () => {
  it.each([
    ["source.txt", "text/plain"],
    ["source.md", "text/markdown"],
    ["source.markdown", ""],
    ["source.py", "text/x-python"],
  ])("accepts qualified %s", (name, type) => {
    expect(
      validateDocumentFile(new File(["sample"], name, { type }), false),
    ).toBeNull();
  });
  it("rejects unsupported extension, mismatched MIME and per-format oversized files", () => {
    expect(
      validateDocumentFile(new File(["sample"], "source.yaml"), false),
    ).toContain("Choose");
    expect(
      validateDocumentFile(
        new File(["sample"], "source.py", { type: "application/javascript" }),
        false,
      ),
    ).toContain("MIME");
    expect(
      validateDocumentFile(
        new File([new Uint8Array(1048577)], "source.txt"),
        false,
      ),
    ).toContain("1 MiB");
    expect(
      validateDocumentFile(
        new File([new Uint8Array(8388608)], "source.pdf", {
          type: "application/pdf",
        }),
        true,
      ),
    ).toBeNull();
    expect(
      validateDocumentFile(
        new File([new Uint8Array(8388609)], "source.pdf", {
          type: "application/pdf",
        }),
        true,
      ),
    ).toContain("8 MiB");
  });
});

describe("useLiveDocuments React lifecycle", () => {
  it("strict-mode cleanup cannot let ignored-abort requests resurrect data", async () => {
    const first = deferred<DocumentPage>();
    const list = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue(page(""));
    const { client } = setup({ listDocuments: list });
    const context: LiveDocumentsContext = {
      mode: "live",
      workspaceId: "workspace-1",
      capabilities,
    };
    const { result, rerender, unmount } = renderHook(
      ({ current }) => useLiveDocuments(current, { client }),
      {
        initialProps: { current: context },
        reactStrictMode: true,
      },
    );
    expect(list).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(result.current.status).toBe("empty"));
    await act(async () => {
      first.resolve(page());
      await settle();
    });
    expect(result.current.documents).toEqual([]);
    rerender({ current: { ...context, mode: "preview" } });
    expect(result.current.detail).toBeNull();
    expect(result.current.chunks).toEqual([]);
    unmount();
    cleanup();
  });
});
