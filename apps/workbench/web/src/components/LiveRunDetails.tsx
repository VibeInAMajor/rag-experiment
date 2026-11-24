import type { LiveRun } from "../domain/liveSearch";
import { ServerDuration } from "./ServerDuration";
import { SourceFilesProvider, SourceName } from "./SourceName";
import "./live-results.css";

export type LiveResultView = "output" | "stages" | "errors";

export function LiveRunMetadata({ run }: { run: LiveRun }) {
  const fields = [
    ["Workspace", run.workspaceId],
    ["Profile", run.profileId],
    ["Profile revision", run.profileRevision],
    ["Corpus revision", run.corpusRevision ?? "Unavailable"],
    ...(run.response?.embedding_profile_revision
      ? [
          [
            "Embedding profile revision",
            run.response.embedding_profile_revision,
          ],
          ["Index generation", String(run.response.index_generation)],
          ["Model revision", run.response.model_revision ?? "Unavailable"],
          ["Model digest", run.response.model_digest ?? "Unavailable"],
          ["Tokenizer digest", run.response.tokenizer_digest ?? "Unavailable"],
          [
            "Input format revision",
            run.response.input_format_revision ?? "Unavailable",
          ],
        ]
      : []),
    ["Server run ID", run.serverRunId ?? "Not received"],
    ["Request ID", run.requestId ?? "Not received"],
    ["Trace ID", run.traceId ?? "Not received"],
  ];
  return (
    <details className="live-run-metadata">
      <summary>Execution details</summary>
      <dl className="live-provenance">
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="mono">{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export function LiveRunDetails({
  run,
  view = "output",
  json = false,
}: {
  run: LiveRun;
  view?: LiveResultView;
  json?: boolean;
}) {
  if (json)
    return (
      <pre className="json-preview live-json" aria-label="Live response JSON">
        {JSON.stringify(
          run.response ?? {
            source: "live",
            status: run.status,
            submitted: run.submitted,
            error: run.error,
            request_id: run.requestId,
            trace_id: run.traceId,
            run_id: run.serverRunId,
          },
          null,
          2,
        )}
      </pre>
    );

  if (view === "stages")
    return run.stages.length ? (
      <div className="live-stages" aria-label="Server stages">
        {run.stages.map((stage) => (
          <div
            className="live-stage"
            key={stage.stage}
            data-stage={stage.stage}
            data-duration-ms={stage.duration_ms}
          >
            <strong className="mono">{stage.stage}</strong>
            <span
              className={`status ${stage.status === "success" ? "success" : "neutral"}`}
            >
              {stage.status}
            </span>
            <ServerDuration durationMs={stage.duration_ms} />
          </div>
        ))}
      </div>
    ) : (
      <p className="result-empty">No server stage timings received.</p>
    );

  if (view === "errors")
    return run.status === "InterruptedLocally" ? (
      <p className="result-empty">
        Stopped locally. Server cancellation is not confirmed.
      </p>
    ) : run.error ? (
      <div className="detail-error live-error" role="status">
        <strong className="mono">{run.error.code}</strong>
        {run.error.httpStatus !== undefined && (
          <span className="mono">HTTP {run.error.httpStatus}</span>
        )}
        <p>{run.error.message}</p>
      </div>
    ) : (
      <p className="result-empty">No execution errors.</p>
    );

  if (!run.results.length)
    return (
      <p className="result-empty">
        {run.status === "Running"
          ? "Waiting for the search response…"
          : run.status === "Completed"
            ? "No matches for this query."
            : run.status === "InterruptedLocally"
              ? "Stopped locally. Server cancellation is not confirmed."
              : "Search failed. Open Errors for details."}
      </p>
    );

  return (
    <SourceFilesProvider>
      <div className="retrieval-results live-retrieval-results">
        {run.results.map((result) => (
          <article
            className="retrieval-result live-retrieval-result"
            key={result.chunk_id}
            data-source="live"
            data-source-id={result.source_id}
            data-source-version-id={result.source_version_id}
            data-chunk-id={result.chunk_id}
            data-rank={result.rank}
            data-score={String(result.score)}
            data-score-type={result.score_type}
          >
            <span
              className="result-rank mono"
              aria-label={`Rank ${result.rank}`}
            >
              {String(result.rank).padStart(2, "0")}
            </span>
            <div className="live-result-body">
              <div className="result-title">
                <strong>{result.title}</strong>
                <span className="mono">
                  {result.page == null
                    ? "Page unavailable"
                    : `Page ${result.page}`}
                </span>
              </div>
              <p>{result.content}</p>
              <dl className="live-provenance live-source-provenance">
                {[
                  ["Source", result.source_id],
                  ["Source version", result.source_version_id],
                  ["Chunk", result.chunk_id],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd className="mono">
                      {label === "Source" ? (
                        <SourceName
                          workspaceId={run.workspaceId}
                          sourceId={result.source_id}
                          versionId={result.source_version_id}
                        />
                      ) : (
                        value
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="live-score">
              <span
                className="result-score mono"
                aria-label={
                  result.score_type === "cosine_distance"
                    ? "Raw cosine distance, lower is better"
                    : "Raw PostgreSQL ts_rank_cd score"
                }
              >
                {String(result.score)}
              </span>
              <span className="mono">{result.score_type}</span>
              {result.score_type === "cosine_distance" && (
                <small>Lower is better</small>
              )}
            </div>
          </article>
        ))}
      </div>
    </SourceFilesProvider>
  );
}
