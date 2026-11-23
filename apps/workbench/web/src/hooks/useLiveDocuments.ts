import { useEffect, useRef, useState } from "react";
import { createWorkbenchApiClient } from "../api/client";
import type { IngestionResponse } from "../api/contracts";
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
  const fingerprint = documentsContextFingerprint(context);
  const renderedFingerprint = useRef(fingerprint);
  useEffect(() => {
    lifecycle.start();
    return () => lifecycle.stop(false);
  }, [lifecycle]);
  useEffect(() => {
    renderedFingerprint.current = fingerprint;
    lifecycle.contextChanged();
  }, [lifecycle, fingerprint]);
  // The effect clears old state; this guard also hides it in the first render of a new scope.
  const state =
    renderedFingerprint.current === fingerprint
      ? lifecycle.state
      : emptyLiveDocuments();
  return {
    ...state,
    refresh: () => lifecycle.refresh(),
    loadMore: () => lifecycle.loadMore(),
    selectSource: (id: string | null) => lifecycle.selectSource(id),
    refreshSelected: () => lifecycle.refreshSelected(),
    loadMoreChunks: () => lifecycle.loadMoreChunks(),
    inspectJob: (id?: string) => lifecycle.inspectJob(id),
    chooseFile: (file: File | null, replace = false) =>
      lifecycle.chooseFile(file, replace),
    submitUpload: () => lifecycle.submitUpload(),
    retryUpload: () => lifecycle.retryUpload(),
    stopUpload: () => lifecycle.stopUpload(),
    clearUpload: () => lifecycle.clearUpload(),
  };
}
export type LiveDocumentsModel = ReturnType<typeof useLiveDocuments>;
export type { LiveDocumentsContext } from "../domain/liveDocuments";
