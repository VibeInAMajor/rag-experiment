import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkbenchApiError, type WorkbenchApiClient } from "../api/client";
import type {
  BackendCapabilities,
  LiveResponse,
  ReadyResponse,
  WorkspacePage,
} from "../api/contracts";
import { BackendDiscovery } from "../domain/backendDiscovery";

const meta = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-1",
  trace_id: "trace-1",
} as const;

function capabilities(): BackendCapabilities {
  return {
    ...meta,
    backend_revision: "workbench-api-lexical-v1",
    deployment_mode: "single_workspace_dev",
    service_state: "running",
    profiles: [
      {
        profile_id: "postgres-fts-baseline",
        profile_revision: "postgres-fts-baseline-r1",
        kind: "lexical_search",
        workspace_ids: ["development"],
        corpus_id: "development-corpus-v1",
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
      },
    ],
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
    dependencies: {
      database: {
        status: "ready",
        workspace_id: "development",
        source_count: 8,
        chunk_count: 8,
        schema_revision: "0001",
      },
    },
  };
}

function clientFixture() {
  const caps = capabilities();
  const live: LiveResponse = {
    ...meta,
    status: "alive",
    backend_revision: caps.backend_revision,
  };
  const ready: ReadyResponse = {
    ...meta,
    status: "ready",
    backend_revision: caps.backend_revision,
    ready_profile_ids: ["postgres-fts-baseline"],
  };
  const page: WorkspacePage = {
    ...meta,
    items: [
      { workspace_id: "development", name: "Development", status: "ready" },
    ],
    next_cursor: null,
  };
  const client = {
    getLive: vi.fn<WorkbenchApiClient["getLive"]>().mockResolvedValue(live),
    getReady: vi.fn<WorkbenchApiClient["getReady"]>().mockResolvedValue(ready),
    getCapabilities: vi
      .fn<WorkbenchApiClient["getCapabilities"]>()
      .mockResolvedValue(caps),
    listWorkspaces: vi
      .fn<WorkbenchApiClient["listWorkspaces"]>()
      .mockResolvedValue(page),
  };
  const changed = vi.fn();
  return {
    client,
    caps,
    live,
    ready,
    page,
    changed,
    discovery: new BackendDiscovery(client, changed),
  };
}

function notReady() {
  return new WorkbenchApiError("Search is not ready.", {
    kind: "http",
    code: "NOT_READY",
    httpStatus: 503,
    retryable: true,
    requestId: "ready-request",
    traceId: "ready-trace",
  });
}

afterEach(() => vi.useRealTimers());

describe("backend discovery", () => {
  it("qualifies the discovered profile and server-returned workspace", async () => {
    const { discovery, changed, client } = clientFixture();
    await discovery.refresh();
    expect(changed.mock.calls[0][0].status).toBe("checking");
    expect(discovery.state).toMatchObject({
      status: "ready",
      selectedWorkspaceId: "development",
      profile: { profile_revision: "postgres-fts-baseline-r1" },
    });
    expect(discovery.state.lastCheckedAt).not.toBeNull();
    expect(client.listWorkspaces).toHaveBeenCalledWith({
      limit: 50,
      signal: expect.any(AbortSignal),
    });
  });

  it("retains a safe 503 diagnostic despite successful liveness", async () => {
    const { discovery, client, caps } = clientFixture();
    client.getReady.mockRejectedValue(notReady());
    caps.profiles = [];
    caps.features.search = false;
    caps.dependencies.database.status = "unavailable";
    await discovery.refresh();
    expect(discovery.state).toMatchObject({
      status: "not_ready",
      profile: null,
      selectedWorkspaceId: null,
      error: { code: "NOT_READY", httpStatus: 503, traceId: "ready-trace" },
      capabilities: {
        profiles: [],
        dependencies: { database: { status: "unavailable" } },
      },
    });
    expect(client.listWorkspaces).not.toHaveBeenCalled();
  });

  it("reports incompatible database schema without enabling a profile", async () => {
    const { discovery, client, caps } = clientFixture();
    client.getReady.mockRejectedValue(notReady());
    caps.dependencies.database.status = "incompatible";
    await discovery.refresh();
    expect(discovery.state.status).toBe("incompatible");
    expect(discovery.state.profile).toBeNull();
  });

  it("does not infer readiness from an empty profile list", async () => {
    const { discovery, caps, ready } = clientFixture();
    caps.profiles = [];
    ready.ready_profile_ids = [];
    await discovery.refresh();
    expect(discovery.state.status).toBe("not_ready");
    expect(discovery.state.profile).toBeNull();
  });

  it.each(["starting", "stopping", "stopped"] as const)(
    "rejects search readiness while service is %s",
    async (serviceState) => {
      const { discovery, caps } = clientFixture();
      caps.service_state = serviceState;
      await discovery.refresh();
      expect(discovery.state.status).toBe("not_ready");
    },
  );

  it("rejects contradictory readiness profile IDs", async () => {
    const { discovery, ready } = clientFixture();
    ready.ready_profile_ids = ["other-profile"];
    await discovery.refresh();
    expect(discovery.state.error?.code).toBe("READINESS_MISMATCH");
    expect(discovery.state.status).toBe("incompatible");
  });

  it("rejects mixed backend snapshots", async () => {
    const { discovery, live } = clientFixture();
    live.backend_revision = "older-backend";
    await discovery.refresh();
    expect(discovery.state.error?.code).toBe("BACKEND_REVISION_MISMATCH");
  });

  it("uses the current server-approved revision without hardcoding its version", async () => {
    const { discovery, caps } = clientFixture();
    caps.profiles[0].profile_revision = "postgres-fts-baseline-r2";
    await discovery.refresh();
    expect(discovery.state.status).toBe("ready");
    expect(discovery.state.profile?.profile_revision).toBe(
      "postgres-fts-baseline-r2",
    );
  });

  it("requires explicit selection when only new approved lexical IDs are available", async () => {
    const { discovery, caps, ready, changed } = clientFixture();
    caps.profiles[0].profile_id = "postgres-fts-bounded";
    caps.profiles[0].profile_revision = "bounded-r1";
    ready.ready_profile_ids = ["postgres-fts-bounded"];
    await discovery.refresh();
    expect(discovery.state).toMatchObject({
      status: "awaiting_profile",
      profile: null,
      selectedWorkspaceId: "development",
      error: { code: "PROFILE_SELECTION_REQUIRED" },
    });
    expect(discovery.selectProfile("postgres-fts-bounded")).toBe(true);
    expect(discovery.state.status).toBe("checking");
    await vi.waitFor(() => expect(discovery.state.status).toBe("ready"));
    expect(discovery.state.profile?.profile_id).toBe("postgres-fts-bounded");
    expect(changed).toHaveBeenCalled();
  });

  it("keeps lexical default and requires explicit selection of qualified Dense", async () => {
    const { discovery, caps, ready } = clientFixture();
    const dense = {
      ...caps.profiles[0],
      profile_id: "postgres-dense-exact",
      profile_revision: "postgres-dense-exact-r1",
      kind: "dense_search" as const,
      score_type: "cosine_distance" as const,
      score_direction: "lower_is_better" as const,
      embedding_profile_revision: "qwen-local-r1",
      index_generation: 4,
      min_coverage: 1 as const,
    };
    caps.profiles.push(dense);
    ready.ready_profile_ids.push(dense.profile_id);
    await discovery.refresh();
    expect(discovery.state.profile?.profile_id).toBe("postgres-fts-baseline");
    expect(discovery.selectProfile(dense.profile_id)).toBe(true);
    await vi.waitFor(() =>
      expect(discovery.state.profile?.kind).toBe("dense_search"),
    );
    caps.profiles = caps.profiles.filter(
      (item) => item.profile_id !== dense.profile_id,
    );
    ready.ready_profile_ids = ["postgres-fts-baseline"];
    await discovery.refresh();
    expect(discovery.state.status).toBe("awaiting_profile");
    expect(discovery.state.profile).toBeNull();
  });

  it("never substitutes another profile when an explicitly selected profile is retired", async () => {
    const { discovery, caps, ready } = clientFixture();
    const alternate = {
      ...caps.profiles[0],
      profile_id: "postgres-fts-bounded",
      profile_revision: "bounded-r1",
    };
    caps.profiles.push(alternate);
    ready.ready_profile_ids.push(alternate.profile_id);
    await discovery.refresh();
    expect(discovery.state.profile?.profile_id).toBe("postgres-fts-baseline");
    expect(discovery.selectProfile(alternate.profile_id)).toBe(true);
    await vi.waitFor(() =>
      expect(discovery.state.profile?.profile_id).toBe(alternate.profile_id),
    );
    caps.profiles = caps.profiles.filter(
      (item) => item.profile_id !== alternate.profile_id,
    );
    ready.ready_profile_ids = ["postgres-fts-baseline"];
    await discovery.refresh();
    expect(discovery.state).toMatchObject({
      status: "awaiting_profile",
      profile: null,
      error: { code: "PROFILE_NOT_AVAILABLE" },
    });
    expect(discovery.selectProfile("postgres-fts-baseline")).toBe(true);
    await vi.waitFor(() => expect(discovery.state.status).toBe("ready"));
  });

  it("refuses selection outside the advertised workspace and never sends a request", async () => {
    const { discovery, caps, ready, client } = clientFixture();
    caps.profiles.push({
      ...caps.profiles[0],
      profile_id: "foreign-profile",
      workspace_ids: ["foreign"],
    });
    ready.ready_profile_ids.push("foreign-profile");
    await discovery.refresh();
    expect(discovery.selectProfile("foreign-profile")).toBe(false);
    expect(discovery.selectProfile("unregistered")).toBe(false);
    expect(client.getCapabilities).toHaveBeenCalledTimes(1);
    expect(discovery.state.profile?.profile_id).toBe("postgres-fts-baseline");
  });

  it("rejects unsupported score semantics even when a profile is advertised as ready", async () => {
    const { discovery, caps, client } = clientFixture();
    caps.profiles[0].score_type = "bm25_raw";
    await discovery.refresh();
    expect(discovery.state.error?.code).toBe("PROFILE_NOT_SUPPORTED");
    expect(client.listWorkspaces).not.toHaveBeenCalled();
  });

  it("requires intersection with the authorized workspace list", async () => {
    const { discovery, page } = clientFixture();
    page.items[0].workspace_id = "foreign";
    await discovery.refresh();
    expect(discovery.state.status).toBe("incompatible");
    expect(discovery.state.selectedWorkspaceId).toBeNull();
    expect(discovery.state.error?.code).toBe("WORKSPACE_NOT_AUTHORIZED");
  });

  it("never treats a cosmetic workspace name as authorization", async () => {
    const { discovery, client } = clientFixture();
    await discovery.refresh();
    expect(discovery.selectWorkspace("My renamed workspace")).toBe(false);
    expect(discovery.state.selectedWorkspaceId).toBe("development");
    expect(client.listWorkspaces).toHaveBeenCalledTimes(1);
  });

  it("follows opaque cursors without deriving workspace IDs", async () => {
    const { discovery, client, page } = clientFixture();
    client.listWorkspaces
      .mockResolvedValueOnce({
        ...meta,
        items: [],
        next_cursor: "opaque-next-token",
      })
      .mockResolvedValueOnce(page);
    await discovery.refresh();
    expect(client.listWorkspaces.mock.calls[1][0]).toMatchObject({
      cursor: "opaque-next-token",
      limit: 50,
    });
    expect(discovery.state.status).toBe("ready");
  });

  it("rejects repeated opaque cursors", async () => {
    const { discovery, client } = clientFixture();
    client.listWorkspaces.mockResolvedValue({
      ...meta,
      items: [],
      next_cursor: "repeated-token",
    });
    await discovery.refresh();
    expect(client.listWorkspaces).toHaveBeenCalledTimes(2);
    expect(discovery.state.error?.code).toBe("WORKSPACE_PAGE_LIMIT");
  });

  it("bounds workspace pagination to ten pages", async () => {
    const { discovery, client } = clientFixture();
    let pageNumber = 0;
    client.listWorkspaces.mockImplementation(async () => ({
      ...meta,
      items: [],
      next_cursor: `page-${++pageNumber}`,
    }));
    await discovery.refresh();
    expect(client.listWorkspaces).toHaveBeenCalledTimes(10);
    expect(discovery.state.status).toBe("incompatible");
  });

  it("rejects duplicate workspace IDs across pages", async () => {
    const { discovery, client, page } = clientFixture();
    client.listWorkspaces
      .mockResolvedValueOnce({ ...page, next_cursor: "next-page" })
      .mockResolvedValueOnce(page);
    await discovery.refresh();
    expect(discovery.state.error?.code).toBe("WORKSPACE_PAGE_MISMATCH");
  });

  it("clears previous ready data before a failed explicit refresh", async () => {
    const { discovery, client } = clientFixture();
    await discovery.refresh();
    const previousCheck = discovery.state.lastCheckedAt;
    client.getLive.mockRejectedValue(
      new WorkbenchApiError("API unavailable.", {
        kind: "transport",
        code: "TRANSPORT_ERROR",
      }),
    );
    const refresh = discovery.refresh();
    expect(discovery.state).toMatchObject({
      status: "checking",
      profile: null,
      workspaces: [],
      lastCheckedAt: previousCheck,
    });
    expect(discovery.state.capabilities).toBeUndefined();
    await refresh;
    expect(discovery.state.status).toBe("unavailable");
    expect(discovery.state.capabilities).toBeUndefined();
  });

  it("ignores an old response after a newer request finishes", async () => {
    const { discovery, client, caps } = clientFixture();
    let release: ((value: BackendCapabilities) => void) | undefined;
    client.getCapabilities.mockReturnValueOnce(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const older = discovery.refresh();
    await discovery.refresh();
    expect(discovery.state.status).toBe("ready");
    caps.service_state = "stopped";
    release?.(caps);
    await older;
    expect(discovery.state.status).toBe("ready");
  });

  it("aborts and rejects late responses after switching to Preview", async () => {
    vi.useFakeTimers();
    const { discovery, client, caps } = clientFixture();
    let release: ((value: BackendCapabilities) => void) | undefined;
    client.getCapabilities.mockReturnValueOnce(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const pending = discovery.refresh();
    const signal = client.getLive.mock.calls[0][0]?.signal;
    discovery.reset();
    await pending;
    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    release?.(caps);
    await Promise.resolve();
    expect(discovery.state.status).toBe("unconfigured");
  });

  it("bounds the whole discovery generation and cleans its deadline", async () => {
    vi.useFakeTimers();
    const { discovery, client } = clientFixture();
    client.getCapabilities.mockReturnValue(new Promise(() => {}));
    const pending = discovery.refresh();
    await vi.advanceTimersByTimeAsync(15000);
    await pending;
    expect(discovery.state.status).toBe("unavailable");
    expect(discovery.state.error?.code).toBe("DISCOVERY_TIMEOUT");
    expect(client.getLive.mock.calls[0][0]?.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("surfaces invalid configuration as incompatible without crashing render", async () => {
    const discovery = new BackendDiscovery(() => {
      throw new WorkbenchApiError("Invalid public API URL.", {
        kind: "configuration",
        code: "INVALID_API_URL",
      });
    }, vi.fn());
    await discovery.refresh();
    expect(discovery.state).toMatchObject({
      status: "incompatible",
      error: { code: "INVALID_API_URL" },
    });
  });
});
