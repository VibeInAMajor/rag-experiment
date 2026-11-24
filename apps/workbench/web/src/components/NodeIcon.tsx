import {
  Database,
  FileInput,
  FileText,
  GitMerge,
  Layers,
  ScanLine,
  Scissors,
  Search,
  TextSearch,
  VectorSquare,
} from "lucide-react";
import type { NodeKind } from "../domain/types";

const icons = {
  files: FileInput,
  parser: FileText,
  chunker: Scissors,
  "document-embedder": ScanLine,
  writer: Database,
  query: Search,
  "text-embedder": VectorSquare,
  bm25: TextSearch,
  "keyword-search": TextSearch,
  "query-embedding": TextSearch,
  "dense-search": TextSearch,
  vector: ScanLine,
  joiner: GitMerge,
  results: Layers,
};

export function NodeIcon({
  kind,
  size = 16,
}: {
  kind: NodeKind;
  size?: number;
}) {
  const Icon = icons[kind];
  return <Icon size={size} strokeWidth={1.7} aria-hidden="true" />;
}
