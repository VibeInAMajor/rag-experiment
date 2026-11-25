// @vitest-environment jsdom
import "../test/dialog";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type {
  BackendCapabilities,
  DocumentDetail,
  JsonValue,
} from "../api/contracts";
import { emptyLiveDocuments } from "../domain/liveDocuments";
import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import { DocumentsView } from "./DocumentsView";
import { DocumentChunks, DocumentsError } from "./LiveDocumentDetails";
import { DocumentUploadDialog } from "./DocumentUploadDialog";

afterEach(cleanup);

const markdownDetail: DocumentDetail = {
  contract_revision: "rag-api-v1.0",
  request_id: "request",
  trace_id: "trace",
  workspace_id: "development",
  corpus_revision: "corpus",
  source_id: "source",
  title: "notes.md",
  media_type: "text/markdown",
  status: "ready",
  active_version_id: "version",
  chunk_count: 1,
  updated_at: "2026-11-25T12:00:00Z",
  warnings: [],
  original_content_available: false,
};

it("expands folders with icons and preserves the parent error while filtering Ready descendants", () => {
  const model = controller();
  const common = {
    media_type: "text/plain",
    active_version_id: "version-1",
    chunk_count: 1,
    updated_at: "2026-11-25T12:00:00Z",
  };
  model.documents = [
    {
      ...common,
      source_id: "ready",
      title: "ready.txt",
      status: "ready",
      upload_location: {
        group_id: "selection",
        path: "Research/ready.txt",
        folder_totals: [2],
      },
    },
    {
      ...common,
      source_id: "error",
      title: "broken.txt",
      status: "error",
      upload_location: {
        group_id: "selection",
        path: "Research/sub/broken.txt",
        folder_totals: [2, 1],
      },
    },
  ];
  const { container } = render(
    <DocumentsView
      mode="live"
      controller={model}
      capabilities={capabilities}
    />,
  );
  expect(screen.queryByText("ready.txt")).toBeNull();
  expect(screen.getByText("1 / 2 files ready")).toBeTruthy();
  expect(container.querySelector(".documents-folder-icon svg")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Expand folder Research" }),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "Expand folder Research/sub",
    }),
  );
  expect(screen.getByText("broken.txt")).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Document status" }), {
    target: { value: "ready" },
  });
  expect(screen.queryByText("broken.txt")).toBeNull();
  expect(screen.getByText("ready.txt")).toBeTruthy();
  expect(screen.getByText("Error")).toBeTruthy();
});

function controller(): LiveDocumentsModel {
  return {
    ...emptyLiveDocuments(),
    status: "ready",
    uploadQueue: [],
    uploadQueueBusy: false,
    chooseFiles: vi.fn(),
    startUploads: vi.fn(),
    stopUploads: vi.fn(),
    retryQueuedUpload: vi.fn(),
    refresh: vi.fn(async () => {}),
    loadMore: vi.fn(async () => {}),
    selectSource: vi.fn(),
    refreshSelected: vi.fn(async () => {}),
    loadMoreChunks: vi.fn(async () => {}),
    inspectJob: vi.fn(async () => {}),
    chooseFile: vi.fn(),
    submitUpload: vi.fn(async () => {}),
    retryUpload: vi.fn(async () => {}),
    stopUpload: vi.fn(),
    clearUpload: vi.fn(),
  };
}
const capabilities: BackendCapabilities = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-1",
  trace_id: "trace-1",
  backend_revision: "backend-r1",
  deployment_mode: "single_workspace_dev",
  service_state: "running",
  profiles: [],
  features: {
    documents: true,
    search: true,
    document_details: true,
    upload: true,
    jobs: true,
  },
  dependencies: { database: { status: "ready" } },
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
};

it("labels loaded-only filtering and never substitutes Preview for an empty live corpus", () => {
  const model = controller();
  model.status = "empty";
  render(
    <DocumentsView
      mode="live"
      controller={model}
      capabilities={capabilities}
    />,
  );
  expect(
    screen.getByRole("searchbox", { name: "Filter loaded documents" }),
  ).toBeTruthy();
  expect(
    screen.getByText("No persisted sources were returned for this workspace."),
  ).toBeTruthy();
  expect(screen.getByText("0 loaded")).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Load more documents" }),
  ).toBeNull();
});

it("keeps malicious content inert and labels Markdown fragments with source lines", () => {
  const model = controller();
  model.detail = markdownDetail;
  const malicious = '<img src="https://attacker.invalid" onerror="alert(1)">';
  model.chunks = [
    {
      chunk_id: "chunk-1",
      order: 0,
      content: malicious,
      content_hash: "a".repeat(64),
      page: null,
      section_path: ["Example"],
      metadata: {
        start_line: 4,
        end_line: 9,
        qualified_name: "Example.run",
        table_row_start: 0,
        table_row_end: 3,
        table_row_index_basis: "zero-based-half-open",
      },
    },
  ];
  const { container } = render(
    <DocumentChunks model={model} compact={false} />,
  );
  expect(screen.getByText(malicious)).toBeTruthy();
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("Фрагмент 1 · Строки 4–9")).toBeTruthy();
  expect(screen.queryByText(/Page Unavailable/)).toBeNull();
  expect(container.textContent).toContain('"start_line": 4');
  expect(container.textContent).toContain('"table_row_start": 0');
});

it("preserves the actual PDF page number without changing it to the fragment ordinal", () => {
  const model = controller();
  model.detail = {
    ...markdownDetail,
    media_type: "application/pdf",
    title: "notes.pdf",
  };
  model.chunks = [
    {
      chunk_id: "pdf",
      order: 4,
      content: "PDF text",
      content_hash: "a".repeat(64),
      page: 7,
      section_path: [],
      metadata: {},
    },
  ];
  render(<DocumentChunks model={model} compact />);
  expect(screen.getByText("Order 4 · Page 7")).toBeTruthy();
});

it.each<Record<string, JsonValue>>([
  {},
  { start_line: "4", end_line: 9 },
  { start_line: 4, end_line: 3 },
])("does not invent Markdown lines from invalid metadata %j", (metadata) => {
  const model = controller();
  model.detail = markdownDetail;
  model.chunks = [
    {
      chunk_id: "md",
      order: 50,
      content: "Markdown text",
      content_hash: "a".repeat(64),
      page: null,
      section_path: [],
      metadata,
    },
  ];
  render(<DocumentChunks model={model} compact />);
  expect(screen.getByText("Фрагмент 51")).toBeTruthy();
  expect(screen.queryByText(/Page/)).toBeNull();
});

it("preserves server correlation and known job identifiers", () => {
  render(
    <DocumentsError
      error={{
        code: "VERSION_CONFLICT",
        message: "Review the current source version.",
        retryable: false,
        requestId: "request-1",
        traceId: "trace-1",
        jobId: "job-1",
      }}
    />,
  );
  expect(screen.getByRole("alert").textContent).toContain(
    "VERSION_CONFLICT · Request request-1 · Trace trace-1 · Job job-1",
  );
});

it("offers multiple files and recursive folders, with explicit queue confirmation", () => {
  const model = controller();
  const file = new File(["hello"], "hello.py", { type: "text/x-python" });
  model.uploadQueue = [
    {
      id: "operation-1",
      path: "folder/sub/hello.py",
      phase: "ready",
      file,
    },
  ];
  const close = vi.fn();
  render(
    <DocumentUploadDialog
      model={model}
      capabilities={capabilities}
      replace={false}
      uploadAllowed
      onClose={close}
    />,
  );
  expect(screen.getByRole("dialog", { name: "Upload document" })).toBeTruthy();
  const input = screen.getByLabelText("Choose files");
  expect(input.getAttribute("accept")).toBe(".txt,.md,.markdown,.py");
  expect(input.hasAttribute("multiple")).toBe(true);
  expect(document.activeElement).toBe(input);
  const modal = screen.getByRole("dialog", { name: "Upload document" });
  expect(modal.getAttribute("style")).toContain("1000px");
  fireEvent.click(
    screen.getByRole("button", { name: "Use compact upload window" }),
  );
  expect(modal.getAttribute("style")).toContain("560px");
  fireEvent.click(
    screen.getByRole("button", { name: "Use wide upload window" }),
  );
  expect(modal.getAttribute("style")).toContain("1000px");
  const folder = screen.getByLabelText("Choose folder (including subfolders)");
  expect(folder.hasAttribute("webkitdirectory")).toBe(true);
  fireEvent.change(folder, { target: { files: [file] } });
  expect(model.chooseFiles).toHaveBeenCalledWith([file]);
  expect(model.startUploads).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Upload 1 file" }));
  expect(model.startUploads).toHaveBeenCalledOnce();
});

it("exposes same-operation retry and disables writes after capability loss", () => {
  const model = controller();
  model.upload = {
    phase: "unknown",
    file: new File(["hello"], "hello.txt"),
    idempotencyKey: "same-key",
    response: null,
  };
  const { rerender } = render(
    <DocumentUploadDialog
      model={model}
      capabilities={capabilities}
      replace
      uploadAllowed
      onClose={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry same operation" }));
  expect(model.retryUpload).toHaveBeenCalledOnce();
  rerender(
    <DocumentUploadDialog
      model={model}
      capabilities={capabilities}
      replace
      uploadAllowed={false}
      onClose={vi.fn()}
    />,
  );
  expect(
    screen
      .getByRole("button", { name: "Retry same operation" })
      .hasAttribute("disabled"),
  ).toBe(true);
  expect(screen.getByLabelText("Source file").hasAttribute("disabled")).toBe(
    true,
  );
});

it("passes replacement intent with the selected File and closes the native modal before restoring focus", () => {
  const model = controller();
  const onClose = vi.fn(() => {
    expect(
      screen.getByRole("dialog", { hidden: true }).hasAttribute("open"),
    ).toBe(false);
  });
  render(
    <DocumentUploadDialog
      model={model}
      capabilities={capabilities}
      replace
      uploadAllowed
      onClose={onClose}
    />,
  );
  const file = new File(["replacement"], "replacement.py", {
    type: "text/x-python",
  });
  fireEvent.change(screen.getByLabelText("Source file"), {
    target: { files: [file] },
  });
  expect(model.chooseFile).toHaveBeenCalledWith(file, true);
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledOnce();
  expect(model.submitUpload).not.toHaveBeenCalled();
});

it("keeps the asynchronous queue running when the modal is dismissed", () => {
  const model = controller();
  model.upload = {
    phase: "submitting",
    file: new File(["pending"], "pending.txt"),
    response: null,
  };
  const onClose = vi.fn();
  model.uploadQueueBusy = true;
  model.uploadQueue = [
    {
      id: "pending",
      path: "pending.txt",
      file: model.upload.file,
      phase: "submitting",
    },
  ];
  render(
    <DocumentUploadDialog
      model={model}
      capabilities={capabilities}
      replace={false}
      uploadAllowed
      onClose={onClose}
    />,
  );
  expect(screen.getByText("Uploading and processing…")).toBeTruthy();
  const modal = screen.getByRole("dialog", { name: "Upload document" });
  fireEvent(modal, new Event("cancel", { cancelable: true }));
  expect(model.stopUpload).not.toHaveBeenCalled();
  expect(model.stopUploads).not.toHaveBeenCalled();
  expect(onClose).toHaveBeenCalledOnce();
  expect(model.clearUpload).not.toHaveBeenCalled();
});
