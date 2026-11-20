import { afterEach, describe, expect, it, vi } from "vitest";
import {
  capabilityVersion,
  requestValidation,
  ValidationRequests,
} from "./validation";
import {
  createPipeline,
  checkDraftConnection,
  exportPipeline,
  importPipeline,
  checkPreviewGraph,
} from "./graph";
import { createNode } from "./catalog";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function reply(
  init: RequestInit | undefined,
  overrides: Record<string, unknown> = {},
) {
  const request = JSON.parse(String(init?.body));
  return new Response(
    JSON.stringify({
      status: "valid",
      issues: [],
      requestId: request.requestId,
      validator: "haystack",
      capabilityVersion,
      mode: request.mode,
      ...overrides,
    }),
  );
}

describe("authoritative validation transport", () => {
  it("aborts a genuinely pending request at its deadline", async () => {
    vi.useFakeTimers();
    let aborted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener(
              "abort",
              () => {
                aborted = true;
                reject(init.signal?.reason);
              },
              { once: true },
            );
          }),
      ),
    );
    const request = requestValidation(
      createPipeline("blank").graph,
      new AbortController().signal,
    );
    const failure = expect(request).rejects.toMatchObject({
      name: "TimeoutError",
    });
    await vi.advanceTimersByTimeAsync(2999);
    expect(aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await failure;
    expect(aborted).toBe(true);
  });
  it("requires correlated authoritative capability and level", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, init) => Promise.resolve(reply(init))),
    );
    expect(
      (
        await requestValidation(
          createPipeline("blank").graph,
          new AbortController().signal,
        )
      ).status,
    ).toBe("valid");
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, init) =>
        Promise.resolve(reply(init, { capabilityVersion: "old" })),
      ),
    );
    await expect(
      requestValidation(
        createPipeline("blank").graph,
        new AbortController().signal,
      ),
    ).rejects.toThrow("mismatch");
  });
  it("never accepts a failed transport as valid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("", { status: 503 }))),
    );
    await expect(
      requestValidation(
        createPipeline("blank").graph,
        new AbortController().signal,
      ),
    ).rejects.toThrow("unavailable");
  });
  it("rejects malformed and contradictory diagnostics", async () => {
    for (const overrides of [
      { issues: [{ code: 4, message: "x" }] },
      { status: "valid", issues: [{ code: "BAD", message: "problem" }] },
      { validator: "local" },
      { mode: "draft" },
      { requestId: "wrong" },
    ]) {
      vi.stubGlobal(
        "fetch",
        vi.fn((_url, init) => Promise.resolve(reply(init, overrides))),
      );
      await expect(
        requestValidation(
          createPipeline("blank").graph,
          new AbortController().signal,
        ),
      ).rejects.toThrow();
    }
  });
  it("propagates timeout without guessing a verdict", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new DOMException("deadline", "TimeoutError"))),
    );
    await expect(
      requestValidation(
        createPipeline("blank").graph,
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ name: "TimeoutError" });
  });
  it("discards out-of-order responses even if a transport ignores cancellation", async () => {
    const pending: (() => void)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, init) =>
          new Promise<Response>((resolve) =>
            pending.push(() => resolve(reply(init))),
          ),
      ),
    );
    const requests = new ValidationRequests();
    const old = requests.submit(createPipeline("blank").graph);
    const next = requests.submit(createPipeline("blank").graph);
    pending[1]();
    expect((await next)?.status).toBe("valid");
    pending[0]();
    expect(await old).toBeUndefined();
  });
  it("invalidates an in-flight result after a graph edit", async () => {
    let finish: (() => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, init) =>
          new Promise<Response>((resolve) => {
            finish = () => resolve(reply(init));
          }),
      ),
    );
    const requests = new ValidationRequests();
    const old = requests.submit(createPipeline("blank").graph);
    requests.invalidate();
    finish?.();
    expect(await old).toBeUndefined();
  });
});

describe("drafts are not semantic verdicts", () => {
  it("allows structurally safe incompatible handles while preview remains restricted", () => {
    const pipeline = createPipeline("blank");
    const files = createNode("files", { x: 0, y: 0 });
    const search = createNode("bm25", { x: 300, y: 0 });
    const edge = {
      id: "draft",
      source: files.id,
      target: search.id,
      sourceHandle: "files",
      targetHandle: "query",
    };
    pipeline.graph = { nodes: [files, search], edges: [] };
    expect(checkDraftConnection(pipeline.graph, edge)).toBeNull();
    pipeline.graph.edges = [edge];
    expect(importPipeline(exportPipeline(pipeline)).graph.edges).toHaveLength(
      1,
    );
    expect(checkPreviewGraph(pipeline.graph).length).toBeGreaterThan(0);
  });
});
