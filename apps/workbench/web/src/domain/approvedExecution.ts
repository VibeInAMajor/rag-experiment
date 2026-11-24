import type { SearchRequest } from "../api/contracts";
import {
  isSupportedSearchProfile,
  type BackendDiscoveryState,
} from "./backendDiscovery";
import type { Graph, GraphIssue, WorkbenchNode } from "./types";

export type ApprovedSearchMatch =
  | {
      supported: true;
      workspaceId: string;
      request: SearchRequest;
      effectiveTopK: number;
    }
  | { supported: false; issues: GraphIssue[] };

function unsupported(
  message: string,
  issue: Omit<GraphIssue, "message"> = {},
): ApprovedSearchMatch {
  return {
    supported: false,
    issues: [{ code: "LIVE_GRAPH_UNSUPPORTED", ...issue, message }],
  };
}

function parameter(
  node: WorkbenchNode,
  key: string,
): string | number | undefined {
  const values = node.data.parameters;
  if (
    !values ||
    typeof values !== "object" ||
    Array.isArray(values) ||
    Reflect.ownKeys(values).length !== 1 ||
    !Object.hasOwn(values, key)
  )
    return undefined;
  return values[key];
}

function boundedInteger(value: unknown, maximum: number): value is number {
  return (
    typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value >= 1 &&
    value <= maximum
  );
}

function approvedDiscovery(discovery: BackendDiscoveryState): boolean {
  if (discovery.status !== "ready" || !discovery.capabilities) return false;
  const { profile, selectedWorkspaceId, capabilities } = discovery;
  const { parameters } = profile;
  return (
    capabilities.contract_revision === "rag-api-v1.0" &&
    capabilities.service_state === "running" &&
    capabilities.features.search &&
    capabilities.dependencies.database.status === "ready" &&
    (capabilities.dependencies.database.workspace_id == null ||
      capabilities.dependencies.database.workspace_id ===
        selectedWorkspaceId) &&
    isSupportedSearchProfile(profile) &&
    profile.workspace_ids.includes(selectedWorkspaceId) &&
    discovery.workspaces.some(
      (workspace) =>
        workspace.workspace_id === selectedWorkspaceId &&
        workspace.status === "ready",
    ) &&
    capabilities.profiles.some(
      (advertised) =>
        advertised.profile_id === profile.profile_id &&
        advertised.profile_revision === profile.profile_revision &&
        advertised.kind === profile.kind &&
        advertised.score_type === profile.score_type &&
        advertised.corpus_id === profile.corpus_id &&
        (profile.kind !== "dense_search" ||
          (advertised.kind === "dense_search" &&
            advertised.embedding_profile_revision ===
              profile.embedding_profile_revision &&
            advertised.index_generation === profile.index_generation &&
            advertised.min_coverage === profile.min_coverage &&
            advertised.score_direction === profile.score_direction)) &&
        advertised.workspace_ids.includes(selectedWorkspaceId) &&
        advertised.parameters.query.max_length ===
          parameters.query.max_length &&
        advertised.parameters.top_k.maximum === parameters.top_k.maximum &&
        advertised.parameters.top_k.default === parameters.top_k.default &&
        advertised.limits.max_request_bytes ===
          profile.limits.max_request_bytes &&
        advertised.limits.timeout_ms === profile.limits.timeout_ms &&
        advertised.limits.max_concurrent_searches ===
          profile.limits.max_concurrent_searches &&
        advertised.limits.max_corpus_chunks ===
          profile.limits.max_corpus_chunks &&
        advertised.limits.max_corpus_bytes === profile.limits.max_corpus_bytes,
    ) &&
    parameters.query.type === "string" &&
    parameters.query.min_length === 1 &&
    boundedInteger(parameters.query.max_length, 4096) &&
    parameters.top_k.type === "integer" &&
    parameters.top_k.minimum === 1 &&
    boundedInteger(parameters.top_k.maximum, 50)
  );
}

export function matchApprovedSearchGraph(
  graph: Graph,
  discovery: BackendDiscoveryState,
): ApprovedSearchMatch {
  if (!approvedDiscovery(discovery) || discovery.status !== "ready")
    return unsupported(
      "A ready, compatible Live profile and authorized workspace are required.",
      { code: "LIVE_PROFILE_UNAVAILABLE" },
    );
  const dense = discovery.profile.kind === "dense_search";
  const nodeCount = dense ? 4 : 3;
  const edgeCount = dense ? 3 : 2;
  if (graph.nodes.length !== nodeCount || graph.edges.length !== edgeCount)
    return unsupported(
      dense
        ? "Live Dense supports only Search query → Query embedding → Dense search → Search results."
        : "Live supports only Search query → Keyword search → Search results, with three components and two connections.",
    );
  if (
    new Set(graph.nodes.map((node) => node.id)).size !== nodeCount ||
    new Set(graph.edges.map((edge) => edge.id)).size !== edgeCount ||
    graph.nodes.some(
      (node) => typeof node.id !== "string" || !node.id.trim(),
    ) ||
    graph.edges.some((edge) => typeof edge.id !== "string" || !edge.id.trim())
  )
    return unsupported(
      "Live components and connections require distinct, nonempty identifiers.",
    );
  const queryNode = graph.nodes.find((node) => node.data.kind === "query");
  const retrieverNode = graph.nodes.find(
    (node) => node.data.kind === (dense ? "dense-search" : "keyword-search"),
  );
  const embedder = graph.nodes.find(
    (node) => node.data.kind === "query-embedding",
  );
  const resultNode = graph.nodes.find((node) => node.data.kind === "results");
  if (!queryNode || !retrieverNode || !resultNode)
    return unsupported(
      dense
        ? "Use exactly one Search query, Query embedding, Dense search and Search results component for Live Dense."
        : "Use exactly one Search query, Keyword search and Search results component for Live.",
    );
  if (
    dense &&
    (!embedder ||
      !embedder.data.parameters ||
      typeof embedder.data.parameters !== "object" ||
      Array.isArray(embedder.data.parameters) ||
      Reflect.ownKeys(embedder.data.parameters).length !== 0)
  )
    return unsupported(
      "Live Query embedding uses the server-qualified model and accepts no parameters.",
    );
  const expected = [
    {
      source: queryNode.id,
      sourceHandle: "query",
      target: embedder?.id ?? retrieverNode.id,
      targetHandle: dense ? "text" : "query",
    },
    {
      source: retrieverNode.id,
      sourceHandle: "documents",
      target: resultNode.id,
      targetHandle: "documents",
    },
  ];
  if (dense && embedder)
    expected.push({
      source: embedder.id,
      sourceHandle: "embedding",
      target: retrieverNode.id,
      targetHandle: "embedding",
    });
  for (const edge of graph.edges) {
    const matching = expected.find(
      (candidate) =>
        edge.source === candidate.source &&
        edge.sourceHandle === candidate.sourceHandle &&
        edge.target === candidate.target &&
        edge.targetHandle === candidate.targetHandle,
    );
    if (!matching)
      return unsupported("Use only the approved search template connections.", {
        edgeId: edge.id,
      });
    expected.splice(expected.indexOf(matching), 1);
  }
  const rawQuery = parameter(queryNode, "query");
  const query = typeof rawQuery === "string" ? rawQuery.trim() : "";
  const points = Array.from(query);
  if (
    points.length < 1 ||
    points.length > discovery.profile.parameters.query.max_length ||
    query.includes("\0") ||
    points.some((point) => {
      const code = point.charCodeAt(0);
      return point.length === 1 && code >= 0xd800 && code <= 0xdfff;
    })
  )
    return unsupported(
      "Query must have only the query parameter, containing 1–4096 valid Unicode characters without NUL.",
      { nodeId: queryNode.id, field: "query" },
    );
  const topK = parameter(retrieverNode, "topK");
  const limit = parameter(resultNode, "limit");
  const maximum = discovery.profile.parameters.top_k.maximum;
  if (!boundedInteger(topK, maximum))
    return unsupported(
      `${dense ? "Dense search" : "Keyword search"} must have only topK, a whole number between 1 and ${maximum}.`,
      { nodeId: retrieverNode.id, field: "topK" },
    );
  if (!boundedInteger(limit, maximum))
    return unsupported(
      `Search results must have only limit, a whole number between 1 and ${maximum}.`,
      { nodeId: resultNode.id, field: "limit" },
    );
  const effectiveTopK = Math.min(topK, limit);
  return {
    supported: true,
    workspaceId: discovery.selectedWorkspaceId,
    effectiveTopK,
    request: {
      query,
      top_k: effectiveTopK,
      profile_id: discovery.profile.profile_id,
      expected_profile_revision: discovery.profile.profile_revision,
    },
  };
}
