import type {
  ApiMeta,
  ConfigurationDocument,
  ConfigurationValidation,
  BackendCapabilities,
  LiveResponse,
  LocalSourceFile,
  ReadyResponse,
  SearchRequest,
  SearchResponse,
  SourceRevealResponse,
  WorkspacePage,
} from "./contracts";
import {
  decodeCapabilities,
  decodeConfigurationDocument,
  decodeConfigurationSave,
  decodeConfigurationValidation,
  decodeFailure,
  decodeLive,
  decodeLocalSourceFile,
  decodeReady,
  decodeSearch,
  decodeSearchRequest,
  decodeSourceReveal,
  decodeWorkspaces,
  validateCursor,
  validateResourceId,
} from "./decode";
import { invalidResponse, WorkbenchApiError } from "./errors";

export { WorkbenchApiError } from "./errors";

export type RequestOptions = { signal?: AbortSignal };
export type WorkspaceOptions = RequestOptions & {
  cursor?: string;
  limit?: number;
};
export type WorkbenchApiClient = {
  getConfiguration(options?: RequestOptions): Promise<ConfigurationDocument>;
  validateConfiguration(
    yaml: string,
    options?: RequestOptions,
  ): Promise<ConfigurationValidation>;
  saveConfiguration(
    yaml: string,
    expectedRevision: string,
    options?: RequestOptions,
  ): Promise<ConfigurationDocument>;
  getLive(options?: RequestOptions): Promise<LiveResponse>;
  getReady(options?: RequestOptions): Promise<ReadyResponse>;
  getCapabilities(options?: RequestOptions): Promise<BackendCapabilities>;
  listWorkspaces(options?: WorkspaceOptions): Promise<WorkspacePage>;
  search(
    workspaceId: string,
    body: SearchRequest,
    options?: RequestOptions,
  ): Promise<SearchResponse>;
  getLocalFile(
    workspaceId: string,
    sourceId: string,
    versionId: string,
    options?: RequestOptions,
  ): Promise<LocalSourceFile>;
  revealLocalFile(
    workspaceId: string,
    sourceId: string,
    versionId: string,
    options?: RequestOptions,
  ): Promise<SourceRevealResponse>;
};

function publicBase(value: string): string {
  const fail = () => {
    throw new WorkbenchApiError(
      "Use a public HTTP API URL without credentials, query or fragment.",
      { kind: "configuration", code: "INVALID_API_URL" },
    );
  };
  if (
    !value ||
    value.trim() !== value ||
    /[\s\\\u0000-\u001f\u007f]/u.test(value)
  )
    fail();
  let url: URL;
  try {
    url = new URL(value, "http://workbench.invalid");
  } catch {
    return fail();
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    value.startsWith("//")
  )
    fail();
  if (!value.startsWith("/") && !/^https?:\/\//.test(value)) fail();
  return value.replace(/\/+$/, "");
}

function correlate(response: Response, data: ApiMeta): void {
  const header = response.headers.get("X-Request-ID");
  if (header !== null && header !== data.request_id) invalidResponse();
}

export function createWorkbenchApiClient({
  baseUrl = import.meta.env.VITE_WORKBENCH_API_BASE_URL ?? "/api/v1",
  fetchImpl = globalThis.fetch,
  timeoutMs = 5000,
  searchTimeoutMs = 15000,
}: {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  searchTimeoutMs?: number;
} = {}): WorkbenchApiClient {
  const base = publicBase(baseUrl);
  if (
    [timeoutMs, searchTimeoutMs].some(
      (value) => !Number.isSafeInteger(value) || value < 1 || value > 60000,
    )
  )
    throw new WorkbenchApiError("Use a bounded API request timeout.", {
      kind: "configuration",
      code: "INVALID_TIMEOUT",
    });

  async function request<T extends ApiMeta>(
    path: string,
    decode: (value: unknown) => T,
    { signal }: RequestOptions = {},
    transport: {
      body?: object;
      method?: "POST" | "PUT";
      configuration?: boolean;
      headers?: Record<string, string>;
      timeoutMs?: number;
      maxResponseChars?: number;
    } = {},
  ): Promise<T> {
    const controller = new AbortController();
    let rejectAbort: (error: WorkbenchApiError) => void = () => {};
    const interrupted = new Promise<never>((_resolve, reject) => {
      rejectAbort = reject;
    });
    const cancel = (timeout: boolean) => {
      const error = new WorkbenchApiError(
        timeout
          ? "Backend request timed out. Retry when available."
          : "Backend request interrupted locally.",
        {
          kind: timeout ? "timeout" : "cancelled",
          code: timeout ? "TIMEOUT" : "CANCELLED",
          retryable: timeout,
        },
      );
      controller.abort(error);
      rejectAbort(error);
    };
    const onAbort = () => cancel(false);
    signal?.addEventListener("abort", onAbort, { once: true });
    const timer = setTimeout(
      () => cancel(true),
      transport.timeoutMs ?? timeoutMs,
    );
    try {
      const operation = async () => {
        if (
          transport.configuration &&
          typeof window !== "undefined" &&
          new URL(base, window.location.href).origin !== window.location.origin
        ) {
          throw new WorkbenchApiError(
            "Configuration requires the application's same-origin API proxy.",
            {
              kind: "configuration",
              code: "CONFIGURATION_SAME_ORIGIN_REQUIRED",
            },
          );
        }
        if (signal?.aborted) {
          cancel(false);
          throw controller.signal.reason;
        }
        const response = await fetchImpl(`${base}${path}`, {
          method:
            transport.method ?? (transport.body === undefined ? "GET" : "POST"),
          headers: {
            Accept: "application/json",
            ...(transport.configuration
              ? { "X-Workbench-Request": "configuration" }
              : {}),
            ...transport.headers,
            ...(transport.body === undefined
              ? {}
              : { "Content-Type": "application/json" }),
          },
          ...(transport.body === undefined
            ? {}
            : { body: JSON.stringify(transport.body) }),
          signal: controller.signal,
          credentials: "omit",
          cache: "no-store",
          redirect: "error",
        });
        const contentType = response.headers
          .get("Content-Type")
          ?.split(";")[0]
          .trim()
          .toLowerCase();
        if (contentType !== "application/json") {
          if (response.ok) invalidResponse();
          throw new WorkbenchApiError(
            "Backend is unavailable. Check the API service and proxy.",
            {
              kind: "transport",
              code: "INVALID_GATEWAY_RESPONSE",
              httpStatus: response.status,
              retryable: true,
            },
          );
        }
        const responseBody = await response.text();
        if (responseBody.length > (transport.maxResponseChars ?? 1048576))
          invalidResponse();
        let value: unknown;
        try {
          value = JSON.parse(responseBody);
        } catch {
          return invalidResponse();
        }
        if (!response.ok) {
          const failure = decodeFailure(value, response.status);
          correlate(response, failure);
          throw new WorkbenchApiError(
            "Backend request failed. Check the reported code and retry when available.",
            {
              kind: "http",
              code: failure.error.code,
              httpStatus: response.status,
              retryable: failure.error.retryable,
              requestId: failure.request_id,
              traceId: failure.trace_id,
              runId: failure.error.run_id ?? undefined,
            },
          );
        }
        if (response.status !== 200) invalidResponse();
        const data = decode(value);
        correlate(response, data);
        return data;
      };
      return await Promise.race([operation(), interrupted]);
    } catch (error) {
      if (error instanceof WorkbenchApiError) throw error;
      if (
        controller.signal.aborted &&
        controller.signal.reason instanceof WorkbenchApiError
      )
        throw controller.signal.reason;
      throw new WorkbenchApiError(
        "Backend is unavailable. Check the API service and proxy.",
        { kind: "transport", code: "NETWORK_ERROR", retryable: true },
      );
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
  }

  const localFilePath = (
    workspaceId: string,
    sourceId: string,
    versionId: string,
  ) => {
    const [workspace, source, version] = [workspaceId, sourceId, versionId].map(
      (value) => encodeURIComponent(validateResourceId(value)),
    );
    return `/workspaces/${workspace}/sources/${source}/versions/${version}/local-file`;
  };

  return {
    getConfiguration: (options) =>
      request("/configuration", decodeConfigurationDocument, options, {
        configuration: true,
        maxResponseChars: 400000,
      }),
    validateConfiguration: (yaml, options) =>
      request(
        "/configuration/validate",
        decodeConfigurationValidation,
        options,
        {
          configuration: true,
          body: { yaml },
        },
      ),
    saveConfiguration: (yaml, expectedRevision, options) =>
      request("/configuration", decodeConfigurationSave, options, {
        configuration: true,
        method: "PUT",
        body: { yaml, expected_revision: expectedRevision },
        maxResponseChars: 400000,
      }),
    search: async (workspaceId, body, options) => {
      const scope = validateResourceId(workspaceId);
      const submitted = decodeSearchRequest(body);
      return request(
        `/workspaces/${encodeURIComponent(scope)}/search`,
        (value) => decodeSearch(value, scope, submitted),
        options,
        {
          body: submitted,
          timeoutMs: searchTimeoutMs,
          maxResponseChars: 67108864,
        },
      );
    },
    getLocalFile: async (workspaceId, sourceId, versionId, options) =>
      request(
        localFilePath(workspaceId, sourceId, versionId),
        decodeLocalSourceFile,
        options,
      ),
    revealLocalFile: async (workspaceId, sourceId, versionId, options) =>
      request(
        `${localFilePath(workspaceId, sourceId, versionId)}/reveal`,
        decodeSourceReveal,
        options,
        { body: {} },
      ),
    getLive: (options) => request("/health/live", decodeLive, options),
    getReady: (options) => request("/health/ready", decodeReady, options),
    getCapabilities: (options) =>
      request("/capabilities", decodeCapabilities, options),
    listWorkspaces: (options = {}) => {
      const { cursor, limit = 50 } = options;
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100)
        return Promise.reject(
          new WorkbenchApiError(
            "Workspace page limit must be between 1 and 100.",
            { kind: "configuration", code: "INVALID_PAGE_LIMIT" },
          ),
        );
      const query = new URLSearchParams({ limit: String(limit) });
      if (cursor !== undefined) {
        try {
          query.set("cursor", validateCursor(cursor));
        } catch (error) {
          return Promise.reject(error);
        }
      }
      return request(`/workspaces?${query}`, decodeWorkspaces, options);
    },
  };
}
