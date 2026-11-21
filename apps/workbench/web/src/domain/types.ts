import type { Edge, Node, Viewport } from "@xyflow/react";

export type NodeKind =
  | "files"
  | "parser"
  | "chunker"
  | "document-embedder"
  | "writer"
  | "query"
  | "text-embedder"
  | "bm25"
  | "keyword-search"
  | "vector"
  | "joiner"
  | "results";
export type ValueKind = "files" | "documents" | "text" | "embedding";
export type NodeStatus = "idle" | "running" | "success" | "error";
export type NodeData = {
  kind: NodeKind;
  label: string;
  parameters: Record<string, string | number>;
  status?: NodeStatus;
};
export type WorkbenchNode = Node<NodeData, "workbench">;
export type Graph = {
  nodes: WorkbenchNode[];
  edges: Edge[];
  viewport?: Viewport;
};
export type TemplateId = "blank" | "indexing" | "retrieval" | "keyword";
export type Pipeline = {
  id: string;
  name: string;
  description: string;
  templateId: TemplateId;
  graph: Graph;
  updatedAt: string;
};
export type Port = {
  id: string;
  label: string;
  valueKind: ValueKind;
  required?: boolean;
  multiple?: boolean;
};
export type Parameter = {
  key: string;
  label: string;
  type: "text" | "number" | "textarea" | "select";
  required?: boolean;
  options?: string[];
  min?: number;
};
export type NodeDefinition = {
  kind: NodeKind;
  label: string;
  component: string;
  group: "Inputs" | "Processing" | "Retrieval" | "Outputs";
  description: string;
  inputs: Port[];
  outputs: Port[];
  parameters: Parameter[];
  defaults: Record<string, string | number>;
};
export type GraphIssue = {
  nodeId?: string;
  edgeId?: string;
  code?: string;
  field?: string;
  message: string;
};
export type PreviewDocument = {
  id: string;
  name: string;
  type: string;
  size: string;
  status: "Indexed" | "Processing" | "Failed";
  chunks: number;
  addedAt: string;
  pages: number;
  parser: string;
  sections: string[];
  content: string;
  warnings: string[];
  chunkPreviews?: { id: string; page: number; content: string }[];
};
export type RetrievalResult = {
  id: string;
  title: string;
  page: number;
  score: number;
  content: string;
  sourceId: string;
};
export type NodeResult = {
  nodeId: string;
  label: string;
  status: "success" | "error";
  durationMs: number;
  summary: string;
  output: Record<string, unknown>;
};
export type PreviewRun = {
  id: string;
  pipelineId: string;
  pipelineName: string;
  startedAt: string;
  durationMs: number;
  status: "Running" | "Completed" | "Failed" | "Cancelled";
  graph: Graph;
  nodes: NodeResult[];
  results: RetrievalResult[];
  errors: string[];
};
export type ExecutionMode = "preview" | "live";

export type WorkbenchSettings = {
  workspaceName: string;
  defaultTemplate: TemplateId;
  showGrid: boolean;
  reducedMotion: boolean;
  resultLimit: number;
  previewScenario: "success" | "error";
  previewDelay: number;
};
