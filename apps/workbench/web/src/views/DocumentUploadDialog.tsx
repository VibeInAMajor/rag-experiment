import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, X } from "lucide-react";
import type { BackendCapabilities } from "../api/contracts";
import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import { DocumentsError } from "./LiveDocumentDetails";
import { DocumentUploadSelection } from "./DocumentUploadSelection";

export function DocumentUploadDialog({
  model,
  capabilities,
  replace,
  uploadAllowed,
  onClose,
}: {
  model: LiveDocumentsModel;
  capabilities: BackendCapabilities | null;
  replace: boolean;
  uploadAllowed: boolean;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [compact, setCompact] = useState(false);
  const { upload } = model;
  const pending = upload.phase === "submitting";
  const pdf = capabilities?.pdf_ingestion;
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    element?.querySelector("input")?.focus();
    return () => element?.close();
  }, []);
  const close = () => {
    dialog.current?.close();
    onClose();
  };
  return (
    <dialog
      ref={dialog}
      className="view-dialog documents-upload-dialog"
      style={{ width: `min(${compact ? 560 : 1000}px, calc(100vw - 32px))` }}
      aria-labelledby="upload-dialog-title"
      aria-describedby="upload-dialog-description"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <header className="detail-heading">
        <h2 id="upload-dialog-title">
          {replace ? "Replace source file" : "Upload document"}
        </h2>
        <div className="view-actions">
          <button
            type="button"
            className="icon-button"
            aria-label={
              compact ? "Use wide upload window" : "Use compact upload window"
            }
            title={
              compact ? "Use wide upload window" : "Use compact upload window"
            }
            onClick={() => setCompact((value) => !value)}
          >
            {compact ? <Maximize2 size={17} /> : <Minimize2 size={17} />}
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Close upload dialog"
            onClick={close}
          >
            <X size={18} />
          </button>
        </div>
      </header>
      <p id="upload-dialog-description" className="view-dialog-copy">
        {replace
          ? "Replace one file."
          : "Choose files or a folder, including all subfolders."}{" "}
        TXT, Markdown and Python: up to 1 MiB each.{" "}
        {pdf?.available
          ? `PDF: up to ${pdf.max_bytes / 1024 / 1024} MiB and ${pdf.max_pages} pages. Text layer: ${pdf.text_layer ? "available" : "unavailable"}; page provenance: ${pdf.page_provenance ? "available" : "unavailable"}; table rows: ${pdf.table_rows ? "available" : "unavailable"}. No OCR, visual understanding or original-file download.`
          : "PDF upload is unavailable in this runtime."}
      </p>
      {replace && (
        <p className="detail-notice">
          Replacement requires the source’s current active version. A version
          conflict must be reviewed before a new submission.
        </p>
      )}
      {!replace ? (
        <>
          <DocumentUploadSelection
            model={model}
            pdfAvailable={pdf?.available === true}
            foldersPersisted={capabilities?.features.upload_folders === true}
            uploadAllowed={uploadAllowed}
          />
          <div className="view-dialog-actions">
            <button type="button" className="button" onClick={close}>
              Close
            </button>
          </div>
        </>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (uploadAllowed && upload.phase === "ready")
              void model.submitUpload();
          }}
        >
          <label
            className="view-field documents-upload-field"
            htmlFor="document-file"
          >
            Source file
            <input
              id="document-file"
              name="document-file"
              type="file"
              accept={`.txt,.md,.markdown,.py${pdf?.available ? ",.pdf" : ""}`}
              disabled={pending || !uploadAllowed}
              aria-describedby="upload-file-help"
              onChange={(event) =>
                model.chooseFile(event.target.files?.[0] ?? null, replace)
              }
            />
          </label>
          <p id="upload-file-help" className="detail-caption">
            The server validates file type, bytes and parser readiness. Python
            source is parsed, never executed.
          </p>
          {upload.file && (
            <p className="documents-upload-filename">
              Selected: {upload.file.name} ·{" "}
              {upload.file.size.toLocaleString("en-GB")} bytes
            </p>
          )}
          {!uploadAllowed && (
            <p className="detail-notice" role="status">
              Upload capability is unavailable. This operation is read only.
            </p>
          )}
          <DocumentsError error={upload.error} />
          <div role="status" aria-live="polite">
            {pending && (
              <p>Uploading and processing… You can close this dialog.</p>
            )}
            {upload.phase === "unknown" && (
              <p className="detail-notice">
                Server outcome is unconfirmed. Retry the same operation with its
                original file and idempotency key. Choosing a different file
                starts a new operation and cannot reverse any previous
                publication.
              </p>
            )}
            {upload.phase === "conflict" && (
              <p className="detail-notice">
                Conflict. Refresh document details, review the current version,
                then choose the file again to confirm a new operation.
              </p>
            )}
            {upload.response && (
              <p>
                Confirmed {upload.response.outcome}
                {upload.response.replayed ? " · Replay confirmed" : ""}. Job:{" "}
                <span className="mono">{upload.response.job_id}</span>
              </p>
            )}
          </div>
          <div className="view-dialog-actions">
            <button type="button" className="button" onClick={close}>
              Close
            </button>
            {upload.phase === "unknown" ||
            (upload.phase === "failed" && upload.error?.retryable) ? (
              <button
                type="button"
                className="button primary"
                disabled={!uploadAllowed}
                onClick={() => void model.retryUpload()}
              >
                Retry same operation
              </button>
            ) : (
              <button
                type="submit"
                className="button primary"
                disabled={!uploadAllowed || upload.phase !== "ready"}
              >
                {replace ? "Confirm replacement" : "Confirm upload"}
              </button>
            )}
          </div>
        </form>
      )}
      <p className="detail-caption documents-resize-help">
        Drag the bottom-right corner to resize this window, or use the width
        button in the header.
      </p>
    </dialog>
  );
}
