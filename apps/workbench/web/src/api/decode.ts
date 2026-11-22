import {
  contractRevision,
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
  const expectedStages = ["corpus_load", "retrieval", "projection"] as const;
  const stages = array(item.stages, 3).map((entry, index) => {
    const stage = object(entry);
    return {
      stage: literal(stage.stage, expectedStages[index]),
      status: choice(stage.status, ["success", "skipped"]),
      duration_ms: finiteNumber(stage.duration_ms),
    };
  });
  if (
    stages.length !== 3 ||
    stages.reduce((sum, stage) => sum + stage.duration_ms, 0) >
      durationMs + 1e-6
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
      score: finiteNumber(result.score),
      score_type: literal(result.score_type, "postgres_ts_rank_cd"),
    };
  });
  const seen = new Set<string>();
  for (let index = 0; index < results.length; index++) {
    const result = results[index];
    const previous = results[index - 1];
    if (
      seen.has(result.chunk_id) ||
      (previous &&
        (result.score > previous.score ||
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
    profile_id: literal(item.profile_id, "postgres-fts-baseline"),
    profile_revision: literal(
      item.profile_revision,
      "postgres-fts-baseline-r1",
    ),
    run_id: identifier(item.run_id),
    status: literal(item.status, "success"),
    duration_ms: durationMs,
    stages,
    results,
  };
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
  const profileId = choice(item.profile_id, [
    "bm25-v1",
    "postgres-keyword-v1",
    "postgres-fts-baseline",
  ]);
  const scoreType = choice(item.score_type, [
    "bm25_raw",
    "postgres_ts_rank_cd",
  ]);
  if (
    scoreType !== (profileId === "bm25-v1" ? "bm25_raw" : "postgres_ts_rank_cd")
  )
    invalidResponse();
  const workspaceIds = uniqueIds(item.workspace_ids, 1);
  if (!workspaceIds.length) invalidResponse();
  return {
    profile_id: profileId,
    profile_revision: identifier(item.profile_revision),
    kind: literal(item.kind, "lexical_search"),
    workspace_ids: workspaceIds,
    corpus_id: identifier(item.corpus_id),
    score_type: scoreType,
    parameters: {
      query: {
        type: literal(query.type, "string"),
        min_length: literal(query.min_length, 1),
        max_length: literal(query.max_length, 4096),
      },
      top_k: {
        type: literal(topK.type, "integer"),
        default: literal(topK.default, 10),
        minimum: literal(topK.minimum, 1),
        maximum: literal(topK.maximum, 50),
      },
    },
    limits: {
      max_request_bytes: literal(limits.max_request_bytes, 32768),
      timeout_ms: literal(limits.timeout_ms, 10000),
      max_concurrent_searches: literal(limits.max_concurrent_searches, 2),
      max_corpus_chunks: literal(limits.max_corpus_chunks, 10000),
      max_corpus_bytes: literal(limits.max_corpus_bytes, 52428800),
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
    },
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
