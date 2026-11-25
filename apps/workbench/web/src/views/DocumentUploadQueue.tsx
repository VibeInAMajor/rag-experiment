import { useState } from "react";
import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import { DocumentsError } from "./LiveDocumentDetails";
import { Download } from "lucide-react";
import {
  documentUploadReport,
  uploadIssues,
} from "../domain/documentUploadReport";

export function DocumentUploadQueue({
  model,
  uploadAllowed,
}: {
  model: LiveDocumentsModel;
  uploadAllowed: boolean;
}) {
  const [visibleCount, setVisibleCount] = useState(100);
  const items = model.uploadQueue;
  if (!items.length) return null;
  const count = (phase: string) =>
    items.filter((item) => item.phase === phase).length;
  const downloadReport = () => {
    const generatedAt = new Date();
    const url = URL.createObjectURL(
      new Blob(["\uFEFF", documentUploadReport(items, generatedAt)], {
        type: "text/plain;charset=utf-8",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `document-upload-errors-${generatedAt.toISOString().slice(0, 10)}.txt`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <section
      className="data-panel documents-ingestion documents-upload-queue"
      aria-label="Upload queue"
    >
      <h2>Upload queue</h2>
      <p role="status" aria-live="polite">
        {count("succeeded")} uploaded · {count("submitting")} uploading ·{" "}
        {count("queued") + count("ready")} waiting ·{" "}
        {count("failed") + count("unknown")} need attention · {count("skipped")}{" "}
        skipped
      </p>
      <p className="detail-caption">
        You can close the dialog or switch pages while uploads continue. Keep
        this browser tab open. Folder paths identify files here; documents are
        stored individually.
      </p>
      <div className="view-actions">
        {uploadIssues(items).length > 0 && (
          <button type="button" className="button" onClick={downloadReport}>
            <Download size={15} aria-hidden="true" />
            Download error report (.txt)
          </button>
        )}
        {count("ready") > 0 && (
          <button
            type="button"
            className="button primary"
            disabled={
              !uploadAllowed ||
              model.uploadQueueBusy ||
              model.upload.phase === "submitting"
            }
            onClick={model.startUploads}
          >
            Upload {count("ready")} {count("ready") === 1 ? "file" : "files"}
          </button>
        )}
        {model.uploadQueueBusy && (
          <button type="button" className="button" onClick={model.stopUploads}>
            Stop queue locally
          </button>
        )}
      </div>
      <ol className="documents-upload-items">
        {items.slice(0, visibleCount).map((item) => (
          <li key={item.id}>
            <div className="documents-upload-item-heading">
              <strong>{item.path}</strong>
              <span>
                {item.phase === "submitting"
                  ? "Uploading and processing…"
                  : item.phase === "succeeded"
                    ? "Uploaded"
                    : item.phase}
              </span>
            </div>
            <DocumentsError error={item.error} />
            {item.response && (
              <p className="detail-caption">
                Confirmed {item.response.outcome}
                {item.response.replayed ? " · Replay confirmed" : ""} · Job:{" "}
                <span className="mono">{item.response.job_id}</span>
              </p>
            )}
            {(item.phase === "unknown" ||
              (item.phase === "failed" && item.error?.retryable)) && (
              <button
                type="button"
                className="button"
                disabled={!uploadAllowed || model.upload.phase === "submitting"}
                onClick={() => model.retryQueuedUpload(item.id)}
              >
                Retry same operation
                <span className="sr-only"> for {item.path}</span>
              </button>
            )}
          </li>
        ))}
      </ol>
      {items.length > visibleCount && (
        <button
          type="button"
          className="button"
          onClick={() => setVisibleCount((value) => value + 100)}
        >
          Show more files ({items.length - visibleCount} remaining)
        </button>
      )}
    </section>
  );
}
