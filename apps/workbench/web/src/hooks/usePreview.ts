import { useEffect, useRef, useState } from "react";
import {
  createPreviewRun,
  completePreviewNode,
  finishPreviewRun,
} from "../domain/preview";
import { topologicalNodeIds } from "../domain/graph";
import type { Pipeline, PreviewRun, WorkbenchSettings } from "../domain/types";

function pause(milliseconds: number, signal: AbortSignal): Promise<boolean> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve(false);
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", cancel);
      resolve(true);
    }, milliseconds);
    function cancel() {
      window.clearTimeout(timer);
      resolve(false);
    }
    signal.addEventListener("abort", cancel, { once: true });
  });
}

export function usePreview(
  setRuns: React.Dispatch<React.SetStateAction<PreviewRun[]>>,
) {
  const controller = useRef<AbortController | null>(null);
  const [runningNodeId, setRunningNodeId] = useState<string | null>(null);
  const [liveRunId, setLiveRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => () => controller.current?.abort(), []);

  async function runPipeline(pipeline: Pipeline, settings: WorkbenchSettings) {
    if (controller.current) return;
    let run = createPreviewRun(pipeline);
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setLiveRunId(run.id);
    setRuns((previous) => [run, ...previous]);
    try {
      for (const nodeId of topologicalNodeIds(pipeline.graph)) {
        const node = pipeline.graph.nodes.find((item) => item.id === nodeId)!;
        setRunningNodeId(nodeId);
        if (!(await pause(settings.previewDelay, abort.signal))) break;
        const result = completePreviewNode(run, node, settings.previewScenario);
        run = { ...run, nodes: [...run.nodes, result] };
        const currentRun = run;
        setRuns((previous) =>
          previous.map((item) =>
            item.id === currentRun.id ? currentRun : item,
          ),
        );
        if (result.status === "error") break;
      }
      run = abort.signal.aborted
        ? {
            ...run,
            status: "Cancelled",
            durationMs: run.nodes.reduce(
              (sum, node) => sum + node.durationMs,
              0,
            ),
          }
        : finishPreviewRun(run, settings.previewScenario, settings.resultLimit);
      const finalRun = run;
      setRuns((previous) =>
        previous.map((item) => (item.id === finalRun.id ? finalRun : item)),
      );
    } finally {
      controller.current = null;
      setBusy(false);
      setRunningNodeId(null);
    }
  }

  return {
    runPipeline,
    stop: () => controller.current?.abort(),
    runningNodeId,
    liveRunId,
    busy,
  };
}
