import { useEffect, useRef, useState } from "react";
import {
  createWorkbenchApiClient,
  WorkbenchApiError,
  type AgentRunOptions,
} from "../api/client";
import type {
  AgentCatalog,
  AgentEvent,
  AgentRun,
  AgentRunPage,
  AgentSelection,
} from "../api/contracts";

export function isAgentRunActive(run: AgentRun): boolean {
  return run.status === "queued" || run.status === "running";
}

type Timeline = {
  run: AgentRun;
  events: AgentEvent[];
  cursor: string | null;
  hasMore: boolean;
};

type OperationsState = {
  connection: "loading" | "connected" | "unavailable" | "disconnected";
  catalog: AgentCatalog | null;
  currentRun: AgentRun | null;
  history: AgentRunPage | null;
  historyKey: string;
  timeline: Timeline | null;
  updatedAt: number | null;
};

const initialState: OperationsState = {
  connection: "loading",
  catalog: null,
  currentRun: null,
  history: null,
  historyKey: "",
  timeline: null,
  updatedAt: null,
};

const detailLimit = 50;
const maxVisibleEvents = 300;

export function useAgentOperations(
  { agentId, model, status, cursor }: AgentRunOptions,
  selectedRunId: string | null,
  onHistoryReset: () => void,
) {
  const [client] = useState(createWorkbenchApiClient);
  const [state, setState] = useState(initialState);
  const [refreshId, setRefreshId] = useState(0);
  const [saving, setSaving] = useState(false);
  const [selectionMessage, setSelectionMessage] = useState("");
  const selectionRequest = useRef<AbortController | null>(null);
  const activePoll = useRef<AbortController | null>(null);
  const cache = useRef<OperationsState>(initialState);
  const historyKey = JSON.stringify([agentId, model, status, cursor]);
  const refresh = () => setRefreshId((value) => value + 1);

  useEffect(() => {
    return () => selectionRequest.current?.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    activePoll.current = controller;
    const { signal } = controller;
    let timer: ReturnType<typeof setTimeout>;
    let delay = 0;
    let catalogAt = 0;
    let errors = 0;

    const publish = (next: OperationsState) => {
      if (signal.aborted) return;
      cache.current = next;
      setState(next);
    };

    async function poll() {
      if (document.hidden) return;
      const prior = cache.current;
      let catalog = prior.catalog;
      try {
        if (!catalog || Date.now() - catalogAt > 30_000) {
          catalog = await client.getAgentCatalog({ signal });
          catalogAt = Date.now();
        }
        if (!catalog.history_available) {
          publish({
            ...initialState,
            connection: "connected",
            catalog,
            updatedAt: Date.now(),
          });
          delay = 5000;
          return;
        }
        const effectiveAgentId = agentId ?? catalog.agents[0]?.agent_id;
        const head = await client.listAgentRuns({
          agentId: effectiveAgentId,
          limit: 20,
          signal,
        });
        const currentRun =
          head.runs.find(isAgentRunActive) ?? head.runs[0] ?? null;
        const history =
          model || status || cursor
            ? await client.listAgentRuns({
                agentId: effectiveAgentId,
                model,
                status,
                cursor,
                limit: 20,
                signal,
              })
            : head;
        const selected = selectedRunId ?? currentRun?.run_id ?? null;
        const candidate = [...head.runs, ...history.runs].find(
          (run) => run.run_id === selected,
        );
        let timeline =
          prior.timeline?.run.run_id === selected ? prior.timeline : null;
        if (
          selected &&
          (!timeline ||
            timeline.hasMore ||
            (candidate?.last_sequence ?? timeline.run.last_sequence) !==
              timeline.run.last_sequence ||
            isAgentRunActive(timeline.run))
        ) {
          try {
            const update = await client.getAgentRun(selected, {
              signal,
              cursor: timeline?.cursor ?? undefined,
              limit: detailLimit,
            });
            const last = timeline?.events.at(-1)?.sequence ?? 0;
            if (
              update.events.length &&
              update.events[0].sequence !== last + 1
            ) {
              timeline = null;
            } else {
              timeline = {
                run: update.run,
                events: [...(timeline?.events ?? []), ...update.events].slice(
                  -maxVisibleEvents,
                ),
                cursor: update.next_cursor,
                hasMore: update.has_more,
              };
            }
          } catch (error) {
            if (
              !(error instanceof WorkbenchApiError) ||
              (error.code !== "AGENT_RUN_NOT_FOUND" && error.httpStatus !== 400)
            )
              throw error;
            timeline = null;
          }
        }
        errors = 0;
        publish({
          connection: "connected",
          catalog,
          currentRun,
          history,
          historyKey,
          timeline,
          updatedAt: Date.now(),
        });
        delay = timeline?.hasMore
          ? 30
          : (currentRun && isAgentRunActive(currentRun)) ||
              (timeline && isAgentRunActive(timeline.run))
            ? 1000
            : 3500;
      } catch (error) {
        if (signal.aborted) return;
        errors += 1;
        catalogAt = 0;
        if (
          error instanceof WorkbenchApiError &&
          error.code === "INVALID_AGENT_CURSOR" &&
          cursor
        ) {
          onHistoryReset();
        } else if (
          error instanceof WorkbenchApiError &&
          (error.code === "AGENT_OPERATIONS_UNAVAILABLE" ||
            error.code === "AGENT_HISTORY_UNAVAILABLE" ||
            error.code === "AGENT_OPERATIONS_SAME_ORIGIN_REQUIRED" ||
            error.httpStatus === 404)
        ) {
          const availableCatalog =
            error.code === "AGENT_HISTORY_UNAVAILABLE" ? catalog : null;
          publish({
            ...initialState,
            connection: "unavailable",
            catalog: availableCatalog,
          });
        } else {
          publish({ ...prior, catalog, connection: "disconnected" });
        }
        delay = Math.min(15_000, 1000 * 2 ** Math.min(errors, 4));
      } finally {
        if (!signal.aborted && !document.hidden)
          timer = setTimeout(() => void poll(), delay);
      }
    }

    const reconnect = () => {
      if (!document.hidden) setRefreshId((value) => value + 1);
    };
    const visibilityChanged = () => setRefreshId((value) => value + 1);
    document.addEventListener("visibilitychange", visibilityChanged);
    window.addEventListener("online", reconnect);
    if (!document.hidden && !selectionRequest.current) void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visibilityChanged);
      window.removeEventListener("online", reconnect);
    };
  }, [
    client,
    refreshId,
    agentId,
    model,
    status,
    cursor,
    selectedRunId,
    historyKey,
    onHistoryReset,
  ]);

  async function selectProfile(
    agent: string,
    profile: string,
    current: AgentSelection,
  ) {
    if (selectionRequest.current || profile === current.profile_id) return;
    activePoll.current?.abort();
    const controller = new AbortController();
    selectionRequest.current = controller;
    setSaving(true);
    setSelectionMessage("");
    try {
      await client.saveAgentSelection(agent, profile, current.revision, {
        signal: controller.signal,
      });
      if (!controller.signal.aborted)
        setSelectionMessage("Saved for the next eligible run.");
    } catch (error) {
      if (!controller.signal.aborted) {
        setSelectionMessage(
          error instanceof WorkbenchApiError && error.httpStatus === 409
            ? "The selection changed or is unavailable. Review the refreshed profiles."
            : "Could not confirm the selection. The saved profile will be refreshed.",
        );
      }
    } finally {
      selectionRequest.current = null;
      if (!controller.signal.aborted) {
        setSaving(false);
        refresh();
      }
    }
  }

  return {
    ...state,
    history: state.historyKey === historyKey ? state.history : null,
    timeline:
      state.timeline?.run.run_id === (selectedRunId ?? state.currentRun?.run_id)
        ? state.timeline
        : null,
    refresh,
    saving,
    selectionMessage,
    selectProfile,
  };
}
