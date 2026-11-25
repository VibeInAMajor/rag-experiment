import { WorkbenchApiError, type WorkbenchApiClient } from "../api/client";
import type {
  ActiveChunkItem,
  BackendCapabilities,
  DocumentDetail,
  DocumentItem,
  IngestionJobResponse,
  IngestionResponse,
} from "../api/contracts";
import type { ExecutionMode } from "./types";

export type LiveDocumentsContext = {
  mode: ExecutionMode;
  workspaceId: string | null;
  capabilities: BackendCapabilities | null;
  enabled?: boolean;
  corpusRevision?: string | null;
  profileRevision?: string | null;
};
export type DocumentError = {
  code: string;
  message: string;
  retryable: boolean;
  httpStatus?: number;
  requestId?: string;
  traceId?: string;
  jobId?: string;
};
export type UploadOperation = {
  phase:
    | "idle"
    | "ready"
    | "submitting"
    | "unknown"
    | "failed"
    | "conflict"
    | "succeeded";
  file: File | null;
  sourceId?: string;
  expectedActiveVersionId?: string;
  idempotencyKey?: string;
  response: IngestionResponse | null;
  error?: DocumentError;
  jobId?: string;
};
export type LiveDocumentsState = {
  status: "idle" | "loading" | "ready" | "empty" | "unavailable" | "error";
  documents: DocumentItem[];
  nextCursor: string | null;
  corpusRevision: string | null;
  listBusy: boolean;
  error: DocumentError | null;
  notice: string | null;
  selectedSourceId: string | null;
  detail: DocumentDetail | null;
  detailBusy: boolean;
  detailError: DocumentError | null;
  chunks: ActiveChunkItem[];
  chunksNextCursor: string | null;
  chunksBusy: boolean;
  chunksError: DocumentError | null;
  job: IngestionJobResponse | null;
  jobBusy: boolean;
  jobError: DocumentError | null;
  upload: UploadOperation;
};
export type DocumentsClient = Pick<
  WorkbenchApiClient,
  | "listDocuments"
  | "getDocumentDetail"
  | "listActiveChunks"
  | "uploadDocument"
  | "getIngestionJob"
>;

export function emptyLiveDocuments(): LiveDocumentsState {
  return {
    status: "idle",
    documents: [],
    nextCursor: null,
    corpusRevision: null,
    listBusy: false,
    error: null,
    notice: null,
    selectedSourceId: null,
    detail: null,
    detailBusy: false,
    detailError: null,
    chunks: [],
    chunksNextCursor: null,
    chunksBusy: false,
    chunksError: null,
    job: null,
    jobBusy: false,
    jobError: null,
    upload: { phase: "idle", file: null, response: null },
  };
}
export function documentsContextFingerprint(
  context: LiveDocumentsContext,
): string {
  return JSON.stringify([
    context.mode,
    context.workspaceId,
    context.enabled !== false,
    context.corpusRevision,
    context.profileRevision,
    context.capabilities?.features,
    context.capabilities?.pdf_ingestion?.available,
  ]);
}
function scope(context: LiveDocumentsContext): string {
  return JSON.stringify([context.mode, context.workspaceId]);
}
export function documentError(error: unknown): DocumentError {
  if (error instanceof WorkbenchApiError)
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      httpStatus: error.httpStatus,
      requestId: error.requestId,
      traceId: error.traceId,
      jobId: error.jobId,
    };
  return {
    code: "DOCUMENT_REQUEST_FAILED",
    message: "The document request failed. Check the connection and retry.",
    retryable: true,
  };
}
function incompatible(): never {
  throw new WorkbenchApiError(
    "The document snapshot changed. Refresh documents before continuing.",
    { kind: "protocol", code: "DOCUMENT_SNAPSHOT_CHANGED", retryable: true },
  );
}
export function validateDocumentFile(
  file: File,
  pdfAvailable: boolean,
): string | null {
  const extension = file.name.toLowerCase().split(".").pop();
  const mime = file.type.toLowerCase().split(";", 1)[0].trim();
  const mimes: Record<string, string[]> = {
    txt: ["text/plain"],
    md: ["text/markdown", "text/x-markdown", "text/plain"],
    markdown: ["text/markdown", "text/x-markdown", "text/plain"],
    py: ["text/x-python", "application/x-python-code", "text/plain"],
    pdf: ["application/pdf"],
  };
  if (!extension || !mimes[extension])
    return "Choose a TXT, Markdown or Python file, or an available text-layer PDF.";
  if (extension === "pdf" && !pdfAvailable)
    return "PDF ingestion is unavailable on this server.";
  if (mime && !mimes[extension].includes(mime))
    return "The file MIME type does not match a qualified upload format.";
  const limit = extension === "pdf" ? 8388608 : 1048576;
  if (file.size < 1 || file.size > limit)
    return extension === "pdf"
      ? "Choose a nonempty PDF up to 8 MiB (32 pages maximum)."
      : "Choose a nonempty text file up to 1 MiB.";
  return null;
}

type Channel = "list" | "detail" | "chunks" | "job" | "upload";
type Pending = {
  controller: AbortController;
  generation: number;
  identity: string;
};

export class LiveDocumentsRequests {
  state = emptyLiveDocuments();
  private generation = 0;
  private active = new Map<Channel, Pending>();
  private identity = "";
  private workspaceScope = "";
  private running = false;

  constructor(
    private client: DocumentsClient | (() => DocumentsClient),
    private currentContext: () => LiveDocumentsContext,
    private onChange: () => void,
    private onPublished: (response: IngestionResponse) => void = () => {},
  ) {}

  private api() {
    return typeof this.client === "function" ? this.client() : this.client;
  }
  private update(patch: Partial<LiveDocumentsState>) {
    this.state = { ...this.state, ...patch };
    this.onChange();
  }
  private cancel(channel: Channel) {
    this.active.get(channel)?.controller.abort();
    this.active.delete(channel);
  }
  private begin(channel: Channel): Pending {
    this.cancel(channel);
    const pending = {
      controller: new AbortController(),
      generation: this.generation,
      identity: this.identity,
    };
    this.active.set(channel, pending);
    return pending;
  }
  private current(channel: Channel, pending: Pending) {
    return (
      this.running &&
      this.active.get(channel) === pending &&
      pending.generation === this.generation &&
      !pending.controller.signal.aborted &&
      pending.identity === documentsContextFingerprint(this.currentContext())
    );
  }
  private available() {
    const context = this.currentContext();
    return (
      this.running &&
      context.mode === "live" &&
      context.enabled !== false &&
      Boolean(context.workspaceId && context.capabilities?.features.documents)
    );
  }
  start() {
    this.running = true;
    this.contextChanged();
  }
  stop(notify = true) {
    this.running = false;
    this.generation++;
    for (const channel of this.active.keys()) this.cancel(channel);
    const upload =
      this.state.upload.phase === "submitting"
        ? this.unknownUpload()
        : this.state.upload;
    this.state = { ...emptyLiveDocuments(), upload };
    if (notify) this.onChange();
  }
  contextChanged() {
    const context = this.currentContext();
    const identity = documentsContextFingerprint(context);
    if (identity === this.identity && this.state.status !== "idle") return;
    const sameScope = scope(context) === this.workspaceScope;
    this.identity = identity;
    this.workspaceScope = scope(context);
    this.generation++;
    for (const channel of this.active.keys()) this.cancel(channel);
    const upload = sameScope
      ? this.state.upload.phase === "submitting"
        ? this.unknownUpload()
        : this.state.upload
      : emptyLiveDocuments().upload;
    this.update({ ...emptyLiveDocuments(), upload });
    if (this.available()) void this.refresh();
    else
      this.update({
        status:
          context.mode === "live" && context.enabled !== false
            ? "unavailable"
            : "idle",
      });
  }

  async refresh(
    preferredSourceId = this.state.selectedSourceId,
    expectedVersionId?: string,
    chunkRestarted = false,
  ): Promise<void> {
    if (!this.available()) return;
    this.cancel("detail");
    this.cancel("chunks");
    this.update({
      documents: [],
      nextCursor: null,
      corpusRevision: null,
      status: "loading",
      selectedSourceId: preferredSourceId,
      detail: null,
      detailBusy: false,
      detailError: null,
      chunks: [],
      chunksNextCursor: null,
      chunksBusy: false,
      chunksError: null,
    });
    await this.fetchList(
      false,
      preferredSourceId,
      expectedVersionId,
      false,
      chunkRestarted,
    );
  }
  async loadMore(): Promise<void> {
    if (!this.available() || this.state.listBusy || !this.state.nextCursor)
      return;
    await this.fetchList(true, this.state.selectedSourceId);
  }
  private async fetchList(
    append: boolean,
    preferredSourceId: string | null,
    expectedVersionId?: string,
    restarted = false,
    chunkRestarted = false,
  ): Promise<void> {
    const workspaceId = this.currentContext().workspaceId!;
    const cursor = append ? this.state.nextCursor : null;
    const revision = append ? this.state.corpusRevision : null;
    const pending = this.begin("list");
    this.update({ listBusy: true, error: null });
    try {
      const page = await this.api().listDocuments(workspaceId, {
        limit: 50,
        cursor: cursor ?? undefined,
        expectedCorpusRevision: revision ?? undefined,
        signal: pending.controller.signal,
      });
      if (!this.current("list", pending)) return;
      if (page.workspace_id !== workspaceId) incompatible();
      if (revision && page.corpus_revision !== revision) {
        if (restarted) incompatible();
        this.update({
          notice: "The corpus changed; loaded pages were cleared.",
        });
        await this.restartList(preferredSourceId, true);
        return;
      }
      if (append && page.next_cursor && page.next_cursor === cursor)
        incompatible();
      const documents = append ? [...this.state.documents] : [];
      const ids = new Set(documents.map((item) => item.source_id));
      for (const item of page.items)
        if (!ids.has(item.source_id)) {
          documents.push(item);
          ids.add(item.source_id);
        }
      this.update({
        documents,
        nextCursor: page.next_cursor,
        corpusRevision: page.corpus_revision,
        status: documents.length ? "ready" : "empty",
        listBusy: false,
      });
      if (!append) {
        const selected = preferredSourceId ?? documents[0]?.source_id ?? null;
        if (selected)
          await this.selectSource(selected, expectedVersionId, chunkRestarted);
        else this.update({ selectedSourceId: null });
      }
    } catch (error) {
      if (!this.current("list", pending)) return;
      if (
        error instanceof WorkbenchApiError &&
        error.code === "INVALID_CURSOR" &&
        !restarted
      ) {
        this.update({
          notice:
            "The document cursor expired; loaded pages were cleared and restarted.",
        });
        await this.restartList(preferredSourceId, true);
        return;
      }
      this.update({
        status: "error",
        listBusy: false,
        error: documentError(error),
      });
    } finally {
      if (this.active.get("list") === pending) this.active.delete("list");
    }
  }
  private async restartList(selected: string | null, restarted: boolean) {
    this.cancel("detail");
    this.cancel("chunks");
    this.update({
      documents: [],
      nextCursor: null,
      corpusRevision: null,
      detail: null,
      detailBusy: false,
      detailError: null,
      chunks: [],
      chunksNextCursor: null,
      chunksBusy: false,
      chunksError: null,
      status: "loading",
    });
    await this.fetchList(false, selected, undefined, restarted);
  }
  async selectSource(
    sourceId: string | null,
    expectedVersionId?: string,
    chunkRestarted = false,
  ): Promise<void> {
    if (!this.available()) return;
    this.cancel("detail");
    this.cancel("chunks");
    this.update({
      selectedSourceId: sourceId,
      detail: null,
      detailBusy: true,
      detailError: null,
      chunks: [],
      chunksNextCursor: null,
      chunksBusy: false,
      chunksError: null,
    });
    if (!sourceId) {
      this.update({ detailBusy: false });
      return;
    }
    const context = this.currentContext();
    if (!context.capabilities?.features.document_details) {
      this.update({
        detailBusy: false,
        detailError: {
          code: "DETAILS_UNAVAILABLE",
          message: "Document details are unavailable on this server.",
          retryable: false,
        },
      });
      return;
    }
    const pending = this.begin("detail");
    const revision = this.state.corpusRevision;
    try {
      const detail = await this.api().getDocumentDetail(
        context.workspaceId!,
        sourceId,
        {
          signal: pending.controller.signal,
          expectedCorpusRevision: revision ?? undefined,
          expectedVersionId,
        },
      );
      if (!this.current("detail", pending)) return;
      if (
        detail.workspace_id !== context.workspaceId ||
        detail.source_id !== sourceId ||
        (revision && detail.corpus_revision !== revision) ||
        (expectedVersionId && detail.active_version_id !== expectedVersionId)
      )
        incompatible();
      this.update({ detail, detailBusy: false });
      if (detail.active_version_id)
        await this.fetchChunks(false, chunkRestarted);
    } catch (error) {
      if (this.current("detail", pending))
        this.update({ detailBusy: false, detailError: documentError(error) });
    } finally {
      if (this.active.get("detail") === pending) this.active.delete("detail");
    }
  }
  async refreshSelected() {
    if (this.state.selectedSourceId)
      await this.refresh(this.state.selectedSourceId);
  }
  async loadMoreChunks() {
    if (this.state.chunksNextCursor && !this.state.chunksBusy)
      await this.fetchChunks(true);
  }
  private async fetchChunks(append: boolean, restarted = false): Promise<void> {
    const detail = this.state.detail;
    if (!this.available() || !detail?.active_version_id) return;
    const cursor = append ? this.state.chunksNextCursor : null;
    const pending = this.begin("chunks");
    this.update({ chunksBusy: true, chunksError: null });
    try {
      const page = await this.api().listActiveChunks(
        detail.workspace_id,
        detail.source_id,
        {
          signal: pending.controller.signal,
          limit: 50,
          cursor: cursor ?? undefined,
          expectedVersionId: detail.active_version_id,
          expectedCorpusRevision: detail.corpus_revision,
        },
      );
      if (!this.current("chunks", pending)) return;
      if (
        page.workspace_id !== detail.workspace_id ||
        page.source_id !== detail.source_id ||
        page.source_version_id !== detail.active_version_id ||
        page.corpus_revision !== detail.corpus_revision ||
        (append && cursor && page.next_cursor === cursor)
      )
        incompatible();
      const chunks = append ? [...this.state.chunks] : [];
      const ids = new Set(chunks.map((item) => item.chunk_id));
      for (const item of page.items)
        if (!ids.has(item.chunk_id)) {
          chunks.push(item);
          ids.add(item.chunk_id);
        }
      const bounded = chunks.length >= 1000 && Boolean(page.next_cursor);
      this.update({
        chunks: chunks.slice(0, 1000),
        chunksNextCursor: bounded ? null : page.next_cursor,
        chunksBusy: false,
        ...(bounded
          ? {
              notice:
                "The inspection limit of 1,000 loaded chunks was reached. Additional chunks remain on the server.",
            }
          : {}),
      });
    } catch (error) {
      if (!this.current("chunks", pending)) return;
      if (
        error instanceof WorkbenchApiError &&
        error.code === "INVALID_CURSOR" &&
        !restarted
      ) {
        this.update({
          chunks: [],
          chunksNextCursor: null,
          notice:
            "The chunk cursor expired; refreshing the authoritative source snapshot.",
          chunksBusy: false,
        });
        await this.refresh(detail.source_id, undefined, true);
        return;
      }
      this.update({ chunksBusy: false, chunksError: documentError(error) });
    } finally {
      if (this.active.get("chunks") === pending) this.active.delete("chunks");
    }
  }
  async inspectJob(jobId = this.state.upload.jobId): Promise<void> {
    if (
      !this.available() ||
      !jobId ||
      !this.currentContext().capabilities?.features.jobs
    )
      return;
    const workspaceId = this.currentContext().workspaceId!;
    const pending = this.begin("job");
    this.update({ job: null, jobBusy: true, jobError: null });
    try {
      const job = await this.api().getIngestionJob(workspaceId, jobId, {
        signal: pending.controller.signal,
      });
      if (!this.current("job", pending)) return;
      if (job.workspace_id !== workspaceId || job.job_id !== jobId)
        incompatible();
      this.update({ job, jobBusy: false });
    } catch (error) {
      if (this.current("job", pending))
        this.update({ jobBusy: false, jobError: documentError(error) });
    } finally {
      if (this.active.get("job") === pending) this.active.delete("job");
    }
  }
  chooseFile(file: File | null, replace = false): void {
    if (this.state.upload.phase === "submitting") return;
    if (!file) {
      this.clearUpload();
      return;
    }
    const context = this.currentContext();
    const detail = this.state.detail;
    const message =
      validateDocumentFile(
        file,
        context.capabilities?.pdf_ingestion?.available === true,
      ) ??
      (replace &&
      (!detail?.active_version_id ||
        detail.source_id !== this.state.selectedSourceId)
        ? "Load the current source version before replacing it."
        : null);
    this.update({
      upload: {
        phase: message ? "failed" : "ready",
        file,
        response: null,
        ...(replace && detail?.active_version_id
          ? {
              sourceId: detail.source_id,
              expectedActiveVersionId: detail.active_version_id,
            }
          : {}),
        ...(message
          ? { error: { code: "INVALID_FILE", message, retryable: false } }
          : { idempotencyKey: crypto.randomUUID() }),
      },
      job: null,
      jobError: null,
    });
  }
  clearUpload() {
    if (this.state.upload.phase === "submitting") return;
    this.cancel("job");
    this.update({
      upload: emptyLiveDocuments().upload,
      job: null,
      jobBusy: false,
      jobError: null,
    });
  }
  private unknownUpload(): UploadOperation {
    return {
      ...this.state.upload,
      phase: "unknown",
      error: {
        code: "UPLOAD_OUTCOME_UNKNOWN",
        message:
          "Request stopped locally; the server outcome may be unknown. Retry the same operation to confirm its result.",
        retryable: true,
      },
    };
  }
  stopUpload() {
    if (this.state.upload.phase !== "submitting") return;
    this.cancel("upload");
    this.update({ upload: this.unknownUpload() });
  }
  async retryUpload() {
    await this.submitUpload();
  }
  async submitUpload(): Promise<void> {
    const operation = this.state.upload;
    if (
      !this.available() ||
      !this.currentContext().capabilities?.features.upload ||
      !["ready", "unknown", "failed"].includes(operation.phase) ||
      !operation.file ||
      !operation.idempotencyKey ||
      (operation.phase === "failed" && !operation.error?.retryable)
    )
      return;
    const context = this.currentContext();
    const validation = validateDocumentFile(
      operation.file,
      context.capabilities?.pdf_ingestion?.available === true,
    );
    if (validation) {
      this.update({
        upload: {
          ...operation,
          phase: "failed",
          error: {
            code: "INVALID_FILE",
            message: validation,
            retryable: false,
          },
        },
      });
      return;
    }
    const pending = this.begin("upload");
    this.update({
      upload: { ...operation, phase: "submitting", error: undefined },
    });
    try {
      const response = await this.api().uploadDocument(
        context.workspaceId!,
        {
          file: operation.file,
          idempotencyKey: operation.idempotencyKey,
          sourceId: operation.sourceId,
          expectedActiveVersionId: operation.expectedActiveVersionId,
          pdfAvailable: context.capabilities?.pdf_ingestion?.available === true,
        },
        { signal: pending.controller.signal },
      );
      if (!this.current("upload", pending)) return;
      if (
        response.workspace_id !== context.workspaceId ||
        (operation.sourceId && response.source_id !== operation.sourceId)
      )
        incompatible();
      this.update({
        upload: {
          ...operation,
          phase: "succeeded",
          error: undefined,
          response,
          jobId: response.job_id,
        },
        notice: "Publication confirmed.",
      });
      // Publication already changed the corpus even if a subsequent read is interrupted.
      this.onPublished(response);
      await Promise.all([
        this.refresh(response.source_id, response.source_version_id),
        this.inspectJob(response.job_id),
      ]);
    } catch (error) {
      if (!this.current("upload", pending)) return;
      const details = documentError(error);
      const uncertain =
        !(error instanceof WorkbenchApiError) ||
        ["transport", "timeout", "cancelled", "protocol"].includes(
          error.kind,
        ) ||
        error.httpStatus === 504;
      this.update({
        upload: {
          ...operation,
          phase:
            details.httpStatus === 409
              ? "conflict"
              : uncertain
                ? "unknown"
                : "failed",
          error: uncertain
            ? {
                ...details,
                message:
                  "The server outcome is unconfirmed. Retry this operation with the same file and key.",
                retryable: true,
              }
            : details,
          jobId: details.jobId,
        },
      });
      if (details.httpStatus === 409 && operation.sourceId)
        await this.refresh(operation.sourceId);
    } finally {
      if (this.active.get("upload") === pending) this.active.delete("upload");
    }
  }
}
