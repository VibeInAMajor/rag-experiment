import {
  contractRevision,
  type ApiFailure,
  type ApiMeta,
  type BackendCapabilities,
  type BackendProfile,
  type LiveResponse,
  type ReadyResponse,
  type WorkspacePage,
} from "./contracts";
import { invalidResponse } from "./errors";

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    invalidResponse();
  return value as Record<string, unknown>;
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
