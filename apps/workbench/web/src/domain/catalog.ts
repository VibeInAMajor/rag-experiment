import type { NodeDefinition, NodeKind, WorkbenchNode } from "./types";

export const catalog: NodeDefinition[] = [
  {
    kind: "files",
    label: "Document source",
    component: "Workspace files",
    group: "Inputs",
    description: "Choose the documents that enter your indexing pipeline.",
    inputs: [],
    outputs: [{ id: "files", label: "Files", valueKind: "files" }],
    parameters: [
      { key: "source", label: "Source", type: "text", required: true },
    ],
    defaults: { source: "Workspace documents" },
  },
  {
    kind: "parser",
    label: "Parse documents",
    component: "DoclingConverter",
    group: "Processing",
    description:
      "Extract readable text while keeping headings, tables and page references.",
    inputs: [
      { id: "files", label: "Files", valueKind: "files", required: true },
    ],
    outputs: [{ id: "documents", label: "Documents", valueKind: "documents" }],
    parameters: [
      {
        key: "format",
        label: "Output format",
        type: "select",
        options: ["Markdown", "Structured chunks"],
      },
    ],
    defaults: { format: "Markdown" },
  },
  {
    kind: "chunker",
    label: "Split into chunks",
    component: "DocumentSplitter",
    group: "Processing",
    description:
      "Create passages with enough shared context for useful retrieval.",
    inputs: [
      {
        id: "documents",
        label: "Documents",
        valueKind: "documents",
        required: true,
      },
    ],
    outputs: [{ id: "documents", label: "Chunks", valueKind: "documents" }],
    parameters: [
      {
        key: "size",
        label: "Chunk size",
        type: "number",
        min: 1,
        required: true,
      },
      {
        key: "overlap",
        label: "Overlap",
        type: "number",
        min: 0,
        required: true,
      },
    ],
    defaults: { size: 500, overlap: 50 },
  },
  {
    kind: "document-embedder",
    label: "Embed documents",
    component: "OpenAIDocumentEmbedder",
    group: "Processing",
    description:
      "Represent each passage as a vector using the local embedding profile.",
    inputs: [
      {
        id: "documents",
        label: "Chunks",
        valueKind: "documents",
        required: true,
      },
    ],
    outputs: [
      { id: "documents", label: "Embedded chunks", valueKind: "documents" },
    ],
    parameters: [
      {
        key: "model",
        label: "Embedding profile",
        type: "select",
        options: ["Qwen3-Embedding-4B"],
      },
      {
        key: "batchSize",
        label: "Batch size",
        type: "number",
        min: 1,
        required: true,
      },
    ],
    defaults: { model: "Qwen3-Embedding-4B", batchSize: 16 },
  },
  {
    kind: "writer",
    label: "Write to knowledge base",
    component: "DocumentWriter",
    group: "Outputs",
    description: "Publish processed passages to the selected knowledge base.",
    inputs: [
      {
        id: "documents",
        label: "Embedded chunks",
        valueKind: "documents",
        required: true,
      },
    ],
    outputs: [],
    parameters: [
      {
        key: "collection",
        label: "Knowledge base",
        type: "text",
        required: true,
      },
    ],
    defaults: { collection: "Product knowledge" },
  },
  {
    kind: "query",
    label: "Search query",
    component: "Pipeline input",
    group: "Inputs",
    description: "Start a search with a question or a precise phrase.",
    inputs: [],
    outputs: [{ id: "query", label: "Query", valueKind: "text" }],
    parameters: [
      { key: "query", label: "Question", type: "textarea", required: true },
    ],
    defaults: { query: "How are document updates published safely?" },
  },
  {
    kind: "text-embedder",
    label: "Embed query",
    component: "OpenAITextEmbedder",
    group: "Processing",
    description:
      "Turn the question into a vector using the same profile as your documents.",
    inputs: [{ id: "text", label: "Query", valueKind: "text", required: true }],
    outputs: [{ id: "embedding", label: "Embedding", valueKind: "embedding" }],
    parameters: [
      {
        key: "model",
        label: "Embedding profile",
        type: "select",
        options: ["Qwen3-Embedding-4B"],
      },
    ],
    defaults: { model: "Qwen3-Embedding-4B" },
  },
  {
    kind: "bm25",
    label: "BM25 search",
    component: "InMemoryBM25Retriever",
    group: "Retrieval",
    description: "Find exact terms and identifiers with BM25 keyword ranking.",
    inputs: [
      { id: "query", label: "Query", valueKind: "text", required: true },
    ],
    outputs: [{ id: "documents", label: "Matches", valueKind: "documents" }],
    parameters: [
      {
        key: "collection",
        label: "Knowledge base",
        type: "text",
        required: true,
      },
      {
        key: "topK",
        label: "Candidates",
        type: "number",
        min: 1,
        required: true,
      },
    ],
    defaults: { collection: "Product knowledge", topK: 20 },
  },
  {
    kind: "vector",
    label: "Semantic search",
    component: "PgvectorEmbeddingRetriever",
    group: "Retrieval",
    description:
      "Find passages with a similar meaning, even when the words differ.",
    inputs: [
      {
        id: "embedding",
        label: "Embedding",
        valueKind: "embedding",
        required: true,
      },
    ],
    outputs: [{ id: "documents", label: "Matches", valueKind: "documents" }],
    parameters: [
      {
        key: "collection",
        label: "Knowledge base",
        type: "text",
        required: true,
      },
      {
        key: "topK",
        label: "Candidates",
        type: "number",
        min: 1,
        required: true,
      },
    ],
    defaults: { collection: "Product knowledge", topK: 20 },
  },
  {
    kind: "joiner",
    label: "Combine results",
    component: "DocumentJoiner",
    group: "Processing",
    description: "Merge ranked candidates with reciprocal rank fusion.",
    inputs: [
      {
        id: "documents",
        label: "Ranked documents",
        valueKind: "documents",
        required: true,
        multiple: true,
      },
    ],
    outputs: [
      { id: "documents", label: "Combined matches", valueKind: "documents" },
    ],
    parameters: [
      {
        key: "topK",
        label: "Keep candidates",
        type: "number",
        min: 1,
        required: true,
      },
    ],
    defaults: { topK: 8 },
  },
  {
    kind: "results",
    label: "Search results",
    component: "Pipeline output",
    group: "Outputs",
    description:
      "Inspect the relevant passages together with their sources and page references.",
    inputs: [
      {
        id: "documents",
        label: "Documents",
        valueKind: "documents",
        required: true,
      },
    ],
    outputs: [],
    parameters: [
      {
        key: "limit",
        label: "Results to show",
        type: "number",
        min: 1,
        required: true,
      },
    ],
    defaults: { limit: 5 },
  },
];

export function getDefinition(kind: NodeKind): NodeDefinition {
  const definition = catalog.find((item) => item.kind === kind);
  if (!definition) throw new Error(`Unknown component: ${kind}`);
  return definition;
}

export function createNode(
  kind: NodeKind,
  position: { x: number; y: number },
): WorkbenchNode {
  const definition = getDefinition(kind);
  return {
    id: crypto.randomUUID(),
    type: "workbench",
    position: { ...position },
    data: {
      kind,
      label: definition.label,
      parameters: { ...definition.defaults },
      status: "idle",
    },
  };
}
