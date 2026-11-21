import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkbenchApiError } from "../api/client";
import type { LocalSourceFile, SourceRevealResponse } from "../api/contracts";
import { SourceNameLabel } from "./SourceName";
import {
  SourceFilesRequests,
  SourceRevealRequest,
  type SourceFileClient,
} from "./sourceFiles";

const meta = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-file",
  trace_id: "trace-file",
} as const;
const file: LocalSourceFile = { ...meta, name: "report.pdf", can_reveal: true };
const identity = {
  workspaceId: "workspace",
  sourceId: "source",
  versionId: "version",
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
function fixture() {
  const client: SourceFileClient = {
    getLocalFile: vi
      .fn<SourceFileClient["getLocalFile"]>()
      .mockResolvedValue(file),
    revealLocalFile: vi
      .fn<SourceFileClient["revealLocalFile"]>()
      .mockResolvedValue({ ...meta, status: "revealed" }),
  };
  return { client, requests: new SourceFilesRequests(client) };
}

describe("source names", () => {
  it("renders only a clickable real filename, without action menus or icons", () => {
    const html = renderToStaticMarkup(
      <SourceNameLabel fallback="source" file={file} onReveal={() => {}} />,
    );
    expect(html).toContain('role="link"');
    expect(html).toContain(">report.pdf</button>");
    expect(html).not.toContain("<svg");
    expect(html).not.toContain("menu");
    expect(html).not.toContain("file:");
    expect(html.match(/<button/g)).toHaveLength(1);
  });

  it("renders demo sources and unresolved identity as plain text", () => {
    for (const metadata of [
      undefined,
      {
        ...meta,
        name: null,
        can_reveal: false,
        reason: "demo_source",
      } as const,
    ]) {
      const html = renderToStaticMarkup(
        <SourceNameLabel
          fallback="demo-source"
          file={metadata}
          onReveal={() => {}}
        />,
      );
      expect(html).toContain("demo-source");
      expect(html).not.toContain("<button");
      expect(html).not.toContain('role="link"');
      expect(html).not.toContain('role="status"');
    }
  });

  it("escapes filenames and disables the same text link while opening", () => {
    const html = renderToStaticMarkup(
      <SourceNameLabel
        fallback="source"
        file={{ ...file, name: "<script>alert(1)</script>.pdf" }}
        pending
        onReveal={() => {}}
      />,
    );
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script");
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-busy="true"');
  });

  it("shows an accessible message only after an action error", () => {
    const html = renderToStaticMarkup(
      <SourceNameLabel
        fallback="source"
        file={file}
        error="File could not be shown. SOURCE_FILE_UNAVAILABLE"
        onReveal={() => {}}
      />,
    );
    expect(html).toContain('role="status"');
    expect(html).toContain("SOURCE_FILE_UNAVAILABLE");
  });
});

describe("source file request lifecycle", () => {
  it("deduplicates only in-flight metadata and does not retain resolved private responses", async () => {
    const { client, requests } = fixture();
    const pending = deferred<LocalSourceFile>();
    vi.mocked(client.getLocalFile).mockReturnValueOnce(pending.promise);
    const first = requests.lookup(identity, new AbortController().signal);
    const second = requests.lookup(identity, new AbortController().signal);
    await vi.waitFor(() =>
      expect(client.getLocalFile).toHaveBeenCalledTimes(1),
    );
    pending.resolve(file);
    expect(await first).toEqual(file);
    expect(await second).toEqual(file);
    await requests.lookup(identity, new AbortController().signal);
    expect(client.getLocalFile).toHaveBeenCalledTimes(2);
    requests.clear();
  });

  it("bounds metadata requests to four concurrent lookups", async () => {
    const { client, requests } = fixture();
    const pending = Array.from({ length: 8 }, () =>
      deferred<LocalSourceFile>(),
    );
    vi.mocked(client.getLocalFile).mockImplementation(
      (_workspace, source) => pending[Number(source)].promise,
    );
    const all = pending.map((_, index) =>
      requests.lookup(
        { ...identity, sourceId: String(index) },
        new AbortController().signal,
      ),
    );
    await vi.waitFor(() =>
      expect(client.getLocalFile).toHaveBeenCalledTimes(4),
    );
    for (const value of pending.slice(0, 4)) value.resolve(file);
    await Promise.all(all.slice(0, 4));
    await vi.waitFor(() =>
      expect(client.getLocalFile).toHaveBeenCalledTimes(8),
    );
    for (const value of pending.slice(4)) value.resolve(file);
    await Promise.all(all);
    requests.clear();
  });

  it("keeps a shared lookup alive for another mounted subscriber and cancels after both leave", async () => {
    const { client, requests } = fixture();
    const pending = deferred<LocalSourceFile>();
    vi.mocked(client.getLocalFile).mockReturnValue(pending.promise);
    const first = new AbortController();
    const second = new AbortController();
    const a = requests.lookup(identity, first.signal);
    const b = requests.lookup(identity, second.signal);
    await vi.waitFor(() =>
      expect(client.getLocalFile).toHaveBeenCalledTimes(1),
    );
    const underlying = vi.mocked(client.getLocalFile).mock.calls[0][3]?.signal;
    first.abort();
    await expect(a).rejects.toMatchObject({ kind: "cancelled" });
    expect(underlying?.aborted).toBe(false);
    second.abort();
    await expect(b).rejects.toMatchObject({ kind: "cancelled" });
    expect(underlying?.aborted).toBe(true);
    pending.resolve(file);
    requests.clear();
  });

  it("does not start a queued lookup whose subscriber has left", async () => {
    const { client, requests } = fixture();
    const pending = deferred<LocalSourceFile>();
    vi.mocked(client.getLocalFile).mockReturnValue(pending.promise);
    const active = Array.from({ length: 4 }, (_, index) =>
      requests.lookup(
        { ...identity, sourceId: String(index) },
        new AbortController().signal,
      ),
    );
    const controller = new AbortController();
    const queued = requests.lookup(
      { ...identity, sourceId: "queued" },
      controller.signal,
    );
    await vi.waitFor(() =>
      expect(client.getLocalFile).toHaveBeenCalledTimes(4),
    );
    controller.abort();
    await expect(queued).rejects.toMatchObject({ kind: "cancelled" });
    pending.resolve(file);
    await Promise.all(active);
    expect(client.getLocalFile).toHaveBeenCalledTimes(4);
    requests.clear();
  });

  it("makes one reveal request for repeated activation, permits an explicit retry, and cancels locally", async () => {
    const { client, requests } = fixture();
    const pending = deferred<SourceRevealResponse>();
    vi.mocked(client.revealLocalFile).mockReturnValueOnce(pending.promise);
    const reveal = new SourceRevealRequest(requests, identity);
    const first = reveal.run();
    const repeated = reveal.run();
    expect(repeated).toBe(first);
    await vi.waitFor(() =>
      expect(client.revealLocalFile).toHaveBeenCalledTimes(1),
    );
    reveal.stop();
    expect(
      vi.mocked(client.revealLocalFile).mock.calls[0][3]?.signal?.aborted,
    ).toBe(true);
    pending.reject(
      new WorkbenchApiError("Cancelled", {
        kind: "cancelled",
        code: "CANCELLED",
      }),
    );
    await expect(first).rejects.toMatchObject({ kind: "cancelled" });
    await reveal.run();
    expect(client.revealLocalFile).toHaveBeenCalledTimes(2);
  });
});
