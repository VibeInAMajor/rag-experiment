// @vitest-environment jsdom
import "../test/dialog";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { BackendCapabilities } from "../api/contracts";
import { emptyLiveDocuments } from "../domain/liveDocuments";
import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import { DocumentsView } from "./DocumentsView";
import { DocumentChunks, DocumentsError } from "./LiveDocumentDetails";
import { DocumentUploadDialog } from "./DocumentUploadDialog";

afterEach(cleanup);

function controller(): LiveDocumentsModel {
  return {
    ...emptyLiveDocuments(),
    status: "ready",
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

it("keeps malicious chunk content inert and preserves missing page provenance", () => {
  const model = controller();
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
  expect(screen.getByText("Order 0 · Page Unavailable")).toBeTruthy();
  expect(container.textContent).toContain('"start_line": 4');
  expect(container.textContent).toContain('"table_row_start": 0');
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

it("opens an accessible single-file dialog with conditional PDF and explicit confirmation", () => {
  const model = controller();
  model.upload = {
    phase: "ready",
    file: new File(["hello"], "hello.py", { type: "text/x-python" }),
    response: null,
  };
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
  const input = screen.getByLabelText("Source file");
  expect(input.getAttribute("accept")).toBe(".txt,.md,.markdown,.py");
  expect(input.hasAttribute("multiple")).toBe(false);
  expect(document.activeElement).toBe(input);
  fireEvent.click(screen.getByRole("button", { name: "Confirm upload" }));
  expect(model.submitUpload).toHaveBeenCalledOnce();
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
      replace={false}
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
      replace={false}
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

it("stops a pending POST locally on modal cancellation without claiming rollback", () => {
  const model = controller();
  model.upload = {
    phase: "submitting",
    file: new File(["pending"], "pending.txt"),
    response: null,
  };
  const onClose = vi.fn();
  render(
    <DocumentUploadDialog
      model={model}
      capabilities={capabilities}
      replace={false}
      uploadAllowed
      onClose={onClose}
    />,
  );
  expect(
    screen.getByText("Publishing synchronously… Waiting for the server."),
  ).toBeTruthy();
  const modal = screen.getByRole("dialog", { name: "Upload document" });
  fireEvent(modal, new Event("cancel", { cancelable: true }));
  expect(model.stopUpload).toHaveBeenCalledOnce();
  expect(onClose).toHaveBeenCalledOnce();
  expect(model.clearUpload).not.toHaveBeenCalled();
});
