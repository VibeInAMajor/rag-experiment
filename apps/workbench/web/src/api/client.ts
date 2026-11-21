import type {
  ApiMeta,
  BackendCapabilities,
  LiveResponse,
  ReadyResponse,
  WorkspacePage,
} from "./contracts";
import {
  decodeCapabilities,
  decodeFailure,
  decodeLive,
  decodeReady,
  decodeWorkspaces,
  validateCursor,
} from "./decode";
import { invalidResponse, WorkbenchApiError } from "./errors";

export { WorkbenchApiError } from "./errors";

export type RequestOptions = { signal?: AbortSignal };
export type WorkspaceOptions = RequestOptions & {
  cursor?: string;
  limit?: number;
};
export type WorkbenchApiClient = {
  getLive(options?: RequestOptions): Promise<LiveResponse>;
  getReady(options?: RequestOptions): Promise<ReadyResponse>;
  getCapabilities(options?: RequestOptions): Promise<BackendCapabilities>;
  listWorkspaces(options?: WorkspaceOptions): Promise<WorkspacePage>;
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
}: {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
} = {}): WorkbenchApiClient {
  const base = publicBase(baseUrl);
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000)
    throw new WorkbenchApiError("Use a bounded API request timeout.", {
      kind: "configuration",
      code: "INVALID_TIMEOUT",
    });

  async function request<T extends ApiMeta>(
    path: string,
    decode: (value: unknown) => T,
    { signal }: RequestOptions = {},
  ): Promise<T> {
    const controller = new AbortController();
    let rejectAbort: (error: WorkbenchApiError) => void = () => {};
    const interrupted = new Promise<never>((_resolve, reject) => {
      rejectAbort = reject;
    });
    const cancel = (timeout: boolean) => {
      const error = new WorkbenchApiError(
        timeout
          ? "Backend discovery timed out. Retry the connection."
          : "Backend discovery cancelled.",
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
    const timer = setTimeout(() => cancel(true), timeoutMs);
    try {
      const operation = async () => {
        if (signal?.aborted) {
          cancel(false);
          throw controller.signal.reason;
        }
        const response = await fetchImpl(`${base}${path}`, {
          method: "GET",
          headers: { Accept: "application/json" },
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
        const body = await response.text();
        if (body.length > 1048576) invalidResponse();
        let value: unknown;
        try {
          value = JSON.parse(body);
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

  return {
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
