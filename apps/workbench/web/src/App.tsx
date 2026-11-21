import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  Check,
  CircleAlert,
  Command,
  FileText,
  GitBranch,
  Keyboard,
  Play,
  Settings2,
  X,
} from "lucide-react";
import {
  initialPipelines,
  previewDocuments,
  initialRuns,
  defaultSettings,
} from "./domain/fixtures";
import {
  createPipeline,
  exportPipeline,
  importPipeline,
  checkPreviewGraph,
} from "./domain/graph";
import type {
  GraphIssue,
  ExecutionMode,
  Pipeline,
  PreviewRun,
  TemplateId,
} from "./domain/types";
import { useGraphHistory } from "./hooks/useGraphHistory";
import { usePreview } from "./hooks/usePreview";
import { useValidation } from "./hooks/useValidation";
import { useBackendDiscovery } from "./hooks/useBackendDiscovery";
import { ExecutionControls } from "./components/ExecutionControls";
import { PipelinesView } from "./views/PipelinesView";
import { DocumentsView } from "./views/DocumentsView";
import { RunsView } from "./views/RunsView";
import { SettingsView } from "./views/SettingsView";
import "./views/views.css";

type Page = "editor" | "pipelines" | "documents" | "runs" | "settings";
const PipelineEditor = lazy(() =>
  import("./components/PipelineEditor").then((module) => ({
    default: module.PipelineEditor,
  })),
);

export function App() {
  const [pipelines, setPipelines] = useState<Pipeline[]>(() =>
    structuredClone(initialPipelines),
  );
  const [runs, setRuns] = useState<PreviewRun[]>(() =>
    structuredClone(initialRuns),
  );
  const [settings, setSettings] = useState(defaultSettings);
  const [mode, setMode] = useState<ExecutionMode>("preview");
  const discovery = useBackendDiscovery(mode);
  const [activeId, setActiveId] = useState(initialPipelines[0].id);
  const [page, setPage] = useState<Page>("editor");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [issues, setIssues] = useState<GraphIssue[]>([]);
  const [showValidationIssues, setShowValidationIssues] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const toastTimer = useRef<number | null>(null);
  const help = useRef<HTMLDialogElement>(null);
  const pipeline =
    pipelines.find((item) => item.id === activeId) ?? pipelines[0];
  const [fallback] = useState(() => createPipeline("blank"));
  const current = pipeline ?? fallback;
  const history = useGraphHistory(current, setPipelines);
  const preview = usePreview(setRuns);
  const validation = useValidation(current);
  const displayedRun =
    mode === "preview"
      ? runs.find((run) => run.pipelineId === current.id)
      : undefined;
  const changeMode = (next: ExecutionMode) => {
    if (next === mode) return;
    preview.stop();
    setIssues([]);
    setResultsOpen(false);
    setMode(next);
  };

  useEffect(
    () => () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
    },
    [],
  );
  const notify = (message: string, error = false) => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    setToast({ message, error });
    toastTimer.current = window.setTimeout(
      () => setToast(null),
      error ? 6500 : 3500,
    );
  };

  const openPipeline = (id: string) => {
    setActiveId(id);
    setPage("editor");
    setSelectedNodeId(null);
    setIssues([]);
    setShowValidationIssues(false);
    setResultsOpen(false);
  };
  const newPipeline = (template: TemplateId) => {
    const created = createPipeline(template);
    setPipelines((previous) => [...previous, created]);
    openPipeline(created.id);
  };
  const renamePipeline = (id: string, name: string) =>
    setPipelines((previous) =>
      previous.map((item) =>
        item.id === id
          ? { ...item, name, updatedAt: new Date().toISOString() }
          : item,
      ),
    );

  const downloadPipeline = () => {
    const serialized = exportPipeline(current);
    try {
      importPipeline(serialized);
    } catch (error) {
      notify(
        error instanceof Error
          ? error.message
          : "Fix the pipeline before exporting.",
        true,
      );
      return;
    }
    const url = URL.createObjectURL(
      new Blob([serialized], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${current.name.replace(/[^a-z0-9-]/gi, "-").toLowerCase() || "pipeline"}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify("Pipeline exported.");
  };

  const uploadPipeline = async (file: File) => {
    try {
      if (file.size > 1000000)
        throw new Error("Pipeline files must be smaller than 1 MB.");
      const imported = importPipeline(await file.text());
      const id = crypto.randomUUID();
      setPipelines((previous) => [
        ...previous,
        { ...imported, id, updatedAt: new Date().toISOString() },
      ]);
      openPipeline(id);
      notify("Pipeline imported.");
    } catch (error) {
      notify(
        error instanceof Error
          ? error.message
          : "The pipeline could not be imported.",
        true,
      );
    }
  };

  const checkPreview = () => {
    const found = checkPreviewGraph(current.graph);
    setIssues(
      found.map((issue) => ({
        ...issue,
        message: `Preview only: ${issue.message}`,
      })),
    );
    if (found.length) {
      setResultsOpen(true);
      notify(
        `${found.length} validation issue${found.length === 1 ? "" : "s"} found.`,
        true,
      );
    } else
      notify("Fixture preview checks passed; this is not Haystack validation.");
    return found.length === 0;
  };

  return (
    <div
      className={`app-shell ${settings.reducedMotion ? "reduce-motion" : ""}`}
    >
      <a className="skip-link" href="#main-content">
        Skip to workspace
      </a>
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          <span>
            haystack<span className="brand-product mono">WORKBENCH</span>
          </span>
        </div>
        <span className="header-divider" />
        <div className="workspace-name">
          <span className="workspace-avatar">
            {settings.workspaceName.charAt(0).toUpperCase()}
          </span>
          {settings.workspaceName}
        </div>
        <div className="header-right">
          <ExecutionControls
            mode={mode}
            onChange={changeMode}
            state={discovery.state}
          />
          <button
            className="icon-button"
            title="Keyboard shortcuts"
            aria-label="Keyboard shortcuts"
            onClick={() => help.current?.showModal()}
          >
            <Keyboard size={18} />
          </button>
        </div>
      </header>
      <div className="app-body">
        <nav className="navigation-rail" aria-label="Main navigation">
          <div className="navigation-main">
            {(
              [
                { id: "pipelines", label: "Pipelines", icon: GitBranch },
                { id: "documents", label: "Documents", icon: FileText },
                { id: "runs", label: "Runs", icon: Play },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                className={`nav-item ${page === item.id || (page === "editor" && item.id === "pipelines") ? "active" : ""}`}
                aria-current={
                  page === item.id ||
                  (page === "editor" && item.id === "pipelines")
                    ? "page"
                    : undefined
                }
                onClick={() => setPage(item.id)}
              >
                <item.icon size={21} strokeWidth={1.6} />
                <span>{item.label}</span>
              </button>
            ))}
          </div>
          <div className="navigation-bottom">
            <button
              className={`nav-item ${page === "settings" ? "active" : ""}`}
              aria-current={page === "settings" ? "page" : undefined}
              onClick={() => setPage("settings")}
            >
              <Settings2 size={21} strokeWidth={1.6} />
              <span>Settings</span>
            </button>
            <span className="rail-version mono">V0.1</span>
          </div>
        </nav>
        <main id="main-content" className="main-content" tabIndex={-1}>
          {page === "editor" && (
            <Suspense
              fallback={<div className="result-empty">Loading workspace…</div>}
            >
              <PipelineEditor
                pipeline={current}
                settings={settings}
                selectedNodeId={selectedNodeId}
                onSelectNode={setSelectedNodeId}
                onGraphChange={(update, record) => {
                  history.updateGraph(update, record);
                  if (record !== false) setIssues([]);
                }}
                onBack={() => setPage("pipelines")}
                onExport={downloadPipeline}
                onImport={uploadPipeline}
                onValidate={() => {
                  setShowValidationIssues(true);
                  setIssues([]);
                  setResultsOpen(true);
                  void validation.validate();
                }}
                validationStatus={validation.state.status}
                onRun={() => {
                  if (mode !== "preview") return;
                  setShowValidationIssues(false);
                  if (checkPreview()) {
                    setResultsOpen(true);
                    void preview
                      .runPipeline(current, settings)
                      .catch((error: unknown) =>
                        notify(
                          error instanceof Error
                            ? error.message
                            : "Preview failed.",
                          true,
                        ),
                      );
                  }
                }}
                runDisabledReason={
                  mode === "live"
                    ? "Live search execution is not connected yet"
                    : undefined
                }
                onStop={preview.stop}
                onRename={(name) => renamePipeline(current.id, name)}
                onUndo={history.undo}
                onRedo={history.redo}
                canUndo={history.canUndo}
                canRedo={history.canRedo}
                busy={mode === "preview" && preview.busy}
                runningNodeId={
                  mode === "preview" &&
                  preview.busy &&
                  displayedRun?.id === preview.liveRunId
                    ? preview.runningNodeId
                    : null
                }
                run={displayedRun}
                issues={[
                  ...issues,
                  ...(showValidationIssues ? validation.state.issues : []).map(
                    (issue) => ({
                      ...issue,
                      message: `${issue.code}${issue.nodeId ? ` · ${current.graph.nodes.find((node) => node.id === issue.nodeId)?.data.label ?? issue.nodeId}` : ""}${issue.edgeId ? ` · edge ${issue.edgeId}` : ""}: ${issue.message}`,
                    }),
                  ),
                ]}
                resultsOpen={resultsOpen}
                onResultsOpen={setResultsOpen}
                notify={notify}
              />
            </Suspense>
          )}
          {page === "pipelines" && (
            <PipelinesView
              pipelines={pipelines}
              defaultTemplate={settings.defaultTemplate}
              runs={mode === "preview" ? runs : []}
              onOpen={openPipeline}
              onCreate={newPipeline}
              onRename={renamePipeline}
              onDelete={(id) => {
                if (
                  preview.busy &&
                  id ===
                    runs.find((run) => run.id === preview.liveRunId)?.pipelineId
                ) {
                  notify(
                    "Stop the preview before deleting this pipeline.",
                    true,
                  );
                  return;
                }
                setPipelines((previous) =>
                  previous.filter((item) => item.id !== id),
                );
                if (activeId === id) setActiveId("");
              }}
              onImport={uploadPipeline}
            />
          )}
          {page === "documents" &&
            (mode === "preview" ? (
              <DocumentsView documents={previewDocuments} />
            ) : (
              <section
                className="view-page"
                aria-labelledby="live-documents-title"
              >
                <header className="view-heading">
                  <h1 id="live-documents-title">Documents</h1>
                </header>
                <p className="live-empty">
                  Live document listing is not connected yet.
                </p>
                <p className="live-empty">
                  {discovery.state.capabilities?.features.documents
                    ? "The API supports read-only listing."
                    : "Document availability has not been confirmed."}
                </p>
              </section>
            ))}
          {page === "runs" &&
            (mode === "preview" ? (
              <RunsView
                runs={runs}
                onOpenPipeline={(id) => {
                  if (pipelines.some((item) => item.id === id)) {
                    openPipeline(id);
                    setResultsOpen(true);
                  } else notify("This pipeline has been deleted.", true);
                }}
              />
            ) : (
              <section className="view-page" aria-labelledby="live-runs-title">
                <header className="view-heading">
                  <h1 id="live-runs-title">Runs</h1>
                </header>
                <p className="live-empty">
                  No Live runs. Search execution is not connected yet.
                </p>
              </section>
            ))}
          {page === "settings" && (
            <SettingsView
              settings={settings}
              onChange={setSettings}
              mode={mode}
              discovery={discovery}
            />
          )}
        </main>
      </div>
      {toast && (
        <div
          className={`toast ${toast.error ? "error" : ""}`}
          role={toast.error ? "alert" : "status"}
        >
          {toast.error ? <CircleAlert size={17} /> : <Check size={17} />}
          <span>{toast.message}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={14} />
          </button>
        </div>
      )}
      <dialog
        className="shortcuts-dialog"
        ref={help}
        onClick={(event) => {
          if (event.target === event.currentTarget) help.current?.close();
        }}
      >
        <div className="panel-heading">
          <span>
            <Command size={16} />
            Keyboard shortcuts
          </span>
          <button
            className="icon-button"
            aria-label="Close shortcuts"
            onClick={() => help.current?.close()}
          >
            <X size={16} />
          </button>
        </div>
        <dl>
          <div>
            <dt>Undo / redo</dt>
            <dd>
              <kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>Z</kbd>
            </dd>
          </div>
          <div>
            <dt>Duplicate node</dt>
            <dd>
              <kbd>Ctrl</kbd> <kbd>D</kbd>
            </dd>
          </div>
          <div>
            <dt>Export pipeline</dt>
            <dd>
              <kbd>Ctrl</kbd> <kbd>S</kbd>
            </dd>
          </div>
          <div>
            <dt>Remove selection</dt>
            <dd>
              <kbd>Delete</kbd>
            </dd>
          </div>
          <div>
            <dt>Move node</dt>
            <dd>
              <kbd>Arrow keys</kbd>
            </dd>
          </div>
          <div>
            <dt>Clear selection</dt>
            <dd>
              <kbd>Esc</kbd>
            </dd>
          </div>
        </dl>
      </dialog>
    </div>
  );
}
