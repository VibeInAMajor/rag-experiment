import { useEffect, useRef, useState } from "react";
import {
  createWorkbenchApiClient,
  type WorkbenchApiClient,
} from "../api/client";
import {
  BackendDiscovery,
  initialDiscoveryState,
  type BackendDiscoveryState,
} from "../domain/backendDiscovery";
import type { ExecutionMode } from "../domain/types";

export type { BackendDiscoveryState } from "../domain/backendDiscovery";

export function useBackendDiscovery(
  mode: ExecutionMode,
  options: { client?: WorkbenchApiClient } = {},
) {
  const [state, setState] = useState<BackendDiscoveryState>(
    initialDiscoveryState,
  );
  const discovery = useRef<BackendDiscovery | null>(null);
  if (!discovery.current)
    discovery.current = new BackendDiscovery(
      options.client ?? createWorkbenchApiClient,
      setState,
    );
  const activeMode = useRef(mode);
  activeMode.current = mode;
  const requests = discovery.current;
  useEffect(() => {
    if (mode === "live") void requests.refresh();
    else requests.reset();
    return () => requests.invalidate();
  }, [mode, requests]);
  const visibleState: BackendDiscoveryState =
    mode === "preview" ? initialDiscoveryState() : state;
  return {
    state: visibleState,
    refresh() {
      if (activeMode.current === "live") void discovery.current?.refresh();
    },
    selectWorkspace(workspaceId: string) {
      if (activeMode.current === "live")
        discovery.current?.selectWorkspace(workspaceId);
    },
    selectProfile(profileId: string) {
      if (activeMode.current === "live")
        discovery.current?.selectProfile(profileId);
    },
  };
}
