import { useEffect, useRef, useState } from "react";
import { createWorkbenchApiClient } from "../api/client";
import type { IngestionResponse } from "../api/contracts";
import { DocumentUploadQueue } from "../domain/documentUploadQueue";
import {
  documentsContextFingerprint,
  emptyLiveDocuments,
  LiveDocumentsRequests,
  type DocumentsClient,
  type LiveDocumentsContext,
} from "../domain/liveDocuments";

export function useLiveDocuments(
  context: LiveDocumentsContext,
  options: {
    client?: DocumentsClient;
    onPublished?: (response: IngestionResponse) => void;
  } = {},
) {
  const [, setRevision] = useState(0);
  const currentContext = useRef(context);
  currentContext.current = context;
  const onPublished = useRef(options.onPublished);
  onPublished.current = options.onPublished;
  const requests = useRef<LiveDocumentsRequests | null>(null);
  if (!requests.current)
    requests.current = new LiveDocumentsRequests(
      options.client ?? createWorkbenchApiClient,
      () => currentContext.current,
      () => setRevision((value) => value + 1),
      (response) => onPublished.current?.(response),
    );
  const lifecycle = requests.current;
  const queueRef = useRef<DocumentUploadQueue | null>(null);
  if (!queueRef.current)
    queueRef.current = new DocumentUploadQueue(
      options.client ?? createWorkbenchApiClient,
      () => currentContext.current,
      () => setRevision((value) => value + 1),
      (response) => onPublished.current?.(response),
      () => {
        void lifecycle.refresh();
      },
    );
  const queue = queueRef.current;
  const fingerprint = documentsContextFingerprint(context);
  const renderedFingerprint = useRef(fingerprint);
  useEffect(() => {
    lifecycle.start();
    return () => {
      lifecycle.stop(false);
      queue.stop(false);
    };
  }, [lifecycle, queue]);
  useEffect(() => {
    renderedFingerprint.current = fingerprint;
    lifecycle.contextChanged();
    queue.contextChanged();
  }, [lifecycle, queue, fingerprint]);
  // The effect clears old state; this guard also hides it in the first render of a new scope.
  const state =
    renderedFingerprint.current === fingerprint
      ? lifecycle.state
      : emptyLiveDocuments();
  return {
    ...state,
    uploadQueue: renderedFingerprint.current === fingerprint ? queue.items : [],
    uploadQueueBusy: queue.busy,
    chooseFiles: (files: File[]) => queue.choose(files),
    startUploads: () => {
      if (lifecycle.state.upload.phase !== "submitting") queue.start();
    },
    stopUploads: () => queue.stop(),
    retryQueuedUpload: (id: string) => {
      if (lifecycle.state.upload.phase !== "submitting") queue.retry(id);
    },
    refresh: () => lifecycle.refresh(),
    loadMore: () => lifecycle.loadMore(),
    selectSource: (id: string | null) => lifecycle.selectSource(id),
    refreshSelected: () => lifecycle.refreshSelected(),
    loadMoreChunks: () => lifecycle.loadMoreChunks(),
    inspectJob: (id?: string) => lifecycle.inspectJob(id),
    chooseFile: (file: File | null, replace = false) => {
      if (!queue.busy) lifecycle.chooseFile(file, replace);
    },
    submitUpload: async () => {
      if (!queue.busy) await lifecycle.submitUpload();
    },
    retryUpload: async () => {
      if (!queue.busy) await lifecycle.retryUpload();
    },
    stopUpload: () => lifecycle.stopUpload(),
    clearUpload: () => lifecycle.clearUpload(),
  };
}
export type LiveDocumentsModel = ReturnType<typeof useLiveDocuments>;
export type { LiveDocumentsContext } from "../domain/liveDocuments";
