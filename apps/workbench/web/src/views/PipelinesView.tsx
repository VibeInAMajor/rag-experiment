import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  FilePlus2,
  GitBranch,
  Pencil,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import type { Pipeline, TemplateId } from "../domain/types";
import type { RunEntry } from "../domain/liveSearch";
import "./views.css";

type Props = {
  pipelines: Pipeline[];
  runs: RunEntry[];
  defaultTemplate: TemplateId;
  onOpen: (id: string) => void;
  onCreate: (template: TemplateId) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onImport: (file: File) => void;
};

const templates: { id: TemplateId; title: string; description: string }[] = [
  {
    id: "keyword",
    title: "Keyword search",
    description: "Search the approved PostgreSQL lexical profile.",
  },
  {
    id: "blank",
    title: "Blank pipeline",
    description: "Start with an empty canvas.",
  },
  {
    id: "indexing",
    title: "Document indexing",
    description: "Parse, split, embed, and index documents.",
  },
  {
    id: "retrieval",
    title: "Hybrid retrieval",
    description: "Combine BM25 and vector search results.",
  },
];

export function PipelinesView({
  pipelines,
  runs,
  defaultTemplate,
  onOpen,
  onCreate,
  onRename,
  onDelete,
  onImport,
}: Props) {
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState<{
    type: "new" | "rename" | "delete";
    pipeline?: Pipeline;
  } | null>(null);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const visible = pipelines.filter((pipeline) =>
    pipeline.name.toLowerCase().includes(query.toLowerCase()),
  );
  const preferredTemplates = [
    ...templates.filter((template) => template.id === defaultTemplate),
    ...templates.filter((template) => template.id !== defaultTemplate),
  ];

  useEffect(() => {
    if (dialog && !dialogRef.current?.open) dialogRef.current?.showModal();
    if (!dialog) dialogRef.current?.close();
  }, [dialog]);

  function closeDialog() {
    setDialog(null);
    setNameError("");
  }

  return (
    <section className="view-page" aria-labelledby="pipelines-title">
      <header className="view-heading">
        <div>
          <p className="view-eyebrow">Workbench</p>
          <h1 id="pipelines-title">Pipelines</h1>
          <p>Build and inspect document workflows.</p>
        </div>
        <div className="view-actions">
          <input
            ref={importRef}
            type="file"
            accept=".json,application/json"
            hidden
            aria-label="Import pipeline JSON"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onImport(file);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            className="button"
            onClick={() => importRef.current?.click()}
          >
            <Upload size={16} />
            Import
          </button>
          <button
            type="button"
            className="button primary"
            onClick={() => setDialog({ type: "new" })}
          >
            <Plus size={16} />
            New pipeline
          </button>
        </div>
      </header>
      <div className="view-toolbar">
        <label className="view-search">
          <Search size={16} />
          <span className="sr-only">Search pipelines</span>
          <input
            type="search"
            placeholder="Search pipelines"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <span className="view-count mono">
          {visible.length} {visible.length === 1 ? "pipeline" : "pipelines"}
        </span>
      </div>
      <div className="data-panel data-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Nodes</th>
              <th>Last run</th>
              <th>Updated</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((pipeline) => {
              const lastRun = runs
                .filter((entry) => entry.run.pipelineId === pipeline.id)
                .sort((a, b) =>
                  b.run.startedAt.localeCompare(a.run.startedAt),
                )[0];
              return (
                <tr key={pipeline.id}>
                  <td>
                    <button
                      type="button"
                      className="data-name"
                      onClick={() => onOpen(pipeline.id)}
                    >
                      <span className="data-file-icon">
                        <GitBranch size={17} />
                      </span>
                      <span>
                        <strong>{pipeline.name}</strong>
                        <small>{pipeline.description}</small>
                      </span>
                      <ArrowRight className="data-open-arrow" size={16} />
                    </button>
                  </td>
                  <td className="mono">{pipeline.graph.nodes.length}</td>
                  <td>
                    {lastRun ? (
                      <>
                        <span className="run-source mono">
                          {lastRun.source === "live" ? "Live" : "Preview"}
                        </span>
                        <span
                          className={`status ${lastRun.run.status === "Completed" ? "success" : lastRun.run.status === "Failed" ? "error" : lastRun.run.status === "Running" ? "running" : "neutral"}`}
                        >
                          {lastRun.run.status === "InterruptedLocally"
                            ? "Interrupted locally"
                            : lastRun.run.status}
                        </span>
                      </>
                    ) : (
                      <span className="view-muted">Not run</span>
                    )}
                  </td>
                  <td className="data-date mono">
                    {new Date(pipeline.updatedAt).toLocaleDateString("en-GB", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    })}
                  </td>
                  <td>
                    <div className="view-actions">
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Rename ${pipeline.name}`}
                        onClick={() => {
                          setName(pipeline.name);
                          setDialog({ type: "rename", pipeline });
                        }}
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Delete ${pipeline.name}`}
                        onClick={() => setDialog({ type: "delete", pipeline })}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visible.length === 0 && (
          <div className="view-empty">
            <GitBranch size={28} />
            <h2>
              {query ? "No matching pipelines" : "Create your first pipeline"}
            </h2>
            <p>
              {query
                ? "Try a different name."
                : "Start with a template or an empty canvas."}
            </p>
            <button
              type="button"
              className="button"
              onClick={() =>
                query ? setQuery("") : setDialog({ type: "new" })
              }
            >
              {query ? "Clear search" : "New pipeline"}
            </button>
          </div>
        )}
      </div>
      <dialog
        ref={dialogRef}
        className="view-dialog"
        aria-labelledby="pipeline-dialog-title"
        aria-describedby={
          dialog?.type === "delete" ? "pipeline-delete-description" : undefined
        }
        onCancel={closeDialog}
      >
        {dialog && (
          <>
            <header className="detail-heading">
              <h2 id="pipeline-dialog-title">
                {dialog.type === "new"
                  ? "New pipeline"
                  : dialog.type === "rename"
                    ? "Rename pipeline"
                    : "Delete pipeline?"}
              </h2>
              <button
                type="button"
                className="icon-button"
                onClick={closeDialog}
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </header>
            {dialog.type === "new" && (
              <div className="view-template-list">
                {preferredTemplates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    className="view-template"
                    autoFocus={template.id === defaultTemplate}
                    onClick={() => {
                      onCreate(template.id);
                      closeDialog();
                    }}
                  >
                    <span className="data-file-icon">
                      <FilePlus2 size={19} />
                    </span>
                    <span>
                      <strong>{template.title}</strong>
                      <small>{template.description}</small>
                    </span>
                    <ArrowRight size={17} />
                  </button>
                ))}
              </div>
            )}
            {dialog.type === "rename" && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!name.trim()) {
                    setNameError("Enter a pipeline name.");
                    return;
                  }
                  if (dialog.pipeline)
                    onRename(dialog.pipeline.id, name.trim());
                  closeDialog();
                }}
              >
                <label className="view-field">
                  Pipeline name
                  <input
                    className="input"
                    value={name}
                    onChange={(event) => {
                      setName(event.target.value);
                      setNameError("");
                    }}
                    autoFocus
                    maxLength={100}
                    aria-invalid={!!nameError}
                    aria-describedby={
                      nameError ? "pipeline-name-error" : undefined
                    }
                  />
                </label>
                {nameError && (
                  <p
                    id="pipeline-name-error"
                    className="view-error"
                    role="alert"
                  >
                    {nameError}
                  </p>
                )}
                <div className="view-dialog-actions">
                  <button
                    type="button"
                    className="button"
                    onClick={closeDialog}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="button primary">
                    Save name
                  </button>
                </div>
              </form>
            )}
            {dialog.type === "delete" && (
              <>
                <p
                  id="pipeline-delete-description"
                  className="view-dialog-copy"
                >
                  Delete <strong>{dialog.pipeline?.name}</strong> from this
                  session? This action cannot be undone.
                </p>
                <div className="view-dialog-actions">
                  <button
                    type="button"
                    className="button"
                    autoFocus
                    onClick={closeDialog}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="button danger"
                    onClick={() => {
                      if (dialog.pipeline) onDelete(dialog.pipeline.id);
                      closeDialog();
                    }}
                  >
                    Delete pipeline
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </dialog>
    </section>
  );
}
