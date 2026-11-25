import { WorkbenchApiError } from "../api/client";
import type { IngestionResponse, UploadLocation } from "../api/contracts";
import {
  documentError,
  validateDocumentFile,
  type DocumentError,
  type DocumentsClient,
  type LiveDocumentsContext,
} from "./liveDocuments";

export type QueuedDocumentUpload = {
  id: string;
  path: string;
  file: File | null;
  phase:
    | "ready"
    | "queued"
    | "submitting"
    | "succeeded"
    | "failed"
    | "unknown"
    | "skipped";
  error?: DocumentError;
  response?: IngestionResponse;
  location?: UploadLocation;
};

export class DocumentUploadQueue {
  items: QueuedDocumentUpload[] = [];
  private active = new Map<string, AbortController>();
  private workspaceScope: string;
  private published = false;

  constructor(
    private client: DocumentsClient | (() => DocumentsClient),
    private context: () => LiveDocumentsContext,
    private onChange: () => void,
    private onPublished: (response: IngestionResponse) => void,
    private onSettled: () => void,
  ) {
    this.workspaceScope = this.scope();
  }

  get busy() {
    return this.items.some((item) =>
      ["queued", "submitting"].includes(item.phase),
    );
  }

  private scope() {
    const context = this.context();
    return JSON.stringify([context.mode, context.workspaceId]);
  }

  private available() {
    const context = this.context();
    return (
      context.mode === "live" &&
      Boolean(context.workspaceId) &&
      context.capabilities?.service_state === "running" &&
      context.capabilities.features.upload === true
    );
  }

  contextChanged() {
    if (this.workspaceScope !== this.scope()) {
      this.stop(false);
      this.items = [];
      this.published = false;
      this.workspaceScope = this.scope();
      this.onChange();
    } else if (!this.available()) {
      this.stop();
    } else {
      this.pump();
    }
  }

  choose(files: File[]) {
    if (this.busy || !files.length || !this.available()) return;
    const groupId = crypto.randomUUID();
    const totals = new Map<string, number>();
    for (const file of files) {
      const folders = file.webkitRelativePath?.split("/").slice(0, -1) ?? [];
      folders.forEach((_, index) => {
        const path = folders.slice(0, index + 1).join("/");
        totals.set(path, (totals.get(path) ?? 0) + 1);
      });
    }
    this.items = files.map((file) => {
      const folders = file.webkitRelativePath?.split("/").slice(0, -1) ?? [];
      const message = validateDocumentFile(
        file,
        this.context().capabilities?.pdf_ingestion?.available === true,
      );
      return {
        id: crypto.randomUUID(),
        path: file.webkitRelativePath || file.name,
        file: message ? null : file,
        phase: message ? "skipped" : "ready",
        ...(folders.length
          ? {
              location: {
                group_id: groupId,
                path: file.webkitRelativePath,
                folder_totals: folders.map((_, index) =>
                  totals.get(folders.slice(0, index + 1).join("/"))!,
                ),
              },
            }
          : {}),
        ...(message
          ? { error: { code: "INVALID_FILE", message, retryable: false } }
          : {}),
      };
    });
    this.onChange();
  }

  start() {
    if (!this.available()) return;
    this.items = this.items.map((item) =>
      item.phase === "ready" ? { ...item, phase: "queued" } : item,
    );
    this.onChange();
    this.pump();
  }

  retry(id: string) {
    if (!this.available()) return;
    const item = this.items.find((entry) => entry.id === id);
    if (
      !item?.file ||
      !(
        item.phase === "unknown" ||
        (item.phase === "failed" && item.error?.retryable)
      )
    )
      return;
    this.update(id, { phase: "queued", error: undefined });
    this.pump();
  }

  stop(notify = true) {
    for (const controller of this.active.values()) controller.abort();
    this.active.clear();
    this.items = this.items.map((item) =>
      item.phase === "submitting"
        ? {
            ...item,
            phase: "unknown",
            error: {
              code: "UPLOAD_OUTCOME_UNKNOWN",
              message:
                "Stopped locally. The server outcome is unconfirmed; retry the same operation to confirm it.",
              retryable: true,
            },
          }
        : item.phase === "queued"
          ? { ...item, phase: "ready" }
          : item,
    );
    if (notify) {
      this.onChange();
      this.settled();
    }
  }

  private update(id: string, change: Partial<QueuedDocumentUpload>) {
    this.items = this.items.map((item) =>
      item.id === id ? { ...item, ...change } : item,
    );
    this.onChange();
  }

  private pump() {
    if (!this.available()) return;
    // The HTTP boundary admits at most two concurrent uploads.
    while (this.active.size < 2) {
      const item = this.items.find((entry) => entry.phase === "queued");
      if (!item) break;
      const controller = new AbortController();
      this.active.set(item.id, controller);
      this.update(item.id, { phase: "submitting", error: undefined });
      void this.submit(item, controller);
    }
    if (!this.busy) this.settled();
  }

  private settled() {
    if (!this.published) return;
    this.published = false;
    this.onSettled();
  }

  private async submit(
    item: QueuedDocumentUpload,
    controller: AbortController,
  ) {
    const context = this.context();
    const current = () =>
      this.active.get(item.id) === controller &&
      this.workspaceScope === this.scope();
    try {
      if (!item.file || !context.workspaceId) return;
      const client =
        typeof this.client === "function" ? this.client() : this.client;
      const response = await client.uploadDocument(
        context.workspaceId,
        {
          file: item.file,
          idempotencyKey: item.id,
          pdfAvailable: context.capabilities?.pdf_ingestion?.available === true,
          ...(item.location &&
          context.capabilities?.features.upload_folders === true
            ? { uploadLocation: item.location }
            : {}),
        },
        { signal: controller.signal },
      );
      if (!current()) return;
      if (response.workspace_id !== context.workspaceId)
        throw new WorkbenchApiError(
          "The upload response belongs to a different workspace.",
          { kind: "protocol", code: "UPLOAD_SCOPE_CHANGED", retryable: true },
        );
      this.update(item.id, { phase: "succeeded", file: null, response });
      this.published = true;
      this.onPublished(response);
    } catch (error) {
      if (!current()) return;
      const details = documentError(error);
      const uncertain =
        !(error instanceof WorkbenchApiError) ||
        ["transport", "timeout", "cancelled", "protocol"].includes(
          error.kind,
        ) ||
        error.httpStatus === 504;
      this.update(item.id, {
        phase: uncertain ? "unknown" : "failed",
        error: uncertain
          ? {
              ...details,
              message:
                "The server outcome is unconfirmed. Retry this operation with the same file and key.",
              retryable: true,
            }
          : details,
      });
    } finally {
      if (current()) {
        this.active.delete(item.id);
        this.pump();
      }
    }
  }
}
