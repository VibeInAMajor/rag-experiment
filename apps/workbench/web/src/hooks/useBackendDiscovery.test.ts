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

  it("requires a supported discovered profile revision", async () => {
    const { discovery, caps } = clientFixture();
    caps.profiles[0].profile_revision = "postgres-fts-baseline-r2";
    await discovery.refresh();
    expect(discovery.state.status).toBe("incompatible");
    expect(discovery.state.error?.code).toBe("PROFILE_NOT_SUPPORTED");
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
