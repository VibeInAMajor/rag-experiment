import { previewDocuments } from "./fixtures";
import { topologicalNodeIds, validateGraph } from "./graph";
import type {
  NodeResult,
  Pipeline,
  PreviewRun,
  RetrievalResult,
  WorkbenchNode,
  WorkbenchSettings,
} from "./types";

type Scenario = WorkbenchSettings["previewScenario"];

const previewResults: RetrievalResult[] = [
  {
    id: "result-version",
    sourceId: "doc-platform",
    title: "RAG platform architecture.pdf",
    page: 9,
    score: 0.96,
    content:
      "Prepare the new document version, validate its passages and embeddings, then publish it. Keep the previous active version readable until preparation succeeds.",
  },
  {
    id: "result-recovery",
    sourceId: "doc-operations",
    title: "Knowledge base operations.md",
    page: 1,
    score: 0.91,
    content:
      "Unchanged passages reuse compatible embeddings. Interrupted updates never replace the active version with an incomplete one; recovery completes pending cleanup.",
  },
  {
    id: "result-evidence",
    sourceId: "doc-retrieval",
    title: "Retrieval quality playbook.docx",
    page: 5,
    score: 0.87,
    content:
      "Preserve source and page references with each result. Combine keyword and semantic candidate ranks using reciprocal rank fusion.",
  },
  {
    id: "result-workspace",
    sourceId: "doc-policy",
    title: "Workspace data policy.pdf",
    page: 3,
    score: 0.82,
    content:
      "Verify workspace and source ownership before returning any passage. Client-defined filters cannot replace server-side workspace restrictions.",
  },
];

function failureNodeId(run: PreviewRun): string | undefined {
  const preferred =
    run.graph.nodes.find(
      (node) =>
        node.data.kind === "text-embedder" ||
        node.data.kind === "document-embedder",
    ) ??
    run.graph.nodes.find((node) => node.data.kind === "parser") ??
    run.graph.nodes[0];
  return preferred?.id;
}

export function createPreviewRun(pipeline: Pipeline): PreviewRun {
  const issues = validateGraph(pipeline.graph);
  if (issues.length) throw new Error(issues[0].message);
  topologicalNodeIds(pipeline.graph);
  const graph = structuredClone(pipeline.graph);
  graph.nodes.forEach((node) => {
    node.data.status = "idle";
  });
  return {
    id: crypto.randomUUID(),
    pipelineId: pipeline.id,
    pipelineName: pipeline.name,
    startedAt: new Date().toISOString(),
    durationMs: 0,
    status: "Running",
    graph,
    nodes: [],
    results: [],
    errors: [],
  };
}

export function completePreviewNode(
  run: PreviewRun,
  node: WorkbenchNode,
  scenario: Scenario,
): NodeResult {
  if (!run.graph.nodes.some((item) => item.id === node.id))
    throw new Error("The component does not belong to this run.");
  if (scenario === "error" && node.id === failureNodeId(run)) {
    return {
      nodeId: node.id,
      label: node.data.label,
      status: "error",
      durationMs: 240,
      summary: "Simulated service error. No request was sent.",
      output: {
        preview: true,
        error_code: "PREVIEW_SERVICE_UNAVAILABLE",
        retryable: true,
        message:
          "This is the configured error scenario. Switch to the success scenario to continue the preview.",
      },
    };
  }
  const indexed = previewDocuments.filter(
    (document) => document.status === "Indexed",
  );
  const summaries: Record<
    WorkbenchNode["data"]["kind"],
    { durationMs: number; summary: string; output: Record<string, unknown> }
  > = {
    files: {
      durationMs: 8,
      summary: `${indexed.length} sample documents selected`,
      output: { files: indexed.map((document) => document.name) },
    },
    parser: {
      durationMs: 326,
      summary: "Text, headings and page references extracted",
      output: {
        documents: indexed.length,
        pages: indexed.reduce((total, document) => total + document.pages, 0),
        parser: "Fixture extraction",
        warnings: ["Sample output; no documents were parsed."],
      },
    },
    chunker: {
      durationMs: 42,
      summary: "100 sample passages prepared",
      output: {
        chunks: 100,
        chunk_size: node.data.parameters.size,
        overlap: node.data.parameters.overlap,
      },
    },
    "document-embedder": {
      durationMs: 184,
      summary: "Sample vectors prepared for 100 passages",
      output: {
        documents: 100,
        dimensions: 2560,
        model: "Qwen3-Embedding-4B",
        inference_called: false,
      },
    },
    writer: {
      durationMs: 28,
      summary: "Preview complete. No documents were written.",
      output: {
        sample_documents: 100,
        documents_written: 0,
        knowledge_base: node.data.parameters.collection,
      },
    },
    query: {
      durationMs: 3,
      summary: "Sample search input received",
      output: { query: node.data.parameters.query },
    },
    "text-embedder": {
      durationMs: 48,
      summary: "Sample query embedding prepared",
      output: {
        dimensions: 2560,
        model: "Qwen3-Embedding-4B",
        inference_called: false,
      },
    },
    bm25: {
      durationMs: 18,
      summary: "BM25 branch returned sample candidates",
      output: {
        returned: Math.min(
          Number(node.data.parameters.topK),
          previewResults.length,
        ),
        ranking: "BM25 preview",
        search_executed: false,
      },
    },
    vector: {
      durationMs: 24,
      summary: "Semantic branch returned sample candidates",
      output: {
        returned: Math.min(
          Number(node.data.parameters.topK),
          previewResults.length,
        ),
        metric: "cosine",
        search_executed: false,
      },
    },
    joiner: {
      durationMs: 7,
      summary: "Sample candidate ranks combined",
      output: {
        method: "reciprocal_rank_fusion",
        returned: Math.min(
          Number(node.data.parameters.topK),
          previewResults.length,
        ),
      },
    },
    results: {
      durationMs: 2,
      summary: "Sample passages ready to inspect",
      output: {
        returned: Math.min(
          Number(node.data.parameters.limit),
          previewResults.length,
        ),
        scores: "Illustrative scores, not measured retrieval quality",
      },
    },
  };
  const result = summaries[node.data.kind];
  return {
    nodeId: node.id,
    label: node.data.label,
    status: "success",
    ...result,
    output: { preview: true, ...result.output },
  };
}

export function finishPreviewRun(
  run: PreviewRun,
  scenario: Scenario,
  resultLimit: number,
): PreviewRun {
  if (run.status === "Cancelled") return run;
  const errors = run.nodes
    .filter((node) => node.status === "error")
    .map((node) => `${node.label}: ${node.summary}`);
  const completedIds = new Set(
    run.nodes
      .filter((node) => node.status === "success")
      .map((node) => node.nodeId),
  );
  const allCompleted = run.graph.nodes.every((node) =>
    completedIds.has(node.id),
  );
  const failed = errors.length > 0 || scenario === "error" || !allCompleted;
  if (failed && !errors.length)
    errors.push(
      allCompleted
        ? "The configured preview failure scenario was selected."
        : "The preview stopped before all components completed.",
    );
  const resultNode = run.graph.nodes.find(
    (node) => node.data.kind === "results",
  );
  const retrievalRun = run.graph.nodes.some(
    (node) => node.data.kind === "bm25" || node.data.kind === "vector",
  );
  const requestedLimit = Number.isFinite(resultLimit)
    ? Math.max(1, Math.floor(resultLimit))
    : 5;
  const nodeLimit = resultNode
    ? Math.max(1, Number(resultNode.data.parameters.limit) || 5)
    : requestedLimit;
  return {
    ...run,
    status: failed ? "Failed" : "Completed",
    durationMs: run.nodes.reduce((total, node) => total + node.durationMs, 0),
    errors,
    results:
      !failed && retrievalRun && resultNode
        ? previewResults
            .slice(0, Math.min(requestedLimit, nodeLimit))
            .map((result) => ({ ...result }))
        : [],
  };
}
