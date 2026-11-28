import type {
  AgentCatalog,
  AgentRunDetail,
  AgentRunPage,
  AgentRunStatus,
  AgentSelectionResult,
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
  DocumentPage,
  DocumentDetail,
  ActiveChunkPageResponse,
  IngestionResponse,
  IngestionJobResponse,
  UploadLocation,
} from "./contracts";
import {
  decodeAgentCatalog,
  decodeAgentRunDetail,
  decodeAgentRunPage,
  decodeAgentSelection,
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
  validateAgentProfileId,
  decodeDocumentPage,
  decodeDocumentDetail,
  decodeActiveChunkPage,
  decodeIngestionResponse,
  decodeIngestionJob,
  type DocumentDecodeContext,
} from "./decode";
import { invalidResponse, WorkbenchApiError } from "./errors";

export { WorkbenchApiError } from "./errors";

export type RequestOptions = { signal?: AbortSignal };
export type WorkspaceOptions = RequestOptions & {
  cursor?: string;
  limit?: number;
};
export type AgentRunOptions = WorkspaceOptions & {
  agentId?: string;
  model?: string;
  status?: AgentRunStatus;
};
export type DocumentContextOptions = RequestOptions & DocumentDecodeContext;
export type DocumentPageOptions = WorkspaceOptions & DocumentDecodeContext;
export type ChunkPageOptions = DocumentPageOptions;
export type DocumentUploadRequest = {
  file: File;
  idempotencyKey: string;
  sourceId?: string;
  expectedActiveVersionId?: string;
  pdfAvailable?: boolean;
  uploadLocation?: UploadLocation;
};
type RequestTransport = {
  method?: "POST" | "PUT";
  configuration?: boolean;
  operations?: boolean;
  headers?: Record<string, string>;
  timeoutMs?: number;
  maxResponseChars?: number;
} & (
  | { body?: object; form?: never; upload?: never }
  | { body?: never; form: FormData; upload: true }
);
export type WorkbenchApiClient = {
  listDocuments(
    workspaceId: string,
    options?: DocumentPageOptions,
  ): Promise<DocumentPage>;
  getDocumentDetail(
    workspaceId: string,
    sourceId: string,
    options?: DocumentContextOptions,
  ): Promise<DocumentDetail>;
  listActiveChunks(
    workspaceId: string,
    sourceId: string,
    options?: ChunkPageOptions,
  ): Promise<ActiveChunkPageResponse>;
  getIngestionJob(
    workspaceId: string,
    jobId: string,
    options?: RequestOptions,
  ): Promise<IngestionJobResponse>;
  uploadDocument(
    workspaceId: string,
    body: DocumentUploadRequest,
    options?: RequestOptions,
  ): Promise<IngestionResponse>;
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
  getAgentCatalog(options?: RequestOptions): Promise<AgentCatalog>;
  listAgentRuns(options?: AgentRunOptions): Promise<AgentRunPage>;
  getAgentRun(
    runId: string,
    options?: WorkspaceOptions,
  ): Promise<AgentRunDetail>;
  saveAgentSelection(
    agentId: string,
    profileId: string,
    revision: string,
    options?: RequestOptions,
  ): Promise<AgentSelectionResult>;
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

function pageQuery({ limit = 50, cursor }: WorkspaceOptions): URLSearchParams {
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100)
    throw new WorkbenchApiError("Page limit must be between 1 and 100.", {
      kind: "configuration",
      code: "INVALID_PAGE_LIMIT",
    });
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor !== undefined) query.set("cursor", validateCursor(cursor));
  return query;
}

function validateUpload(body: DocumentUploadRequest): string {
  const fail = (code: string, message: string): never => {
    throw new WorkbenchApiError(message, { kind: "configuration", code });
  };
  if (!/^[A-Za-z0-9_-]{8,128}$/.test(body.idempotencyKey))
    fail(
      "INVALID_IDEMPOTENCY_KEY",
      "Use the same secure operation key when retrying an upload.",
    );
  if (
    (body.sourceId === undefined) !==
    (body.expectedActiveVersionId === undefined)
  )
    fail(
      "INVALID_UPDATE_FIELDS",
      "Replacement requires a source and its expected active version.",
    );
  const rules: Record<string, readonly string[]> = {
    txt: ["text/plain"],
    md: ["text/markdown", "text/x-markdown", "text/plain"],
    markdown: ["text/markdown", "text/x-markdown", "text/plain"],
    py: ["text/x-python", "application/x-python-code", "text/plain"],
    pdf: ["application/pdf"],
  };
  const extension = body.file.name.split(".").at(-1)?.toLowerCase() ?? "";
  const aliases = Object.hasOwn(rules, extension)
    ? rules[extension]
    : undefined;
  const mime = body.file.type.split(";", 1)[0].trim().toLowerCase();
  if (!aliases || (mime && !aliases.includes(mime)))
    return fail(
      "UNSUPPORTED_FORMAT",
      "Choose a qualified TXT, Markdown, Python or available text-layer PDF file.",
    );
  if (extension === "pdf" && body.pdfAvailable !== true)
    fail(
      "PDF_UNAVAILABLE",
      "PDF ingestion is unavailable in the current backend.",
    );
  const maximum = extension === "pdf" ? 8388608 : 1048576;
  if (
    !Number.isSafeInteger(body.file.size) ||
    body.file.size < 1 ||
    body.file.size > maximum
  )
    fail(
      "CONTENT_LIMIT_EXCEEDED",
      `Choose a nonempty file no larger than ${maximum} bytes.`,
    );
  return mime || aliases[0];
}

export function createWorkbenchApiClient({
  baseUrl = import.meta.env.VITE_WORKBENCH_API_BASE_URL ?? "/api/v1",
  fetchImpl = globalThis.fetch,
  timeoutMs = 5000,
  searchTimeoutMs = 15000,
  uploadTimeoutMs = 240000,
}: {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  searchTimeoutMs?: number;
  uploadTimeoutMs?: number;
} = {}): WorkbenchApiClient {
  const base = publicBase(baseUrl);
  if (
    [timeoutMs, searchTimeoutMs].some(
      (value) => !Number.isSafeInteger(value) || value < 1 || value > 60000,
    ) ||
    !Number.isSafeInteger(uploadTimeoutMs) ||
    uploadTimeoutMs < 1 ||
    uploadTimeoutMs > 240000
  )
    throw new WorkbenchApiError("Use a bounded API request timeout.", {
      kind: "configuration",
      code: "INVALID_TIMEOUT",
    });

  async function request<T extends ApiMeta>(
    path: string,
    decode: (value: unknown, httpStatus: number) => T,
    { signal }: RequestOptions = {},
    transport: RequestTransport = {},
  ): Promise<T> {
    const controller = new AbortController();
    let rejectAbort: (error: WorkbenchApiError) => void = () => {};
    const interrupted = new Promise<never>((_resolve, reject) => {
      rejectAbort = reject;
    });
    const cancel = (timeout: boolean) => {
      const error = new WorkbenchApiError(
        timeout
          ? transport.upload
            ? "Upload timed out; server outcome may be unknown. Retry the same operation key."
            : "Backend request timed out. Retry when available."
          : transport.upload
            ? "Request stopped locally; server outcome may be unknown."
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
          (transport.configuration || transport.operations) &&
          typeof window !== "undefined" &&
          new URL(base, window.location.href).origin !== window.location.origin
        ) {
          throw new WorkbenchApiError(
            transport.operations
              ? "Agent operations require the application's same-origin API proxy."
              : "Configuration requires the application's same-origin API proxy.",
            {
              kind: "configuration",
              code: transport.operations
                ? "AGENT_OPERATIONS_SAME_ORIGIN_REQUIRED"
                : "CONFIGURATION_SAME_ORIGIN_REQUIRED",
            },
          );
        }
        if (signal?.aborted) {
          cancel(false);
          throw controller.signal.reason;
        }
        const response = await fetchImpl(`${base}${path}`, {
          method:
            transport.method ??
            (transport.body === undefined && transport.form === undefined
              ? "GET"
              : "POST"),
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
          ...(transport.form !== undefined
            ? { body: transport.form }
            : transport.body === undefined
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
          const messages: Record<string, string> = {
            PAYLOAD_TOO_LARGE:
              "The upload exceeds the server's file or request byte limit.",
            DOCUMENT_PROCESSING_LIMIT_EXCEEDED:
              "The file was received, but its processing exceeded a chunk count, text or metadata limit.",
            CORPUS_LIMIT_EXCEEDED:
              "The workspace has reached its indexed document capacity. This is not the file upload size limit.",
            MODEL_TOKEN_LIMIT_EXCEEDED:
              "A prepared passage exceeds the embedding model's token budget. This is not the file byte limit.",
          };
          throw new WorkbenchApiError(
            messages[failure.error.code] ??
              "Backend request failed. Check the reported code and retry when available.",
            {
              kind: "http",
              code: failure.error.code,
              httpStatus: response.status,
              retryable: failure.error.retryable,
              requestId: failure.request_id,
              traceId: failure.trace_id,
              runId: failure.error.run_id ?? undefined,
              jobId: failure.error.job_id ?? undefined,
            },
          );
        }
        if (
          response.status !== 200 &&
          !(transport.upload && response.status === 201)
        )
          invalidResponse();
        const data = decode(value, response.status);
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
        transport.upload
          ? "Upload connection failed; server outcome may be unknown. Retry the same operation key."
          : "Backend is unavailable. Check the API service and proxy.",
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
    listDocuments: async (workspaceId, options = {}) => {
      const scope = validateResourceId(workspaceId);
      return request(
        `/workspaces/${encodeURIComponent(scope)}/documents?${pageQuery(options)}`,
        (value) => decodeDocumentPage(value, scope, options),
        options,
      );
    },
    getDocumentDetail: async (workspaceId, sourceId, options = {}) => {
      const scope = validateResourceId(workspaceId);
      const source = validateResourceId(sourceId);
      return request(
        `/workspaces/${encodeURIComponent(scope)}/documents/${encodeURIComponent(source)}`,
        (value) => decodeDocumentDetail(value, scope, source, options),
        options,
        { maxResponseChars: 4194304 },
      );
    },
    listActiveChunks: async (workspaceId, sourceId, options = {}) => {
      const scope = validateResourceId(workspaceId);
      const source = validateResourceId(sourceId);
      return request(
        `/workspaces/${encodeURIComponent(scope)}/documents/${encodeURIComponent(source)}/chunks?${pageQuery(options)}`,
        (value) => decodeActiveChunkPage(value, scope, source, options),
        options,
        { maxResponseChars: 16777216 },
      );
    },
    getIngestionJob: async (workspaceId, jobId, options) => {
      const scope = validateResourceId(workspaceId);
      const job = validateResourceId(jobId);
      return request(
        `/workspaces/${encodeURIComponent(scope)}/jobs/${encodeURIComponent(job)}`,
        (value) => decodeIngestionJob(value, scope, job),
        options,
      );
    },
    uploadDocument: async (workspaceId, body, options) => {
      const scope = validateResourceId(workspaceId);
      const mime = validateUpload(body);
      const form = new FormData();
      // Browsers otherwise send application/octet-stream for extensions without an OS MIME mapping.
      form.append(
        "file",
        body.file.type ? body.file : body.file.slice(0, body.file.size, mime),
        body.file.name,
      );
      if (
        body.sourceId !== undefined &&
        body.expectedActiveVersionId !== undefined
      ) {
        form.append("source_id", validateResourceId(body.sourceId));
        form.append(
          "expected_active_version_id",
          validateResourceId(body.expectedActiveVersionId),
        );
      }
      if (body.uploadLocation !== undefined)
        form.append("upload_location", JSON.stringify(body.uploadLocation));
      return request(
        `/workspaces/${encodeURIComponent(scope)}/documents`,
        (value, status) =>
          decodeIngestionResponse(value, scope, status, body.sourceId),
        options,
        {
          form,
          upload: true,
          headers: { "Idempotency-Key": body.idempotencyKey },
          timeoutMs: uploadTimeoutMs,
        },
      );
    },
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
    getAgentCatalog: (options) =>
      request("/agents", decodeAgentCatalog, options, { operations: true }),
    listAgentRuns: async ({ agentId, model, status, ...options } = {}) => {
      const query = pageQuery(options);
      if (agentId) query.set("agent_id", validateResourceId(agentId));
      if (model) query.set("model", model);
      if (status) query.set("status", status);
      return request(`/agents/runs?${query}`, decodeAgentRunPage, options, {
        operations: true,
      });
    },
    getAgentRun: async (runId, options = {}) => {
      const id = validateResourceId(runId);
      return request(
        `/agents/runs/${encodeURIComponent(id)}?${pageQuery(options)}`,
        (value) => decodeAgentRunDetail(value, id),
        options,
        { operations: true, maxResponseChars: 500000 },
      );
    },
    saveAgentSelection: async (agentId, profileId, revision, options) => {
      const agent = validateResourceId(agentId);
      const profile = validateAgentProfileId(profileId);
      return request(
        `/agents/${encodeURIComponent(agent)}/selection`,
        (value) => decodeAgentSelection(value, agent, profile),
        options,
        {
          operations: true,
          method: "PUT",
          headers: { "X-Workbench-Request": "agent-operations" },
          body: { profile_id: profile, expected_revision: revision },
        },
      );
    },
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
