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
      status: "awaiting_profile";
      selectedWorkspaceId: string;
      profile: null;
    }
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
export type BackendDiscoveryClient = Pick<
  WorkbenchApiClient,
  "getLive" | "getReady" | "getCapabilities" | "listWorkspaces"
>;

export function isSupportedLexicalProfile(profile: BackendProfile): boolean {
  return (
    profile.kind === "lexical_search" &&
    profile.score_type === "postgres_ts_rank_cd" &&
    supportedProfileBounds(profile)
  );
}

export function isSupportedDenseProfile(profile: BackendProfile): boolean {
  return (
    profile.kind === "dense_search" &&
    profile.profile_id === "postgres-dense-exact" &&
    profile.profile_revision === "postgres-dense-exact-r1" &&
    profile.score_type === "cosine_distance" &&
    profile.score_direction === "lower_is_better" &&
    /^[A-Za-z0-9_-]{1,128}$/.test(profile.embedding_profile_revision) &&
    Number.isSafeInteger(profile.index_generation) &&
    profile.index_generation >= 0 &&
    profile.min_coverage === 1 &&
    supportedProfileBounds(profile)
  );
}

export function isSupportedSearchProfile(profile: BackendProfile): boolean {
  return isSupportedLexicalProfile(profile) || isSupportedDenseProfile(profile);
}

function supportedProfileBounds(profile: BackendProfile): boolean {
  const bounded = (value: number, maximum: number) =>
    Number.isSafeInteger(value) && value >= 1 && value <= maximum;
  return (
    /^[A-Za-z0-9_-]{1,128}$/.test(profile.profile_id) &&
    /^[A-Za-z0-9_-]{1,128}$/.test(profile.profile_revision) &&
    profile.parameters.query.type === "string" &&
    profile.parameters.query.min_length === 1 &&
    bounded(profile.parameters.query.max_length, 4096) &&
    profile.parameters.top_k.type === "integer" &&
    profile.parameters.top_k.minimum === 1 &&
    bounded(profile.parameters.top_k.maximum, 50) &&
    bounded(
      profile.parameters.top_k.default,
      profile.parameters.top_k.maximum,
    ) &&
    bounded(profile.limits.max_request_bytes, 32768) &&
    bounded(profile.limits.timeout_ms, 10000) &&
    bounded(profile.limits.max_concurrent_searches, 2) &&
    bounded(profile.limits.max_corpus_chunks, 10000) &&
    bounded(profile.limits.max_corpus_bytes, 52428800)
  );
}
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
  private preferredProfileId: string | null = null;

  constructor(
    private client: BackendDiscoveryClient | (() => BackendDiscoveryClient),
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
    this.preferredProfileId = null;
    this.publish(initialDiscoveryState());
  }

  selectWorkspace(workspaceId: string): boolean {
    if (
      !["ready", "awaiting_profile"].includes(this.state.status) ||
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

  selectProfile(profileId: string): boolean {
    const workspaceId = this.state.selectedWorkspaceId;
    if (
      !["ready", "awaiting_profile"].includes(this.state.status) ||
      !workspaceId ||
      !this.state.capabilities?.profiles.some(
        (profile) =>
          profile.profile_id === profileId &&
          isSupportedSearchProfile(profile) &&
          profile.workspace_ids.includes(workspaceId),
      )
    )
      return false;
    this.preferredProfileId = profileId;
    void this.refresh();
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
    const profiles = capabilities.profiles.filter(isSupportedSearchProfile);
    if (!profiles.length) {
      unavailable(
        "incompatible",
        conflict(
          "PROFILE_NOT_SUPPORTED",
          "No compatible search profile is advertised. Update compatible services and refresh.",
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
    const workspaceProfiles = profiles.filter(
      (item) =>
        selectedWorkspaceId && item.workspace_ids.includes(selectedWorkspaceId),
    );
    if (
      !selectedWorkspaceId ||
      !workspaces.some(
        (workspace) => workspace.workspace_id === selectedWorkspaceId,
      ) ||
      !workspaceProfiles.length ||
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
    const preferredId = this.preferredProfileId ?? "postgres-fts-baseline";
    const profile = workspaceProfiles.find(
      (item) => item.profile_id === preferredId,
    );
    if (!profile) {
      finish({
        status: "awaiting_profile",
        capabilities,
        workspaces,
        selectedWorkspaceId,
        profile: null,
        error: conflict(
          this.preferredProfileId
            ? "PROFILE_NOT_AVAILABLE"
            : "PROFILE_SELECTION_REQUIRED",
          this.preferredProfileId
            ? "The selected profile is no longer available. Choose an approved profile."
            : "Choose an approved search profile before searching.",
        ),
      });
      return;
    }
    this.preferredProfileId = profile.profile_id;
    finish({
      status: "ready",
      capabilities,
      workspaces,
      selectedWorkspaceId,
      profile,
    });
  }
}
