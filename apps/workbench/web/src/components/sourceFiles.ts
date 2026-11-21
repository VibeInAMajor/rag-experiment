import { WorkbenchApiError, type WorkbenchApiClient } from "../api/client";
import type { LocalSourceFile, SourceRevealResponse } from "../api/contracts";

export type SourceFileIdentity = {
  workspaceId: string;
  sourceId: string;
  versionId: string;
};
export type SourceFileClient = Pick<
  WorkbenchApiClient,
  "getLocalFile" | "revealLocalFile"
>;
type ClientFactory = SourceFileClient | (() => SourceFileClient);
type Lookup = {
  identity: SourceFileIdentity;
  controller: AbortController;
  started: boolean;
  users: number;
  settled: boolean;
  promise: Promise<LocalSourceFile>;
  resolve: (value: LocalSourceFile) => void;
  reject: (error: unknown) => void;
};

function cancelled() {
  return new WorkbenchApiError("Source request cancelled.", {
    kind: "cancelled",
    code: "CANCELLED",
  });
}

export class SourceFilesRequests {
  private lookups = new Map<string, Lookup>();
  private queue: Lookup[] = [];
  private active = 0;

  constructor(private client: ClientFactory) {}

  private api() {
    return typeof this.client === "function" ? this.client() : this.client;
  }
  private key(identity: SourceFileIdentity) {
    return JSON.stringify([
      identity.workspaceId,
      identity.sourceId,
      identity.versionId,
    ]);
  }

  lookup(
    identity: SourceFileIdentity,
    signal: AbortSignal,
  ): Promise<LocalSourceFile> {
    if (signal.aborted) return Promise.reject(cancelled());
    const key = this.key(identity);
    let job = this.lookups.get(key);
    if (!job) {
      let resolve!: Lookup["resolve"];
      let reject!: Lookup["reject"];
      const promise = new Promise<LocalSourceFile>((done, fail) => {
        resolve = done;
        reject = fail;
      });
      job = {
        identity,
        controller: new AbortController(),
        started: false,
        users: 0,
        settled: false,
        promise,
        resolve,
        reject,
      };
      this.lookups.set(key, job);
      this.queue.push(job);
    }
    const current = job;
    current.users++;
    const result = new Promise<LocalSourceFile>((resolve, reject) => {
      let finished = false;
      const finish = (callback: () => void) => {
        if (finished) return;
        finished = true;
        signal.removeEventListener("abort", onAbort);
        current.users--;
        if (!current.users && !current.settled) {
          current.controller.abort();
          if (this.lookups.get(key) === current) this.lookups.delete(key);
          if (!current.started) current.reject(cancelled());
        }
        callback();
      };
      const onAbort = () => finish(() => reject(cancelled()));
      signal.addEventListener("abort", onAbort, { once: true });
      current.promise.then(
        (value) => finish(() => resolve(value)),
        (error: unknown) => finish(() => reject(error)),
      );
    });
    this.pump();
    return result;
  }

  private pump() {
    while (this.active < 4 && this.queue.length) {
      const job = this.queue.shift();
      if (!job || job.controller.signal.aborted) continue;
      job.started = true;
      this.active++;
      const { workspaceId, sourceId, versionId } = job.identity;
      void Promise.resolve()
        .then(() =>
          this.api().getLocalFile(workspaceId, sourceId, versionId, {
            signal: job.controller.signal,
          }),
        )
        .then(
          (value) => {
            job.settled = true;
            job.resolve(value);
          },
          (error: unknown) => {
            job.settled = true;
            job.reject(error);
          },
        )
        .finally(() => {
          this.active--;
          const key = this.key(job.identity);
          if (this.lookups.get(key) === job) this.lookups.delete(key);
          this.pump();
        });
    }
  }

  reveal(
    identity: SourceFileIdentity,
    signal: AbortSignal,
  ): Promise<SourceRevealResponse> {
    return this.api().revealLocalFile(
      identity.workspaceId,
      identity.sourceId,
      identity.versionId,
      { signal },
    );
  }

  clear() {
    for (const job of this.lookups.values()) {
      job.controller.abort();
      job.reject(cancelled());
    }
    this.lookups.clear();
    this.queue = [];
  }
}

export class SourceRevealRequest {
  private pending?: Promise<SourceRevealResponse>;
  private controller?: AbortController;
  constructor(
    private requests: SourceFilesRequests,
    private identity: SourceFileIdentity,
  ) {}
  get busy() {
    return Boolean(this.pending);
  }
  run(): Promise<SourceRevealResponse> {
    if (this.pending) return this.pending;
    const controller = new AbortController();
    this.controller = controller;
    const pending = Promise.resolve()
      .then(() => this.requests.reveal(this.identity, controller.signal))
      .finally(() => {
        if (this.pending === pending) {
          this.pending = undefined;
          this.controller = undefined;
        }
      });
    this.pending = pending;
    return pending;
  }
  stop() {
    this.controller?.abort();
  }
}
