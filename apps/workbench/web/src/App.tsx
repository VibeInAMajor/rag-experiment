import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type SetStateAction,
} from "react";
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
import { useLiveSearch } from "./hooks/useLiveSearch";
import { matchApprovedKeywordGraph } from "./domain/approvedExecution";
import {
  graphFingerprint,
  type LiveRun,
  type RunEntry,
} from "./domain/liveSearch";
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

function retainSessionRuns(entries: RunEntry[]): RunEntry[] {
  return entries
    .sort((a, b) => b.run.startedAt.localeCompare(a.run.startedAt))
    .slice(0, 100);
}

export function App() {
  const [pipelines, setPipelines] = useState<Pipeline[]>(() =>
    structuredClone(initialPipelines),
  );
  const [sessionRuns, setSessionRuns] = useState<RunEntry[]>(() =>
    structuredClone(initialRuns).map((run) => ({ source: "preview", run })),
  );
  const runs = sessionRuns.flatMap((entry) =>
    entry.source === "preview" ? [entry.run] : [],
  );
  const liveRuns = sessionRuns.flatMap((entry) =>
    entry.source === "live" ? [entry.run] : [],
  );
  const setRuns = (update: SetStateAction<PreviewRun[]>) =>
    setSessionRuns((previous) => {
      const currentRuns = previous.flatMap((entry) =>
        entry.source === "preview" ? [entry.run] : [],
      );
      const nextRuns =
        typeof update === "function" ? update(currentRuns) : update;
      return retainSessionRuns([
        ...previous.filter((entry) => entry.source !== "preview"),
        ...nextRuns.map((run): RunEntry => ({ source: "preview", run })),
      ]);
    });
  const setLiveRuns = (update: SetStateAction<LiveRun[]>) =>
    setSessionRuns((previous) => {
      const currentRuns = previous.flatMap((entry) =>
        entry.source === "live" ? [entry.run] : [],
      );
      const nextRuns =
        typeof update === "function" ? update(currentRuns) : update;
      return retainSessionRuns([
        ...previous.filter((entry) => entry.source !== "live"),
        ...nextRuns.map((run): RunEntry => ({ source: "live", run })),
      ]);
    });
  const [settings, setSettings] = useState(defaultSettings);
  const [mode, setMode] = useState<ExecutionMode>("preview");
  const discovery = useBackendDiscovery(mode);
  const [activeId, setActiveId] = useState(initialPipelines[0].id);
  const [page, setPage] = useState<Page>("editor");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [issues, setIssues] = useState<GraphIssue[]>([]);
  const [showValidationIssues, setShowValidationIssues] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [submittedLiveContext, setSubmittedLiveContext] = useState<{
    pipelineId: string;
    graph: string;
    workspaceId: string;
    profileId: string;
    profileRevision: string;
  } | null>(null);
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
  const live = useLiveSearch(
    {
      mode,
      pipeline: current,
      workspaceId: discovery.state.selectedWorkspaceId,
      profile: discovery.state.profile,
    },
    setLiveRuns,
    { onInvalidateDiscovery: discovery.refresh },
  );
  const approved = matchApprovedKeywordGraph(current.graph, discovery.state);
  const visibleLiveRun = liveRuns.find(
    (run) =>
      submittedLiveContext &&
      run.pipelineId === current.id &&
      run.pipelineId === submittedLiveContext.pipelineId &&
      graphFingerprint(run.graphSnapshot) === submittedLiveContext.graph &&
      submittedLiveContext.graph === graphFingerprint(current.graph) &&
      run.workspaceId === submittedLiveContext.workspaceId &&
      run.profileId === submittedLiveContext.profileId &&
      run.profileRevision === submittedLiveContext.profileRevision &&
      ((run.workspaceId === discovery.state.selectedWorkspaceId &&
        run.profileId === discovery.state.profile?.profile_id &&
        run.profileRevision === discovery.state.profile?.profile_revision) ||
        ((run.status === "Failed" || run.status === "InterruptedLocally") &&
          (discovery.state.selectedWorkspaceId === null ||
            run.workspaceId === discovery.state.selectedWorkspaceId))),
  );
  const previewRun = runs.find((run) => run.pipelineId === current.id);
  const displayedRun: RunEntry | undefined =
    mode === "preview"
      ? previewRun && { source: "preview", run: previewRun }
      : visibleLiveRun && { source: "live", run: visibleLiveRun };
  const changeMode = (next: ExecutionMode) => {
    if (next === mode) return;
    preview.stop();
    live.stop();
    setToast(null);
    setSubmittedLiveContext(null);
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
    live.stop();
    setSubmittedLiveContext(null);
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
                  if (record !== false) {
                    live.stop();
                    setSubmittedLiveContext(null);
                  }
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
                  setToast(null);
                  setShowValidationIssues(false);
                  if (mode === "live") {
                    if (!approved.supported) return;
                    setIssues([]);
                    setResultsOpen(true);
                    setSubmittedLiveContext({
                      pipelineId: current.id,
                      graph: graphFingerprint(current.graph),
                      workspaceId: approved.workspaceId,
                      profileId: approved.request.profile_id,
                      profileRevision:
                        approved.request.expected_profile_revision,
                    });
                    void live.run(
                      current,
                      approved.request,
                      approved.workspaceId,
                    );
                    return;
                  }
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
                    ? approved.supported
                      ? undefined
                      : approved.issues.map((issue) => issue.message).join(" ")
                    : undefined
                }
                executionNotice={
                  mode === "live" && approved.supported
                    ? `Requesting up to ${approved.effectiveTopK} results · ${discovery.state.profile?.score_type}. Supported Live profile; constructor validation is separate.`
                    : undefined
                }
                onStop={mode === "live" ? live.stop : preview.stop}
                onRename={(name) => renamePipeline(current.id, name)}
                onUndo={history.undo}
                onRedo={history.redo}
                canUndo={history.canUndo}
                canRedo={history.canRedo}
                busy={mode === "live" ? live.busy : preview.busy}
                liveMode={mode === "live"}
                runningNodeId={
                  mode === "preview" &&
                  preview.busy &&
                  previewRun?.id === preview.liveRunId
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
              runs={sessionRuns}
              onOpen={openPipeline}
              onCreate={newPipeline}
              onRename={renamePipeline}
              onDelete={(id) => {
                if (live.busy && id === current.id) live.stop();
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
          {page === "runs" && (
            <RunsView
              runs={sessionRuns}
              onOpenPipeline={(id) => {
                if (pipelines.some((item) => item.id === id)) {
                  openPipeline(id);
                  setResultsOpen(true);
                } else notify("This pipeline has been deleted.", true);
              }}
            />
          )}
          {page === "settings" && (
            <SettingsView
              settings={settings}
              onChange={setSettings}
              mode={mode}
              discovery={discovery}
              onWorkspaceChange={() => {
                live.stop();
                setSubmittedLiveContext(null);
              }}
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
