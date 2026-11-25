import { Fragment, useState, type ReactNode } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
} from "lucide-react";
import type { DocumentTreeNode } from "../domain/documentFolders";
import { documentTimestamp } from "./documentPresentation";

export function DocumentFolderTable({
  nodes,
  selectedSourceId,
  expandMatches,
  onSelect,
}: {
  nodes: DocumentTreeNode[];
  selectedSourceId: string | null;
  expandMatches: boolean;
  onSelect: (sourceId: string, button: HTMLButtonElement) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const rows = (items: DocumentTreeNode[], depth = 0): ReactNode =>
    items.map((node) => {
      if (node.kind === "folder") {
        const open = expandMatches || expanded.has(node.key);
        const Icon = open ? FolderOpen : Folder;
        return (
          <Fragment key={node.key}>
            <tr className="documents-folder-row">
              <td style={{ paddingLeft: 18 + depth * 22 }}>
                <button
                  type="button"
                  className="data-name"
                  aria-expanded={open}
                  aria-label={`${open ? "Collapse" : "Expand"} folder ${node.path}`}
                  onClick={() =>
                    setExpanded((current) => {
                      const next = new Set(current);
                      if (next.has(node.key)) next.delete(node.key);
                      else next.add(node.key);
                      return next;
                    })
                  }
                >
                  {open ? (
                    <ChevronDown size={14} aria-hidden="true" />
                  ) : (
                    <ChevronRight size={14} aria-hidden="true" />
                  )}
                  <span className="data-file-icon documents-folder-icon">
                    <Icon size={21} aria-hidden="true" />
                  </span>
                  <span>
                    <strong>{node.name}</strong>
                    <small>
                      {node.ready} / {node.expected} files ready
                      {node.loaded < node.expected
                        ? ` · ${node.expected - node.loaded} not loaded in this view`
                        : ""}
                    </small>
                  </span>
                </button>
              </td>
              <td>
                <DocumentStatus status={node.status} />
              </td>
              <td className="mono">—</td>
              <td className="data-date">Folder</td>
            </tr>
            {open ? rows(node.children, depth + 1) : null}
          </Fragment>
        );
      }
      const document = node.document;
      return (
        <tr
          key={node.key}
          className={
            document?.source_id === selectedSourceId ? "data-selected" : ""
          }
        >
          <td style={{ paddingLeft: 40 + depth * 22 }}>
            <button
              type="button"
              className="data-name"
              aria-pressed={document?.source_id === selectedSourceId}
              disabled={!document}
              onClick={(event) => {
                if (document) onSelect(document.source_id, event.currentTarget);
              }}
            >
              <span className="data-file-icon">
                <FileText size={17} aria-hidden="true" />
              </span>
              <span>
                <strong>{node.name}</strong>
                <small className="mono">
                  {document
                    ? `${document.media_type} · ${document.source_id}`
                    : (node.upload?.error?.message ??
                      "Waiting for publication")}
                </small>
              </span>
            </button>
          </td>
          <td>
            <DocumentStatus status={node.status} />
            {document?.error_code && (
              <small className="documents-error-code mono">
                {document.error_code}
              </small>
            )}
          </td>
          <td className="mono">
            {document?.chunk_count ?? node.upload?.response?.chunk_count ?? "—"}
          </td>
          <td className="data-date">
            {document ? documentTimestamp(document.updated_at) : "Upload queue"}
          </td>
        </tr>
      );
    });
  return (
    <table className="data-table documents-folder-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Status</th>
          <th>Chunks</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>{rows(nodes)}</tbody>
    </table>
  );
}

function DocumentStatus({ status }: { status: DocumentTreeNode["status"] }) {
  return (
    <span
      className={`status ${status === "ready" ? "success" : ["error", "unknown"].includes(status) ? "error" : "running"}`}
    >
      {status === "ready"
        ? "Ready"
        : status === "error"
          ? "Error"
          : status === "unknown"
            ? "Unconfirmed"
            : status === "pending"
              ? "Waiting"
              : "Processing"}
    </span>
  );
}
