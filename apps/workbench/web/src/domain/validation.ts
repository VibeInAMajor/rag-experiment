import type { Graph } from "./types";
import { portableGraph } from "./graph";

export const capabilityVersion = "workbench-components-v1";
export type ValidationIssue = {
  code: string;
  message: string;
  nodeId?: string;
  edgeId?: string;
  field?: string;
};
export type ValidationResponse = {
  status: "valid" | "invalid" | "unsupported";
  issues: ValidationIssue[];
  requestId: string;
  validator: "haystack";
  capabilityVersion: string;
  mode: "draft" | "complete";
};
export type ValidationState = {
  status:
    "unchecked" | "checking" | "unavailable" | ValidationResponse["status"];
  issues: ValidationIssue[];
};

export async function requestValidation(
  graph: Graph,
  signal: AbortSignal,
  mode: "draft" | "complete" = "complete",
): Promise<ValidationResponse> {
  const requestId = crypto.randomUUID();
  const deadline = new AbortController();
  const timer = setTimeout(
    () =>
      deadline.abort(new DOMException("Validation timed out.", "TimeoutError")),
    3000,
  );
  try {
    const response = await fetch("/api/pipelines/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.any([signal, deadline.signal]),
      body: JSON.stringify({
        schemaVersion: 1,
        graph: portableGraph(graph),
        requestId,
        mode,
      }),
    });
    if (!response.ok)
      throw new Error(
        "Validation service unavailable. Start the local validator and retry.",
      );
    const value: unknown = await response.json();
    if (!value || typeof value !== "object")
      throw new Error("Invalid validator response.");
    const item = value as Record<string, unknown>;
    if (
      item.validator !== "haystack" ||
      item.requestId !== requestId ||
      item.capabilityVersion !== capabilityVersion ||
      item.mode !== mode ||
      !["valid", "invalid", "unsupported"].includes(String(item.status)) ||
      !Array.isArray(item.issues)
    )
      throw new Error(
        "Validator capability or response mismatch. Restart compatible frontend and validator.",
      );
    const issues: ValidationIssue[] = item.issues.map((issue: unknown) => {
      if (!issue || typeof issue !== "object")
        throw new Error("Invalid validator diagnostics.");
      const data = issue as Record<string, unknown>;
      if (
        typeof data.code !== "string" ||
        typeof data.message !== "string" ||
        ["nodeId", "edgeId", "field"].some(
          (key) => data[key] !== undefined && typeof data[key] !== "string",
        )
      )
        throw new Error("Invalid validator diagnostics.");
      return {
        code: data.code,
        message: data.message,
        ...(typeof data.nodeId === "string" ? { nodeId: data.nodeId } : {}),
        ...(typeof data.edgeId === "string" ? { edgeId: data.edgeId } : {}),
        ...(typeof data.field === "string" ? { field: data.field } : {}),
      };
    });
    if (item.status === "valid" && issues.length)
      throw new Error("Inconsistent validator result.");
    return {
      status: item.status as ValidationResponse["status"],
      issues,
      requestId,
      validator: "haystack",
      capabilityVersion,
      mode,
    };
  } finally {
    clearTimeout(timer);
  }
}

export class ValidationRequests {
  private generation = 0;
  private controller?: AbortController;
  invalidate() {
    this.generation++;
    this.controller?.abort();
  }
  async submit(graph: Graph): Promise<ValidationResponse | undefined> {
    this.invalidate();
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    try {
      const result = await requestValidation(graph, controller.signal);
      return generation === this.generation ? result : undefined;
    } catch (error) {
      if (generation !== this.generation) return undefined;
      throw error;
    }
  }
}
