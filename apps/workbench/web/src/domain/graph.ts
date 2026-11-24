import type { Edge } from "@xyflow/react";
import { catalog, createNode, getDefinition } from "./catalog";
import type {
  Graph,
  GraphIssue,
  NodeKind,
  Pipeline,
  TemplateId,
  WorkbenchNode,
} from "./types";

type Connection = {
  source: string | null;
  target: string | null;
  sourceHandle?: string | null;
  targetHandle?: string | null;
};
const templates: Record<TemplateId, { name: string; description: string }> = {
  dense: {
    name: "Dense search",
    description:
      "Search a qualified local embedding generation by exact cosine distance.",
  },
  keyword: {
    name: "Keyword search",
    description:
      "Search the persisted corpus with an approved Live lexical profile.",
  },
  retrieval: {
    name: "Hybrid document search",
    description:
      "Combine precise keywords and semantic meaning to find the right passages.",
  },
  indexing: {
    name: "Document indexing",
    description: "Parse, split and prepare your documents for search.",
  },
  blank: {
    name: "Untitled pipeline",
    description: "Build a pipeline from the component library.",
  },
};

function connect(
  source: WorkbenchNode,
  sourceHandle: string,
  target: WorkbenchNode,
  targetHandle: string,
): Edge {
  return {
    id: crypto.randomUUID(),
    source: source.id,
    target: target.id,
    sourceHandle,
    targetHandle,
    type: "smoothstep",
  };
}

export function createPipeline(templateId: TemplateId): Pipeline {
  const nodes: WorkbenchNode[] = [];
  const edges: Edge[] = [];
  if (templateId === "retrieval") {
    const query = createNode("query", { x: 0, y: 160 });
    const keyword = createNode("bm25", { x: 260, y: 20 });
    const embed = createNode("text-embedder", { x: 260, y: 300 });
    const semantic = createNode("vector", { x: 520, y: 300 });
    const joiner = createNode("joiner", { x: 780, y: 160 });
    const results = createNode("results", { x: 1040, y: 160 });
    nodes.push(query, keyword, embed, semantic, joiner, results);
    edges.push(
      connect(query, "query", keyword, "query"),
      connect(query, "query", embed, "text"),
      connect(embed, "embedding", semantic, "embedding"),
      connect(keyword, "documents", joiner, "documents"),
      connect(semantic, "documents", joiner, "documents"),
      connect(joiner, "documents", results, "documents"),
    );
  } else if (templateId === "keyword") {
    const query = createNode("query", { x: 0, y: 160 });
    query.data.parameters.query = "retention";
    const keyword = createNode("keyword-search", { x: 300, y: 160 });
    const results = createNode("results", { x: 600, y: 160 });
    nodes.push(query, keyword, results);
    edges.push(
      connect(query, "query", keyword, "query"),
      connect(keyword, "documents", results, "documents"),
    );
  } else if (templateId === "dense") {
    const query = createNode("query", { x: 0, y: 160 });
    query.data.parameters.query = "How long are backups retained?";
    const embedder = createNode("query-embedding", { x: 260, y: 160 });
    const retriever = createNode("dense-search", { x: 520, y: 160 });
    const results = createNode("results", { x: 780, y: 160 });
    nodes.push(query, embedder, retriever, results);
    edges.push(
      connect(query, "query", embedder, "text"),
      connect(embedder, "embedding", retriever, "embedding"),
      connect(retriever, "documents", results, "documents"),
    );
  } else if (templateId === "indexing") {
    const kinds: NodeKind[] = [
      "files",
      "parser",
      "chunker",
      "document-embedder",
      "writer",
    ];
    nodes.push(
      ...kinds.map((kind, index) =>
        createNode(kind, { x: index * 260, y: 160 }),
      ),
    );
    for (let index = 0; index < nodes.length - 1; index++) {
      edges.push(
        connect(
          nodes[index],
          index === 0 ? "files" : "documents",
          nodes[index + 1],
          index === 0 ? "files" : "documents",
        ),
      );
    }
  }
  return {
    id: crypto.randomUUID(),
    ...templates[templateId],
    templateId,
    updatedAt: new Date().toISOString(),
    graph: { nodes, edges },
  };
}

export function topologicalNodeIds(graph: Graph): string[] {
  const indegree = new Map(graph.nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(
    graph.nodes.map((node) => [node.id, [] as string[]]),
  );
  for (const edge of graph.edges) {
    if (!indegree.has(edge.source) || !indegree.has(edge.target))
      throw new Error("A connection refers to a missing component.");
    indegree.set(edge.target, indegree.get(edge.target)! + 1);
    outgoing.get(edge.source)!.push(edge.target);
  }
  const ready = graph.nodes
    .filter((node) => indegree.get(node.id) === 0)
    .map((node) => node.id);
  const order: string[] = [];
  for (let index = 0; index < ready.length; index++) {
    const id = ready[index];
    order.push(id);
    for (const target of outgoing.get(id)!) {
      const remaining = indegree.get(target)! - 1;
      indegree.set(target, remaining);
      if (remaining === 0) ready.push(target);
    }
  }
  if (order.length !== graph.nodes.length)
    throw new Error(
      "Fixture preview requires a DAG. Remove the cycle to preview; this is not a Haystack restriction.",
    );
  return order;
}

export function checkDraftConnection(
  graph: Graph,
  connection: Connection,
): string | null {
  const source = graph.nodes.find((node) => node.id === connection.source);
  const target = graph.nodes.find((node) => node.id === connection.target);
  if (!source || !target) return "Choose two existing components.";
  if (
    !getDefinition(source.data.kind).outputs.some(
      (port) => port.id === connection.sourceHandle,
    ) ||
    !getDefinition(target.data.kind).inputs.some(
      (port) => port.id === connection.targetHandle,
    )
  )
    return "Choose existing editor input and output handles.";
  if (
    graph.edges.some(
      (edge) =>
        edge.source === source.id &&
        edge.target === target.id &&
        edge.sourceHandle === connection.sourceHandle &&
        edge.targetHandle === connection.targetHandle,
    )
  )
    return "These ports are already connected.";
  return null;
}

export function checkPreviewConnection(
  graph: Graph,
  connection: Connection,
): string | null {
  const source = graph.nodes.find((node) => node.id === connection.source);
  const target = graph.nodes.find((node) => node.id === connection.target);
  if (!source || !target) return "Choose two existing components.";
  if (source.id === target.id) return "A component cannot connect to itself.";
  const output = getDefinition(source.data.kind).outputs.find(
    (port) => port.id === connection.sourceHandle,
  );
  const input = getDefinition(target.data.kind).inputs.find(
    (port) => port.id === connection.targetHandle,
  );
  if (!output || !input)
    return "Connect an output port to an existing input port.";
  if (output.valueKind !== input.valueKind)
    return `This input expects ${input.valueKind}, but the output provides ${output.valueKind}.`;
  if (
    graph.edges.some(
      (edge) =>
        edge.source === source.id &&
        edge.target === target.id &&
        edge.sourceHandle === output.id &&
        edge.targetHandle === input.id,
    )
  ) {
    return "These ports are already connected.";
  }
  if (
    !input.multiple &&
    graph.edges.some(
      (edge) => edge.target === target.id && edge.targetHandle === input.id,
    )
  )
    return "This input accepts only one connection.";
  const pending = [target.id];
  const visited = new Set<string>();
  while (pending.length) {
    const id = pending.pop()!;
    if (id === source.id)
      return "Fixture preview cannot simulate this cycle; Haystack may support the loop.";
    if (visited.has(id)) continue;
    visited.add(id);
    pending.push(
      ...graph.edges
        .filter((edge) => edge.source === id)
        .map((edge) => edge.target),
    );
  }
  return null;
}

export function checkPreviewGraph(graph: Graph): GraphIssue[] {
  const issues: GraphIssue[] = [];
  if (!graph.nodes.length)
    return [{ message: "Add a component to start building your pipeline." }];
  const ids = new Set<string>();
  for (const node of graph.nodes) {
    if (
      ["keyword-search", "query-embedding", "dense-search"].includes(
        node.data.kind,
      )
    )
      issues.push({
        nodeId: node.id,
        code: "PREVIEW_UNSUPPORTED",
        message: `${node.data.label} requires Live mode and a ready backend profile. Preview does not simulate this component.`,
      });
    if (ids.has(node.id))
      issues.push({
        nodeId: node.id,
        message: "Component identifiers must be unique.",
      });
    ids.add(node.id);
    const definition = getDefinition(node.data.kind);
    for (const port of definition.inputs) {
      if (
        port.required &&
        !graph.edges.some(
          (edge) => edge.target === node.id && edge.targetHandle === port.id,
        )
      ) {
        issues.push({
          nodeId: node.id,
          message: `${node.data.label}: connect the ${port.label.toLowerCase()} input.`,
        });
      }
    }
    for (const parameter of definition.parameters) {
      const value = node.data.parameters[parameter.key];
      if (
        parameter.required &&
        (value === undefined || (typeof value === "string" && !value.trim()))
      ) {
        issues.push({
          nodeId: node.id,
          message: `${node.data.label}: ${parameter.label} is required.`,
        });
      } else if (
        value !== undefined &&
        parameter.type === "number" &&
        (typeof value !== "number" ||
          !Number.isFinite(value) ||
          !Number.isInteger(value) ||
          (parameter.min !== undefined && value < parameter.min))
      ) {
        issues.push({
          nodeId: node.id,
          message: `${node.data.label}: ${parameter.label} must be a whole number${parameter.min !== undefined ? ` of at least ${parameter.min}` : ""}.`,
        });
      } else if (
        value !== undefined &&
        parameter.options &&
        !parameter.options.includes(String(value))
      ) {
        issues.push({
          nodeId: node.id,
          message: `${node.data.label}: choose a supported ${parameter.label.toLowerCase()}.`,
        });
      }
    }
    if (
      node.data.kind === "chunker" &&
      Number(node.data.parameters.overlap) >= Number(node.data.parameters.size)
    ) {
      issues.push({
        nodeId: node.id,
        message: `${node.data.label}: overlap must be smaller than chunk size.`,
      });
    }
    if (
      node.data.kind === "document-embedder" &&
      Number(node.data.parameters.batchSize) > 16
    ) {
      issues.push({
        nodeId: node.id,
        message: `${node.data.label}: the local embedding profile accepts at most 16 items per batch.`,
      });
    }
  }
  const edgeIds = new Set<string>();
  graph.edges.forEach((edge, index) => {
    if (edgeIds.has(edge.id))
      issues.push({ message: "Connection identifiers must be unique." });
    edgeIds.add(edge.id);
    const message = checkPreviewConnection(
      { nodes: graph.nodes, edges: graph.edges.slice(0, index) },
      edge,
    );
    if (message) issues.push({ nodeId: edge.target, message });
  });
  return issues;
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error(`${label} must be an object.`);
  return value as Record<string, unknown>;
}

function keys(
  value: Record<string, unknown>,
  allowed: string[],
  label: string,
): void {
  if (Object.keys(value).some((key) => !allowed.includes(key)))
    throw new Error(`${label} contains an unsupported field.`);
}

function text(value: unknown, label: string, maximum = 200): string {
  if (typeof value !== "string" || !value.trim() || value.length > maximum)
    throw new Error(`${label} must contain 1–${maximum} characters.`);
  return value;
}

function coordinate(value: unknown, label: string): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    Math.abs(value) > 100000
  )
    throw new Error(`${label} must be a finite canvas coordinate.`);
  return value;
}

function parseNode(value: unknown): WorkbenchNode {
  const node = object(value, "Component");
  keys(node, ["id", "type", "position", "data"], "Component");
  if (node.type !== "workbench") throw new Error("Unsupported component type.");
  const data = object(node.data, "Component data");
  keys(data, ["kind", "label", "parameters", "status"], "Component data");
  const kind = catalog.find((item) => item.kind === data.kind)?.kind;
  if (!kind) throw new Error("Unknown component kind.");
  if (
    data.status !== undefined &&
    !["idle", "running", "success", "error"].includes(String(data.status))
  )
    throw new Error("Unsupported component status.");
  const parameters = object(data.parameters, "Component parameters");
  const definition = getDefinition(kind);
  keys(
    parameters,
    definition.parameters.map((parameter) => parameter.key),
    "Component parameters",
  );
  const cleanParameters: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(parameters)) {
    if (typeof value !== "string" && typeof value !== "number")
      throw new Error("Parameter values must be text or numbers.");
    if (typeof value === "number" && !Number.isFinite(value))
      throw new Error("Parameter values must be finite.");
    if (typeof value === "string" && value.length > 12000)
      throw new Error("Parameter text is too long.");
    const parameter = definition.parameters.find((item) => item.key === key)!;
    if ((parameter.type === "number") !== (typeof value === "number"))
      throw new Error(`Invalid value type for ${parameter.label}.`);
    if (
      typeof value === "number" &&
      (!Number.isInteger(value) ||
        (parameter.min !== undefined && value < parameter.min))
    )
      throw new Error(`Invalid range for ${parameter.label}.`);
    if (parameter.options && !parameter.options.includes(String(value)))
      throw new Error(`Unsupported value for ${parameter.label}.`);
    cleanParameters[key] = value;
  }
  if (
    kind === "chunker" &&
    typeof cleanParameters.size === "number" &&
    typeof cleanParameters.overlap === "number" &&
    cleanParameters.overlap >= cleanParameters.size
  )
    throw new Error("Overlap must be smaller than chunk size.");
  if (
    kind === "document-embedder" &&
    typeof cleanParameters.batchSize === "number" &&
    cleanParameters.batchSize > 16
  )
    throw new Error(
      "Batch size cannot exceed 16 for the local embedding profile.",
    );
  const position = object(node.position, "Position");
  keys(position, ["x", "y"], "Position");
  return {
    id: text(node.id, "Component ID"),
    type: "workbench",
    position: {
      x: coordinate(position.x, "Position x"),
      y: coordinate(position.y, "Position y"),
    },
    data: {
      kind,
      label: text(data.label, "Component label"),
      parameters: cleanParameters,
      status: "idle",
    },
  };
}

function parseEdge(value: unknown): Edge {
  const edge = object(value, "Connection");
  keys(
    edge,
    ["id", "source", "target", "sourceHandle", "targetHandle", "type"],
    "Connection",
  );
  if (edge.type !== undefined && edge.type !== "smoothstep")
    throw new Error("Unsupported connection type.");
  return {
    id: text(edge.id, "Connection ID"),
    source: text(edge.source, "Connection source"),
    target: text(edge.target, "Connection target"),
    sourceHandle: text(edge.sourceHandle, "Output port"),
    targetHandle: text(edge.targetHandle, "Input port"),
    type: "smoothstep",
  };
}

export function portableGraph(graph: Graph): Graph {
  return {
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      type: "workbench",
      position: { x: node.position.x, y: node.position.y },
      data: {
        kind: node.data.kind,
        label: node.data.label,
        parameters: { ...node.data.parameters },
        status: "idle",
      },
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      type: "smoothstep",
    })),
    ...(graph.viewport
      ? {
          viewport: {
            x: graph.viewport.x,
            y: graph.viewport.y,
            zoom: graph.viewport.zoom,
          },
        }
      : {}),
  };
}

function portablePipeline(pipeline: Pipeline): Pipeline {
  return {
    id: pipeline.id,
    name: pipeline.name,
    description: pipeline.description,
    templateId: pipeline.templateId,
    updatedAt: pipeline.updatedAt,
    graph: portableGraph(pipeline.graph),
  };
}
export function exportPipeline(pipeline: Pipeline): string {
  return JSON.stringify(
    { schemaVersion: 1, pipeline: portablePipeline(pipeline) },
    null,
    2,
  );
}

export function importPipeline(serialized: string): Pipeline {
  if (serialized.length > 1000000)
    throw new Error("Pipeline files must be smaller than 1 MB.");
  let decoded: unknown;
  try {
    decoded = JSON.parse(serialized, (key, value: unknown) => {
      if (["__proto__", "prototype", "constructor"].includes(key))
        throw new Error("Unsupported object key.");
      return value;
    });
  } catch {
    throw new Error("The pipeline file is not valid, safe JSON.");
  }
  const envelope = object(decoded, "Pipeline file");
  keys(envelope, ["schemaVersion", "pipeline"], "Pipeline file");
  if (envelope.schemaVersion !== 1)
    throw new Error("Unsupported pipeline schema version.");
  const pipeline = object(envelope.pipeline, "Pipeline");
  keys(
    pipeline,
    ["id", "name", "description", "templateId", "updatedAt", "graph"],
    "Pipeline",
  );
  if (
    pipeline.templateId !== "blank" &&
    pipeline.templateId !== "retrieval" &&
    pipeline.templateId !== "keyword" &&
    pipeline.templateId !== "dense" &&
    pipeline.templateId !== "indexing"
  )
    throw new Error("Unsupported pipeline template.");
  const graphData = object(pipeline.graph, "Graph");
  keys(graphData, ["nodes", "edges", "viewport"], "Graph");
  if (!Array.isArray(graphData.nodes) || graphData.nodes.length > 100)
    throw new Error("A pipeline may contain up to 100 components.");
  if (!Array.isArray(graphData.edges) || graphData.edges.length > 300)
    throw new Error("A pipeline may contain up to 300 connections.");
  const graph: Graph = { nodes: graphData.nodes.map(parseNode), edges: [] };
  if (new Set(graph.nodes.map((node) => node.id)).size !== graph.nodes.length)
    throw new Error("Component identifiers must be unique.");
  const edgeIds = new Set<string>();
  for (const item of graphData.edges) {
    const edge = parseEdge(item);
    if (edgeIds.has(edge.id))
      throw new Error("Connection identifiers must be unique.");
    const issue = checkDraftConnection(graph, edge);
    if (issue) throw new Error(issue);
    edgeIds.add(edge.id);
    graph.edges.push(edge);
  }
  if (graphData.viewport !== undefined) {
    const viewport = object(graphData.viewport, "Viewport");
    keys(viewport, ["x", "y", "zoom"], "Viewport");
    if (
      typeof viewport.zoom !== "number" ||
      !Number.isFinite(viewport.zoom) ||
      viewport.zoom < 0.1 ||
      viewport.zoom > 4
    )
      throw new Error("Viewport zoom must be between 0.1 and 4.");
    graph.viewport = {
      x: coordinate(viewport.x, "Viewport x"),
      y: coordinate(viewport.y, "Viewport y"),
      zoom: viewport.zoom,
    };
  }
  const updatedAt = text(pipeline.updatedAt, "Update date", 50);
  if (!Number.isFinite(Date.parse(updatedAt)))
    throw new Error("Update date must be valid.");
  if (
    typeof pipeline.description !== "string" ||
    pipeline.description.length > 2000
  )
    throw new Error("Description must contain at most 2000 characters.");
  return {
    id: text(pipeline.id, "Pipeline ID"),
    name: text(pipeline.name, "Pipeline name"),
    description: pipeline.description,
    templateId: pipeline.templateId,
    updatedAt,
    graph,
  };
}
