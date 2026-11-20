import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Check, CircleAlert, LoaderCircle } from "lucide-react";
import { getDefinition } from "../domain/catalog";
import type { WorkbenchNode } from "../domain/types";
import { NodeIcon } from "./NodeIcon";

export function PipelineNode({ data, selected }: NodeProps<WorkbenchNode>) {
  const definition = getDefinition(data.kind);
  const resource = ["files", "writer", "results"].includes(data.kind);
  return (
    <div
      className={`pipeline-node ${selected ? "selected" : ""} ${resource ? "resource" : ""} state-${data.status ?? "idle"}`}
    >
      <div className="node-heading">
        <span className="node-icon">
          <NodeIcon kind={data.kind} size={18} />
        </span>
        <span className="node-title">{data.label}</span>
        {data.status === "success" && (
          <Check
            size={14}
            className="node-state success-text"
            aria-label="Completed"
          />
        )}
        {data.status === "running" && (
          <LoaderCircle
            size={14}
            className="node-state spinning"
            aria-label="Running"
          />
        )}
        {data.status === "error" && (
          <CircleAlert
            size={14}
            className="node-state error-text"
            aria-label="Failed"
          />
        )}
      </div>
      <div className="node-component mono">{definition.component}</div>
      <div className="node-ports">
        <div>
          {definition.inputs.map((port) => (
            <div className="node-port input-port" key={port.id}>
              <Handle
                type="target"
                position={Position.Left}
                id={port.id}
                aria-label={`${data.label} input ${port.label}`}
              />
              <span>
                {port.label}
                {port.required && <span className="port-required">*</span>}
              </span>
            </div>
          ))}
        </div>
        <div>
          {definition.outputs.map((port) => (
            <div className="node-port output-port" key={port.id}>
              <span>{port.label}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={port.id}
                aria-label={`${data.label} output ${port.label}`}
              />
            </div>
          ))}
        </div>
      </div>
      {data.kind === "query" && (
        <div className="node-detail">{String(data.parameters.query ?? "")}</div>
      )}
      {["bm25", "vector", "joiner"].includes(data.kind) && (
        <div className="node-detail mono">
          {data.kind === "joiner"
            ? "RECIPROCAL RANK FUSION"
            : `TOP K ${data.parameters.topK ?? 20}`}
        </div>
      )}
      {data.kind === "chunker" && (
        <div className="node-detail mono">
          {data.parameters.size ?? 500} TOKENS · {data.parameters.overlap ?? 50}{" "}
          OVERLAP
        </div>
      )}
    </div>
  );
}
