import { afterEach, describe, expect, it, vi } from "vitest";
import openApiText from "../../../api/openapi.json?raw";
import { createWorkbenchApiClient, WorkbenchApiError } from "./client";
import {
  contractRevision,
  type ApiMeta,
  type BackendCapabilities,
  type BackendProfile,
} from "./contracts";

const meta: ApiMeta = {
  contract_revision: contractRevision,
  request_id: "request-1",
  trace_id: "trace-1",
};
const profile: BackendProfile = {
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
};
const capabilities: BackendCapabilities = {
  ...meta,
  backend_revision: "workbench-api-lexical-v1",
  deployment_mode: "single_workspace_dev",
  service_state: "running",
  profiles: [profile],
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

function json(value: unknown, status = 200, requestId = "request-1") {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "X-Request-ID": requestId,
    },
  });
}

function clientFor(value: unknown, status = 200) {
  const fetchImpl = vi
    .fn<typeof fetch>()
    .mockImplementation(async () => json(value, status));
  return { client: createWorkbenchApiClient({ fetchImpl }), fetchImpl };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

describe("Workbench API discovery transport", () => {
  it("matches implemented discriminator and required-field assumptions against published OpenAPI", () => {
    const schema = JSON.parse(openApiText);
    expect(schema.info.version).toBe(contractRevision);
    expect(schema.components.schemas.LiveResponse.properties.status.const).toBe(
      "alive",
    );
    expect(
      schema.components.schemas.ReadyResponse.properties.status.const,
    ).toBe("ready");
    expect(schema.components.schemas.CapabilitiesResponse.required).toEqual(
      expect.arrayContaining([
        "request_id",
        "trace_id",
        "backend_revision",
        "service_state",
        "profiles",
      ]),
    );
    const scoreSchema =
      schema.components.schemas.ExecutionProfile.properties.score_type;
    expect(scoreSchema.enum ?? [scoreSchema.const]).toContain(
      "postgres_ts_rank_cd",
    );
    for (const [key, value] of Object.entries(profile.limits))
      expect(
        schema.components.schemas.ProfileLimits.properties[key].default,
      ).toBe(value);
    const revisionSchema =
      schema.components.schemas.SearchResponse.properties.profile_revision;
    expect(revisionSchema.type).toBe("string");
    expect(
      revisionSchema.const === profile.profile_revision ||
        new RegExp(revisionSchema.pattern).test(profile.profile_revision),
    ).toBe(true);
  });

  it("decodes genuine discovery shapes and uses only GET, public headers and no browser credentials", async () => {
    const { client, fetchImpl } = clientFor(capabilities);
    expect(await client.getCapabilities()).toEqual(capabilities);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/capabilities",
      expect.objectContaining({
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      }),
    );
  });

  it("accepts empty profiles as a valid unavailable-capability response", async () => {
    const { client } = clientFor({
      ...capabilities,
      profiles: [],
      features: {
        documents: false,
        search: false,
        upload: false,
        document_details: false,
        jobs: false,
      },
      dependencies: { database: { status: "unavailable" } },
    });
    expect((await client.getCapabilities()).profiles).toEqual([]);
  });

  it("decodes bounded registered lexical profiles without changing the baseline shape", async () => {
    const registered = {
      ...profile,
      profile_id: "postgres-fts-bounded",
      profile_revision: "bounded-r4",
      parameters: {
        query: { type: "string", min_length: 1, max_length: 256 },
        top_k: { type: "integer", default: 2, minimum: 1, maximum: 3 },
      },
      limits: { ...profile.limits, timeout_ms: 5000, max_corpus_chunks: 1000 },
    };
    expect(
      (
        await clientFor({
          ...capabilities,
          profiles: [registered],
        }).client.getCapabilities()
      ).profiles,
    ).toEqual([registered]);
  });

  it.each([
    { contract_revision: "rag-api-v9" },
    { request_id: "unsafe/id" },
    { trace_id: "" },
    { service_state: "sleeping" },
    { deployment_mode: "multi_tenant" },
    { profiles: [profile, profile] },
    { profiles: [{ ...profile, workspace_ids: [] }] },
    { profiles: [{ ...profile, workspace_ids: ["unsafe/id"] }] },
    { profiles: [{ ...profile, score_type: "bm25_raw" }] },
    { profiles: [{ ...profile, kind: "generation" }] },
    { profiles: [{ ...profile, profile_id: "bad/profile" }] },
    {
      profiles: [
        {
          ...profile,
          parameters: {
            ...profile.parameters,
            top_k: { ...profile.parameters.top_k, default: 4, maximum: 3 },
          },
        },
      ],
    },
    {
      profiles: [
        {
          ...profile,
          parameters: {
            ...profile.parameters,
            top_k: { ...profile.parameters.top_k, maximum: 51 },
          },
        },
      ],
    },
    {
      profiles: [
        {
          ...profile,
          parameters: {
            ...profile.parameters,
            query: { ...profile.parameters.query, max_length: 4097 },
          },
        },
      ],
    },
    {
      profiles: [
        { ...profile, limits: { ...profile.limits, timeout_ms: null } },
      ],
    },
    {
      profiles: [
        { ...profile, limits: { ...profile.limits, timeout_ms: 1e200 } },
      ],
    },
    { features: { documents: true, search: "true" } },
    { dependencies: { database: { status: "ready", chunk_count: -1 } } },
    { dependencies: { database: { status: "ready", source_count: 1.5 } } },
  ])("rejects malformed capabilities %#", async (override) => {
    const { client } = clientFor({ ...capabilities, ...override });
    await expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "protocol",
      code: "INVALID_RESPONSE",
    });
  });

  it("does not promote additive fields to operations or trust payload type assertions", async () => {
    const { client } = clientFor({
      ...capabilities,
      upload: true,
      features: { ...capabilities.features, upload: true },
    });
    expect(await client.getCapabilities()).not.toHaveProperty("upload");
    expect((await client.getCapabilities()).features).toEqual({
      documents: true,
      search: true,
      upload: true,
      document_details: true,
      jobs: true,
    });
  });

  it("decodes liveness and readiness separately", async () => {
    const { client, fetchImpl } = clientFor({
      ...meta,
      status: "alive",
      backend_revision: "backend-1",
    });
    expect((await client.getLive()).status).toBe("alive");
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/v1/health/live");
    fetchImpl.mockResolvedValue(
      json({
        ...meta,
        status: "ready",
        backend_revision: "backend-1",
        ready_profile_ids: [profile.profile_id],
      }),
    );
    expect((await client.getReady()).ready_profile_ids).toEqual([
      profile.profile_id,
    ]);
    fetchImpl.mockResolvedValue(
      json({
        ...meta,
        status: "ready",
        backend_revision: "backend-1",
        ready_profile_ids: [profile.profile_id, profile.profile_id],
      }),
    );
    await expect(client.getReady()).rejects.toMatchObject({ kind: "protocol" });
  });

  it("passes opaque cursors as query parameters without interpreting their contents", async () => {
    const page = {
      ...meta,
      items: [
        { workspace_id: "development", name: "Development", status: "ready" },
      ],
      next_cursor: "opaque.signature",
    };
    const { client, fetchImpl } = clientFor(page);
    expect(
      await client.listWorkspaces({ cursor: "opaque.signature", limit: 25 }),
    ).toEqual(page);
    expect(fetchImpl.mock.calls[0][0]).toBe(
      "/api/v1/workspaces?limit=25&cursor=opaque.signature",
    );
    await expect(
      client.listWorkspaces({ cursor: "//unsafe?scope=other" }),
    ).rejects.toMatchObject({ kind: "protocol" });
    await expect(client.listWorkspaces({ limit: 0 })).rejects.toMatchObject({
      kind: "configuration",
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it.each([
    { items: [{ name: "Missing ID", status: "ready" }], next_cursor: null },
    { items: [], next_cursor: "" },
    { items: [], next_cursor: "/redirect" },
    { items: [], next_cursor: "x".repeat(513) },
    {
      items: [
        { workspace_id: "development", name: "Dev", status: "ready" },
        { workspace_id: "development", name: "Dev", status: "ready" },
      ],
      next_cursor: null,
    },
  ])("rejects invalid workspace pages %#", async (page) => {
    await expect(
      clientFor({ ...meta, ...page }).client.listWorkspaces(),
    ).rejects.toMatchObject({ kind: "protocol" });
  });

  it.each([404, 409, 429, 503, 504])(
    "retains safe structured errors and correlation for HTTP %s",
    async (status) => {
      const { client } = clientFor(
        {
          ...meta,
          error: {
            code: status === 503 ? "NOT_READY" : "REQUEST_FAILED",
            message: "internal credential text must not be shown",
            http_status: status,
            retryable: true,
            run_id: "run-1",
            fields: null,
          },
        },
        status,
      );
      const failure = await client.getReady().catch((error: unknown) => error);
      expect(failure).toBeInstanceOf(WorkbenchApiError);
      expect(failure).toMatchObject({
        kind: "http",
        httpStatus: status,
        retryable: true,
        traceId: "trace-1",
        requestId: "request-1",
        runId: "run-1",
      });
      expect(String(failure)).not.toContain("credential");
    },
  );

  it("rejects conflicting error status and request correlation", async () => {
    const { client, fetchImpl } = clientFor(
      {
        ...meta,
        error: {
          code: "NOT_READY",
          message: "Unavailable",
          http_status: 409,
          retryable: true,
        },
      },
      503,
    );
    await expect(client.getReady()).rejects.toMatchObject({ kind: "protocol" });
    fetchImpl.mockResolvedValue(json(capabilities, 200, "other-request"));
    await expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "protocol",
    });
    fetchImpl.mockResolvedValue(
      json(
        {
          ...meta,
          error: {
            code: "NOT_READY",
            message: "Unavailable",
            http_status: 503,
            retryable: true,
          },
        },
        503,
        "other-request",
      ),
    );
    await expect(client.getReady()).rejects.toMatchObject({ kind: "protocol" });
  });

  it("reports proxy HTML/network errors without displaying response contents", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("<html>secret proxy stack</html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
    );
    const client = createWorkbenchApiClient({ fetchImpl });
    await expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "transport",
      httpStatus: 502,
    });
    fetchImpl.mockRejectedValue(new Error("secret connection details"));
    await expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "transport",
      code: "NETWORK_ERROR",
    });
  });

  it("rejects invalid successful JSON and incorrect content types", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response("{", { headers: { "Content-Type": "application/json" } }),
      );
    const client = createWorkbenchApiClient({ fetchImpl });
    await expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "protocol",
    });
    fetchImpl.mockResolvedValue(new Response(JSON.stringify(capabilities)));
    await expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "protocol",
    });
  });

  it("times out even when fetch ignores abort and clears its timer", async () => {
    vi.useFakeTimers();
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockImplementation(() => new Promise(() => {}));
    const client = createWorkbenchApiClient({ fetchImpl, timeoutMs: 20 });
    const result = expect(client.getCapabilities()).rejects.toMatchObject({
      kind: "timeout",
      code: "TIMEOUT",
    });
    await vi.advanceTimersByTimeAsync(20);
    await result;
    expect(fetchImpl.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("distinguishes caller cancellation from timeout and removes the listener", async () => {
    vi.useFakeTimers();
    const signal = new AbortController();
    const remove = vi.spyOn(signal.signal, "removeEventListener");
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockImplementation(() => new Promise(() => {}));
    const client = createWorkbenchApiClient({ fetchImpl });
    const result = expect(
      client.getCapabilities({ signal: signal.signal }),
    ).rejects.toMatchObject({ kind: "cancelled", retryable: false });
    signal.abort();
    await result;
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function));
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not fetch for an already aborted signal and clears successful-request timers", async () => {
    vi.useFakeTimers();
    const signal = new AbortController();
    signal.abort();
    const { client, fetchImpl } = clientFor(capabilities);
    await expect(
      client.getCapabilities({ signal: signal.signal }),
    ).rejects.toMatchObject({ kind: "cancelled" });
    expect(fetchImpl).not.toHaveBeenCalled();
    await client.getCapabilities();
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([
    "postgres://db/secret",
    "https://user:password@example.com/api",
    "//example.com/api",
    "api/v1",
    "/api/v1?token=secret",
    "/api/v1#secret",
    " https://example.com/api",
    "/api\\v1",
  ])("rejects unsafe API base %s", (baseUrl) => {
    expect(() => createWorkbenchApiClient({ baseUrl })).toThrow(
      WorkbenchApiError,
    );
  });

  it("supports an explicitly public origin/path and configured public environment override", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => json(capabilities));
    await createWorkbenchApiClient({
      baseUrl: "https://api.example.test/public/v1/",
      fetchImpl,
    }).getCapabilities();
    expect(fetchImpl.mock.calls[0][0]).toBe(
      "https://api.example.test/public/v1/capabilities",
    );
    vi.stubEnv("VITE_WORKBENCH_API_BASE_URL", "/public/api/v1");
    await createWorkbenchApiClient({ fetchImpl }).getCapabilities();
    expect(fetchImpl.mock.calls[1][0]).toBe("/public/api/v1/capabilities");
  });
});
