import { describe, expect, it, vi } from "vitest";
import { WorkbenchApiError, type WorkbenchApiClient } from "../api/client";
import type {
  BackendProfile,
  SearchRequest,
  SearchResponse,
} from "../api/contracts";
import { createPipeline } from "../domain/graph";
import {
  graphFingerprint,
  LiveSearchRequests,
  type LiveRun,
  type LiveSearchContext,
} from "../domain/liveSearch";

const submitted: SearchRequest = {
  query: "retention",
  top_k: 5,
  profile_id: "postgres-fts-baseline",
  expected_profile_revision: "postgres-fts-baseline-r1",
};
const profile: BackendProfile = {
  profile_id: "postgres-fts-baseline",
  profile_revision: "postgres-fts-baseline-r1",
  kind: "lexical_search",
  workspace_ids: ["development"],
  corpus_id: "corpus-1",
  score_type: "postgres_ts_rank_cd",
  parameters: {
    query: { type: "string", min_length: 1, max_length: 4096 },
    top_k: { type: "integer", default: 10, minimum: 1, maximum: 50 },
  },
  limits: {
    max_request_bytes: 32768,
    timeout_ms: 10000,
    max_concurrent_searches: 2,
    max_corpus_chunks: 10000,
    max_corpus_bytes: 52428800,
  },
};
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
        chunk_id: "chunk-1",
        source_id: "source-1",
        source_version_id: "source-1-v1",
        title: "Real source",
        content: "Real passage",
        rank: 1,
        score: 0.10000000149011612,
        score_type: "postgres_ts_rank_cd",
      },
    ],
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
function harness() {
  let context: LiveSearchContext = {
    mode: "live",
    pipeline: createPipeline("keyword"),
    workspaceId: "development",
    profile,
  };
  let runs: LiveRun[] = [];
  const search = vi
    .fn<WorkbenchApiClient["search"]>()
    .mockResolvedValue(response());
  const client: Pick<WorkbenchApiClient, "search"> = {
    search,
  };
  const changed = vi.fn();
  const invalidate = vi.fn();
  const requests = new LiveSearchRequests(
    client,
    (update) => {
      runs = update(runs);
    },
    () => context,
    changed,
    invalidate,
  );
  return {
    requests,
    search,
    changed,
    invalidate,
    get runs() {
      return runs;
    },
    get context() {
      return context;
    },
    set context(value) {
      context = value;
    },
    run() {
      return requests.run(context.pipeline, submitted, "development");
    },
  };
}

describe("Live search request lifecycle used by useLiveSearch", () => {
  it("records immutable submitted context and only measured server values", async () => {
    const state = harness();
    await state.run();
    expect(state.runs[0]).toMatchObject({
      source: "live",
      status: "Completed",
      pipelineId: state.context.pipeline.id,
      submitted,
      serverRunId: "server-run-1",
      traceId: "trace-1",
      requestId: "request-1",
      durationMs: 10,
      corpusRevision: "corpus-1",
      results: response().results,
      stages: response().stages,
      response: response(),
    });
    expect(state.runs[0].id).not.toBe(state.runs[0].serverRunId);
    expect(state.runs[0]).not.toHaveProperty("nodes");
    state.context.pipeline.graph.nodes[0].data.label = "Changed";
    expect(state.runs[0].graphSnapshot.nodes[0].data.label).not.toBe("Changed");
    expect(state.requests.busy).toBe(false);
    expect(state.requests.activeRunId).toBeNull();
  });
  it("does not execute for Preview, stale revision or foreign workspace", async () => {
    const state = harness();
    state.context = { ...state.context, mode: "preview" };
    await state.run();
    state.context = {
      ...state.context,
      mode: "live",
      profile: { ...profile, profile_revision: "stale" },
    };
    await state.run();
    state.context = { ...state.context, profile, workspaceId: "foreign" };
    await state.run();
    expect(state.search).not.toHaveBeenCalled();
    expect(state.runs).toEqual([]);
  });
  it("guards double submit and marks zero hits completed", async () => {
    const state = harness();
    const pending = deferred<SearchResponse>();
    state.search.mockReturnValue(pending.promise);
    const first = state.run();
    await state.run();
    expect(state.search).toHaveBeenCalledTimes(1);
    expect(state.requests.busy).toBe(true);
    pending.resolve({ ...response(), results: [] });
    await first;
    expect(state.runs[0].status).toBe("Completed");
    expect(state.runs[0].results).toEqual([]);
  });
  it("Stop aborts locally and late success cannot overwrite the interrupted run", async () => {
    const state = harness();
    const pending = deferred<SearchResponse>();
    state.search.mockReturnValue(pending.promise);
    const operation = state.run();
    state.requests.stop();
    expect(state.search.mock.calls[0][2]?.signal?.aborted).toBe(true);
    expect(state.runs[0]).toMatchObject({
      status: "InterruptedLocally",
      results: [],
      stages: [],
      error: { code: "INTERRUPTED_LOCALLY" },
    });
    expect(state.runs[0].error?.message).toContain(
      "server cancellation is not confirmed",
    );
    pending.resolve(response());
    await operation;
    expect(state.runs[0].status).toBe("InterruptedLocally");
    expect(state.runs[0].serverRunId).toBeUndefined();
  });
  it("Stop then Run permits a new request and rejects out-of-order completion", async () => {
    const state = harness();
    const old = deferred<SearchResponse>();
    const latest = deferred<SearchResponse>();
    state.search
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(latest.promise);
    const first = state.run();
    state.requests.stop();
    const second = state.run();
    latest.resolve({ ...response(), run_id: "latest-run" });
    await second;
    old.resolve({ ...response(), run_id: "obsolete-run" });
    await first;
    expect(state.runs.map((run) => run.status)).toEqual([
      "Completed",
      "InterruptedLocally",
    ]);
    expect(state.runs[0].serverRunId).toBe("latest-run");
    expect(state.runs[1].serverRunId).toBeUndefined();
  });
  it.each(["mode", "pipeline", "graph", "workspace", "profile"])(
    "invalidates pending request on %s change",
    async (change) => {
      const state = harness();
      const pending = deferred<SearchResponse>();
      state.search.mockReturnValue(pending.promise);
      const operation = state.run();
      if (change === "mode")
        state.context = { ...state.context, mode: "preview" };
      if (change === "pipeline")
        state.context = {
          ...state.context,
          pipeline: createPipeline("keyword"),
        };
      if (change === "graph")
        state.context = {
          ...state.context,
          pipeline: {
            ...state.context.pipeline,
            graph: {
              ...state.context.pipeline.graph,
              nodes: state.context.pipeline.graph.nodes.map((node, index) =>
                index === 0
                  ? {
                      ...node,
                      data: { ...node.data, parameters: { query: "GIN" } },
                    }
                  : node,
              ),
            },
          },
        };
      if (change === "workspace")
        state.context = { ...state.context, workspaceId: "other" };
      if (change === "profile")
        state.context = {
          ...state.context,
          profile: { ...profile, profile_revision: "next" },
        };
      state.requests.contextChanged();
      pending.resolve(response());
      await operation;
      expect(state.runs[0].status).toBe("InterruptedLocally");
      expect(state.runs[0].results).toEqual([]);
    },
  );
  it("late response also checks live context before React effects run", async () => {
    const state = harness();
    const pending = deferred<SearchResponse>();
    state.search.mockReturnValue(pending.promise);
    const operation = state.run();
    state.context = { ...state.context, mode: "preview" };
    pending.resolve(response());
    await operation;
    expect(state.runs[0].status).toBe("InterruptedLocally");
    expect(state.runs[0].response).toBeUndefined();
  });
  it("ignores viewport/selection/measurement changes while preserving actual graph edits", () => {
    const graph = createPipeline("keyword").graph;
    const same = structuredClone(graph);
    same.viewport = { x: 10, y: 20, zoom: 2 };
    same.nodes[0].selected = true;
    same.nodes[0].measured = { width: 400, height: 250 };
    same.nodes[0].data.status = "success";
    expect(graphFingerprint(same)).toBe(graphFingerprint(graph));
    same.nodes[0].data.parameters.query = "GIN";
    expect(graphFingerprint(same)).not.toBe(graphFingerprint(graph));
  });
  it.each([
    [400, "INVALID_REQUEST"],
    [404, "WORKSPACE_NOT_FOUND"],
    [409, "PROFILE_NOT_AVAILABLE"],
    [429, "SEARCH_BUSY"],
    [503, "DEPENDENCY_UNAVAILABLE"],
    [504, "SEARCH_TIMEOUT"],
  ])(
    "records HTTP %s, correlation and appropriate discovery invalidation",
    async (status, code) => {
      const state = harness();
      state.search.mockRejectedValue(
        new WorkbenchApiError("Safe backend error", {
          kind: "http",
          code: String(code),
          httpStatus: Number(status),
          retryable: true,
          runId: "failed-server-run",
          requestId: "request-error",
          traceId: "trace-error",
        }),
      );
      await state.run();
      expect(state.runs[0]).toMatchObject({
        status: "Failed",
        serverRunId: "failed-server-run",
        requestId: "request-error",
        traceId: "trace-error",
        results: [],
        stages: [],
        error: { code, httpStatus: status },
      });
      expect(state.runs[0].durationMs).toBeUndefined();
      expect(state.invalidate).toHaveBeenCalledTimes(
        [404, 409, 503].includes(Number(status)) ? 1 : 0,
      );
    },
  );
  it.each(["protocol", "transport", "timeout"] as const)(
    "keeps %s failures separate from server success",
    async (kind) => {
      const state = harness();
      state.search.mockRejectedValue(
        new WorkbenchApiError("Safe failure", {
          kind,
          code: kind.toUpperCase(),
        }),
      );
      await state.run();
      expect(state.runs[0]).toMatchObject({
        status: "Failed",
        error: { code: kind.toUpperCase() },
        results: [],
      });
      expect(state.runs[0].serverRunId).toBeUndefined();
    },
  );
  it("caps Live history to 100 session entries", async () => {
    const state = harness();
    for (let index = 0; index < 103; index++) await state.run();
    expect(state.runs).toHaveLength(100);
    expect(new Set(state.runs.map((run) => run.id)).size).toBe(100);
  });
  it("unmount interruption prevents late notifications or success", async () => {
    const state = harness();
    const pending = deferred<SearchResponse>();
    state.search.mockReturnValue(pending.promise);
    const operation = state.run();
    state.requests.stop(false);
    const notifications = state.changed.mock.calls.length;
    pending.resolve(response());
    await operation;
    expect(state.changed).toHaveBeenCalledTimes(notifications);
    expect(state.runs[0].status).toBe("InterruptedLocally");
  });
});
