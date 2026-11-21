import { afterEach, describe, expect, it, vi } from "vitest";
import { createWorkbenchApiClient } from "./client";
import type { SearchRequest, SearchResponse } from "./contracts";

const submitted: SearchRequest = {
  query: "retention",
  top_k: 5,
  profile_id: "postgres-fts-baseline",
  expected_profile_revision: "postgres-fts-baseline-r1",
};
afterEach(() => vi.useRealTimers());
function response(): SearchResponse {
  return {
    contract_revision: "rag-api-v1.0",
    request_id: "request-1",
    trace_id: "trace-1",
    mode: "live",
    workspace_id: "development",
    corpus_revision: "corpus-1",
    profile_id: "postgres-fts-baseline",
    profile_revision: "postgres-fts-baseline-r1",
    run_id: "server-run-1",
    status: "success",
    duration_ms: 10,
    stages: [
      { stage: "corpus_load", status: "success", duration_ms: 3 },
      { stage: "retrieval", status: "success", duration_ms: 5 },
      { stage: "projection", status: "success", duration_ms: 1 },
    ],
    results: [
      {
        chunk_id: "chunk-a",
        source_id: "source-a",
        source_version_id: "source-a-v1",
        title: "Backups",
        content: "Actual retention passage",
        rank: 1,
        score: 0.10000000149011612,
        score_type: "postgres_ts_rank_cd",
      },
    ],
  };
}
function clientFor(value: unknown, status = 200) {
  const fetchImpl = vi.fn<typeof fetch>().mockImplementation(
    async () =>
      new Response(JSON.stringify(value), {
        status,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "request-1",
        },
      }),
  );
  return { client: createWorkbenchApiClient({ fetchImpl }), fetchImpl };
}

describe("Live search HTTP boundary", () => {
  it("uses a separate bounded execution deadline and never retries POST", async () => {
    vi.useFakeTimers();
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockImplementation(() => new Promise(() => {}));
    const client = createWorkbenchApiClient({
      fetchImpl,
      timeoutMs: 5,
      searchTimeoutMs: 20,
    });
    const failed = expect(
      client.search("development", submitted),
    ).rejects.toMatchObject({ kind: "timeout", code: "TIMEOUT" });
    await vi.advanceTimersByTimeAsync(5);
    expect(fetchImpl.mock.calls[0][1]?.signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(15);
    await failed;
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("aborts a pending POST locally without claiming server cancellation", async () => {
    const controller = new AbortController();
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockImplementation(() => new Promise(() => {}));
    const failed = expect(
      createWorkbenchApiClient({ fetchImpl }).search("development", submitted, {
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ kind: "cancelled", code: "CANCELLED" });
    controller.abort();
    await failed;
    expect(fetchImpl.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
  it("posts exactly four canonical fields and preserves raw server values and absent page", async () => {
    const original = response();
    const { client, fetchImpl } = clientFor(original);
    expect(await client.search("development", submitted)).toEqual(original);
    expect(fetchImpl.mock.calls[0][0]).toBe(
      "/api/v1/workspaces/development/search",
    );
    const request = fetchImpl.mock.calls[0][1];
    expect(request).toMatchObject({
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
    });
    expect(JSON.parse(String(request?.body))).toEqual(submitted);
    expect(Object.keys(JSON.parse(String(request?.body)))).toEqual([
      "query",
      "top_k",
      "profile_id",
      "expected_profile_revision",
    ]);
    expect(
      (await client.search("development", submitted)).results[0],
    ).not.toHaveProperty("page");
  });
  it("accepts zero hits, nullable page and arbitrary plain-text passages", async () => {
    const value = response();
    value.results = [];
    expect(
      (await clientFor(value).client.search("development", submitted)).results,
    ).toEqual([]);
    value.results = response().results;
    value.results[0].page = null;
    value.results[0].content =
      "<script>window.injected=true</script>\nraw document";
    expect(
      (await clientFor(value).client.search("development", submitted))
        .results[0].content,
    ).toBe(value.results[0].content);
  });
  it.each([
    { mode: "preview" },
    { workspace_id: "foreign" },
    { profile_id: "bm25-v1" },
    { profile_revision: "stale" },
    { run_id: "" },
    { run_id: "bad/id" },
    { request_id: "bad/id" },
    { contract_revision: "unknown" },
    { duration_ms: -1 },
    { duration_ms: null },
    { stages: [] },
    { stages: [...response().stages, response().stages[0]] },
    {
      stages: [
        response().stages[1],
        response().stages[0],
        response().stages[2],
      ],
    },
    {
      stages: response().stages.map((stage) => ({ ...stage, duration_ms: 20 })),
    },
    { results: [{ ...response().results[0], score: null }] },
    { results: [{ ...response().results[0], score: -1 }] },
    { results: [{ ...response().results[0], score_type: "bm25_raw" }] },
    { results: [{ ...response().results[0], source_version_id: undefined }] },
    { results: [{ ...response().results[0], page: 0 }] },
    { results: [{ ...response().results[0], page: 1.5 }] },
    { results: [{ ...response().results[0], rank: 2 }] },
    { results: [response().results[0], { ...response().results[0], rank: 2 }] },
    {
      results: [
        response().results[0],
        { ...response().results[0], chunk_id: "chunk-b", rank: 2, score: 1 },
      ],
    },
    {
      results: [
        { ...response().results[0], chunk_id: "chunk-b" },
        { ...response().results[0], rank: 2 },
      ],
    },
  ])("rejects malformed or contradictory success %#", async (override) => {
    await expect(
      clientFor({ ...response(), ...override }).client.search(
        "development",
        submitted,
      ),
    ).rejects.toMatchObject({ kind: "protocol" });
  });
  it("rejects oversized result count and accepts stable ASCII tie ordering", async () => {
    const value = response();
    value.results = [
      value.results[0],
      { ...value.results[0], chunk_id: "chunk-b", rank: 2 },
    ];
    await expect(
      clientFor(value).client.search("development", { ...submitted, top_k: 1 }),
    ).rejects.toMatchObject({ kind: "protocol" });
    expect(
      (
        await clientFor(value).client.search("development", submitted)
      ).results.map((hit) => hit.chunk_id),
    ).toEqual(["chunk-a", "chunk-b"]);
  });
  it.each([
    { ...submitted, query: " " },
    { ...submitted, query: "a\0b" },
    { ...submitted, query: "\ud800" },
    { ...submitted, query: "a".repeat(4097) },
    { ...submitted, top_k: 0 },
    { ...submitted, top_k: 51 },
    { ...submitted, top_k: 1.5 },
    { ...submitted, top_k: true },
    { ...submitted, graph: { nodes: [] } },
  ])("rejects invalid requests without issuing HTTP %#", async (body) => {
    const { client, fetchImpl } = clientFor(response());
    await expect(
      client.search("development", body as SearchRequest),
    ).rejects.toMatchObject({ kind: "protocol" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
  it("rejects unsafe workspace paths and counts Unicode codepoints", async () => {
    const { client, fetchImpl } = clientFor(response());
    await expect(client.search("../foreign", submitted)).rejects.toMatchObject({
      kind: "protocol",
    });
    expect(fetchImpl).not.toHaveBeenCalled();
    await client.search("development", {
      ...submitted,
      query: "😀".repeat(4096),
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
  it.each([
    [400, "INVALID_REQUEST"],
    [404, "WORKSPACE_NOT_FOUND"],
    [409, "PROFILE_NOT_AVAILABLE"],
    [429, "SEARCH_BUSY"],
    [503, "DEPENDENCY_UNAVAILABLE"],
    [504, "SEARCH_TIMEOUT"],
  ])("preserves HTTP %s and safe server correlation", async (status, code) => {
    const value = {
      contract_revision: "rag-api-v1.0",
      request_id: "request-1",
      trace_id: "trace-1",
      error: {
        code,
        message: "Do not display server content",
        retryable: status !== 400,
        http_status: status,
        run_id: "error-run-1",
      },
    };
    await expect(
      clientFor(value, Number(status)).client.search("development", submitted),
    ).rejects.toMatchObject({
      kind: "http",
      httpStatus: status,
      code,
      runId: "error-run-1",
      traceId: "trace-1",
    });
  });
});
