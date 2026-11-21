import { useEffect, useRef, useState } from "react";
import {
  createWorkbenchApiClient,
  type WorkbenchApiClient,
} from "../api/client";
import {
  LiveSearchRequests,
  liveContextFingerprint,
  type LiveRunUpdate,
  type LiveSearchContext,
} from "../domain/liveSearch";

export function useLiveSearch(
  context: LiveSearchContext,
  setRuns: LiveRunUpdate,
  options: {
    client?: Pick<WorkbenchApiClient, "search">;
    onInvalidateDiscovery?: () => void;
  } = {},
) {
  const [, setRevision] = useState(0);
  const activeContext = useRef(context);
  activeContext.current = context;
  const invalidate = useRef(options.onInvalidateDiscovery);
  invalidate.current = options.onInvalidateDiscovery;
  const requests = useRef<LiveSearchRequests | null>(null);
  if (!requests.current)
    requests.current = new LiveSearchRequests(
      options.client ?? createWorkbenchApiClient,
      setRuns,
      () => activeContext.current,
      () => setRevision((value) => value + 1),
      () => invalidate.current?.(),
    );
  const lifecycle = requests.current;
  const fingerprint = liveContextFingerprint(context);
  useEffect(() => {
    lifecycle.contextChanged();
  }, [lifecycle, fingerprint]);
  useEffect(() => () => lifecycle.stop(false), [lifecycle]);
  return {
    busy: lifecycle.busy,
    activeRunId: lifecycle.activeRunId,
    run: (...args: Parameters<LiveSearchRequests["run"]>) =>
      lifecycle.run(...args),
    stop: () => lifecycle.stop(),
  };
}
