import { createPipeline } from "./graph";
import type {
  Pipeline,
  PreviewDocument,
  PreviewRun,
  WorkbenchSettings,
} from "./types";

export const previewDocuments: PreviewDocument[] = [
  {
    id: "doc-platform",
    name: "RAG platform architecture.pdf",
    type: "PDF",
    size: "2.4 MB",
    status: "Indexed",
    chunks: 48,
    addedAt: "2026-11-19T10:20:00Z",
    pages: 24,
    parser: "Docling",
    sections: [
      "Overview",
      "Indexing lifecycle",
      "Version publication",
      "Retrieval and ranking",
    ],
    content:
      "A document update is prepared as a new source version. Parsing, chunking and embedding finish before the active version changes. Publish only after validating the complete chunk set. If preparation fails, continue serving the previous version.",
    chunkPreviews: [
      {
        id: "platform-001",
        page: 9,
        content:
          "A document update is prepared as a new source version. Parsing, chunking and embedding finish before the active version changes.",
      },
      {
        id: "platform-002",
        page: 10,
        content:
          "Publish only after validating the complete chunk set. If preparation fails, continue serving the previous version.",
      },
    ],
    warnings: [],
  },
  {
    id: "doc-operations",
    name: "Knowledge base operations.md",
    type: "Markdown",
    size: "42 KB",
    status: "Indexed",
    chunks: 16,
    addedAt: "2026-11-19T14:35:00Z",
    pages: 1,
    parser: "Markdown converter",
    sections: ["Document updates", "Recovery", "Deletion", "Troubleshooting"],
    content:
      "Unchanged content and compatible processing profiles reuse existing embeddings. A changed file creates a new version. Keep the old version readable until the new passages are validated; a recovery job completes interrupted cleanup.",
    chunkPreviews: [
      {
        id: "operations-001",
        page: 1,
        content:
          "Unchanged content and compatible processing profiles reuse existing embeddings. A changed file creates a new version.",
      },
      {
        id: "operations-002",
        page: 1,
        content:
          "Keep the old version readable until the new passages are validated; a recovery job completes interrupted cleanup.",
      },
    ],
    warnings: [],
  },
  {
    id: "doc-retrieval",
    name: "Retrieval quality playbook.docx",
    type: "DOCX",
    size: "186 KB",
    status: "Indexed",
    chunks: 22,
    addedAt: "2026-11-20T08:10:00Z",
    pages: 12,
    parser: "DOCX converter",
    sections: [
      "Keyword matching",
      "Semantic matching",
      "Rank fusion",
      "Evaluation",
    ],
    content:
      "Keyword retrieval finds precise identifiers. Semantic retrieval captures related meaning and paraphrases. Reciprocal rank fusion combines candidate ranks without adding incomparable raw scores. Always keep source and page information with each passage.",
    chunkPreviews: [
      {
        id: "retrieval-001",
        page: 4,
        content:
          "Keyword retrieval finds precise identifiers. Semantic retrieval captures related meaning and paraphrases.",
      },
      {
        id: "retrieval-002",
        page: 5,
        content:
          "Reciprocal rank fusion combines candidate ranks without adding incomparable raw scores. Always keep source and page information with each passage.",
      },
    ],
    warnings: [],
  },
  {
    id: "doc-policy",
    name: "Workspace data policy.pdf",
    type: "PDF",
    size: "724 KB",
    status: "Indexed",
    chunks: 14,
    addedAt: "2026-11-20T09:05:00Z",
    pages: 8,
    parser: "Docling",
    sections: ["Workspace boundaries", "Source access", "Data lifecycle"],
    content:
      "Every document and passage belongs to a workspace. Resolve workspace restrictions on the server and verify source ownership on every read, update and delete. A client-provided filter is not an authorization boundary.",
    chunkPreviews: [
      {
        id: "policy-001",
        page: 2,
        content:
          "Every document and passage belongs to a workspace. Resolve workspace restrictions on the server and verify source ownership on every read, update and delete.",
      },
      {
        id: "policy-002",
        page: 3,
        content: "A client-provided filter is not an authorization boundary.",
      },
    ],
    warnings: ["One table was exported as plain text."],
  },
  {
    id: "doc-scanned",
    name: "Scanned meeting notes.pdf",
    type: "PDF",
    size: "3.1 MB",
    status: "Failed",
    chunks: 0,
    addedAt: "2026-11-20T09:40:00Z",
    pages: 6,
    parser: "PDF converter",
    sections: [],
    content: "",
    warnings: [
      "No text layer found. OCR is required before this document can be indexed.",
    ],
  },
];

export const initialPipelines: Pipeline[] = [
  createPipeline("retrieval"),
  createPipeline("indexing"),
];

export const initialRuns: PreviewRun[] = [];

export const defaultSettings: WorkbenchSettings = {
  workspaceName: "Personal workspace",
  defaultTemplate: "retrieval",
  showGrid: true,
  reducedMotion: false,
  resultLimit: 5,
  previewScenario: "success",
  previewDelay: 480,
};
