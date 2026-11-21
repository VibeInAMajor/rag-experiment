import { useState } from "react";
import {
  ArrowUpRight,
  CircleCheck,
  Clock3,
  ListFilter,
  Play,
  X,
} from "lucide-react";
import type { LiveRun, RunEntry } from "../domain/liveSearch";
import { ServerDuration } from "../components/ServerDuration";
import {
  LiveRunDetails,
  LiveRunMetadata,
  type LiveResultView,
} from "../components/LiveRunDetails";
import "./views.css";

export function RunsView({
  runs,
  onOpenPipeline,
}: {
  runs: RunEntry[];
  onOpenPipeline: (id: string) => void;
}) {
  const [status, setStatus] = useState("All");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"results" | "nodes" | "errors">("results");
  const selectedEntry = runs.find((entry) => entry.run.id === selectedId);
  const selected =
    selectedEntry?.source === "preview" ? selectedEntry.run : undefined;
  const selectedLive =
    selectedEntry?.source === "live" ? selectedEntry.run : undefined;
  const visible = runs
    .filter((entry) => status === "All" || entry.run.status === status)
    .slice()
    .sort((a, b) => b.run.startedAt.localeCompare(a.run.startedAt));
  const statusClass = (value: string) =>
    value === "Completed"
      ? "success"
      : value === "Failed"
        ? "error"
        : value === "Running"
          ? "running"
          : "neutral";

  return (
    <section className="view-page" aria-labelledby="runs-title">
      <header className="view-heading">
        <div>
          <p className="view-eyebrow">Execution</p>
          <h1 id="runs-title">Runs</h1>
          <p>Session history · cleared on refresh.</p>
        </div>
        <span className="view-count mono">
          {runs.length} {runs.length === 1 ? "run" : "runs"}
        </span>
      </header>
      <div className="view-toolbar">
        <label className="view-filter">
          <ListFilter size={16} />
          <span className="sr-only">Run status</span>
          <select
            className="input"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {[
              "All",
              "Running",
              "Completed",
              "Failed",
              "Cancelled",
              "InterruptedLocally",
            ].map((value) => (
              <option key={value} value={value}>
                {value === "All"
                  ? "All statuses"
                  : value === "InterruptedLocally"
                    ? "Interrupted locally"
                    : value}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        className={`view-detail-layout${selectedEntry ? " has-detail" : ""}`}
      >
        <div className="data-panel data-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Pipeline</th>
                <th>Source</th>
                <th>Status</th>
                <th>Started</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((entry) => {
                const run = entry.run;
                return (
                  <tr
                    key={run.id}
                    data-source={entry.source}
                    className={run.id === selectedId ? "data-selected" : ""}
                  >
                    <td>
                      <button
                        type="button"
                        className="data-name"
                        aria-pressed={selectedId === run.id}
                        onClick={() => {
                          setSelectedId(run.id);
                          setTab(
                            run.status === "Failed" ? "errors" : "results",
                          );
                        }}
                      >
                        <span className="data-file-icon">
                          <Play size={16} />
                        </span>
                        <span>
                          <strong>{run.pipelineName}</strong>
                          <small className="mono">
                            {entry.source === "live"
                              ? (entry.run.serverRunId ?? "Awaiting server ID")
                              : run.id}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <span className="run-source mono">
                        {entry.source === "live" ? "Live" : "Preview"}
                      </span>
                    </td>
                    <td>
                      <span className={`status ${statusClass(run.status)}`}>
                        {run.status === "InterruptedLocally"
                          ? "Interrupted locally"
                          : run.status}
                      </span>
                    </td>
                    <td className="data-date mono">
                      {new Date(run.startedAt).toLocaleString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="mono data-nowrap">
                      {entry.source === "live" ? (
                        entry.run.durationMs === undefined ? (
                          "—"
                        ) : (
                          <ServerDuration durationMs={entry.run.durationMs} />
                        )
                      ) : (
                        `${(entry.run.durationMs / 1000).toFixed(2)}s`
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {visible.length === 0 && (
            <div className="view-empty">
              <Clock3 size={28} />
              <h2>{runs.length ? "No matching runs" : "No runs yet"}</h2>
              <p>
                {runs.length
                  ? "Choose a different status."
                  : "Run a pipeline to inspect its results here."}
              </p>
              {runs.length > 0 && (
                <button
                  type="button"
                  className="button"
                  onClick={() => setStatus("All")}
                >
                  Clear filter
                </button>
              )}
            </div>
          )}
        </div>
        {selected && (
          <aside
            className="detail-panel"
            aria-label={`Run details: ${selected.pipelineName}`}
          >
            <header className="detail-heading">
              <div>
                <span className={`status ${statusClass(selected.status)}`}>
                  {selected.status}
                </span>
                <h2>{selected.pipelineName}</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close run details"
                onClick={() => setSelectedId(null)}
              >
                <X size={18} />
              </button>
            </header>
            <div className="detail-run-summary">
              <span className="mono">{selected.id}</span>
              <button
                type="button"
                className="button small"
                onClick={() => onOpenPipeline(selected.pipelineId)}
              >
                Open pipeline
                <ArrowUpRight size={14} />
              </button>
            </div>
            <div
              className="detail-tabs"
              role="tablist"
              aria-label="Run details"
            >
              {(["results", "nodes", "errors"] as const).map((value) => (
                <button
                  type="button"
                  key={value}
                  id={`run-tab-${value}`}
                  role="tab"
                  aria-selected={tab === value}
                  aria-controls="run-tab-panel"
                  tabIndex={tab === value ? 0 : -1}
                  onClick={() => setTab(value)}
                  onKeyDown={(event) => {
                    const tabs = ["results", "nodes", "errors"] as const;
                    const next =
                      event.key === "ArrowRight"
                        ? (tabs.indexOf(tab) + 1) % 3
                        : event.key === "ArrowLeft"
                          ? (tabs.indexOf(tab) + 2) % 3
                          : -1;
                    if (next >= 0) {
                      event.preventDefault();
                      setTab(tabs[next]);
                      document.getElementById(`run-tab-${tabs[next]}`)?.focus();
                    }
                  }}
                >
                  {value === "results"
                    ? "Results"
                    : value === "nodes"
                      ? "Nodes"
                      : "Errors"}
                  <span className="mono">
                    {value === "results"
                      ? selected.results.length
                      : value === "nodes"
                        ? selected.nodes.length
                        : selected.errors.length}
                  </span>
                </button>
              ))}
            </div>
            <div
              className="detail-body"
              id="run-tab-panel"
              role="tabpanel"
              aria-labelledby={`run-tab-${tab}`}
            >
              {tab === "results" && (
                <>
                  {selected.results.map((result, index) => (
                    <article className="detail-result" key={result.id}>
                      <div className="detail-result-heading">
                        <span className="detail-result-rank mono">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <h3>{result.title}</h3>
                        <span className="detail-score mono">
                          {result.score.toFixed(3)}
                        </span>
                      </div>
                      <p>{result.content}</p>
                      <span className="detail-caption mono">
                        Page {result.page} · {result.sourceId}
                      </span>
                    </article>
                  ))}
                  {selected.results.length === 0 && (
                    <div className="detail-empty">
                      <CircleCheck size={23} />
                      <p>
                        {selected.status === "Failed"
                          ? "No results returned."
                          : selected.status === "Running"
                            ? "Results will appear when execution completes."
                            : "No retrieval results. Inspect node outputs for details."}
                      </p>
                    </div>
                  )}
                </>
              )}
              {tab === "nodes" && (
                <>
                  {selected.nodes.map((node) => (
                    <article className="detail-node" key={node.nodeId}>
                      <div className="detail-result-heading">
                        <h3>{node.label}</h3>
                        <span className={`status ${node.status}`}>
                          {node.status}
                        </span>
                      </div>
                      <p>{node.summary}</p>
                      <div className="detail-caption mono">
                        {node.durationMs}ms
                      </div>
                      <details className="detail-json">
                        <summary>Output</summary>
                        <pre>{JSON.stringify(node.output, null, 2)}</pre>
                      </details>
                    </article>
                  ))}
                  {selected.nodes.length === 0 && (
                    <p className="view-muted">No node outputs available.</p>
                  )}
                </>
              )}
              {tab === "errors" && (
                <>
                  {selected.errors.length ? (
                    selected.errors.map((error, index) => (
                      <div key={index} className="detail-error" role="status">
                        <h3>Execution error</h3>
                        <p>{error}</p>
                      </div>
                    ))
                  ) : (
                    <div className="detail-empty">
                      <CircleCheck size={23} />
                      <p>No execution errors.</p>
                    </div>
                  )}
                </>
              )}
            </div>
          </aside>
        )}
        {selectedLive && (
          <LiveRunHistoryDetails
            key={selectedLive.id}
            run={selectedLive}
            onClose={() => setSelectedId(null)}
            onOpenPipeline={onOpenPipeline}
          />
        )}
      </div>
    </section>
  );
}

function LiveRunHistoryDetails({
  run,
  onClose,
  onOpenPipeline,
}: {
  run: LiveRun;
  onClose: () => void;
  onOpenPipeline: (id: string) => void;
}) {
  const [tab, setTab] = useState<LiveResultView>(
    run.status === "Failed" ? "errors" : "output",
  );
  const [json, setJson] = useState(false);
  const tabs = ["output", "stages", "errors"] as const;
  return (
    <aside
      className="detail-panel"
      aria-label={`Run details: ${run.pipelineName}`}
    >
      <header className="detail-heading">
        <div>
          <span className="run-source mono">Live</span>
          <span
            className={`status ${run.status === "Completed" ? "success" : run.status === "Failed" ? "error" : "neutral"}`}
          >
            {run.status === "InterruptedLocally"
              ? "Interrupted locally"
              : run.status}
          </span>
          <h2>{run.pipelineName}</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Close run details"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </header>
      <div className="detail-run-summary">
        <span className="mono">
          {run.serverRunId ?? "Server run ID not received"}
        </span>
        <button
          type="button"
          className="button small"
          onClick={() => onOpenPipeline(run.pipelineId)}
        >
          Open pipeline
          <ArrowUpRight size={14} />
        </button>
      </div>
      <div className="detail-tabs" role="tablist" aria-label="Run details">
        {tabs.map((value, index) => (
          <button
            type="button"
            key={value}
            id={`run-live-tab-${value}`}
            role="tab"
            aria-selected={tab === value}
            aria-controls="run-live-tab-panel"
            tabIndex={tab === value ? 0 : -1}
            onClick={() => setTab(value)}
            onKeyDown={(event) => {
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % tabs.length
                  : event.key === "ArrowLeft"
                    ? (index + tabs.length - 1) % tabs.length
                    : -1;
              if (next >= 0) {
                event.preventDefault();
                setTab(tabs[next]);
                document.getElementById(`run-live-tab-${tabs[next]}`)?.focus();
              }
            }}
          >
            {value === "output"
              ? "Results"
              : value === "stages"
                ? "Stages"
                : "Errors"}
          </button>
        ))}
      </div>
      <div
        className="detail-body"
        id="run-live-tab-panel"
        role="tabpanel"
        aria-labelledby={`run-live-tab-${tab}`}
      >
        <LiveRunMetadata run={run} />
        <button
          type="button"
          className="button small"
          aria-pressed={json}
          onClick={() => setJson(!json)}
        >
          Response JSON
        </button>
        <LiveRunDetails run={run} view={tab} json={json} />
      </div>
    </aside>
  );
}
