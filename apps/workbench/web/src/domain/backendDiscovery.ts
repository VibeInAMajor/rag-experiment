import type { WorkbenchApiClient } from "../api/client";
import { WorkbenchApiError } from "../api/client";
import type {
  BackendCapabilities,
  BackendProfile,
  WorkspaceItem,
} from "../api/contracts";

export type DiscoveryError = {
  code: string;
  message: string;
  traceId?: string;
  requestId?: string;
  httpStatus?: number;
};

type DiscoveryDetails = {
  lastCheckedAt: string | null;
  capabilities?: BackendCapabilities;
  workspaces: WorkspaceItem[];
  error?: DiscoveryError;
};

type DiscoverySelection =
  | {
      status: "ready";
      selectedWorkspaceId: string;
      profile: BackendProfile;
    }
  | {
      status:
        | "unconfigured"
        | "checking"
        | "not_ready"
        | "unavailable"
        | "incompatible";
      selectedWorkspaceId: null;
      profile: null;
    };

export type BackendDiscoveryState = DiscoveryDetails & DiscoverySelection;
type DiscoveryResult = Omit<DiscoveryDetails, "lastCheckedAt"> &
  DiscoverySelection;

const supportedProfile = {
  id: "postgres-fts-baseline",
  revision: "postgres-fts-baseline-r1",
  scoreType: "postgres_ts_rank_cd",
};
const maxWorkspacePages = 10;
const discoveryTimeoutMs = 15000;

export function initialDiscoveryState(): DiscoveryDetails & {
  status: "unconfigured";
  selectedWorkspaceId: null;
  profile: null;
} {
  return {
    status: "unconfigured",
    lastCheckedAt: null,
    workspaces: [],
    selectedWorkspaceId: null,
    profile: null,
  };
}

function diagnostic(error: unknown): DiscoveryError {
  if (error instanceof WorkbenchApiError)
    return {
      code: error.code,
      message: error.message,
      ...(error.traceId ? { traceId: error.traceId } : {}),
      ...(error.requestId ? { requestId: error.requestId } : {}),
      ...(error.httpStatus ? { httpStatus: error.httpStatus } : {}),
    };
  return {
    code: "DISCOVERY_UNAVAILABLE",
    message: "Backend discovery failed. Check the API connection and refresh.",
  };
}

function conflict(code: string, message: string): DiscoveryError {
  return { code, message };
}

// Owns request generations independently of React so cancellation is testable.
export class BackendDiscovery {
  state: BackendDiscoveryState = initialDiscoveryState();
  private generation = 0;
  private controller?: AbortController;
  private preferredWorkspaceId: string | null = null;

  constructor(
    private client: WorkbenchApiClient | (() => WorkbenchApiClient),
    private onChange: (state: BackendDiscoveryState) => void,
  ) {}

  private publish(state: BackendDiscoveryState) {
    this.state = state;
    this.onChange(state);
  }

  invalidate() {
    this.generation++;
    this.controller?.abort();
    this.controller = undefined;
  }

  reset() {
    this.invalidate();
    this.preferredWorkspaceId = null;
    this.publish(initialDiscoveryState());
  }

  selectWorkspace(workspaceId: string): boolean {
    if (
      this.state.status !== "ready" ||
      !this.state.workspaces.some(
        (workspace) => workspace.workspace_id === workspaceId,
      ) ||
      !this.state.capabilities?.profiles.some((profile) =>
        profile.workspace_ids.includes(workspaceId),
      )
    )
      return false;
    if (this.state.selectedWorkspaceId !== workspaceId) {
      this.preferredWorkspaceId = workspaceId;
      void this.refresh();
    }
    return true;
  }

  async refresh(): Promise<void> {
    this.invalidate();
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    this.publish({
      ...initialDiscoveryState(),
      status: "checking",
      lastCheckedAt: this.state.lastCheckedAt,
    });
    const current = () =>
      generation === this.generation && !controller.signal.aborted;
    const finish = (state: DiscoveryResult) => {
      if (current())
        this.publish({
          ...state,
          lastCheckedAt: new Date().toISOString(),
        });
    };
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        reject(new DOMException("Discovery timed out.", "TimeoutError"));
        controller.abort();
      }, discoveryTimeoutMs);
    });
    let onAbort = () => {};
    const cancelled = new Promise<never>((_, reject) => {
      onAbort = () =>
        reject(new DOMException("Discovery cancelled.", "AbortError"));
      controller.signal.addEventListener("abort", onAbort, { once: true });
    });
    try {
      await Promise.race([
        this.discover(controller.signal, finish, current),
        deadline,
        cancelled,
      ]);
    } catch (error) {
      if (generation !== this.generation) return;
      const timedOut =
        error instanceof DOMException && error.name === "TimeoutError";
      this.publish({
        ...initialDiscoveryState(),
        status:
          error instanceof WorkbenchApiError &&
          ["protocol", "configuration"].includes(error.kind)
            ? "incompatible"
            : "unavailable",
        lastCheckedAt: new Date().toISOString(),
        error: timedOut
          ? conflict(
              "DISCOVERY_TIMEOUT",
              "Backend check timed out. Refresh to retry.",
            )
          : diagnostic(error),
      });
    } finally {
      clearTimeout(timer);
      controller.signal.removeEventListener("abort", onAbort);
      if (generation === this.generation) this.controller = undefined;
    }
  }

  private async discover(
    signal: AbortSignal,
    finish: (state: DiscoveryResult) => void,
    current: () => boolean,
  ) {
    const client =
      typeof this.client === "function" ? this.client() : this.client;
    const [liveResult, readyResult, capabilitiesResult] =
      await Promise.allSettled([
        client.getLive({ signal }),
        client.getReady({ signal }),
        client.getCapabilities({ signal }),
      ]);
    if (!current()) return;
    if (liveResult.status === "rejected") throw liveResult.reason;
    if (capabilitiesResult.status === "rejected")
      throw capabilitiesResult.reason;
    const capabilities = capabilitiesResult.value;
    const unavailable = (
      status: "not_ready" | "incompatible",
      error: DiscoveryError,
    ) =>
      finish({
        status,
        capabilities,
        workspaces: [],
        selectedWorkspaceId: null,
        profile: null,
        error,
      });
    if (liveResult.value.backend_revision !== capabilities.backend_revision) {
      unavailable(
        "incompatible",
        conflict(
          "BACKEND_REVISION_MISMATCH",
          "Backend changed during discovery. Refresh to retry.",
        ),
      );
      return;
    }
    if (readyResult.status === "rejected") {
      const error: unknown = readyResult.reason;
      if (
        error instanceof WorkbenchApiError &&
        error.httpStatus === 503 &&
        error.code === "NOT_READY"
      ) {
        unavailable(
          capabilities.dependencies.database.status === "incompatible"
            ? "incompatible"
            : "not_ready",
          diagnostic(error),
        );
        return;
      }
      throw error;
    }
    const ready = readyResult.value;
    if (
      ready.backend_revision !== capabilities.backend_revision ||
      ready.ready_profile_ids.length !== capabilities.profiles.length ||
      ready.ready_profile_ids.some(
        (id) =>
          !capabilities.profiles.some((profile) => profile.profile_id === id),
      )
    ) {
      unavailable(
        "incompatible",
        conflict(
          "READINESS_MISMATCH",
          "Readiness and advertised profiles disagree. Refresh to retry.",
        ),
      );
      return;
    }
    if (
      capabilities.service_state !== "running" ||
      !capabilities.features.search ||
      capabilities.dependencies.database.status !== "ready" ||
      !capabilities.profiles.length
    ) {
      unavailable(
        capabilities.dependencies.database.status === "incompatible"
          ? "incompatible"
          : "not_ready",
        conflict(
          "SEARCH_NOT_READY",
          "Backend search is not ready. Check the database and refresh.",
        ),
      );
      return;
    }
    const profiles = capabilities.profiles.filter(
      (profile) =>
        profile.profile_id === supportedProfile.id &&
        profile.profile_revision === supportedProfile.revision &&
        profile.score_type === supportedProfile.scoreType,
    );
    if (!profiles.length) {
      unavailable(
        "incompatible",
        conflict(
          "PROFILE_NOT_SUPPORTED",
          "No compatible lexical profile is advertised. Update compatible services and refresh.",
        ),
      );
      return;
    }
    const workspaces: WorkspaceItem[] = [];
    const seenIds = new Set<string>();
    const seenCursors = new Set<string>();
    let cursor: string | undefined;
    for (let page = 0; page < maxWorkspacePages; page++) {
      const response = await client.listWorkspaces({
        limit: 50,
        ...(cursor ? { cursor } : {}),
        signal,
      });
      if (!current()) return;
      for (const workspace of response.items) {
        if (seenIds.has(workspace.workspace_id)) {
          unavailable(
            "incompatible",
            conflict(
              "WORKSPACE_PAGE_MISMATCH",
              "Workspace discovery changed. Refresh to retry.",
            ),
          );
          return;
        }
        seenIds.add(workspace.workspace_id);
        if (
          workspace.status === "ready" &&
          profiles.some((profile) =>
            profile.workspace_ids.includes(workspace.workspace_id),
          )
        )
          workspaces.push(workspace);
      }
      if (response.next_cursor === null) break;
      if (
        seenCursors.has(response.next_cursor) ||
        page === maxWorkspacePages - 1
      ) {
        unavailable(
          "incompatible",
          conflict(
            "WORKSPACE_PAGE_LIMIT",
            "Workspace pagination is inconsistent or exceeds the supported limit.",
          ),
        );
        return;
      }
      seenCursors.add(response.next_cursor);
      cursor = response.next_cursor;
    }
    const selectedWorkspaceId =
      this.preferredWorkspaceId ?? workspaces[0]?.workspace_id;
    const profile = profiles.find(
      (item) =>
        selectedWorkspaceId && item.workspace_ids.includes(selectedWorkspaceId),
    );
    if (
      !selectedWorkspaceId ||
      !workspaces.some(
        (workspace) => workspace.workspace_id === selectedWorkspaceId,
      ) ||
      !profile ||
      (capabilities.dependencies.database.workspace_id != null &&
        capabilities.dependencies.database.workspace_id !== selectedWorkspaceId)
    ) {
      unavailable(
        "incompatible",
        conflict(
          "WORKSPACE_NOT_AUTHORIZED",
          "No matching authorized workspace is available for this profile.",
        ),
      );
      return;
    }
    this.preferredWorkspaceId = selectedWorkspaceId;
    finish({
      status: "ready",
      capabilities,
      workspaces,
      selectedWorkspaceId,
      profile,
    });
  }
}
