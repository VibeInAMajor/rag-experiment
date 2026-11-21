import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { SearchResponse } from "../api/contracts";
import type { LiveRun, RunEntry } from "../domain/liveSearch";
import { createPipeline } from "../domain/graph";
import { createPreviewRun } from "../domain/preview";
import { LiveRunDetails, LiveRunMetadata } from "./LiveRunDetails";
import { ResultsPanel } from "./ResultsPanel";
import { RunsView } from "../views/RunsView";

const response: SearchResponse = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-actual",
  trace_id: "trace-actual",
  mode: "live",
  workspace_id: "workspace-actual",
  corpus_revision: "corpus-actual",
  profile_id: "postgres-fts-baseline",
  profile_revision: "postgres-fts-baseline-r1",
  run_id: "server-actual",
  status: "success",
  duration_ms: 19.456789,
  stages: [{ stage: "retrieval", status: "success", duration_ms: 2.3456789 }],
  results: [
    {
      chunk_id: "chunk-actual",
      source_id: "source-actual",
      source_version_id: "version-actual",
      title: '<img src="x" onerror="alert(1)">',
      content: "<script>alert('retrieved text')</script>",
      rank: 3,
      score: 0.10000000149011612,
      score_type: "postgres_ts_rank_cd",
    },
  ],
};

function completedRun(): LiveRun {
  return {
    id: "local-list-id",
    source: "live",
    serverRunId: response.run_id,
    requestId: response.request_id,
    traceId: response.trace_id,
    profileId: response.profile_id,
    profileRevision: response.profile_revision,
    corpusRevision: response.corpus_revision,
    workspaceId: response.workspace_id,
    pipelineId: "keyword-pipeline",
    pipelineName: "Keyword search",
    graphSnapshot: { nodes: [], edges: [] },
    submitted: {
      query: "retention",
      top_k: 5,
      profile_id: response.profile_id,
      expected_profile_revision: response.profile_revision,
    },
    startedAt: "2026-11-21T12:00:00Z",
    status: "Completed",
    durationMs: response.duration_ms,
    stages: response.stages,
    results: response.results,
    response,
  };
}

describe("Live result rendering", () => {
  it("keeps server rank, full raw score, provenance and unavailable page", () => {
    const html = renderToStaticMarkup(<LiveRunDetails run={completedRun()} />);
    for (const value of [
      "Rank 3",
      "0.10000000149011612",
      "postgres_ts_rank_cd",
      "source-actual",
      "version-actual",
      "chunk-actual",
      "Page unavailable",
    ])
      expect(html).toContain(value);
    expect(html).not.toContain("Page 0");
    expect(html).not.toContain("undefined");
    expect(html).not.toContain("%");
  });

  it("renders retrieved HTML as text", () => {
    const html = renderToStaticMarkup(<LiveRunDetails run={completedRun()} />);
    expect(html).toContain("&lt;img");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<script");
  });

  it("shows server timing and preserves the full response in JSON", () => {
    const run = completedRun();
    const stages = renderToStaticMarkup(
      <LiveRunDetails run={run} view="stages" />,
    );
    expect(stages).toContain("retrieval");
    expect(stages).toContain("2.346 ms");
    expect(stages).toContain('data-duration-ms="2.3456789"');
    expect(stages).toContain('data-stage="retrieval"');
    expect(stages).toContain("2.3456789");
    expect(stages).not.toContain("nodeId");
    const html = renderToStaticMarkup(<LiveRunDetails run={run} json />);
    for (const field of [
      "run_id",
      "server-actual",
      "trace-actual",
      "corpus-actual",
      "source_version_id",
      "0.10000000149011612",
      "19.456789",
    ])
      expect(html).toContain(field);
    expect(html).not.toContain("local-list-id");
    const metadata = renderToStaticMarkup(<LiveRunMetadata run={run} />);
    expect(metadata).toContain("request-actual");
    expect(metadata).toContain("trace-actual");
    expect(metadata).toContain("corpus-actual");
  });

  it("distinguishes successful no-hits, failed and locally interrupted runs", () => {
    const run = { ...completedRun(), results: [] };
    expect(renderToStaticMarkup(<LiveRunDetails run={run} />)).toContain(
      "No matches for this query.",
    );
    const failed: LiveRun = {
      ...run,
      status: "Failed",
      durationMs: undefined,
      response: undefined,
      error: {
        code: "SEARCH_BUSY",
        message: "Retry when capacity is available.",
        httpStatus: 429,
      },
    };
    const error = renderToStaticMarkup(
      <LiveRunDetails run={failed} view="errors" />,
    );
    expect(error).toContain("SEARCH_BUSY");
    expect(error).toContain("HTTP 429");
    expect(error).not.toContain("No matches");
    const interrupted: LiveRun = {
      ...failed,
      status: "InterruptedLocally",
      error: undefined,
    };
    expect(
      renderToStaticMarkup(<LiveRunDetails run={interrupted} view="errors" />),
    ).toContain("Server cancellation is not confirmed.");
  });

  it("does not create a canvas-node timeline for Live and keeps constructor issues visible", () => {
    const html = renderToStaticMarkup(
      <ResultsPanel
        run={{ source: "live", run: completedRun() }}
        issues={[{ message: "Constructor validation: unsupported query node" }]}
        selectedNodeId={null}
        onSelectNode={() => {}}
        onClose={() => {}}
      />,
    );
    expect(html).toContain("Stages");
    expect(html).not.toContain(">Nodes<");
    expect(html).toContain("Constructor validation: unsupported query node");
    expect(html).toContain("19.456789");
    expect(html).toContain("19.457 ms");
  });

  it("labels mixed history sources without claiming persistent server history", () => {
    const preview = createPreviewRun(createPipeline("retrieval"));
    const runs: RunEntry[] = [
      { source: "preview", run: preview },
      { source: "live", run: completedRun() },
    ];
    const html = renderToStaticMarkup(
      <RunsView runs={runs} onOpenPipeline={() => {}} />,
    );
    expect(html).toContain('data-source="preview"');
    expect(html).toContain('data-source="live"');
    expect(html).toContain("Session history · cleared on refresh.");
    expect(html).toContain("server-actual");
  });
});
