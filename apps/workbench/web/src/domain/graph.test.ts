import { describe, expect, it } from "vitest";
import { createNode } from "./catalog";
import {
  createPipeline,
  exportPipeline,
  importPipeline,
  topologicalNodeIds,
  validateConnection,
  validateGraph,
} from "./graph";
import {
  completePreviewNode,
  createPreviewRun,
  finishPreviewRun,
} from "./preview";
import type { Graph, PreviewRun } from "./types";

describe("pipeline validation", () => {
  it("accepts the indexing and branched retrieval templates", () => {
    for (const template of ["indexing", "retrieval"] as const)
      expect(validateGraph(createPipeline(template).graph)).toEqual([]);
  });

  it("rejects a connection between incompatible values", () => {
    const source = createNode("query", { x: 0, y: 0 });
    const target = createNode("parser", { x: 300, y: 0 });
    expect(
      validateConnection(
        { nodes: [source, target], edges: [] },
        {
          source: source.id,
          target: target.id,
          sourceHandle: "query",
          targetHandle: "files",
        },
      ),
    ).toContain("expects files");
  });

  it("rejects an edge whose declared port does not exist", () => {
    const graph = createPipeline("retrieval").graph;
    expect(
      validateConnection(
        { ...graph, edges: [] },
        { ...graph.edges[0], sourceHandle: "invented" },
      ),
    ).toContain("existing input port");
  });

  it("rejects duplicate edges and a second producer on a single input", () => {
    const graph = createPipeline("retrieval").graph;
    expect(validateConnection(graph, graph.edges[0])).toContain(
      "already connected",
    );
    const otherQuery = createNode("query", { x: 0, y: 400 });
    expect(
      validateConnection(
        { ...graph, nodes: [...graph.nodes, otherQuery] },
        { ...graph.edges[0], source: otherQuery.id },
      ),
    ).toContain("only one");
  });

  it("allows multiple ranked inputs into the joiner", () => {
    const graph = createPipeline("retrieval").graph;
    const edge = graph.edges[4];
    expect(
      validateConnection(
        { ...graph, edges: graph.edges.filter((item) => item.id !== edge.id) },
        edge,
      ),
    ).toBeNull();
  });

  it("rejects a cycle through multiple compatible components", () => {
    const first = createNode("joiner", { x: 0, y: 0 });
    const second = createNode("joiner", { x: 300, y: 0 });
    const graph: Graph = {
      nodes: [first, second],
      edges: [
        {
          id: "forward",
          source: first.id,
          target: second.id,
          sourceHandle: "documents",
          targetHandle: "documents",
        },
      ],
    };
    const back = {
      source: second.id,
      target: first.id,
      sourceHandle: "documents",
      targetHandle: "documents",
    };
    expect(validateConnection(graph, back)).toContain("cycle");
    expect(() =>
      topologicalNodeIds({
        ...graph,
        edges: [...graph.edges, { id: "back", ...back }],
      }),
    ).toThrow("DAG");
  });

  it("reports missing required inputs and an empty question", () => {
    const graph = createPipeline("retrieval").graph;
    graph.edges = graph.edges.slice(1);
    graph.nodes.find(
      (node) => node.data.kind === "query",
    )!.data.parameters.query = "   ";
    const issues = validateGraph(graph);
    expect(
      issues.some((issue) => issue.message.includes("connect the query")),
    ).toBe(true);
    expect(
      issues.some((issue) => issue.message.includes("Question is required")),
    ).toBe(true);
  });

  it("requires an overlap smaller than the chunk size", () => {
    const graph = createPipeline("indexing").graph;
    const chunker = graph.nodes.find((node) => node.data.kind === "chunker")!;
    chunker.data.parameters.overlap = chunker.data.parameters.size;
    expect(
      validateGraph(graph).some((issue) =>
        issue.message.includes("overlap must be smaller"),
      ),
    ).toBe(true);
  });

  it("orders every producer before its dependent node", () => {
    const graph = createPipeline("retrieval").graph;
    const order = topologicalNodeIds(graph);
    for (const edge of graph.edges)
      expect(order.indexOf(edge.source)).toBeLessThan(
        order.indexOf(edge.target),
      );
  });
});

describe("portable pipeline files", () => {
  it("round-trips nodes, parameters, edges and the saved viewport", () => {
    const pipeline = createPipeline("retrieval");
    pipeline.graph.viewport = { x: 40, y: 20, zoom: 0.75 };
    expect(importPipeline(exportPipeline(pipeline))).toEqual(pipeline);
  });

  it("allows an incomplete graph to be saved and resumed", () => {
    const pipeline = createPipeline("indexing");
    pipeline.graph.edges = [];
    expect(importPipeline(exportPipeline(pipeline)).graph.edges).toEqual([]);
  });

  it("rejects unsupported schemas, components and executable payload fields", () => {
    const serialized = exportPipeline(createPipeline("retrieval"));
    expect(() =>
      importPipeline(
        serialized.replace('"schemaVersion": 1', '"schemaVersion": 99'),
      ),
    ).toThrow("schema");
    expect(() =>
      importPipeline(
        serialized.replace('"kind": "query"', '"kind": "python-code"'),
      ),
    ).toThrow("Unknown component");
    expect(() =>
      importPipeline(
        serialized.replace(
          '"kind": "query"',
          '"kind": "query", "code": "run()"',
        ),
      ),
    ).toThrow("unsupported field");
    expect(() => importPipeline('{"__proto__":{"polluted":true}}')).toThrow(
      "safe JSON",
    );
  });

  it("rejects duplicate node identifiers, broken connections and nonfinite coordinates", () => {
    const payload = JSON.parse(exportPipeline(createPipeline("retrieval")));
    payload.pipeline.graph.nodes[1].id = payload.pipeline.graph.nodes[0].id;
    expect(() => importPipeline(JSON.stringify(payload))).toThrow("unique");
    payload.pipeline.graph.nodes[1].id = "restored";
    payload.pipeline.graph.edges[0].target = "missing";
    expect(() => importPipeline(JSON.stringify(payload))).toThrow(
      "existing components",
    );
    const coordinatePayload = JSON.parse(
      exportPipeline(createPipeline("indexing")),
    );
    coordinatePayload.pipeline.graph.nodes[0].position.x = null;
    expect(() => importPipeline(JSON.stringify(coordinatePayload))).toThrow(
      "finite canvas",
    );
  });

  it("validates imported connections even when all node types are supported", () => {
    const pipeline = createPipeline("blank");
    const first = createNode("joiner", { x: 0, y: 0 });
    const second = createNode("joiner", { x: 300, y: 0 });
    pipeline.graph = {
      nodes: [first, second],
      edges: [
        {
          id: "forward",
          source: first.id,
          target: second.id,
          sourceHandle: "documents",
          targetHandle: "documents",
        },
        {
          id: "backward",
          source: second.id,
          target: first.id,
          sourceHandle: "documents",
          targetHandle: "documents",
        },
      ],
    };
    expect(() => importPipeline(exportPipeline(pipeline))).toThrow("cycle");
    pipeline.graph.edges = [
      pipeline.graph.edges[0],
      { ...pipeline.graph.edges[0], id: "duplicate" },
    ];
    expect(() => importPipeline(exportPipeline(pipeline))).toThrow(
      "already connected",
    );
  });

  it("rejects incorrectly typed parameters and excessive graph sizes", () => {
    const payload = JSON.parse(exportPipeline(createPipeline("indexing")));
    payload.pipeline.graph.nodes[2].data.parameters.size = "500";
    expect(() => importPipeline(JSON.stringify(payload))).toThrow(
      "Invalid value type",
    );
    payload.pipeline.graph.nodes = Array.from(
      { length: 101 },
      () => payload.pipeline.graph.nodes[0],
    );
    expect(() => importPipeline(JSON.stringify(payload))).toThrow(
      "100 components",
    );
  });

  it("rejects invalid numeric ranges from imported files", () => {
    for (const topK of [-1, 1.5]) {
      const pipeline = createPipeline("retrieval");
      pipeline.graph.nodes.find(
        (node) => node.data.kind === "bm25",
      )!.data.parameters.topK = topK;
      expect(() => importPipeline(exportPipeline(pipeline))).toThrow(
        "Invalid range",
      );
    }
    const indexing = createPipeline("indexing");
    indexing.graph.nodes.find(
      (node) => node.data.kind === "document-embedder",
    )!.data.parameters.batchSize = 17;
    expect(() => importPipeline(exportPipeline(indexing))).toThrow(
      "Batch size cannot exceed",
    );
    indexing.graph.nodes.find(
      (node) => node.data.kind === "document-embedder",
    )!.data.parameters.batchSize = 16;
    indexing.graph.nodes.find(
      (node) => node.data.kind === "chunker",
    )!.data.parameters.overlap = 500;
    expect(() => importPipeline(exportPipeline(indexing))).toThrow(
      "Overlap must be smaller",
    );
  });

  it("keeps incomplete parameters editable but blocks their execution", () => {
    const pipeline = createPipeline("retrieval");
    delete pipeline.graph.nodes.find((node) => node.data.kind === "query")!.data
      .parameters.query;
    const restored = importPipeline(exportPipeline(pipeline));
    expect(
      validateGraph(restored.graph).some((issue) =>
        issue.message.includes("Question is required"),
      ),
    ).toBe(true);
    expect(() => createPreviewRun(restored)).toThrow("Question is required");
  });

  it("caps file size and rejects malformed JSON", () => {
    expect(() => importPipeline("x".repeat(1000001))).toThrow("1 MB");
    expect(() => importPipeline("{broken")).toThrow("safe JSON");
  });
});

describe("honest fixture runs", () => {
  function completedRun(
    template: "retrieval" | "indexing",
    scenario: "success" | "error",
  ): PreviewRun {
    const run = createPreviewRun(createPipeline(template));
    for (const id of topologicalNodeIds(run.graph)) {
      const node = run.graph.nodes.find((item) => item.id === id)!;
      const result = completePreviewNode(run, node, scenario);
      run.nodes.push(result);
      if (result.status === "error") break;
    }
    return finishPreviewRun(run, scenario, 3);
  }

  it("returns bounded sample passages only for a completed retrieval graph", () => {
    const run = completedRun("retrieval", "success");
    expect(run.status).toBe("Completed");
    expect(run.results).toHaveLength(3);
    expect(run.nodes.every((node) => node.output.preview === true)).toBe(true);
    expect(completedRun("indexing", "success").results).toEqual([]);
  });

  it("marks the configured failure and never supplies success passages", () => {
    const run = completedRun("retrieval", "error");
    expect(run.status).toBe("Failed");
    expect(run.errors).toHaveLength(1);
    expect(run.results).toEqual([]);
    expect(run.nodes.at(-1)?.output.error_code).toBe(
      "PREVIEW_SERVICE_UNAVAILABLE",
    );
  });

  it("rejects invalid graphs and preserves a cancelled run", () => {
    expect(() => createPreviewRun(createPipeline("blank"))).toThrow(
      "Add a component",
    );
    const run = createPreviewRun(createPipeline("indexing"));
    run.status = "Cancelled";
    expect(finishPreviewRun(run, "success", 5).status).toBe("Cancelled");
  });
});
