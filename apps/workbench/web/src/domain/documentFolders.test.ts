import { describe, expect, it } from "vitest";
import type { DocumentItem } from "../api/contracts";
import {
  buildDocumentFolders,
  filterDocumentFolders,
  type DocumentFolderNode,
} from "./documentFolders";

function file(
  path: string,
  status: DocumentItem["status"] = "ready",
  totals = [2, 1],
  group = "selection-1",
): DocumentItem {
  return {
    source_id: path,
    title: path.split("/").at(-1)!,
    media_type: "text/plain",
    status,
    active_version_id: "version-1",
    chunk_count: 1,
    updated_at: "2026-11-25T12:00:00Z",
    upload_location: { group_id: group, path, folder_totals: totals },
  };
}
function root(documents: DocumentItem[]) {
  return buildDocumentFolders(documents, [])[0] as DocumentFolderNode;
}

describe("document folder hierarchy", () => {
  it("marks the whole tree Ready only when every expected nested file is ready", () => {
    const tree = root([
      file("Research/top.txt", "ready", [2]),
      file("Research/sub/notes.txt"),
    ]);
    expect(tree.status).toBe("ready");
    expect(tree.ready).toBe(2);
    expect(tree.children[0]).toMatchObject({
      name: "sub",
      status: "ready",
      expected: 1,
    });
  });
  it.each(["processing", "error"] as const)(
    "propagates nested %s to its ancestors",
    (status) => {
      const tree = root([
        file("Research/top.txt", "ready", [2]),
        file("Research/sub/notes.txt", status),
      ]);
      expect(tree.status).toBe(status);
      expect(tree.ready).toBe(1);
    },
  );
  it("does not claim readiness from a partial page or hide failures behind a Ready filter", () => {
    const partial = file("Research/top.txt", "ready", [2]);
    partial.folder_states = [
      { file_count: 2, ready_count: 1, status: "processing" },
    ];
    expect(root([partial])).toMatchObject({
      status: "processing",
      loaded: 1,
      expected: 2,
    });
    const tree = buildDocumentFolders(
      [
        file("Research/top.txt", "ready", [2]),
        file("Research/sub/broken.txt", "error"),
      ],
      [],
    );
    expect(filterDocumentFolders(tree, "top", "ready")[0]).toMatchObject({
      kind: "folder",
      status: "error",
      ready: 1,
      expected: 2,
    });
  });
  it("keeps equal folder names from separate selections distinct and legacy files at root", () => {
    const legacy = file("legacy.txt");
    delete legacy.upload_location;
    const tree = buildDocumentFolders(
      [
        file("Research/a.txt", "ready", [1], "first"),
        file("Research/a.txt", "ready", [1], "second"),
        legacy,
      ],
      [],
    );
    expect(tree.map((node) => node.kind)).toEqual(["folder", "folder", "file"]);
    expect(tree[0].key).not.toBe(tree[1].key);
  });
  it("includes active uploads but keeps skipped attempts outside the document tree", () => {
    const tree = buildDocumentFolders(
      [],
      [
        {
          id: "waiting",
          path: "Research/top.txt",
          file: null,
          phase: "ready",
          location: {
            group_id: "selection-1",
            path: "Research/top.txt",
            folder_totals: [2],
          },
        },
        {
          id: "skipped",
          path: "Research/sub/data.csv",
          file: null,
          phase: "skipped",
          location: {
            group_id: "selection-1",
            path: "Research/sub/data.csv",
            folder_totals: [2, 1],
          },
        },
      ],
    );
    expect(tree[0]).toMatchObject({
      status: "processing",
      ready: 0,
      loaded: 1,
      expected: 1,
    });
  });
  it("marks existing documents Ready despite upload attempts that never created a document", () => {
    const document = file("Research/notes.txt", "ready", [5]);
    const tree = buildDocumentFolders(
      [document],
      ["failed", "skipped", "unknown"].map((phase) => ({
        id: phase,
        path: `Research/${phase}.txt`,
        phase: phase as "failed" | "skipped" | "unknown",
        file: null,
        location: {
          group_id: "selection-1",
          path: `Research/${phase}.txt`,
          folder_totals: [5],
        },
      })),
    );
    expect(tree[0]).toMatchObject({
      status: "ready",
      expected: 1,
      ready: 1,
      loaded: 1,
    });
  });
  it("uses the complete server snapshot when all persisted files are ready but only one page is loaded", () => {
    const partial = file("Research/top.txt", "ready", [5]);
    partial.folder_states = [
      { file_count: 3, ready_count: 3, status: "ready" },
    ];
    expect(buildDocumentFolders([partial], [], false)[0]).toMatchObject({
      status: "ready",
      expected: 3,
      ready: 3,
      loaded: 1,
    });
  });
  it("retains session grouping while connected to an older API without folder metadata", () => {
    const item = file("Research/notes.txt", "ready", [1]);
    const location = item.upload_location;
    delete item.upload_location;
    const tree = buildDocumentFolders(
      [item],
      [
        {
          id: "session",
          path: "Research/notes.txt",
          file: null,
          phase: "succeeded",
          location: location ?? undefined,
          response: {
            contract_revision: "rag-api-v1.0",
            request_id: "req",
            trace_id: "trace",
            workspace_id: "workspace",
            source_id: item.source_id,
            source_version_id: "v1",
            job_id: "job",
            outcome: "created",
            status: "completed",
            chunk_count: 1,
            corpus_revision: "revision",
            stages: [],
            replayed: false,
          },
        },
      ],
    );
    expect(tree[0]).toMatchObject({
      kind: "folder",
      status: "ready",
      loaded: 1,
    });
    expect((tree[0] as DocumentFolderNode).children).toHaveLength(1);
    expect(
      filterDocumentFolders(tree, "Research/notes.txt", "all"),
    ).toHaveLength(1);
  });
});
