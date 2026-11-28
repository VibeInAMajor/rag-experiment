import {
  contractRevision,
  agentRunStatuses,
  type AgentCatalog,
  type AgentEvent,
  type AgentMoney,
  type AgentProfile,
  type AgentRun,
  type AgentRunDetail,
  type AgentRunPage,
  type AgentSelection,
  type AgentSelectionResult,
  type AgentTariff,
  type AgentUsage,
  type ConfigurationDocument,
  type ConfigurationValidation,
  type ApiFailure,
  type ApiMeta,
  type BackendCapabilities,
  type BackendProfile,
  type LiveResponse,
  type LocalSourceFile,
  type ReadyResponse,
  type SearchRequest,
  type SearchResponse,
  type SourceRevealResponse,
  type WorkspacePage,
  type DocumentItem,
  type DocumentPage,
  type DocumentDetail,
  type ActiveChunkPageResponse,
  type IngestionResponse,
  type IngestionJobResponse,
  type IngestionStageTiming,
  type JsonValue,
  type PdfIngestionCapabilities,
} from "./contracts";
import { invalidResponse } from "./errors";

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    invalidResponse();
  return value as Record<string, unknown>;
}

function finiteNumber(value: unknown, minimum = 0): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum)
    invalidResponse();
  return value;
}

function positiveInteger(value: unknown): number {
  const number = finiteNumber(value, 1);
  if (!Number.isSafeInteger(number)) invalidResponse();
  return number;
}

function boundedPositiveInteger(value: unknown, maximum: number): number {
  const number = positiveInteger(value);
  if (number > maximum) invalidResponse();
  return number;
}

function documentText(value: unknown): string {
  if (
    typeof value !== "string" ||
    value.length > 52428800 ||
    /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(
      value,
    )
  )
    invalidResponse();
  return value;
}

export function decodeSearchRequest(value: unknown): SearchRequest {
  const item = object(value);
  const keys = Object.keys(item);
  const required = [
    "query",
    "top_k",
    "profile_id",
    "expected_profile_revision",
  ];
  if (
    keys.length !== required.length ||
    keys.some((key) => !required.includes(key)) ||
    typeof item.query !== "string"
  )
    invalidResponse();
  const query = item.query.trim();
  if (query.includes("\0") || [...query].length < 1 || [...query].length > 4096)
    invalidResponse();
  documentText(query);
  const topK = positiveInteger(item.top_k);
  if (topK > 50) invalidResponse();
  return {
    query,
    top_k: topK,
    profile_id: identifier(item.profile_id),
    expected_profile_revision: identifier(item.expected_profile_revision),
  };
}

export function validateResourceId(value: unknown): string {
  return identifier(value);
}

export function decodeLocalSourceFile(value: unknown): LocalSourceFile {
  const item = object(value);
  const name = item.name === null ? null : text(item.name, 510);
  if (name !== null) documentText(name);
  if (
    name !== null &&
    (!name.trim() ||
      [...name].length > 255 ||
      /[/\\:]/u.test(name) ||
      name === "." ||
      name === "..")
  )
    invalidResponse();
  const canReveal = boolean(item.can_reveal);
  const reason =
    item.reason == null
      ? item.reason
      : choice(item.reason, [
          "not_registered",
          "demo_source",
          "root_unconfigured",
          "file_unavailable",
          "host_unavailable",
        ]);
  if (canReveal && (name === null || reason != null)) invalidResponse();
  return {
    ...meta(item),
    name,
    can_reveal: canReveal,
    ...(reason !== undefined ? { reason } : {}),
  };
}

export function decodeSourceReveal(value: unknown): SourceRevealResponse {
  const item = object(value);
  return { ...meta(item), status: literal(item.status, "revealed") };
}

export function decodeSearch(
  value: unknown,
  workspaceId: string,
  submitted: SearchRequest,
): SearchResponse {
  const item = object(value);
  const metadata = meta(item);
  if (
    item.workspace_id !== workspaceId ||
    item.profile_id !== submitted.profile_id ||
    item.profile_revision !== submitted.expected_profile_revision
  )
    invalidResponse();
  const durationMs = finiteNumber(item.duration_ms);
  const dense = submitted.profile_id === "postgres-dense-exact";
  const expectedStages = dense
    ? (["query_embedding", "vector_search", "projection"] as const)
    : (["corpus_load", "retrieval", "projection"] as const);
  const stages = array(item.stages, 3).map((entry, index) => {
    const stage = object(entry);
    return {
      stage: literal(stage.stage, expectedStages[index]),
      status: choice(stage.status, ["success", "skipped"]),
      duration_ms: finiteNumber(stage.duration_ms),
      ...(dense
        ? {
            started_at: timestamp(stage.started_at),
            finished_at: timestamp(stage.finished_at),
          }
        : {}),
    };
  });
  if (
    stages.length !== 3 ||
    stages.reduce((sum, stage) => sum + stage.duration_ms, 0) >
      durationMs + 1e-6
  )
    invalidResponse();
  if (
    dense &&
    stages.some(
      (stage, index) =>
        stage.status !== "success" ||
        Date.parse(timestamp(stage.finished_at)) <
          Date.parse(timestamp(stage.started_at)) ||
        (index > 0 &&
          Date.parse(timestamp(stage.started_at)) <
            Date.parse(timestamp(stages[index - 1].finished_at))),
    )
  )
    invalidResponse();
  const results = array(item.results, submitted.top_k).map((entry, index) => {
    const result = object(entry);
    if (result.rank !== index + 1) invalidResponse();
    return {
      chunk_id: identifier(result.chunk_id),
      source_id: identifier(result.source_id),
      source_version_id: identifier(result.source_version_id),
      title: documentText(result.title),
      content: documentText(result.content),
      ...(result.page === undefined
        ? {}
        : { page: result.page === null ? null : positiveInteger(result.page) }),
      rank: index + 1,
      score: dense ? cosineDistance(result.score) : finiteNumber(result.score),
      score_type: literal(
        result.score_type,
        dense ? "cosine_distance" : "postgres_ts_rank_cd",
      ),
    };
  });
  const seen = new Set<string>();
  for (let index = 0; index < results.length; index++) {
    const result = results[index];
    const previous = results[index - 1];
    if (
      seen.has(result.chunk_id) ||
      (previous &&
        ((dense
          ? result.score < previous.score
          : result.score > previous.score) ||
          (result.score === previous.score &&
            result.chunk_id < previous.chunk_id)))
    )
      invalidResponse();
    seen.add(result.chunk_id);
  }
  return {
    ...metadata,
    mode: literal(item.mode, "live"),
    workspace_id: workspaceId,
    corpus_revision: identifier(item.corpus_revision),
    profile_id: identifier(item.profile_id),
    profile_revision: identifier(item.profile_revision),
    run_id: identifier(item.run_id),
    status: literal(item.status, "success"),
    duration_ms: durationMs,
    ...(dense
      ? {
          embedding_profile_revision: identifier(
            item.embedding_profile_revision,
          ),
          index_generation: nonnegativeInteger(item.index_generation),
          model_revision: text(item.model_revision, 128),
          model_digest: text(item.model_digest, 256),
          tokenizer_digest: text(item.tokenizer_digest, 256),
          input_format_revision: text(item.input_format_revision, 128),
        }
      : {}),
    stages,
    results,
  };
}

function cosineDistance(value: unknown): number {
  const number = finiteNumber(value, -1e-6);
  if (number > 2 + 1e-6) invalidResponse();
  return number;
}

function text(value: unknown, maximum = 4096): string {
  if (
    typeof value !== "string" ||
    !value.length ||
    value.length > maximum ||
    /[\u0000-\u001f\u007f]/u.test(value)
  )
    invalidResponse();
  return value;
}

function identifier(value: unknown): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value))
    invalidResponse();
  return value;
}

function literal<T extends string | number>(value: unknown, expected: T): T {
  if (value !== expected) invalidResponse();
  return expected;
}

function choice<T extends string>(value: unknown, choices: readonly T[]): T {
  for (const item of choices) if (value === item) return item;
  return invalidResponse();
}

function boolean(value: unknown): boolean {
  if (typeof value !== "boolean") invalidResponse();
  return value;
}

function array(value: unknown, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) invalidResponse();
  return value;
}

function uniqueIds(value: unknown, maximum: number): string[] {
  const ids = array(value, maximum).map(identifier);
  if (new Set(ids).size !== ids.length) invalidResponse();
  return ids;
}

function meta(item: Record<string, unknown>): ApiMeta {
  return {
    contract_revision: literal(item.contract_revision, contractRevision),
    request_id: identifier(item.request_id),
    trace_id: identifier(item.trace_id),
  };
}

export function decodeLive(value: unknown): LiveResponse {
  const item = object(value);
  return {
    ...meta(item),
    status: literal(item.status, "alive"),
    backend_revision: identifier(item.backend_revision),
  };
}

export function decodeReady(value: unknown): ReadyResponse {
  const item = object(value);
  return {
    ...meta(item),
    status: literal(item.status, "ready"),
    backend_revision: identifier(item.backend_revision),
    ready_profile_ids: uniqueIds(item.ready_profile_ids, 100),
  };
}

function profile(value: unknown): BackendProfile {
  const item = object(value);
  const parameters = object(item.parameters);
  const query = object(parameters.query);
  const topK = object(parameters.top_k);
  const limits = object(item.limits);
  const profileId = identifier(item.profile_id);
  const scoreType = choice(item.score_type, [
    "bm25_raw",
    "postgres_ts_rank_cd",
    "cosine_distance",
  ]);
  const kind = choice(item.kind, ["lexical_search", "dense_search"]);
  if (
    scoreType !==
    (kind === "dense_search"
      ? "cosine_distance"
      : profileId === "bm25-v1"
        ? "bm25_raw"
        : "postgres_ts_rank_cd")
  )
    invalidResponse();
  const workspaceIds = uniqueIds(item.workspace_ids, 1);
  if (!workspaceIds.length) invalidResponse();
  const maximumTopK = boundedPositiveInteger(topK.maximum, 50);
  return {
    profile_id: profileId,
    profile_revision: identifier(item.profile_revision),
    ...(kind === "dense_search"
      ? {
          kind,
          score_type: literal(scoreType, "cosine_distance"),
          score_direction: literal(item.score_direction, "lower_is_better"),
          embedding_profile_revision: identifier(
            item.embedding_profile_revision,
          ),
          index_generation: nonnegativeInteger(item.index_generation),
          min_coverage: literal(item.min_coverage, 1),
        }
      : {
          kind,
          score_type: literal(
            scoreType,
            profileId === "bm25-v1" ? "bm25_raw" : "postgres_ts_rank_cd",
          ),
        }),
    workspace_ids: workspaceIds,
    corpus_id: identifier(item.corpus_id),
    parameters: {
      query: {
        type: literal(query.type, "string"),
        min_length: literal(query.min_length, 1),
        max_length: boundedPositiveInteger(query.max_length, 4096),
      },
      top_k: {
        type: literal(topK.type, "integer"),
        default: boundedPositiveInteger(topK.default, maximumTopK),
        minimum: literal(topK.minimum, 1),
        maximum: maximumTopK,
      },
    },
    limits: {
      max_request_bytes: boundedPositiveInteger(
        limits.max_request_bytes,
        32768,
      ),
      timeout_ms: boundedPositiveInteger(limits.timeout_ms, 10000),
      max_concurrent_searches: boundedPositiveInteger(
        limits.max_concurrent_searches,
        2,
      ),
      max_corpus_chunks: boundedPositiveInteger(
        limits.max_corpus_chunks,
        10000,
      ),
      max_corpus_bytes: boundedPositiveInteger(
        limits.max_corpus_bytes,
        52428800,
      ),
    },
  };
}

function optionalText(
  value: unknown,
  maximum = 128,
): string | null | undefined {
  return value === null || value === undefined ? value : text(value, maximum);
}

function optionalCount(value: unknown): number | null | undefined {
  if (value === null || value === undefined) return value;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1)
    invalidResponse();
  return value;
}

export function decodeCapabilities(value: unknown): BackendCapabilities {
  const item = object(value);
  const features = object(item.features);
  const database = object(object(item.dependencies).database);
  const profiles = array(item.profiles, 100).map(profile);
  if (
    new Set(profiles.map((entry) => entry.profile_id)).size !== profiles.length
  )
    invalidResponse();
  const workspaceId =
    database.workspace_id === null || database.workspace_id === undefined
      ? database.workspace_id
      : identifier(database.workspace_id);
  return {
    ...meta(item),
    backend_revision: identifier(item.backend_revision),
    deployment_mode: literal(item.deployment_mode, "single_workspace_dev"),
    service_state: choice(item.service_state, [
      "starting",
      "running",
      "stopping",
      "stopped",
    ]),
    profiles,
    features: {
      documents: boolean(features.documents),
      search: boolean(features.search),
      upload: boolean(features.upload),
      ...(features.upload_folders === undefined
        ? {}
        : { upload_folders: boolean(features.upload_folders) }),
      document_details: boolean(features.document_details),
      jobs: boolean(features.jobs),
      ...(features.agent_operations === undefined
        ? {}
        : { agent_operations: boolean(features.agent_operations) }),
    },
    pdf_ingestion: decodePdfCapabilities(item.pdf_ingestion),
    dependencies: {
      database: {
        status: choice(database.status, [
          "unconfigured",
          "ready",
          "unavailable",
          "incompatible",
          "empty",
        ]),
        schema_revision: optionalText(database.schema_revision),
        workspace_id: workspaceId,
        source_count: optionalCount(database.source_count),
        chunk_count: optionalCount(database.chunk_count),
      },
    },
  };
}

export function validateCursor(value: unknown): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_.-]{1,512}$/.test(value))
    invalidResponse();
  return value;
}

function nullable<T>(value: unknown, decode: (input: unknown) => T): T | null {
  return value == null ? null : decode(value);
}

function agentCount(value: unknown): number {
  const count = finiteNumber(value);
  if (!Number.isSafeInteger(count)) invalidResponse();
  return count;
}

function agentPercent(value: unknown): number {
  const percent = finiteNumber(value);
  if (percent > 100) invalidResponse();
  return percent;
}

function agentMoney(value: unknown): AgentMoney {
  return nullable(value, (value) => {
    const amount = text(value, 40);
    if (
      !/^\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?$/.test(amount) ||
      !Number.isFinite(Number(amount))
    )
      invalidResponse();
    return amount;
  });
}

export function validateAgentProfileId(value: unknown): string {
  const profile = text(value, 128);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(profile)) invalidResponse();
  return profile;
}

function agentIdentity(value: unknown): string {
  const result = text(value, 160);
  if (!/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(result)) invalidResponse();
  return result;
}

function agentTariff(value: unknown): AgentTariff {
  const item = object(value);
  const source_url = nullable(item.source_url, (value) => {
    const href = text(value, 512);
    if (
      !/^https:\/\/developers\.openai\.com\/api\/docs\/pricing(?:\.md)?$/.test(
        href,
      )
    )
      invalidResponse();
    return href;
  });
  return {
    version: agentIdentity(item.version),
    provider: agentIdentity(item.provider),
    model: agentIdentity(item.model),
    service_tier: agentIdentity(item.service_tier),
    currency: literal(item.currency, "USD"),
    unit: literal(item.unit, "per_million_tokens"),
    ordinary_input: agentMoney(item.ordinary_input),
    cached_read: agentMoney(item.cached_read),
    cached_write: agentMoney(item.cached_write),
    output: agentMoney(item.output),
    source_url,
    effective_at: nullable(item.effective_at, timestamp),
    verified_at: nullable(item.verified_at, timestamp),
    cache_ttl_seconds: nullable(item.cache_ttl_seconds, positiveInteger),
    status: choice(item.status, ["verified", "stale", "unknown"]),
  };
}

function agentProfile(value: unknown): AgentProfile {
  const item = object(value);
  const qualification = object(item.qualification);
  return {
    profile_id: validateAgentProfileId(item.profile_id),
    provider: agentIdentity(item.provider),
    model: agentIdentity(item.model),
    modes: uniqueIds(item.modes, 16),
    reasoning_effort: agentIdentity(item.reasoning_effort),
    max_estimated_input_tokens: positiveInteger(
      item.max_estimated_input_tokens,
    ),
    max_output_tokens: positiveInteger(item.max_output_tokens),
    max_request_bytes: nullable(item.max_request_bytes, positiveInteger),
    max_response_bytes: nullable(item.max_response_bytes, positiveInteger),
    timeout_seconds: nullable(item.timeout_seconds, finiteNumber),
    reserve_usd: agentMoney(item.reserve_usd),
    cache_mode: agentIdentity(item.cache_mode),
    cache_ttl_seconds: nullable(item.cache_ttl_seconds, positiveInteger),
    qualification: {
      state: choice(qualification.state, [
        "qualified",
        "unqualified",
        "blocked",
        "stale",
      ]),
      revision: nullable(qualification.revision, agentIdentity),
      verified_at: nullable(qualification.verified_at, timestamp),
      reason: nullable(qualification.reason, agentIdentity),
    },
    tariff: nullable(item.tariff, agentTariff),
    selectable: boolean(item.selectable),
  };
}

function agentSelection(value: unknown): AgentSelection {
  const item = object(value);
  return {
    profile_id: validateAgentProfileId(item.profile_id),
    revision: agentIdentity(item.revision),
  };
}

export function decodeAgentCatalog(value: unknown): AgentCatalog {
  const item = object(value);
  const agents = array(item.agents, 16).map((value) => {
    const agent = object(value);
    const profiles = array(agent.profiles, 16).map(agentProfile);
    const default_profile_id = validateAgentProfileId(agent.default_profile_id);
    const selection = agentSelection(agent.selection);
    if (
      new Set(profiles.map((profile) => profile.profile_id)).size !==
        profiles.length ||
      !profiles.some((profile) => profile.profile_id === default_profile_id) ||
      !profiles.some((profile) => profile.profile_id === selection.profile_id)
    )
      invalidResponse();
    return {
      agent_id: identifier(agent.agent_id),
      display_name: text(agent.display_name, 100),
      runtime_revision: agentIdentity(agent.runtime_revision),
      modes: uniqueIds(agent.modes, 16),
      default_profile_id,
      selection,
      profiles,
    };
  });
  if (new Set(agents.map((agent) => agent.agent_id)).size !== agents.length)
    invalidResponse();
  return {
    ...meta(item),
    scope: literal(item.scope, "local-operator"),
    history_available: boolean(item.history_available),
    agents,
  };
}

export function decodeAgentSelection(
  value: unknown,
  expectedAgent: string,
  expectedProfile: string,
): AgentSelectionResult {
  const item = object(value);
  const selection = agentSelection(item.selection);
  if (selection.profile_id !== expectedProfile) invalidResponse();
  return {
    ...meta(item),
    scope: literal(item.scope, "local-operator"),
    agent_id: literal(item.agent_id, expectedAgent),
    selection,
  };
}

function agentUsage(value: unknown): AgentUsage {
  const item = object(value);
  return {
    input_tokens: nullable(item.input_tokens, agentCount),
    ordinary_input_tokens: nullable(item.ordinary_input_tokens, agentCount),
    cached_read_tokens: nullable(item.cached_read_tokens, agentCount),
    cached_write_tokens: nullable(item.cached_write_tokens, agentCount),
    output_tokens: nullable(item.output_tokens, agentCount),
    reasoning_tokens: nullable(item.reasoning_tokens, agentCount),
    total_tokens: nullable(item.total_tokens, agentCount),
  };
}

function agentCoverage(value: unknown) {
  const item = object(value);
  const known_calls = agentCount(item.known_calls);
  const total_calls = agentCount(item.total_calls);
  if (known_calls > total_calls) invalidResponse();
  return { known_calls, total_calls };
}

function agentRun(value: unknown): AgentRun {
  const item = object(value);
  return {
    run_id: identifier(item.run_id),
    agent_id: identifier(item.agent_id),
    mode: agentIdentity(item.mode),
    origin: choice(item.origin, ["evaluation", "calibration"]),
    profile_id: validateAgentProfileId(item.profile_id),
    model: agentIdentity(item.model),
    provider: agentIdentity(item.provider),
    runtime_revision: agentIdentity(item.runtime_revision),
    prompt_revision: nullable(item.prompt_revision, agentIdentity),
    schema_revision: nullable(item.schema_revision, agentIdentity),
    cache_mode: agentIdentity(item.cache_mode),
    tariff: nullable(item.tariff, agentTariff),
    planned_cases: nullable(item.planned_cases, positiveInteger),
    budget_usd: agentMoney(item.budget_usd),
    queued_at: timestamp(item.queued_at),
    started_at: nullable(item.started_at, timestamp),
    finished_at: nullable(item.finished_at, timestamp),
    status: choice(item.status, agentRunStatuses),
    stage: nullable(item.stage, agentIdentity),
    last_sequence: positiveInteger(item.last_sequence),
    completed_cases: agentCount(item.completed_cases),
    reused_cases: agentCount(item.reused_cases),
    failed_cases: agentCount(item.failed_cases ?? 0),
    blocked_cases: agentCount(item.blocked_cases ?? 0),
    actual_models: array(item.actual_models ?? [], 16).map(agentIdentity),
    selection_revision: nullable(item.selection_revision, agentIdentity),
    physical_requests: agentCount(item.physical_requests),
    pending_calls: agentCount(item.pending_calls),
    cache_observed_requests: agentCount(item.cache_observed_requests),
    cache_hit_requests: agentCount(item.cache_hit_requests),
    cache_hit_percent: nullable(item.cache_hit_percent, agentPercent),
    cache_read_percent: nullable(item.cache_read_percent, agentPercent),
    usage: nullable(item.usage, agentUsage),
    usage_coverage: agentCoverage(item.usage_coverage),
    estimated_cost_usd: agentMoney(item.estimated_cost_usd),
    cost_coverage: agentCoverage(item.cost_coverage),
    pending_reserve_usd: agentMoney(item.pending_reserve_usd),
  };
}

export function decodeAgentRunPage(value: unknown): AgentRunPage {
  const item = object(value);
  const runs = array(item.runs, 100).map(agentRun);
  if (new Set(runs.map((run) => run.run_id)).size !== runs.length)
    invalidResponse();
  return {
    ...meta(item),
    scope: literal(item.scope, "local-operator"),
    runs,
    next_cursor: nullable(item.next_cursor, validateCursor),
  };
}

function agentEvent(value: unknown, runId: string): AgentEvent {
  const item = object(value);
  literal(item.schema_version, 1);
  literal(item.scope, "local-operator");
  return {
    run_id: literal(item.run_id, runId),
    sequence: positiveInteger(item.sequence),
    timestamp: timestamp(item.timestamp),
    kind: choice(item.kind, [
      "run_queued",
      "run_started",
      "stage_changed",
      "call_pending",
      "call_completed",
      "case_completed",
      "checkpoint_reused",
      "run_finished",
    ]),
    stage: nullable(item.stage, agentIdentity),
    status: nullable(item.status, (value) => choice(value, agentRunStatuses)),
    reason: nullable(item.reason, agentIdentity),
    case_id: nullable(item.case_id, identifier),
    call: nullable(item.call, (value) => {
      const call = object(value);
      return {
        call_id: identifier(call.call_id),
        case_id: identifier(call.case_id),
        mode: nullable(call.mode, agentIdentity),
        actual_model: nullable(call.actual_model, agentIdentity),
        provider_request_id: nullable(call.provider_request_id, identifier),
        requests: nullable(call.requests, (value) =>
          agentCount(value) > 1 ? invalidResponse() : agentCount(value),
        ),
        elapsed_ms: nullable(call.elapsed_ms, agentCount),
        usage: nullable(call.usage, agentUsage),
        estimated_cost_usd: agentMoney(call.estimated_cost_usd),
        reserve_usd: agentMoney(call.reserve_usd),
      };
    }),
  };
}

export function decodeAgentRunDetail(
  value: unknown,
  runId: string,
): AgentRunDetail {
  const item = object(value);
  const run = agentRun(item.run);
  if (run.run_id !== runId) invalidResponse();
  const events = array(item.events, 100).map((entry) =>
    agentEvent(entry, runId),
  );
  if (
    events.some(
      (event, index) =>
        event.sequence > run.last_sequence ||
        (index > 0 && event.sequence !== events[index - 1].sequence + 1),
    )
  )
    invalidResponse();
  return {
    ...meta(item),
    scope: literal(item.scope, "local-operator"),
    run,
    events,
    next_cursor: nullable(item.next_cursor, validateCursor),
    has_more: boolean(item.has_more),
  };
}

export function decodeWorkspaces(value: unknown): WorkspacePage {
  const item = object(value);
  const items = array(item.items, 100).map((entry) => {
    const workspace = object(entry);
    return {
      workspace_id: identifier(workspace.workspace_id),
      name: text(workspace.name, 4096),
      status: choice(workspace.status, ["ready", "unavailable"]),
    };
  });
  if (new Set(items.map((entry) => entry.workspace_id)).size !== items.length)
    invalidResponse();
  return {
    ...meta(item),
    items,
    next_cursor:
      item.next_cursor === null ? null : validateCursor(item.next_cursor),
  };
}

export function decodeFailure(value: unknown, httpStatus: number): ApiFailure {
  const item = object(value);
  const error = object(item.error);
  if (error.http_status !== httpStatus) invalidResponse();
  const fields =
    error.fields === null || error.fields === undefined
      ? error.fields
      : array(error.fields, 100).map((entry) => {
          const field = object(entry);
          return { field: text(field.field, 256), code: text(field.code, 128) };
        });
  return {
    ...meta(item),
    error: {
      code: identifier(error.code),
      message: text(error.message),
      retryable: boolean(error.retryable),
      http_status: httpStatus,
      run_id:
        error.run_id === null || error.run_id === undefined
          ? error.run_id
          : identifier(error.run_id),
      job_id:
        error.job_id === null || error.job_id === undefined
          ? error.job_id
          : identifier(error.job_id),
      fields,
    },
  };
}

export function decodeConfigurationDocument(
  value: unknown,
): ConfigurationDocument {
  const item = object(value);
  const yaml = documentText(item.yaml);
  const revision = text(item.revision, 80);
  if (
    item.scope !== "application" ||
    item.max_bytes !== 65536 ||
    new TextEncoder().encode(yaml).length > 65536 ||
    !/^config-(?:[0-9a-f]{64}|missing)$/.test(revision)
  )
    invalidResponse();
  return {
    ...meta(item),
    scope: "application",
    yaml,
    revision,
    exists: boolean(item.exists),
    activation: choice(item.activation, ["active", "requires_restart"]),
    max_bytes: 65536,
    effective_default_language: choice(item.effective_default_language, [
      "en",
      "ru",
    ]),
    deployment_overrides: array(item.deployment_overrides, 1).map((value) =>
      choice(value, ["default_language"]),
    ),
  };
}

export function decodeConfigurationSave(value: unknown): ConfigurationDocument {
  if (object(value).status !== "saved") invalidResponse();
  return decodeConfigurationDocument(value);
}

export function decodeConfigurationValidation(
  value: unknown,
): ConfigurationValidation {
  const item = object(value);
  const valid = boolean(item.valid);
  const errors = array(item.errors, 20).map((value) => {
    const issue = object(value);
    return {
      message: text(issue.message, 240),
      path: issue.path === null ? null : text(issue.path, 512),
      line: issue.line === null ? null : positiveInteger(issue.line),
      column: issue.column === null ? null : positiveInteger(issue.column),
    };
  });
  if (valid === errors.length > 0) invalidResponse();
  return {
    ...meta(item),
    valid,
    errors,
    warnings: array(item.warnings, 10).map((value) => text(value, 512)),
  };
}

function decodePdfCapabilities(value: unknown): PdfIngestionCapabilities {
  const item = object(value);
  if (
    item.original_evidence !== false ||
    item.ocr !== false ||
    item.visual_understanding !== false
  )
    invalidResponse();
  const available = boolean(item.available);
  const textLayer = boolean(item.text_layer);
  const pageProvenance = boolean(item.page_provenance);
  const tableRows = boolean(item.table_rows);
  if (available && (!textLayer || !pageProvenance || !tableRows))
    invalidResponse();
  return {
    available,
    text_layer: textLayer,
    page_provenance: pageProvenance,
    table_rows: tableRows,
    original_evidence: false,
    ocr: false,
    visual_understanding: false,
    visual_detection_coverage: literal(
      item.visual_detection_coverage,
      "unverified",
    ),
    max_bytes: literal(item.max_bytes, 8388608),
    max_pages: literal(item.max_pages, 32),
  };
}

function nonnegativeInteger(value: unknown): number {
  const result = finiteNumber(value);
  if (!Number.isSafeInteger(result)) invalidResponse();
  return result;
}

function nullableId(value: unknown): string | null {
  return value === null ? null : identifier(value);
}

function timestamp(value: unknown): string {
  const result = text(value, 64);
  if (
    !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(
      result,
    ) ||
    !Number.isFinite(Date.parse(result))
  )
    invalidResponse();
  const year = Number(result.slice(0, 4));
  const month = Number(result.slice(5, 7));
  const day = Number(result.slice(8, 10));
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > new Date(Date.UTC(year, month, 0)).getUTCDate()
  )
    invalidResponse();
  return result;
}

function boundedDocumentText(value: unknown, maximum = 52428800): string {
  const result = documentText(value);
  if (result.length > maximum) invalidResponse();
  return result;
}

function jsonMap(value: unknown): Record<string, JsonValue> {
  let remaining = 20000;
  const visit = (input: unknown, depth: number): JsonValue => {
    if (--remaining < 0 || depth > 16) invalidResponse();
    if (input === null || typeof input === "boolean") return input;
    if (typeof input === "string") return boundedDocumentText(input, 65536);
    if (typeof input === "number") {
      if (!Number.isFinite(input)) invalidResponse();
      return input;
    }
    if (Array.isArray(input))
      return input.map((entry) => visit(entry, depth + 1));
    const item = object(input);
    return Object.fromEntries(
      Object.entries(item).map(([key, entry]) => {
        boundedDocumentText(key, 512);
        return [key, visit(entry, depth + 1)];
      }),
    );
  };
  const item = object(value);
  return Object.fromEntries(
    Object.entries(item).map(([key, entry]) => {
      boundedDocumentText(key, 512);
      return [key, visit(entry, 1)];
    }),
  );
}

function documentItem(value: unknown): DocumentItem {
  const item = object(value);
  return {
    source_id: identifier(item.source_id),
    title: documentText(item.title),
    media_type: text(item.media_type, 256),
    status: choice(item.status, ["ready", "processing", "error"]),
    active_version_id: nullableId(item.active_version_id),
    chunk_count: nonnegativeInteger(item.chunk_count),
    updated_at: timestamp(item.updated_at),
    ...(item.upload_location == null
      ? {}
      : { upload_location: uploadLocation(item.upload_location) }),
    ...(item.folder_states == null
      ? {}
      : {
          folder_states: documentFolderStates(
            item.folder_states,
            item.upload_location,
          ),
        }),
    ...(item.error_code === undefined
      ? {}
      : { error_code: optionalText(item.error_code) }),
  };
}

function documentFolderStates(value: unknown, location: unknown) {
  const path = uploadLocation(location);
  const states = array(value, 64).map((value) => {
    const item = object(value);
    const count = positiveInteger(item.file_count);
    const ready = nonnegativeInteger(item.ready_count);
    const status = choice(item.status, ["ready", "processing", "error"]);
    if (ready > count || (status === "ready") !== (ready === count))
      invalidResponse();
    return { file_count: count, ready_count: ready, status };
  });
  if (states.length !== path.folder_totals.length) invalidResponse();
  return states;
}

function uploadLocation(value: unknown) {
  const item = object(value);
  const path = text(item.path, 2048);
  const parts = path.split("/");
  const totals = array(item.folder_totals, 64).map(positiveInteger);
  if (
    parts.length !== totals.length + 1 ||
    !totals.length ||
    parts.some((part) => ["", ".", ".."].includes(part)) ||
    /[\\:\u0000-\u001f\u007f\ud800-\udfff]/u.test(path) ||
    totals.some(
      (total, index) =>
        total > 1000000 || (index > 0 && total > totals[index - 1]),
    )
  )
    invalidResponse();
  return { group_id: identifier(item.group_id), path, folder_totals: totals };
}

export type DocumentDecodeContext = {
  expectedCorpusRevision?: string;
  expectedVersionId?: string;
};

function documentScope(
  item: Record<string, unknown>,
  workspaceId: string,
  context: DocumentDecodeContext = {},
) {
  if (
    item.workspace_id !== workspaceId ||
    (context.expectedCorpusRevision !== undefined &&
      item.corpus_revision !== context.expectedCorpusRevision)
  )
    invalidResponse();
  return {
    ...meta(item),
    workspace_id: identifier(item.workspace_id),
    corpus_revision: identifier(item.corpus_revision),
  };
}

export function decodeDocumentPage(
  value: unknown,
  workspaceId: string,
  context: DocumentDecodeContext = {},
): DocumentPage {
  const item = object(value);
  const items = array(item.items, 100).map(documentItem);
  if (new Set(items.map((entry) => entry.source_id)).size !== items.length)
    invalidResponse();
  return {
    ...documentScope(item, workspaceId, context),
    items,
    next_cursor:
      item.next_cursor === null ? null : validateCursor(item.next_cursor),
  };
}

export function decodeDocumentDetail(
  value: unknown,
  workspaceId: string,
  sourceId: string,
  context: DocumentDecodeContext = {},
): DocumentDetail {
  const item = object(value);
  if (
    item.source_id !== sourceId ||
    (context.expectedVersionId !== undefined &&
      item.active_version_id !== context.expectedVersionId) ||
    item.original_content_available !== false
  )
    invalidResponse();
  const base = documentItem(item);
  const result: DocumentDetail = {
    ...documentScope(item, workspaceId, context),
    source_id: base.source_id,
    title: base.title,
    media_type: base.media_type,
    status: base.status,
    active_version_id: base.active_version_id,
    chunk_count: base.chunk_count,
    updated_at: base.updated_at,
    warnings: array(item.warnings, 4096).map((warning) =>
      documentText(warning),
    ),
    original_content_available: false,
  };
  for (const key of [
    "processing_profile",
    "document_processing",
    "parser",
  ] as const) {
    if (item[key] !== undefined)
      result[key] = item[key] === null ? null : jsonMap(item[key]);
  }
  for (const key of [
    "processing_profile_fingerprint",
    "ingestion_policy_revision",
    "source_content_sha256",
  ] as const) {
    if (item[key] !== undefined) result[key] = optionalText(item[key], 4096);
  }
  for (const key of ["source_bytes", "parsed_element_count"] as const) {
    if (item[key] !== undefined)
      result[key] = item[key] === null ? null : nonnegativeInteger(item[key]);
  }
  if (item.language_policy !== undefined)
    result.language_policy =
      item.language_policy === null
        ? null
        : choice(item.language_policy, [
            "unqualified_source_locale",
            "configured_sentence_language",
            "configured_structural_boundaries",
          ] as const);
  if (item.default_language !== undefined)
    result.default_language =
      item.default_language === null
        ? null
        : choice(item.default_language, ["en", "ru"] as const);
  return result;
}

export function decodeActiveChunkPage(
  value: unknown,
  workspaceId: string,
  sourceId: string,
  context: DocumentDecodeContext = {},
): ActiveChunkPageResponse {
  const item = object(value);
  if (
    item.source_id !== sourceId ||
    (context.expectedVersionId !== undefined &&
      item.source_version_id !== context.expectedVersionId)
  )
    invalidResponse();
  const items = array(item.items, 100).map((value) => {
    const entry = object(value);
    const content = boundedDocumentText(entry.content, 32768);
    if (!content.length) invalidResponse();
    return {
      chunk_id: identifier(entry.chunk_id),
      order: nonnegativeInteger(entry.order),
      content,
      content_hash: text(entry.content_hash, 256),
      ...(entry.page === undefined
        ? {}
        : { page: entry.page === null ? null : positiveInteger(entry.page) }),
      section_path: array(entry.section_path, 4096).map((part) =>
        documentText(part),
      ),
      metadata: jsonMap(entry.metadata),
    };
  });
  if (
    new Set(items.map((entry) => entry.chunk_id)).size !== items.length ||
    items.some(
      (entry, index) => index > 0 && entry.order <= items[index - 1].order,
    )
  )
    invalidResponse();
  return {
    ...documentScope(item, workspaceId, context),
    source_id: identifier(item.source_id),
    source_version_id: identifier(item.source_version_id),
    items,
    next_cursor:
      item.next_cursor === null ? null : validateCursor(item.next_cursor),
  };
}

function ingestionStages(value: unknown): IngestionStageTiming[] {
  const stages = array(value, 3).map((value) => {
    const entry = object(value);
    return {
      stage: choice(entry.stage, ["parsing", "chunking", "publication"]),
      duration_ms: finiteNumber(entry.duration_ms),
    };
  });
  if (new Set(stages.map((entry) => entry.stage)).size !== stages.length)
    invalidResponse();
  return stages;
}

export function decodeIngestionResponse(
  value: unknown,
  workspaceId: string,
  httpStatus: number,
  expectedSourceId?: string,
): IngestionResponse {
  const item = object(value);
  const outcome = choice(item.outcome, ["created", "updated", "unchanged"]);
  const replayed = boolean(item.replayed);
  if (
    (httpStatus !== 200 && httpStatus !== 201) ||
    (httpStatus === 201 && (outcome !== "created" || replayed)) ||
    (httpStatus === 200 && outcome === "created" && !replayed) ||
    (expectedSourceId !== undefined && item.source_id !== expectedSourceId)
  )
    invalidResponse();
  return {
    ...documentScope(item, workspaceId),
    source_id: identifier(item.source_id),
    source_version_id: identifier(item.source_version_id),
    job_id: identifier(item.job_id),
    outcome,
    status: literal(item.status, "completed"),
    chunk_count: positiveInteger(item.chunk_count),
    stages: ingestionStages(item.stages),
    replayed,
  };
}

export function decodeIngestionJob(
  value: unknown,
  workspaceId: string,
  jobId: string,
): IngestionJobResponse {
  const item = object(value);
  if (item.workspace_id !== workspaceId || item.job_id !== jobId)
    invalidResponse();
  const states = [
    "pending",
    "parsing",
    "chunking",
    "publishing",
    "completed",
    "failed",
  ] as const;
  const result: IngestionJobResponse = {
    ...meta(item),
    workspace_id: identifier(item.workspace_id),
    job_id: identifier(item.job_id),
    source_id: identifier(item.source_id),
    source_version_id: nullableId(item.source_version_id),
    reserved_version_id: identifier(item.reserved_version_id),
    status: choice(item.status, states),
    stage: choice(item.stage, states),
    retryable: boolean(item.retryable),
    error_code: item.error_code === null ? null : text(item.error_code, 128),
    chunk_count:
      item.chunk_count === null ? null : nonnegativeInteger(item.chunk_count),
    outcome:
      item.outcome === null
        ? null
        : choice(item.outcome, ["created", "updated", "unchanged"] as const),
    created_at: timestamp(item.created_at),
    updated_at: timestamp(item.updated_at),
    finished_at: item.finished_at === null ? null : timestamp(item.finished_at),
    stages: ingestionStages(item.stages),
  };
  if (
    (result.status !== "failed" && result.status !== result.stage) ||
    Date.parse(result.updated_at) < Date.parse(result.created_at) ||
    (result.finished_at !== null &&
      Date.parse(result.finished_at) < Date.parse(result.created_at)) ||
    (result.status === "completed" &&
      (result.source_version_id === null ||
        result.outcome === null ||
        result.chunk_count === null ||
        result.finished_at === null))
  )
    invalidResponse();
  return result;
}
