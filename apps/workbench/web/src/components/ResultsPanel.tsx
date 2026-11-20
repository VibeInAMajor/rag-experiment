import { useState } from "react";
import {
  Braces,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileText,
  LoaderCircle,
} from "lucide-react";
import type { GraphIssue, PreviewRun } from "../domain/types";

export function ResultsPanel({
  run,
  issues,
  selectedNodeId,
  onSelectNode,
  onClose,
}: {
  run?: PreviewRun;
  issues: GraphIssue[];
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"output" | "nodes" | "errors">("output");
  const [json, setJson] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const errors: GraphIssue[] = [
    ...issues,
    ...(run?.errors ?? []).map((message) => ({ message })),
  ];
  const effectiveTab = issues.length ? "errors" : tab;
  return (
    <section className="results-panel" aria-label="Pipeline results">
      <div className="results-heading">
        <div className="results-tabs" role="tablist" aria-label="Result views">
          {(["output", "nodes", "errors"] as const).map((item) => (
            <button
              key={item}
              role="tab"
              aria-selected={effectiveTab === item}
              onClick={() => setTab(item)}
            >
              {item[0].toUpperCase() + item.slice(1)}
              {item === "errors" && errors.length > 0 && (
                <span className="error-count">{errors.length}</span>
              )}
            </button>
          ))}
        </div>
        <div className="results-meta">
          {run && (
            <>
              <span
                className={`status ${run.status === "Completed" ? "success" : run.status === "Failed" ? "error" : "neutral"}`}
              >
                {run.status === "Running" ? (
                  <LoaderCircle size={12} className="spinning" />
                ) : run.status === "Completed" ? (
                  <Check size={12} />
                ) : null}
                {run.status}
              </span>
              <span className="mono">
                {(run.durationMs / 1000).toFixed(2)}s
              </span>
            </>
          )}
          <button
            className={`icon-button ${json ? "active" : ""}`}
            onClick={() => setJson(!json)}
            title="Toggle JSON"
            aria-label="Toggle JSON"
            aria-pressed={json}
          >
            <Braces size={16} />
          </button>
          <button
            className="icon-button"
            onClick={onClose}
            title="Close results"
            aria-label="Close results"
          >
            <ChevronDown size={17} />
          </button>
        </div>
      </div>
      <div className="results-content" role="tabpanel">
        {json ? (
          <pre className="json-preview">
            {JSON.stringify(
              effectiveTab === "errors"
                ? errors
                : effectiveTab === "nodes"
                  ? (run?.nodes ?? [])
                  : (run?.results ?? []),
              null,
              2,
            )}
          </pre>
        ) : effectiveTab === "errors" ? (
          errors.length ? (
            <div className="error-list">
              {errors.map((error, index) => (
                <div key={`${error.message}-${index}`}>
                  <CircleAlert size={16} />
                  <span>
                    {error.message}
                    {error.field && <code> · {error.field}</code>}
                  </span>
                  {error.nodeId && (
                    <button
                      className="button small"
                      onClick={() => {
                        if (error.nodeId) onSelectNode(error.nodeId);
                      }}
                    >
                      Select node
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="result-empty">
              <Check size={18} />
              <span>No errors.</span>
            </div>
          )
        ) : effectiveTab === "nodes" ? (
          <div className="node-result-list">
            {run?.nodes.length ? (
              run.nodes.map((node) => (
                <div key={node.nodeId}>
                  <button
                    className={selectedNodeId === node.nodeId ? "selected" : ""}
                    onClick={() => {
                      onSelectNode(node.nodeId);
                      setExpanded(
                        expanded === node.nodeId ? null : node.nodeId,
                      );
                    }}
                  >
                    <ChevronRight
                      size={13}
                      className={expanded === node.nodeId ? "rotate" : ""}
                    />
                    <span className={`status-dot ${node.status}`} />
                    <strong>{node.label}</strong>
                    <span>{node.summary}</span>
                    <code>{node.durationMs}ms</code>
                  </button>
                  {expanded === node.nodeId && (
                    <pre className="json-preview">
                      {JSON.stringify(node.output, null, 2)}
                    </pre>
                  )}
                </div>
              ))
            ) : (
              <div className="result-empty">
                <LoaderCircle
                  size={18}
                  className={run?.status === "Running" ? "spinning" : ""}
                />
                <span>
                  {run?.status === "Running"
                    ? "Starting preview…"
                    : "No node outputs yet."}
                </span>
              </div>
            )}
          </div>
        ) : run?.results.length ? (
          <div className="retrieval-results">
            {run.results.map((result, index) => (
              <article className="retrieval-result" key={result.id}>
                <span className="result-rank mono">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <div className="result-title">
                    <FileText size={14} />
                    <strong>{result.title}</strong>
                    <span className="mono">P. {result.page}</span>
                  </div>
                  <p>{result.content}</p>
                </div>
                <span className="result-score mono">
                  {result.score.toFixed(3)}
                </span>
              </article>
            ))}
          </div>
        ) : (
          <div className="result-empty">
            {run?.status === "Running" ? (
              <LoaderCircle size={18} className="spinning" />
            ) : run?.status === "Failed" ? (
              <CircleAlert size={18} />
            ) : (
              <FileText size={18} />
            )}
            <span>
              {run?.status === "Running"
                ? "Running pipeline preview…"
                : run?.status === "Completed"
                  ? "Indexing preview complete. Open Nodes to inspect the output."
                  : run?.status === "Failed"
                    ? "Preview failed. Open Errors for details."
                    : "Run a preview to inspect the results."}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
