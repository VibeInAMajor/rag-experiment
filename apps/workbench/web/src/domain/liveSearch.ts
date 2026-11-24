import type { WorkbenchApiClient } from "../api/client";
import { WorkbenchApiError } from "../api/client";
import type {
  BackendProfile,
  SearchRequest,
  SearchResponse,
  SearchResult,
} from "../api/contracts";
import type { ExecutionMode, Graph, Pipeline, PreviewRun } from "./types";
import { portableGraph } from "./graph";

export type LiveRun = {
  id: string;
  source: "live";
  serverRunId?: string;
  requestId?: string;
  traceId?: string;
  profileId: string;
  profileRevision: string;
  corpusRevision?: string;
  workspaceId: string;
  pipelineId: string;
  pipelineName: string;
  graphSnapshot: Graph;
  submitted: SearchRequest;
  startedAt: string;
  status: "Running" | "Completed" | "Failed" | "InterruptedLocally";
  durationMs?: number;
  stages: SearchResponse["stages"];
  results: SearchResult[];
  response?: SearchResponse;
  error?: {
    code: string;
    message: string;
    httpStatus?: number;
    retryable?: boolean;
  };
};

export type RunEntry =
  { source: "preview"; run: PreviewRun } | { source: "live"; run: LiveRun };
export type LiveSearchContext = {
  mode: ExecutionMode;
  pipeline: Pipeline;
  workspaceId: string | null;
  profile: BackendProfile | null;
};
export type LiveRunUpdate = (update: (runs: LiveRun[]) => LiveRun[]) => void;

export function graphFingerprint(graph: Graph): string {
  const { nodes, edges } = portableGraph(graph);
  return JSON.stringify({ nodes, edges });
}

export function liveContextFingerprint(context: LiveSearchContext): string {
  return JSON.stringify([
    context.mode,
    context.pipeline.id,
    graphFingerprint(context.pipeline.graph),
    context.workspaceId,
    context.profile?.profile_id,
    context.profile?.profile_revision,
    context.profile?.kind === "dense_search"
      ? [
          context.profile.embedding_profile_revision,
          context.profile.index_generation,
        ]
      : null,
  ]);
}

function errorDetails(error: unknown): NonNullable<LiveRun["error"]> {
  if (!(error instanceof WorkbenchApiError))
    return {
      code: "SEARCH_FAILED",
      message: "Live search failed. Check the API connection and retry.",
      retryable: true,
    };
  const messages: Record<string, string> = {
    INVALID_REQUEST:
      "The search request is invalid. Check the query and result limits.",
    WORKSPACE_NOT_FOUND:
      "Workspace access changed. Refresh the backend connection.",
    PROFILE_NOT_AVAILABLE:
      "The execution profile changed. Refresh the backend connection.",
    SEARCH_BUSY:
      "The backend is busy. Retry the search when capacity is available.",
    DEPENDENCY_UNAVAILABLE:
      "The database or corpus is unavailable. Refresh the backend connection.",
    NOT_READY: "The backend is not ready. Refresh the backend connection.",
    SEARCH_TIMEOUT:
      "The backend search deadline was reached. Retry when available.",
  };
  return {
    code: error.code,
    message: messages[error.code] ?? error.message,
    httpStatus: error.httpStatus,
    retryable: error.retryable,
  };
}

export class LiveSearchRequests {
  private generation = 0;
  private active?: { id: string; context: string; controller: AbortController };

  constructor(
    private client:
      | Pick<WorkbenchApiClient, "search">
      | (() => Pick<WorkbenchApiClient, "search">),
    private updateRuns: LiveRunUpdate,
    private currentContext: () => LiveSearchContext,
    private onChange: () => void,
    private onInvalidateDiscovery: () => void = () => {},
  ) {}

  get activeRunId(): string | null {
    return this.active?.id ?? null;
  }
  get busy(): boolean {
    return Boolean(this.active);
  }

  private update(id: string, project: (run: LiveRun) => LiveRun) {
    this.updateRuns((runs) =>
      runs.map((run) => (run.id === id ? project(run) : run)),
    );
  }

  stop(notify = true) {
    this.generation++;
    const active = this.active;
    this.active = undefined;
    if (!active) return;
    active.controller.abort();
    this.update(active.id, (run) => ({
      ...run,
      status: "InterruptedLocally",
      error: {
        code: "INTERRUPTED_LOCALLY",
        message:
          "Request interrupted locally; server cancellation is not confirmed.",
        retryable: true,
      },
    }));
    if (notify) this.onChange();
  }

  contextChanged() {
    if (
      this.active &&
      this.active.context !== liveContextFingerprint(this.currentContext())
    )
      this.stop();
  }

  async run(
    pipeline: Pipeline,
    submitted: SearchRequest,
    workspaceId: string,
  ): Promise<void> {
    if (this.active) return;
    const context = this.currentContext();
    if (
      context.mode !== "live" ||
      context.pipeline.id !== pipeline.id ||
      graphFingerprint(context.pipeline.graph) !==
        graphFingerprint(pipeline.graph) ||
      context.workspaceId !== workspaceId ||
      !context.profile ||
      context.profile.profile_id !== submitted.profile_id ||
      context.profile.profile_revision !==
        submitted.expected_profile_revision ||
      !context.profile.workspace_ids.includes(workspaceId)
    )
      return;
    const generation = ++this.generation;
    const controller = new AbortController();
    const id = crypto.randomUUID();
    const identity = liveContextFingerprint(context);
    this.active = { id, context: identity, controller };
    const run: LiveRun = {
      id,
      source: "live",
      profileId: submitted.profile_id,
      profileRevision: submitted.expected_profile_revision,
      workspaceId,
      pipelineId: pipeline.id,
      pipelineName: pipeline.name,
      graphSnapshot: structuredClone(pipeline.graph),
      submitted: structuredClone(submitted),
      startedAt: new Date().toISOString(),
      status: "Running",
      stages: [],
      results: [],
    };
    this.updateRuns((runs) => [run, ...runs].slice(0, 100));
    this.onChange();
    const current = () =>
      generation === this.generation &&
      !controller.signal.aborted &&
      identity === liveContextFingerprint(this.currentContext());
    try {
      const client =
        typeof this.client === "function" ? this.client() : this.client;
      const response = await client.search(workspaceId, submitted, {
        signal: controller.signal,
      });
      if (!current()) return;
      if (
        context.profile.kind === "dense_search" &&
        (response.embedding_profile_revision !==
          context.profile.embedding_profile_revision ||
          response.index_generation !== context.profile.index_generation)
      )
        throw new WorkbenchApiError(
          "The embedding generation changed. Refresh the backend connection.",
          {
            kind: "protocol",
            code: "DENSE_GENERATION_MISMATCH",
            requestId: response.request_id,
            traceId: response.trace_id,
            runId: response.run_id,
          },
        );
      this.update(id, (entry) => ({
        ...entry,
        status: "Completed",
        serverRunId: response.run_id,
        requestId: response.request_id,
        traceId: response.trace_id,
        corpusRevision: response.corpus_revision,
        durationMs: response.duration_ms,
        stages: response.stages,
        results: response.results,
        response,
      }));
    } catch (error) {
      if (!current()) return;
      const interrupted =
        error instanceof WorkbenchApiError && error.kind === "cancelled";
      this.update(id, (entry) => ({
        ...entry,
        status: interrupted ? "InterruptedLocally" : "Failed",
        error: interrupted
          ? {
              code: "INTERRUPTED_LOCALLY",
              message:
                "Request interrupted locally; server cancellation is not confirmed.",
            }
          : errorDetails(error),
        ...(error instanceof WorkbenchApiError
          ? {
              serverRunId: error.runId,
              requestId: error.requestId,
              traceId: error.traceId,
            }
          : {}),
      }));
      if (
        error instanceof WorkbenchApiError &&
        ([404, 409, 503].includes(error.httpStatus ?? 0) ||
          error.code === "DENSE_GENERATION_MISMATCH")
      )
        this.onInvalidateDiscovery();
    } finally {
      if (this.active?.id === id) {
        if (identity !== liveContextFingerprint(this.currentContext()))
          this.stop();
        else {
          this.active = undefined;
          this.onChange();
        }
      }
    }
  }
}
