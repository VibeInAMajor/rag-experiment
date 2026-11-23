import { describe, expect, it } from "vitest";
import { matchApprovedKeywordGraph } from "./approvedExecution";
import type { BackendDiscoveryState } from "./backendDiscovery";
import { createNode } from "./catalog";
import { createPipeline } from "./graph";
import type { Graph } from "./types";

function readyDiscovery(): Extract<BackendDiscoveryState, { status: "ready" }> {
  const profile = {
    profile_id: "postgres-fts-baseline",
    profile_revision: "postgres-fts-baseline-r1",
    kind: "lexical_search",
    score_type: "postgres_ts_rank_cd",
    workspace_ids: ["development"],
    corpus_id: "development-corpus-v1",
    parameters: {
      query: { type: "string", min_length: 1, max_length: 4096 },
      top_k: { type: "integer", minimum: 1, maximum: 50, default: 10 },
    },
    limits: {
      max_request_bytes: 32768,
      timeout_ms: 10000,
      max_concurrent_searches: 2,
      max_corpus_chunks: 10000,
      max_corpus_bytes: 52428800,
    },
  } as const;
  return {
    status: "ready",
    lastCheckedAt: "2026-11-21T00:00:00Z",
    profile: { ...profile, workspace_ids: [...profile.workspace_ids] },
    selectedWorkspaceId: "development",
    workspaces: [
      { workspace_id: "development", name: "Development", status: "ready" },
    ],
    capabilities: {
      contract_revision: "rag-api-v1.0",
      backend_revision: "workbench-api-lexical-v1",
      request_id: "request-1",
      trace_id: "trace-1",
      deployment_mode: "single_workspace_dev",
      service_state: "running",
      profiles: [{ ...profile, workspace_ids: [...profile.workspace_ids] }],
      features: {
        documents: true,
        search: true,
        upload: true,
        document_details: true,
        jobs: true,
      },
      pdf_ingestion: {
        available: false,
        text_layer: false,
        page_provenance: false,
        table_rows: false,
        original_evidence: false,
        ocr: false,
        visual_understanding: false,
        visual_detection_coverage: "unverified",
        max_bytes: 8388608,
        max_pages: 32,
      },
      dependencies: {
        database: { status: "ready", workspace_id: "development" },
      },
    },
  };
}

describe("approved keyword execution", () => {
  it("maps only the four approved fields and the server-authorized workspace", () => {
    const graph = createPipeline("keyword").graph;
    expect(matchApprovedKeywordGraph(graph, readyDiscovery())).toEqual({
      supported: true,
      workspaceId: "development",
      effectiveTopK: 5,
      request: {
        query: "retention",
        top_k: 5,
        profile_id: "postgres-fts-baseline",
        expected_profile_revision: "postgres-fts-baseline-r1",
      },
    });
  });

  it("uses the selected approved lexical ID and revision while enforcing its own smaller bounds", () => {
    const discovery = readyDiscovery();
    const selected = {
      ...discovery.profile,
      profile_id: "postgres-fts-bounded",
      profile_revision: "bounded-r7",
      parameters: {
        query: {
          type: "string" as const,
          min_length: 1 as const,
          max_length: 128,
        },
        top_k: {
          type: "integer" as const,
          minimum: 1 as const,
          maximum: 3,
          default: 2,
        },
      },
    };
    discovery.profile = selected;
    discovery.capabilities!.profiles = [selected];
    const graph = createPipeline("keyword").graph;
    expect(matchApprovedKeywordGraph(graph, discovery).supported).toBe(false);
    graph.nodes[1].data.parameters.topK = 3;
    graph.nodes[2].data.parameters.limit = 2;
    expect(matchApprovedKeywordGraph(graph, discovery)).toMatchObject({
      supported: true,
      request: {
        profile_id: "postgres-fts-bounded",
        expected_profile_revision: "bounded-r7",
        top_k: 2,
      },
    });
    graph.nodes[0].data.parameters.query = "x".repeat(129);
    expect(matchApprovedKeywordGraph(graph, discovery).supported).toBe(false);
  });

  it("ignores node order, labels, coordinates and viewport", () => {
    const graph = createPipeline("keyword").graph;
    graph.nodes.reverse();
    graph.edges.reverse();
    graph.nodes.forEach((node, index) => {
      node.data.label = `Custom label ${index}`;
      node.position = { x: -1000 + index * 200, y: 800 };
    });
    graph.viewport = { x: 40, y: -50, zoom: 0.75 };
    expect(matchApprovedKeywordGraph(graph, readyDiscovery()).supported).toBe(
      true,
    );
  });

  it.each([
    [10, 5, 5],
    [3, 10, 3],
    [50, 50, 50],
    [1, 1, 1],
  ])("honors both topK %s and result limit %s", (topK, limit, expected) => {
    const graph = createPipeline("keyword").graph;
    graph.nodes[1].data.parameters.topK = topK;
    graph.nodes[2].data.parameters.limit = limit;
    const result = matchApprovedKeywordGraph(graph, readyDiscovery());
    expect(result.supported && result.request.top_k).toBe(expected);
  });

  const graphMutations: Array<[string, (graph: Graph) => void]> = [
    [
      "extra node",
      (graph) => {
        graph.nodes.push(createNode("query", { x: 0, y: 0 }));
      },
    ],
    [
      "missing node",
      (graph) => {
        graph.nodes.pop();
      },
    ],
    [
      "two query nodes",
      (graph) => {
        graph.nodes[1].data.kind = "query";
      },
    ],
    [
      "BM25 substitution",
      (graph) => {
        graph.nodes[1].data.kind = "bm25";
      },
    ],
    [
      "duplicate node IDs",
      (graph) => {
        graph.nodes[1].id = graph.nodes[0].id;
      },
    ],
    [
      "empty node ID",
      (graph) => {
        graph.nodes[1].id = "";
      },
    ],
    [
      "extra edge",
      (graph) => {
        graph.edges.push({ ...graph.edges[0], id: "parallel" });
      },
    ],
    [
      "missing edge",
      (graph) => {
        graph.edges.pop();
      },
    ],
    [
      "duplicate edge IDs",
      (graph) => {
        graph.edges[1].id = graph.edges[0].id;
      },
    ],
    [
      "duplicate path",
      (graph) => {
        graph.edges[1] = { ...graph.edges[0], id: "duplicate" };
      },
    ],
    [
      "wrong output handle",
      (graph) => {
        graph.edges[0].sourceHandle = "text";
      },
    ],
    [
      "wrong input handle",
      (graph) => {
        graph.edges[1].targetHandle = "files";
      },
    ],
    [
      "reversed connection",
      (graph) => {
        [graph.edges[0].source, graph.edges[0].target] = [
          graph.edges[0].target,
          graph.edges[0].source,
        ];
      },
    ],
    [
      "cycle",
      (graph) => {
        graph.edges[1].target = graph.nodes[0].id;
      },
    ],
    [
      "dangling connection",
      (graph) => {
        graph.edges[1].source = "unknown";
      },
    ],
    [
      "query extra parameter",
      (graph) => {
        graph.nodes[0].data.parameters.collection = "foreign";
      },
    ],
    [
      "keyword extra parameter",
      (graph) => {
        graph.nodes[1].data.parameters.sql = "unapproved";
      },
    ],
    [
      "results extra parameter",
      (graph) => {
        graph.nodes[2].data.parameters.scope = "foreign";
      },
    ],
    [
      "missing query",
      (graph) => {
        graph.nodes[0].data.parameters = {};
      },
    ],
    [
      "missing topK",
      (graph) => {
        graph.nodes[1].data.parameters = {};
      },
    ],
    [
      "missing limit",
      (graph) => {
        graph.nodes[2].data.parameters = {};
      },
    ],
  ];
  it.each(graphMutations)(
    "rejects %s before a request can be produced",
    (_label, mutate) => {
      const graph = createPipeline("keyword").graph;
      mutate(graph);
      const result = matchApprovedKeywordGraph(graph, readyDiscovery());
      expect(result.supported).toBe(false);
      expect(result).not.toHaveProperty("request");
    },
  );

  it.each([
    "",
    "   ",
    "\0query",
    "a\ud800",
    "\udfff",
    "a".repeat(4097),
    "😀".repeat(4097),
  ])("rejects invalid query %#", (query) => {
    const graph = createPipeline("keyword").graph;
    graph.nodes[0].data.parameters.query = query;
    expect(matchApprovedKeywordGraph(graph, readyDiscovery()).supported).toBe(
      false,
    );
  });

  it("counts Unicode code points and trims the submitted query", () => {
    const graph = createPipeline("keyword").graph;
    const query = "😀".repeat(4096);
    graph.nodes[0].data.parameters.query = `  ${query}  `;
    const result = matchApprovedKeywordGraph(graph, readyDiscovery());
    expect(result.supported && result.request.query).toBe(query);
  });

  it.each([0, -1, 1.5, 51, NaN, Infinity, "5"])(
    "rejects invalid topK or limit %s without clamping",
    (value) => {
      for (const index of [1, 2]) {
        const graph = createPipeline("keyword").graph;
        graph.nodes[index].data.parameters[index === 1 ? "topK" : "limit"] =
          value;
        expect(
          matchApprovedKeywordGraph(graph, readyDiscovery()).supported,
        ).toBe(false);
      }
    },
  );

  it("refuses all existing Preview templates", () => {
    for (const template of ["blank", "retrieval", "indexing"] as const)
      expect(
        matchApprovedKeywordGraph(
          createPipeline(template).graph,
          readyDiscovery(),
        ).supported,
      ).toBe(false);
  });

  it.each([
    "unconfigured",
    "checking",
    "not_ready",
    "unavailable",
    "incompatible",
  ] as const)("requires ready discovery rather than %s", (status) => {
    const discovery: BackendDiscoveryState = {
      ...readyDiscovery(),
      status,
      profile: null,
      selectedWorkspaceId: null,
    };
    expect(
      matchApprovedKeywordGraph(createPipeline("keyword").graph, discovery)
        .supported,
    ).toBe(false);
  });

  it("checks each limit against discovered bounds before taking their minimum", () => {
    const discovery = readyDiscovery();
    Reflect.set(discovery.profile.parameters.top_k, "maximum", 10);
    const graph = createPipeline("keyword").graph;
    graph.nodes[1].data.parameters.topK = 11;
    graph.nodes[2].data.parameters.limit = 5;
    expect(matchApprovedKeywordGraph(graph, discovery).supported).toBe(false);
  });

  const profileMutations: Array<
    [
      string,
      (state: Extract<BackendDiscoveryState, { status: "ready" }>) => void,
    ]
  > = [
    [
      "reserved profile",
      (state) => {
        state.profile.profile_id = "bm25-v1";
      },
    ],
    [
      "stale revision",
      (state) => {
        state.profile.profile_revision = "older-r1";
      },
    ],
    [
      "wrong score",
      (state) => {
        state.profile.score_type = "bm25_raw";
      },
    ],
    [
      "unadvertised profile",
      (state) => {
        if (state.capabilities) state.capabilities.profiles = [];
      },
    ],
    [
      "unavailable database",
      (state) => {
        if (state.capabilities)
          state.capabilities.dependencies.database.status = "unavailable";
      },
    ],
    [
      "search disabled",
      (state) => {
        if (state.capabilities) state.capabilities.features.search = false;
      },
    ],
    [
      "foreign selected workspace",
      (state) => {
        state.selectedWorkspaceId = "foreign";
      },
    ],
    [
      "unlisted workspace",
      (state) => {
        state.workspaces = [];
      },
    ],
    [
      "unavailable workspace",
      (state) => {
        state.workspaces[0].status = "unavailable";
      },
    ],
    [
      "unbound workspace",
      (state) => {
        state.profile.workspace_ids = ["foreign"];
      },
    ],
    [
      "changed corpus",
      (state) => {
        state.profile.corpus_id = "different-corpus";
      },
    ],
  ];
  it.each(profileMutations)(
    "rejects %s without returning execution parameters",
    (_label, mutate) => {
      const discovery = readyDiscovery();
      mutate(discovery);
      expect(
        matchApprovedKeywordGraph(createPipeline("keyword").graph, discovery)
          .supported,
      ).toBe(false);
    },
  );

  it("does not mutate graph or discovery", () => {
    const graph = createPipeline("keyword").graph;
    const discovery = readyDiscovery();
    const before = structuredClone({ graph, discovery });
    matchApprovedKeywordGraph(graph, discovery);
    expect({ graph, discovery }).toEqual(before);
  });
});
