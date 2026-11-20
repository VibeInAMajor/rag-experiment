import { useEffect, useRef, useState } from "react";
import { exportPipeline } from "../domain/graph";
import type { Graph, Pipeline } from "../domain/types";
import { ValidationRequests, type ValidationState } from "../domain/validation";

export function useValidation(pipeline: Pipeline) {
  const fingerprint = JSON.stringify({
    id: pipeline.id,
    nodes: pipeline.graph.nodes.map((node) => ({
      id: node.id,
      data: {
        kind: node.data.kind,
        label: node.data.label,
        parameters: node.data.parameters,
      },
    })),
    edges: pipeline.graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
    })),
  });
  const previousGraph = useRef(fingerprint);
  const revision = useRef(0);
  if (previousGraph.current !== fingerprint) {
    revision.current++;
    previousGraph.current = fingerprint;
  }
  const serialized = exportPipeline(pipeline);
  const snapshot = `${revision.current}:${fingerprint}`;
  const latest = useRef(snapshot);
  latest.current = snapshot;
  const requests = useRef(new ValidationRequests());
  const [result, setResult] = useState<{
    snapshot: string;
    state: ValidationState;
  } | null>(null);
  useEffect(() => {
    requests.current.invalidate();
    return () => requests.current.invalidate();
  }, [snapshot]);
  const state: ValidationState =
    result?.snapshot === snapshot
      ? result.state
      : { status: "unchecked", issues: [] };
  async function validate() {
    const submitted = snapshot;
    setResult({
      snapshot: submitted,
      state: { status: "checking", issues: [] },
    });
    const graph = (JSON.parse(serialized) as { pipeline: { graph: Graph } })
      .pipeline.graph;
    try {
      const response = await requests.current.submit(graph);
      if (response && latest.current === submitted)
        setResult({ snapshot: submitted, state: response });
    } catch (error) {
      if (latest.current === submitted)
        setResult({
          snapshot: submitted,
          state: {
            status: "unavailable",
            issues: [
              {
                code: "VALIDATION_UNAVAILABLE",
                message:
                  error instanceof Error && error.name !== "TimeoutError"
                    ? error.message
                    : "Validation timed out. Start the local validator and retry.",
              },
            ],
          },
        });
    }
  }
  return { state, validate };
}
