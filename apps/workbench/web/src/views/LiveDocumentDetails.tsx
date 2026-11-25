import type { DocumentDetail } from "../api/contracts";
import type { DocumentError } from "../domain/liveDocuments";
import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import {
  boundedDocumentText,
  documentMetadataText,
  documentChunkCaption,
  documentTimestamp,
} from "./documentPresentation";

export function DocumentsError({ error }: { error?: DocumentError | null }) {
  if (!error) return null;
  return (
    <p className="view-error documents-error" role="alert">
      {error.message}{" "}
      <span className="mono">
        {error.code}
        {error.requestId ? ` · Request ${error.requestId}` : ""}
        {error.traceId ? ` · Trace ${error.traceId}` : ""}
        {error.jobId ? ` · Job ${error.jobId}` : ""}
      </span>
    </p>
  );
}

function Metadata({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="documents-metadata">
      <summary>{label}</summary>
      <pre className="mono">{documentMetadataText(value)}</pre>
    </details>
  );
}

export function DocumentChunks({
  model,
  compact,
}: {
  model: LiveDocumentsModel;
  compact: boolean;
}) {
  return (
    <>
      <p className="detail-caption">
        {model.chunks.length} chunks loaded · Active source version{" "}
        {model.detail?.active_version_id ?? "Unavailable"}
      </p>
      {compact && (
        <p className="detail-caption">
          Indexed text from active chunks. Chunk boundaries and extraction can
          differ from the original file.
        </p>
      )}
      <DocumentsError error={model.chunksError} />
      {model.chunksBusy && <p role="status">Loading active chunks…</p>}
      {model.chunks.map((chunk) => {
        const bounded = boundedDocumentText(chunk.content);
        return (
          <article
            className="detail-chunk documents-chunk"
            key={chunk.chunk_id}
            data-chunk-id={chunk.chunk_id}
            data-content-hash={chunk.content_hash}
            data-order={chunk.order}
            data-page={chunk.page ?? ""}
          >
            <div className="detail-caption mono">
              {documentChunkCaption(chunk, model.detail?.media_type)}
            </div>
            {!compact && (
              <dl className="detail-metadata">
                <div>
                  <dt>Chunk ID</dt>
                  <dd className="mono">{chunk.chunk_id}</dd>
                </div>
                <div>
                  <dt>Content hash</dt>
                  <dd className="mono">{chunk.content_hash}</dd>
                </div>
                <div>
                  <dt>Section</dt>
                  <dd>
                    {chunk.section_path.length
                      ? chunk.section_path.join(" / ")
                      : "Not reported"}
                  </dd>
                </div>
              </dl>
            )}
            <pre className="detail-content">{bounded.text}</pre>
            {bounded.truncated && (
              <p className="detail-caption">
                Chunk text display truncated at 12,000 characters.
              </p>
            )}
            {!compact && (
              <Metadata
                label="Chunk metadata · lines, symbols, table rows and page geometry when reported"
                value={chunk.metadata}
              />
            )}
          </article>
        );
      })}
      {!model.chunks.length && !model.chunksBusy && !model.chunksError && (
        <p className="view-muted">No active indexed chunks returned.</p>
      )}
      {model.chunksNextCursor && (
        <button
          type="button"
          className="button"
          disabled={model.chunksBusy}
          onClick={() => void model.loadMoreChunks()}
        >
          Load more chunks
        </button>
      )}
    </>
  );
}

export function DocumentReport({ detail }: { detail: DocumentDetail }) {
  return (
    <>
      <dl className="detail-metadata">
        <div>
          <dt>Status</dt>
          <dd>{detail.status}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{documentTimestamp(detail.updated_at)}</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>{detail.chunk_count}</dd>
        </div>
        <div>
          <dt>Parsed elements</dt>
          <dd>{detail.parsed_element_count ?? "Not reported"}</dd>
        </div>
        <div>
          <dt>Language policy</dt>
          <dd>{detail.language_policy ?? "Not reported"}</dd>
        </div>
        <div>
          <dt>Default language</dt>
          <dd>{detail.default_language ?? "Not reported"}</dd>
        </div>
        <div>
          <dt>Ingestion policy</dt>
          <dd>{detail.ingestion_policy_revision ?? "Not reported"}</dd>
        </div>
        <div>
          <dt>Profile fingerprint</dt>
          <dd className="mono">
            {detail.processing_profile_fingerprint ?? "Not reported"}
          </dd>
        </div>
        <div>
          <dt>Corpus revision</dt>
          <dd className="mono">{detail.corpus_revision}</dd>
        </div>
      </dl>
      <Metadata label="Parser" value={detail.parser} />
      <Metadata label="Processing profile" value={detail.processing_profile} />
      <Metadata
        label="Document processing · visual and original evidence status when reported"
        value={detail.document_processing}
      />
      <h3>Warnings</h3>
      {detail.warnings?.length ? (
        detail.warnings.slice(0, 50).map((warning, index) => {
          const bounded = boundedDocumentText(warning, 2000);
          return (
            <p key={index} className="detail-notice">
              {bounded.text}
              {bounded.truncated ? "… Warning display truncated." : ""}
            </p>
          );
        })
      ) : (
        <p className="view-muted">No parsing warnings reported.</p>
      )}
      {(detail.warnings?.length ?? 0) > 50 && (
        <p className="detail-caption">
          Warning display limited to the first 50 entries.
        </p>
      )}
    </>
  );
}

export function IngestionStatus({
  model,
  jobsAvailable,
  uploadAllowed,
}: {
  model: LiveDocumentsModel;
  jobsAvailable: boolean;
  uploadAllowed: boolean;
}) {
  const { upload, job } = model;
  const result = upload.response;
  if (upload.phase === "idle" && !job && !model.jobError) return null;
  return (
    <section
      className="data-panel documents-ingestion"
      aria-label="Ingestion operation"
    >
      <h2>Ingestion operation</h2>
      <div role="status" aria-live="polite">
        {upload.phase === "submitting" && (
          <p>
            Publishing synchronously… The server has not confirmed an outcome.
          </p>
        )}
        {upload.phase === "unknown" && (
          <p className="detail-notice">
            Request stopped or unconfirmed locally; server outcome may be
            unknown. Retry the same operation to recover its result.
          </p>
        )}
        {upload.phase === "failed" && upload.error?.retryable && (
          <p className="detail-notice">
            Upload failed. Retry the same operation when the reported condition
            is resolved.
          </p>
        )}
        {upload.phase === "conflict" && (
          <p className="detail-notice">
            The operation conflicts with server state. Refresh source details
            and explicitly choose a new replacement before submitting again.
          </p>
        )}
        {result && (
          <>
            <p>
              Confirmed {result.outcome}
              {result.replayed ? " · Replayed operation" : ""} ·{" "}
              {result.chunk_count} chunks
            </p>
            <dl className="detail-metadata">
              <div>
                <dt>Source</dt>
                <dd className="mono">{result.source_id}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd className="mono">{result.source_version_id}</dd>
              </div>
              <div>
                <dt>Job</dt>
                <dd className="mono">{result.job_id}</dd>
              </div>
            </dl>
            <h3>Measured server stages</h3>
            <ul>
              {result.stages.map((stage) => (
                <li key={stage.stage}>
                  {stage.stage}: {stage.duration_ms} ms
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <DocumentsError error={upload.error} />
      <div className="documents-detail-actions">
        {upload.phase === "submitting" && (
          <button type="button" className="button" onClick={model.stopUpload}>
            Stop locally
          </button>
        )}
        {(upload.phase === "unknown" ||
          (upload.phase === "failed" && upload.error?.retryable)) && (
          <button
            type="button"
            className="button"
            disabled={!uploadAllowed}
            onClick={() => void model.retryUpload()}
          >
            Retry same operation
          </button>
        )}
        {jobsAvailable && (upload.jobId || result?.job_id || job?.job_id) && (
          <button
            type="button"
            className="button"
            disabled={model.jobBusy}
            onClick={() =>
              void model.inspectJob(
                upload.jobId ?? result?.job_id ?? job?.job_id,
              )
            }
          >
            Inspect confirmed job status
          </button>
        )}
      </div>
      {model.jobBusy && <p role="status">Loading durable job status…</p>}
      <DocumentsError error={model.jobError} />
      {job && (
        <div className="documents-job">
          <h3>Last confirmed durable job</h3>
          <dl className="detail-metadata">
            <div>
              <dt>Job ID</dt>
              <dd className="mono">{job.job_id}</dd>
            </div>
            <div>
              <dt>Status / stage</dt>
              <dd>
                {job.status} / {job.stage}
              </dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd className="mono">{job.source_id}</dd>
            </div>
            <div>
              <dt>Reserved version</dt>
              <dd className="mono">{job.reserved_version_id}</dd>
            </div>
            <div>
              <dt>Published version</dt>
              <dd className="mono">
                {job.source_version_id ?? "Not reported"}
              </dd>
            </div>
            <div>
              <dt>Outcome</dt>
              <dd>{job.outcome ?? "Not reported"}</dd>
            </div>
            <div>
              <dt>Chunks</dt>
              <dd>{job.chunk_count ?? "Not reported"}</dd>
            </div>
            <div>
              <dt>Retryable</dt>
              <dd>{job.retryable ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Error code</dt>
              <dd>{job.error_code ?? "None reported"}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{documentTimestamp(job.created_at)}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{documentTimestamp(job.updated_at)}</dd>
            </div>
            <div>
              <dt>Finished</dt>
              <dd>{documentTimestamp(job.finished_at)}</dd>
            </div>
          </dl>
          <Metadata label="Measured job stages" value={job.stages} />
          <p className="detail-caption">
            Status fetched by this job ID. No background queue or automatic
            polling is implied.
          </p>
        </div>
      )}
    </section>
  );
}
