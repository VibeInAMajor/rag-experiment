import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  NodeChangeset,
  EdgeChangeset,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
} from "@xyflow/react";
import {
  ArrowDownToLine,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Layers,
  Maximize,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  Redo2,
  Search,
  Square,
  Undo2,
  Upload,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { catalog, createNode, getDefinition } from "../domain/catalog";
import { checkDraftConnection } from "../domain/graph";
import type {
  GraphIssue,
  NodeKind,
  Pipeline,
  PreviewRun,
  WorkbenchNode,
  WorkbenchSettings,
} from "../domain/types";
import type { GraphUpdate } from "../hooks/useGraphHistory";
import { PipelineNode } from "./PipelineNode";
import { NodeIcon } from "./NodeIcon";
import { Inspector } from "./Inspector";
import { ResultsPanel } from "./ResultsPanel";
import type { ValidationState } from "../domain/validation";

const nodeTypes = { workbench: PipelineNode };
const groups = ["Inputs", "Processing", "Retrieval", "Outputs"] as const;

function freePosition(
  nodes: WorkbenchNode[],
  preferred: { x: number; y: number },
) {
  for (let radius = 0; radius <= 12; radius++) {
    for (let row = -radius; row <= radius; row++) {
      for (let column = -radius; column <= radius; column++) {
        if (Math.max(Math.abs(row), Math.abs(column)) !== radius) continue;
        const candidate = {
          x: preferred.x + column * 256,
          y: preferred.y + row * 224,
        };
        if (
          nodes.every(
            (node) =>
              Math.abs(node.position.x - candidate.x) >= 248 ||
              Math.abs(node.position.y - candidate.y) >= 200,
          )
        )
          return candidate;
      }
    }
  }
  return {
    x: preferred.x,
    y: Math.max(0, ...nodes.map((node) => node.position.y)) + 224,
  };
}

type Props = {
  pipeline: Pipeline;
  settings: WorkbenchSettings;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onGraphChange: (update: GraphUpdate, record?: boolean) => void;
  onBack: () => void;
  onExport: () => void;
  onImport: (file: File) => void;
  onValidate: () => void;
  validationStatus: ValidationState["status"];
  onRun: () => void;
  onStop: () => void;
  onRename: (name: string) => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  busy: boolean;
  runningNodeId: string | null;
  run?: PreviewRun;
  issues: GraphIssue[];
  resultsOpen: boolean;
  onResultsOpen: (open: boolean) => void;
  notify: (message: string, error?: boolean) => void;
};

function Editor(props: Props) {
  const {
    pipeline,
    settings,
    onGraphChange,
    selectedNodeId,
    onSelectNode,
    busy,
  } = props;
  const [libraryOpen, setLibraryOpen] = useState(
    () => window.innerWidth >= 1280,
  );
  const [search, setSearch] = useState("");
  const [zoom, setZoom] = useState(100);
  const [renameOpen, setRenameOpen] = useState(false);
  const [selectedEdges, setSelectedEdges] = useState<string[]>([]);
  const importInput = useRef<HTMLInputElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const flow = useReactFlow<WorkbenchNode>();
  const selectedNode = pipeline.graph.nodes.find(
    (node) => node.id === selectedNodeId,
  );
  const initialLayout = useRef(true);
  useEffect(() => {
    if (initialLayout.current) {
      initialLayout.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      void flow.fitView({ padding: 40, maxZoom: 1, duration: 0 });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [props.resultsOpen, flow]);

  const nodes = useMemo(
    () =>
      pipeline.graph.nodes.map((node) => {
        const result = props.run?.nodes.find((item) => item.nodeId === node.id);
        return {
          ...node,
          ariaLabel: node.data.label,
          selected: node.id === selectedNodeId,
          data: {
            ...node.data,
            status:
              props.runningNodeId === node.id
                ? ("running" as const)
                : (result?.status ?? ("idle" as const)),
          },
        };
      }),
    [pipeline.graph.nodes, props.run, props.runningNodeId, selectedNodeId],
  );

  const insertNode = useCallback(
    (kind: NodeKind) => {
      if (pipeline.graph.nodes.length >= 100) {
        props.notify("A pipeline may contain up to 100 components.", true);
        return;
      }
      const wrapper = document
        .querySelector(".flow-canvas")
        ?.getBoundingClientRect();
      const position = flow.screenToFlowPosition({
        x: (wrapper?.left ?? 0) + (wrapper?.width ?? 800) / 2 - 108,
        y: (wrapper?.top ?? 0) + (wrapper?.height ?? 600) / 2 - 70,
      });
      const node = createNode(
        kind,
        freePosition(pipeline.graph.nodes, position),
      );
      onGraphChange((graph) => ({ ...graph, nodes: [...graph.nodes, node] }));
      onSelectNode(node.id);
      window.setTimeout(() => {
        void flow.fitView({ padding: 40, maxZoom: 1, duration: 0 });
      }, 80);
      if (window.innerWidth < 1280) setLibraryOpen(false);
    },
    [flow, onGraphChange, onSelectNode, pipeline.graph.nodes],
  );

  const deleteSelected = useCallback(() => {
    if (!selectedNodeId || busy) return;
    onGraphChange((graph) => ({
      ...graph,
      nodes: graph.nodes.filter((node) => node.id !== selectedNodeId),
      edges: graph.edges.filter(
        (edge) =>
          edge.source !== selectedNodeId && edge.target !== selectedNodeId,
      ),
    }));
    onSelectNode(null);
  }, [selectedNodeId, busy, onGraphChange, onSelectNode]);

  const duplicateSelected = useCallback(() => {
    if (!selectedNode || busy) return;
    if (pipeline.graph.nodes.length >= 100) {
      props.notify("A pipeline may contain up to 100 components.", true);
      return;
    }
    const node: WorkbenchNode = {
      ...structuredClone(selectedNode),
      id: crypto.randomUUID(),
      position: freePosition(pipeline.graph.nodes, {
        x: selectedNode.position.x + 40,
        y: selectedNode.position.y + 180,
      }),
      selected: false,
      data: {
        ...selectedNode.data,
        label: `${selectedNode.data.label.slice(0, 195)} copy`,
      },
    };
    onGraphChange((graph) => ({ ...graph, nodes: [...graph.nodes, node] }));
    onSelectNode(node.id);
  }, [selectedNode, busy, onGraphChange, onSelectNode]);

  useEffect(() => {
    const handleKeys = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement;
      if (element.closest('input, textarea, select, [contenteditable="true"]'))
        return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (!busy) event.shiftKey ? props.onRedo() : props.onUndo();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
        event.preventDefault();
        duplicateSelected();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        props.onExport();
      }
      if (event.key === "Escape") {
        onSelectNode(null);
        setLibraryOpen(false);
      }
      if (event.key === "/") {
        event.preventDefault();
        setLibraryOpen(true);
        requestAnimationFrame(() => searchInput.current?.focus());
      }
    };
    window.addEventListener("keydown", handleKeys);
    return () => window.removeEventListener("keydown", handleKeys);
  }, [busy, duplicateSelected, onSelectNode, props]);

  const connect = (connection: Connection, replace = false) => {
    const target = pipeline.graph.nodes.find(
      (node) => node.id === connection.target,
    );
    const multiple =
      target &&
      getDefinition(target.data.kind).inputs.find(
        (input) => input.id === connection.targetHandle,
      )?.multiple;
    const graph =
      replace && !multiple
        ? {
            ...pipeline.graph,
            edges: pipeline.graph.edges.filter(
              (edge) =>
                edge.target !== connection.target ||
                edge.targetHandle !== connection.targetHandle,
            ),
          }
        : pipeline.graph;
    if (graph.edges.length >= 300) {
      props.notify("A pipeline may contain up to 300 connections.", true);
      return;
    }
    const error = checkDraftConnection(graph, connection);
    if (error) {
      props.notify(error, true);
      return;
    }
    onGraphChange({
      ...graph,
      edges: addEdge(
        { ...connection, id: crypto.randomUUID(), type: "smoothstep" },
        graph.edges,
      ),
    });
  };

  const nodeChanges = (changes: NodeChangeset<WorkbenchNode>) => {
    const significant = changes
      .toArray()
      .filter(
        (change) => change.type !== "select" && change.type !== "dimensions",
      );
    const selected = changes
      .toArray()
      .find((change) => change.type === "select" && change.selected);
    if (selected && selected.type === "select") onSelectNode(selected.id);
    if (!significant.length) return;
    const record = significant.some(
      (change) => change.type !== "position" || change.dragging === undefined,
    );
    onGraphChange((graph) => {
      const nextNodes = new NodeChangeset(significant).applyTo(graph.nodes);
      return {
        ...graph,
        nodes: nextNodes,
        edges: graph.edges.filter(
          (edge) =>
            nextNodes.some((node) => node.id === edge.source) &&
            nextNodes.some((node) => node.id === edge.target),
        ),
      };
    }, record);
  };
  const edgeChanges = (changes: EdgeChangeset) => {
    for (const change of changes.getByType("select"))
      setSelectedEdges((ids) =>
        change.selected
          ? [...new Set([...ids, change.id])]
          : ids.filter((id) => id !== change.id),
      );
    const edits = changes
      .toArray()
      .filter((change) => change.type !== "select");
    if (edits.length)
      onGraphChange((graph) => ({
        ...graph,
        edges: new EdgeChangeset(edits).applyTo(graph.edges),
      }));
  };

  return (
    <div className="editor-page">
      <header className="editor-toolbar">
        <div className="editor-breadcrumb">
          <button
            className="icon-button"
            onClick={props.onBack}
            aria-label="Back to pipelines"
            title="Back to pipelines"
          >
            <ArrowLeft size={17} />
          </button>
          <span className="breadcrumb-parent">Pipelines</span>
          <span className="breadcrumb-slash">/</span>
          {renameOpen ? (
            <input
              className="pipeline-title-input input"
              aria-label="Pipeline name"
              defaultValue={pipeline.name}
              maxLength={100}
              autoFocus
              onBlur={(event) => {
                if (event.target.value.trim())
                  props.onRename(event.target.value.trim());
                setRenameOpen(false);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") setRenameOpen(false);
              }}
            />
          ) : (
            <button
              className="pipeline-title"
              onClick={() => setRenameOpen(true)}
              title="Rename pipeline"
            >
              {pipeline.name}
              <ChevronDown size={13} />
            </button>
          )}
          <span className="draft-label mono">DRAFT</span>
        </div>
        <div className="toolbar-actions">
          <span className="graph-count mono">
            {pipeline.graph.nodes.length} NODES
          </span>
          <button
            className="button small"
            onClick={props.onValidate}
            disabled={busy || props.validationStatus === "checking"}
          >
            <Check size={15} />
            {props.validationStatus === "checking" ? "Checking…" : "Validate"}
          </button>
          <span
            role="status"
            className={`status ${props.validationStatus === "valid" ? "success" : props.validationStatus === "unchecked" || props.validationStatus === "checking" ? "neutral" : "error"}`}
            title="Authoritative Haystack validation; preview is separate"
          >
            {props.validationStatus === "valid"
              ? "Haystack valid"
              : props.validationStatus === "unchecked"
                ? "Not checked"
                : props.validationStatus === "unavailable"
                  ? "Validator unavailable · retry"
                  : props.validationStatus === "unsupported"
                    ? "Unsupported nodes"
                    : props.validationStatus === "invalid"
                      ? "Invalid graph"
                      : "Checking Haystack"}
          </span>
          <button
            className="button small export-button"
            onClick={props.onExport}
          >
            <ArrowDownToLine size={14} />
            Export
          </button>
          {busy ? (
            <button className="button primary small" onClick={props.onStop}>
              <Square size={13} />
              Stop
            </button>
          ) : (
            <button className="button primary small" onClick={props.onRun}>
              <Play size={14} fill="currentColor" />
              Run
            </button>
          )}
        </div>
      </header>
      <div className="editor-workspace">
        {libraryOpen && (
          <aside className="node-library" aria-label="Node library">
            <div className="panel-heading">
              <span>Components</span>
              <button
                className="icon-button"
                onClick={() => setLibraryOpen(false)}
                aria-label="Collapse components"
                title="Collapse components"
              >
                <PanelLeftClose size={16} />
              </button>
            </div>
            <div className="library-search">
              <Search size={14} />
              <input
                ref={searchInput}
                placeholder="Find a component…"
                aria-label="Find a component"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <kbd>/</kbd>
            </div>
            <div className="library-groups">
              {groups.map((group) => {
                const items = catalog.filter(
                  (item) =>
                    item.group === group &&
                    `${item.label} ${item.component}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                );
                return items.length ? (
                  <section className="library-group" key={group}>
                    <h3 className="mono">{group}</h3>
                    {items.map((definition) => (
                      <button
                        key={definition.kind}
                        className={`library-item ${["files", "writer", "results"].includes(definition.kind) ? "resource" : ""}`}
                        disabled={busy}
                        title={definition.description}
                        draggable={!busy}
                        onDragStart={(event) => {
                          event.dataTransfer.setData(
                            "application/workbench-node",
                            definition.kind,
                          );
                          event.dataTransfer.effectAllowed = "copy";
                        }}
                        onClick={() => insertNode(definition.kind)}
                      >
                        <NodeIcon kind={definition.kind} />
                        <span>{definition.label}</span>
                        <Plus size={13} className="add-component" />
                      </button>
                    ))}
                  </section>
                ) : null;
              })}
              {!catalog.some((item) =>
                `${item.label} ${item.component}`
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              ) && <div className="library-empty">No components found.</div>}
            </div>
            <div className="library-bottom">
              <button
                className="button small"
                onClick={() => importInput.current?.click()}
                disabled={busy}
              >
                <Upload size={14} />
                Import pipeline
              </button>
              <span className="mono">JSON · SCHEMA V1</span>
            </div>
          </aside>
        )}
        <div className="canvas-column">
          <div className="canvas-heading">
            <div className="canvas-heading-left">
              {!libraryOpen && (
                <button
                  className="icon-button"
                  onClick={() => setLibraryOpen(true)}
                  aria-label="Open components"
                  title="Open components"
                >
                  <PanelLeftOpen size={16} />
                </button>
              )}
              <span className="status-dot success" />
              <span>
                {pipeline.templateId === "indexing"
                  ? "INDEXING PIPELINE"
                  : pipeline.templateId === "retrieval"
                    ? "QUERY PIPELINE"
                    : "CUSTOM PIPELINE"}
              </span>
            </div>
            <div className="canvas-history">
              <button
                className="icon-button"
                disabled={!props.canUndo || busy}
                onClick={props.onUndo}
                aria-label="Undo"
                title="Undo (Ctrl+Z)"
              >
                <Undo2 size={15} />
              </button>
              <button
                className="icon-button"
                disabled={!props.canRedo || busy}
                onClick={props.onRedo}
                aria-label="Redo"
                title="Redo (Ctrl+Shift+Z)"
              >
                <Redo2 size={15} />
              </button>
            </div>
          </div>
          <div
            className="flow-canvas"
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = "copy";
            }}
            onDrop={(event) => {
              event.preventDefault();
              if (busy) return;
              if (pipeline.graph.nodes.length >= 100) {
                props.notify(
                  "A pipeline may contain up to 100 components.",
                  true,
                );
                return;
              }
              const kind = event.dataTransfer.getData(
                "application/workbench-node",
              );
              if (!catalog.some((item) => item.kind === kind)) return;
              const node = createNode(
                kind as NodeKind,
                flow.screenToFlowPosition({
                  x: event.clientX,
                  y: event.clientY,
                }),
              );
              onGraphChange((graph) => ({
                ...graph,
                nodes: [...graph.nodes, node],
              }));
              onSelectNode(node.id);
            }}
          >
            <ReactFlow<WorkbenchNode>
              nodes={nodes}
              edges={pipeline.graph.edges.map((edge) => ({
                ...edge,
                selected: selectedEdges.includes(edge.id),
              }))}
              nodeTypes={nodeTypes}
              onNodesChange={nodeChanges}
              onEdgesChange={edgeChanges}
              onConnect={(connection) => connect(connection)}
              onNodeClick={(_event, node) => {
                onSelectNode(node.id);
                setSelectedEdges([]);
              }}
              onPaneClick={() => {
                onSelectNode(null);
                setSelectedEdges([]);
              }}
              onNodeDragStart={() => onGraphChange((graph) => graph)}
              onMoveEnd={(_event, viewport) => {
                setZoom(Math.round(viewport.zoom * 100));
                onGraphChange((graph) => ({ ...graph, viewport }), false);
              }}
              onInit={(instance) =>
                setZoom(Math.round(instance.getZoom() * 100))
              }
              defaultViewport={pipeline.graph.viewport}
              nodesDraggable={!busy}
              nodesConnectable={!busy}
              edgesReconnectable={false}
              elevateEdgesOnSelect={false}
              elementsSelectable={!busy}
              deleteKeyCode={busy ? null : ["Backspace", "Delete"]}
              connectionLineType={ConnectionLineType.SmoothStep}
              defaultEdgeOptions={{
                type: "smoothstep",
                style: { stroke: "#9baecb", strokeWidth: 1.5 },
              }}
              fitView={!pipeline.graph.viewport}
              fitViewOptions={{ padding: 40, maxZoom: 1 }}
              minZoom={0.25}
              maxZoom={1.8}
              snapToGrid
              snapGrid={[16, 16]}
              panOnScroll
              selectionOnDrag
              panOnDrag={[1, 2]}
              zoomOnDoubleClick={false}
              zoomOnScroll={false}
              zoomActivationKeyCode="Control"
              forceColorMode="light"
            >
              {settings.showGrid && (
                <Background
                  variant={BackgroundVariant.Dots}
                  gap={20}
                  size={1.1}
                  color="#cbd5e4"
                />
              )}
            </ReactFlow>
            {pipeline.graph.nodes.length === 0 && (
              <div className="canvas-empty">
                <Layers size={34} strokeWidth={1.2} />
                <h2>Your pipeline starts here</h2>
                <button
                  className="button primary"
                  onClick={() => setLibraryOpen(true)}
                >
                  <Plus size={15} />
                  Add a component
                </button>
              </div>
            )}
            <div className="canvas-controls">
              <button
                className="icon-button"
                aria-label="Zoom out"
                title="Zoom out"
                onClick={() =>
                  flow.zoomOut({ duration: settings.reducedMotion ? 0 : 150 })
                }
              >
                <ZoomOut size={16} />
              </button>
              <span className="mono">{zoom}%</span>
              <button
                className="icon-button"
                aria-label="Zoom in"
                title="Zoom in"
                onClick={() =>
                  flow.zoomIn({ duration: settings.reducedMotion ? 0 : 150 })
                }
              >
                <ZoomIn size={16} />
              </button>
              <span className="control-divider" />
              <button
                className="icon-button"
                aria-label="Fit graph"
                title="Fit graph"
                onClick={() =>
                  flow.fitView({
                    padding: 40,
                    duration: settings.reducedMotion ? 0 : 200,
                    maxZoom: 1,
                  })
                }
              >
                <Maximize size={15} />
              </button>
            </div>
            <span className="canvas-hint mono">
              SCROLL TO PAN · CTRL + SCROLL TO ZOOM
            </span>
          </div>
          {props.resultsOpen && (
            <ResultsPanel
              run={props.run}
              issues={props.issues}
              selectedNodeId={selectedNodeId}
              onSelectNode={onSelectNode}
              onClose={() => props.onResultsOpen(false)}
            />
          )}
          <footer className="editor-footer">
            <span className="mono">
              <span className="status-dot success" />
              {props.issues.length
                ? `${props.issues.length} VALIDATION ISSUE${props.issues.length === 1 ? "" : "S"}`
                : "ALL CHANGES IN THIS SESSION"}
            </span>
            <button onClick={() => props.onResultsOpen(!props.resultsOpen)}>
              <Layers size={13} />
              Results
              {props.resultsOpen ? (
                <ChevronDown size={13} />
              ) : (
                <ChevronRight size={13} />
              )}
            </button>
          </footer>
        </div>
        {selectedNode && (
          <Inspector
            node={selectedNode}
            graph={pipeline.graph}
            disabled={busy}
            onChange={onGraphChange}
            onClose={() => onSelectNode(null)}
            onDelete={deleteSelected}
            onDuplicate={duplicateSelected}
            onConnect={(source, sourceHandle, target, targetHandle) =>
              connect({ source, sourceHandle, target, targetHandle }, true)
            }
          />
        )}
      </div>
      <input
        type="file"
        accept=".json,application/json"
        ref={importInput}
        className="sr-only"
        aria-label="Import pipeline JSON"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) props.onImport(file);
          event.currentTarget.value = "";
        }}
      />
    </div>
  );
}

export function PipelineEditor(props: Props) {
  return (
    <ReactFlowProvider key={props.pipeline.id}>
      <Editor {...props} />
    </ReactFlowProvider>
  );
}
