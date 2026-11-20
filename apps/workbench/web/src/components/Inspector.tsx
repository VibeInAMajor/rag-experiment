import { Copy, Link2, Trash2, X } from "lucide-react";
import { getDefinition } from "../domain/catalog";
import type { Graph, WorkbenchNode } from "../domain/types";
import type { GraphUpdate } from "../hooks/useGraphHistory";
import { NodeIcon } from "./NodeIcon";

type Props = {
  node: WorkbenchNode;
  graph: Graph;
  disabled: boolean;
  onChange: (update: GraphUpdate) => void;
  onConnect: (
    source: string,
    sourceHandle: string,
    target: string,
    targetHandle: string,
  ) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onClose: () => void;
};

export function Inspector({
  node,
  graph,
  disabled,
  onChange,
  onConnect,
  onDelete,
  onDuplicate,
  onClose,
}: Props) {
  const definition = getDefinition(node.data.kind);
  const edit = (key: string, value: string | number) =>
    onChange((current) => ({
      ...current,
      nodes: current.nodes.map((item) =>
        item.id === node.id
          ? {
              ...item,
              data: {
                ...item.data,
                parameters: { ...item.data.parameters, [key]: value },
              },
            }
          : item,
      ),
    }));
  return (
    <aside className="inspector" aria-label="Node inspector">
      <div className="panel-heading">
        <span>Configuration</span>
        <button
          className="icon-button"
          onClick={onClose}
          title="Close inspector"
          aria-label="Close inspector"
        >
          <X size={16} />
        </button>
      </div>
      <div className="inspector-identity">
        <span className="node-icon">
          <NodeIcon kind={node.data.kind} size={21} />
        </span>
        <div>
          <strong>{definition.label}</strong>
          <span className="mono">{definition.component}</span>
        </div>
      </div>
      <fieldset disabled={disabled} className="inspector-fields">
        <label className="field">
          Name
          <input
            className="input"
            value={node.data.label}
            maxLength={200}
            onBlur={() => {
              if (!node.data.label.trim())
                onChange((current) => ({
                  ...current,
                  nodes: current.nodes.map((item) =>
                    item.id === node.id
                      ? {
                          ...item,
                          data: { ...item.data, label: definition.label },
                        }
                      : item,
                  ),
                }));
            }}
            onChange={(event) =>
              onChange((current) => ({
                ...current,
                nodes: current.nodes.map((item) =>
                  item.id === node.id
                    ? {
                        ...item,
                        data: { ...item.data, label: event.target.value },
                      }
                    : item,
                ),
              }))
            }
          />
        </label>
        {definition.parameters.map((parameter) => (
          <label className="field" key={parameter.key}>
            {parameter.label}
            {parameter.required && (
              <span className="required-mark" aria-hidden="true">
                *
              </span>
            )}
            {parameter.type === "textarea" ? (
              <textarea
                className="input"
                rows={4}
                value={node.data.parameters[parameter.key] ?? ""}
                onChange={(event) => edit(parameter.key, event.target.value)}
              />
            ) : parameter.type === "select" ? (
              <select
                className="input"
                value={node.data.parameters[parameter.key] ?? ""}
                onChange={(event) => edit(parameter.key, event.target.value)}
              >
                {parameter.options?.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            ) : (
              <input
                className={`input ${parameter.type === "number" ? "mono" : ""}`}
                type={parameter.type}
                min={parameter.min}
                value={node.data.parameters[parameter.key] ?? ""}
                onChange={(event) =>
                  edit(
                    parameter.key,
                    parameter.type === "number" && event.target.value !== ""
                      ? Number(event.target.value)
                      : event.target.value,
                  )
                }
              />
            )}
          </label>
        ))}
      </fieldset>
      <section className="inspector-connections">
        <h3>
          <Link2 size={14} />
          Connections
        </h3>
        {definition.inputs.length === 0 && (
          <p className="muted-note">This node starts the pipeline.</p>
        )}
        {definition.inputs.map((input) => {
          const existing = graph.edges.filter(
            (edge) => edge.target === node.id && edge.targetHandle === input.id,
          );
          const selected =
            !input.multiple && existing[0]
              ? `${existing[0].source}::${existing[0].sourceHandle}`
              : "";
          return (
            <div className="connection-field" key={input.id}>
              <label className="field">
                <span className="connection-label">
                  <span>{input.label}</span>
                  <span className="mono">{input.valueKind}</span>
                </span>
                <select
                  className="input"
                  disabled={disabled}
                  aria-label={`Connect ${node.data.label} ${input.label}`}
                  value={selected}
                  onChange={(event) => {
                    if (!event.target.value) {
                      if (!input.multiple)
                        onChange((current) => ({
                          ...current,
                          edges: current.edges.filter(
                            (edge) =>
                              edge.target !== node.id ||
                              edge.targetHandle !== input.id,
                          ),
                        }));
                      return;
                    }
                    const [source, handle] = event.target.value.split("::");
                    onConnect(source, handle, node.id, input.id);
                  }}
                >
                  <option value="">
                    {input.multiple ? "Add connection…" : "Select an output…"}
                  </option>
                  {graph.nodes
                    .filter((item) => item.id !== node.id)
                    .flatMap((item) =>
                      getDefinition(item.data.kind)
                        .outputs.filter(
                          (port) => port.valueKind === input.valueKind,
                        )
                        .map((port) => (
                          <option
                            key={`${item.id}-${port.id}`}
                            value={`${item.id}::${port.id}`}
                          >
                            {item.data.label} / {port.label}
                          </option>
                        )),
                    )}
                </select>
              </label>
              {existing.map((edge) => (
                <div className="connection-chip" key={edge.id}>
                  <span>
                    {
                      graph.nodes.find((item) => item.id === edge.source)?.data
                        .label
                    }
                  </span>
                  <button
                    className="icon-button"
                    disabled={disabled}
                    aria-label={`Disconnect ${edge.sourceHandle} from ${node.data.label}`}
                    title="Disconnect"
                    onClick={() =>
                      onChange((current) => ({
                        ...current,
                        edges: current.edges.filter(
                          (item) => item.id !== edge.id,
                        ),
                      }))
                    }
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </section>
      <div className="inspector-actions">
        <button
          className="button small"
          disabled={disabled}
          onClick={onDuplicate}
        >
          <Copy size={14} />
          Duplicate
        </button>
        <button
          className="icon-button destructive"
          disabled={disabled}
          title="Delete node"
          aria-label="Delete node"
          onClick={onDelete}
        >
          <Trash2 size={16} />
        </button>
      </div>
    </aside>
  );
}
