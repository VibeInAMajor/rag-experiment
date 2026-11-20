import { useCallback, useRef, useState } from "react";
import type { Graph, Pipeline } from "../domain/types";

export type GraphUpdate = Graph | ((graph: Graph) => Graph);

export function useGraphHistory(
  pipeline: Pipeline,
  setPipelines: React.Dispatch<React.SetStateAction<Pipeline[]>>,
) {
  const histories = useRef(
    new Map<string, { past: Graph[]; future: Graph[] }>(),
  );
  const [, refresh] = useState(0);
  const history = histories.current.get(pipeline.id) ?? {
    past: [],
    future: [],
  };
  const updateGraph = useCallback(
    (update: GraphUpdate, record = true) => {
      const current = histories.current.get(pipeline.id) ?? {
        past: [],
        future: [],
      };
      if (record) {
        current.past.push(structuredClone(pipeline.graph));
        current.past = current.past.slice(-60);
        current.future = [];
      }
      histories.current.set(pipeline.id, current);
      setPipelines((pipelines) =>
        pipelines.map((item) => {
          if (item.id !== pipeline.id) return item;
          return {
            ...item,
            updatedAt: new Date().toISOString(),
            graph: typeof update === "function" ? update(item.graph) : update,
          };
        }),
      );
    },
    [pipeline, setPipelines],
  );
  const travel = useCallback(
    (direction: "past" | "future") => {
      const current = histories.current.get(pipeline.id);
      const next = current?.[direction].pop();
      if (!next || !current) return;
      current[direction === "past" ? "future" : "past"].push(
        structuredClone(pipeline.graph),
      );
      setPipelines((pipelines) =>
        pipelines.map((item) =>
          item.id === pipeline.id
            ? { ...item, graph: next, updatedAt: new Date().toISOString() }
            : item,
        ),
      );
      refresh((value) => value + 1);
    },
    [pipeline, setPipelines],
  );
  return {
    updateGraph,
    undo: () => travel("past"),
    redo: () => travel("future"),
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
  };
}
