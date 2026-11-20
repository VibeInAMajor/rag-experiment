import { useState } from "react";
import { AlertTriangle, FileText, Search, X } from "lucide-react";
import type { PreviewDocument } from "../domain/types";
import "./views.css";

export function DocumentsView({ documents }: { documents: PreviewDocument[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"content" | "chunks" | "report">("content");
  const selected = documents.find((document) => document.id === selectedId);
  const visible = documents.filter(
    (document) =>
      document.name.toLowerCase().includes(query.toLowerCase()) &&
      (status === "All" || document.status === status),
  );

  return (
    <section className="view-page" aria-labelledby="documents-title">
      <header className="view-heading">
        <div>
          <p className="view-eyebrow">Knowledge</p>
          <h1 id="documents-title">Documents</h1>
          <p>Inspect source files and extracted content.</p>
        </div>
        <span className="view-count mono">
          {documents.length} {documents.length === 1 ? "file" : "files"}
        </span>
      </header>
      <div className="view-toolbar">
        <label className="view-search">
          <Search size={16} />
          <span className="sr-only">Search documents</span>
          <input
            type="search"
            placeholder="Search documents"
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
            {["All", "Indexed", "Processing", "Failed"].map((value) => (
              <option key={value} value={value}>
                {value === "All" ? "All statuses" : value}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className={`view-detail-layout${selected ? " has-detail" : ""}`}>
        <div className="data-panel data-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((document) => (
                <tr
                  key={document.id}
                  className={selectedId === document.id ? "data-selected" : ""}
                >
                  <td>
                    <button
                      type="button"
                      className="data-name"
                      aria-pressed={selectedId === document.id}
                      onClick={() => {
                        setSelectedId(document.id);
                        setTab("content");
                      }}
                    >
                      <span className="data-file-icon">
                        <FileText size={17} />
                      </span>
                      <span>
                        <strong>{document.name}</strong>
                        <small className="mono">
                          {document.type} ·{" "}
                          {new Date(document.addedAt).toLocaleDateString(
                            "en-GB",
                            { day: "2-digit", month: "short" },
                          )}
                        </small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <span
                      className={`status ${document.status === "Indexed" ? "success" : document.status === "Failed" ? "error" : "running"}`}
                    >
                      {document.status}
                    </span>
                  </td>
                  <td className="mono">{document.chunks}</td>
                  <td className="mono data-nowrap">{document.size}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {visible.length === 0 && (
            <div className="view-empty">
              <FileText size={28} />
              <h2>
                {documents.length ? "No matching documents" : "No documents"}
              </h2>
              <p>
                {documents.length
                  ? "Adjust your search or status filter."
                  : "No source files available."}
              </p>
              {documents.length > 0 && (
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setQuery("");
                    setStatus("All");
                  }}
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
        </div>
        {selected && (
          <aside
            className="detail-panel"
            aria-label={`Document details: ${selected.name}`}
          >
            <header className="detail-heading">
              <div>
                <span className="view-eyebrow">Document</span>
                <h2>{selected.name}</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setSelectedId(null)}
                aria-label="Close document details"
              >
                <X size={18} />
              </button>
            </header>
            <div
              className="detail-tabs"
              role="tablist"
              aria-label="Document details"
            >
              {(["content", "chunks", "report"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  id={`document-tab-${value}`}
                  role="tab"
                  aria-selected={tab === value}
                  aria-controls="document-tab-panel"
                  tabIndex={tab === value ? 0 : -1}
                  onClick={() => setTab(value)}
                  onKeyDown={(event) => {
                    const tabs = ["content", "chunks", "report"] as const;
                    const next =
                      event.key === "ArrowRight"
                        ? (tabs.indexOf(tab) + 1) % 3
                        : event.key === "ArrowLeft"
                          ? (tabs.indexOf(tab) + 2) % 3
                          : -1;
                    if (next >= 0) {
                      event.preventDefault();
                      setTab(tabs[next]);
                      globalThis.document
                        .getElementById(`document-tab-${tabs[next]}`)
                        ?.focus();
                    }
                  }}
                >
                  {value === "report"
                    ? "Parse report"
                    : value === "content"
                      ? "Content"
                      : "Chunks"}
                </button>
              ))}
            </div>
            <div
              className="detail-body"
              id="document-tab-panel"
              role="tabpanel"
              aria-labelledby={`document-tab-${tab}`}
            >
              {tab === "content" &&
                (selected.content ? (
                  <p className="detail-content">{selected.content}</p>
                ) : (
                  <div className="detail-empty">
                    <FileText size={22} />
                    <p>
                      {selected.status === "Failed"
                        ? "Content could not be extracted."
                        : "No extracted content available."}
                    </p>
                  </div>
                ))}
              {tab === "chunks" && (
                <>
                  <p className="detail-caption mono">
                    {selected.chunks} total chunks
                  </p>
                  {(selected.chunkPreviews ?? []).map((chunk) => (
                    <article key={chunk.id} className="detail-chunk">
                      <span className="detail-caption mono">
                        {chunk.id} · Page {chunk.page}
                      </span>
                      <p>{chunk.content}</p>
                    </article>
                  ))}
                  {!selected.chunkPreviews?.length && (
                    <p className="view-muted">No chunk excerpts available.</p>
                  )}
                </>
              )}
              {tab === "report" && (
                <>
                  <dl className="detail-metadata">
                    <div>
                      <dt>Parser</dt>
                      <dd className="mono">{selected.parser}</dd>
                    </div>
                    <div>
                      <dt>Pages</dt>
                      <dd className="mono">{selected.pages}</dd>
                    </div>
                    <div>
                      <dt>Chunks</dt>
                      <dd className="mono">{selected.chunks}</dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>{selected.status}</dd>
                    </div>
                  </dl>
                  <h3>Notices</h3>
                  {selected.warnings.length ? (
                    selected.warnings.map((warning, index) => (
                      <p className="detail-notice" key={index}>
                        <AlertTriangle size={16} />
                        <span>{warning}</span>
                      </p>
                    ))
                  ) : (
                    <p className="view-muted">No parsing warnings.</p>
                  )}
                </>
              )}
            </div>
          </aside>
        )}
      </div>
    </section>
  );
}
