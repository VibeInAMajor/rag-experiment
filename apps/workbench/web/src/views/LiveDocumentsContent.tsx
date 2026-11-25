import { useRef, useState } from "react";
import { FileText, RefreshCw, Search, Upload, X } from "lucide-react";
import type { BackendCapabilities } from "../api/contracts";
import { SourceFilesProvider, SourceName } from "../components/SourceName";
import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import {
  DocumentChunks,
  DocumentReport,
  DocumentsError,
  IngestionStatus,
} from "./LiveDocumentDetails";
import { DocumentUploadDialog } from "./DocumentUploadDialog";
import { DocumentUploadQueue } from "./DocumentUploadQueue";
import {
  buildDocumentFolders,
  filterDocumentFolders,
} from "../domain/documentFolders";
import { DocumentFolderTable } from "./DocumentFolderTable";

export type LiveDocumentsProps = {
  controller: LiveDocumentsModel;
  capabilities: BackendCapabilities | null;
  onSearchSource?: (source: {
    sourceId: string;
    versionId: string;
    title: string;
  }) => void;
};

export function LiveDocumentsContent({
  controller: model,
  capabilities,
  onSearchSource,
}: LiveDocumentsProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [tab, setTab] = useState<"content" | "chunks" | "report">("content");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [replace, setReplace] = useState(false);
  const lastSelectedButton = useRef<HTMLButtonElement | null>(null);
  const uploadButton = useRef<HTMLButtonElement>(null);
  const uploadTrigger = useRef<HTMLElement | null>(null);
  const uploadAllowed =
    capabilities?.service_state === "running" &&
    capabilities.features.upload === true &&
    !["idle", "unavailable"].includes(model.status);
  const detail = model.detail;
  const visible = filterDocumentFolders(
    buildDocumentFolders(
      model.documents,
      model.uploadQueue,
      !model.nextCursor && !model.listBusy,
    ),
    query,
    status,
  );
  const openUpload = (replacement: boolean) => {
    const activeElement = document.activeElement;
    uploadTrigger.current =
      activeElement instanceof HTMLElement
        ? activeElement
        : uploadButton.current;
    if (!["unknown", "submitting"].includes(model.upload.phase)) {
      model.clearUpload();
    }
    setReplace(
      ["unknown", "submitting"].includes(model.upload.phase)
        ? Boolean(model.upload.sourceId)
        : replacement,
    );
    setUploadOpen(true);
  };

  return (
    <section
      className="view-page documents-live"
      aria-labelledby="documents-title"
    >
      <header className="view-heading">
        <div>
          <p className="view-eyebrow">Knowledge · Live</p>
          <h1 id="documents-title">Documents</h1>
          <p>
            Persisted sources and indexed text from the authorized workspace.
          </p>
        </div>
        <div className="view-actions">
          <span className="view-count mono">
            {model.documents.length} loaded
          </span>
          <button
            type="button"
            className="button"
            disabled={model.listBusy}
            onClick={() => void model.refresh()}
          >
            <RefreshCw size={15} /> Refresh
          </button>
          {uploadAllowed && (
            <button
              ref={uploadButton}
              type="button"
              className="button primary"
              onClick={() => openUpload(false)}
            >
              <Upload size={15} /> Upload
            </button>
          )}
        </div>
      </header>
      {!uploadAllowed && (
        <p className="detail-notice">
          Read only. Upload is unavailable for the current workspace or server
          capabilities.
        </p>
      )}
      <div className="view-toolbar">
        <label className="view-search">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">Filter loaded documents</span>
          <input
            type="search"
            placeholder="Filter loaded documents"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="view-filter">
          <span className="sr-only">Document status</span>
          <select
            className="input"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {["all", "ready", "processing", "error"].map((value) => (
              <option key={value} value={value}>
                {value === "all" ? "All statuses" : value}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div role="status" aria-live="polite">
        {model.notice && <p className="detail-notice">{model.notice}</p>}
        {model.listBusy && <p className="detail-caption">Loading documents…</p>}
      </div>
      <DocumentsError error={model.error} />
      {model.status === "unavailable" && (
        <p className="detail-notice">
          Live documents are unavailable. Restore the backend or its document
          capability, then refresh.
        </p>
      )}
      <div
        className={`view-detail-layout${model.selectedSourceId ? " has-detail" : ""}`}
      >
        <div className="data-panel data-scroll" aria-busy={model.listBusy}>
          <DocumentFolderTable
            nodes={visible}
            selectedSourceId={model.selectedSourceId}
            expandMatches={query.trim() !== "" || status !== "all"}
            onSelect={(sourceId, button) => {
              lastSelectedButton.current = button;
              model.selectSource(sourceId);
              setTab("content");
            }}
          />
          {!visible.length && !model.listBusy && (
            <div className="view-empty">
              <FileText size={28} aria-hidden="true" />
              <h2>
                {model.status === "empty"
                  ? "No documents"
                  : model.documents.length
                    ? "No matching loaded documents"
                    : "No documents loaded"}
              </h2>
              <p>
                {model.status === "empty"
                  ? "No persisted sources were returned for this workspace."
                  : model.documents.length
                    ? "Adjust your loaded-document filter."
                    : "Refresh to request the current source list."}
              </p>
              {model.documents.length > 0 && (
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setQuery("");
                    setStatus("all");
                  }}
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
          {model.nextCursor && (
            <div className="documents-pagination">
              <button
                type="button"
                className="button"
                disabled={model.listBusy}
                onClick={() => void model.loadMore()}
              >
                Load more documents
              </button>
              <p className="detail-caption">
                Filters apply to loaded documents only.
              </p>
            </div>
          )}
        </div>
        {model.selectedSourceId && (
          <aside className="detail-panel" aria-label="Live document details">
            <header className="detail-heading">
              <div>
                <span className="view-eyebrow">Persisted source</span>
                <h2>{detail?.title ?? model.selectedSourceId}</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close document details"
                onClick={() => {
                  model.selectSource(null);
                  lastSelectedButton.current?.focus();
                }}
              >
                <X size={18} />
              </button>
            </header>
            <div
              className="detail-body documents-detail-summary"
              aria-live="polite"
            >
              {model.detailBusy && <p>Loading source details…</p>}
              <DocumentsError error={model.detailError} />
              {!capabilities?.features.document_details && (
                <p className="view-muted">
                  Document details are unavailable from this backend.
                </p>
              )}
              {detail && (
                <>
                  <dl className="detail-metadata">
                    <div>
                      <dt>Source</dt>
                      <dd className="mono">{detail.source_id}</dd>
                    </div>
                    <div>
                      <dt>Active version</dt>
                      <dd className="mono">
                        {detail.active_version_id ?? "Unavailable"}
                      </dd>
                    </div>
                    <div>
                      <dt>Source bytes</dt>
                      <dd className="mono">
                        {detail.source_bytes ?? "Not reported"}
                      </dd>
                    </div>
                    <div>
                      <dt>SHA-256</dt>
                      <dd className="mono">
                        {detail.source_content_sha256 ?? "Not reported"}
                      </dd>
                    </div>
                  </dl>
                  <p className="detail-caption">
                    Original file bytes are unavailable through this API.
                  </p>
                  {detail.active_version_id && (
                    <div className="documents-local-source">
                      <span className="detail-caption">
                        Local original hint:{" "}
                      </span>
                      <SourceFilesProvider>
                        <SourceName
                          workspaceId={detail.workspace_id}
                          sourceId={detail.source_id}
                          versionId={detail.active_version_id}
                        />
                      </SourceFilesProvider>
                      <p className="detail-caption">
                        A filename link reveals the registered file on the API
                        host. It is not a download.
                      </p>
                    </div>
                  )}
                  <div className="documents-detail-actions">
                    <button
                      type="button"
                      className="button"
                      disabled={model.detailBusy}
                      onClick={() => void model.refreshSelected()}
                    >
                      Refresh details
                    </button>
                    {uploadAllowed && detail.active_version_id && (
                      <button
                        type="button"
                        className="button"
                        disabled={model.uploadQueueBusy}
                        onClick={() => openUpload(true)}
                      >
                        Replace file
                      </button>
                    )}
                    {onSearchSource && detail.active_version_id && (
                      <button
                        type="button"
                        className="button"
                        onClick={() => {
                          if (detail.active_version_id)
                            onSearchSource({
                              sourceId: detail.source_id,
                              versionId: detail.active_version_id,
                              title: detail.title,
                            });
                        }}
                      >
                        Search this source
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
            {detail && (
              <>
                <div
                  className="detail-tabs"
                  role="tablist"
                  aria-label="Document details"
                >
                  {(["content", "chunks", "report"] as const).map(
                    (value, index, tabs) => (
                      <button
                        type="button"
                        key={value}
                        id={`live-document-tab-${value}`}
                        role="tab"
                        aria-selected={tab === value}
                        aria-controls="live-document-tab-panel"
                        tabIndex={tab === value ? 0 : -1}
                        onClick={() => setTab(value)}
                        onKeyDown={(event) => {
                          const next =
                            event.key === "ArrowRight"
                              ? (index + 1) % tabs.length
                              : event.key === "ArrowLeft"
                                ? (index + tabs.length - 1) % tabs.length
                                : event.key === "Home"
                                  ? 0
                                  : event.key === "End"
                                    ? tabs.length - 1
                                    : -1;
                          if (next >= 0) {
                            event.preventDefault();
                            setTab(tabs[next]);
                            document
                              .getElementById(`live-document-tab-${tabs[next]}`)
                              ?.focus();
                          }
                        }}
                      >
                        {value === "content"
                          ? "Indexed text"
                          : value === "chunks"
                            ? "Chunks"
                            : "Parse report"}
                      </button>
                    ),
                  )}
                </div>
                <div
                  className="detail-body"
                  id="live-document-tab-panel"
                  role="tabpanel"
                  aria-labelledby={`live-document-tab-${tab}`}
                  tabIndex={0}
                >
                  {tab === "report" ? (
                    <DocumentReport detail={detail} />
                  ) : (
                    <DocumentChunks model={model} compact={tab === "content"} />
                  )}
                </div>
              </>
            )}
          </aside>
        )}
      </div>
      <IngestionStatus
        model={model}
        jobsAvailable={capabilities?.features.jobs === true}
        uploadAllowed={uploadAllowed}
      />
      {!uploadOpen && (
        <DocumentUploadQueue model={model} uploadAllowed={uploadAllowed} />
      )}
      {uploadOpen && (
        <DocumentUploadDialog
          model={model}
          capabilities={capabilities}
          replace={replace}
          uploadAllowed={uploadAllowed}
          onClose={() => {
            setUploadOpen(false);
            uploadTrigger.current?.focus();
          }}
        />
      )}
    </section>
  );
}
