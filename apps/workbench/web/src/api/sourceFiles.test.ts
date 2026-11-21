import { describe, expect, it, vi } from "vitest";
import { createWorkbenchApiClient } from "./client";

const meta = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-file",
  trace_id: "trace-file",
};
function clientFor(value: unknown, status = 200) {
  const fetchImpl = vi.fn<typeof fetch>().mockImplementation(
    async () =>
      new Response(JSON.stringify(value), {
        status,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": meta.request_id,
        },
      }),
  );
  return { client: createWorkbenchApiClient({ fetchImpl }), fetchImpl };
}

describe("local source file transport", () => {
  it("resolves metadata using only server source/version identity", async () => {
    const file = {
      ...meta,
      name: "Технічна документація.pdf",
      can_reveal: true,
    };
    const { client, fetchImpl } = clientFor(file);
    expect(await client.getLocalFile("workspace", "source", "version")).toEqual(
      file,
    );
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/workspaces/workspace/sources/source/versions/version/local-file",
      expect.objectContaining({ method: "GET", credentials: "omit" }),
    );
    expect(fetchImpl.mock.calls[0][1]).not.toHaveProperty("body");
  });

  it("accepts a non-clickable demo and never exposes additional server properties", async () => {
    const { client } = clientFor({
      ...meta,
      name: null,
      can_reveal: false,
      reason: "demo_source",
      internal_note: "ignored",
    });
    expect(await client.getLocalFile("workspace", "source", "version")).toEqual(
      { ...meta, name: null, can_reveal: false, reason: "demo_source" },
    );
  });

  it("reveals a source with exactly one POST of an empty JSON object", async () => {
    const { client, fetchImpl } = clientFor({ ...meta, status: "revealed" });
    expect(
      await client.revealLocalFile("workspace", "source", "version"),
    ).toEqual({ ...meta, status: "revealed" });
    expect(fetchImpl).toHaveBeenCalledOnce();
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/workspaces/workspace/sources/source/versions/version/local-file/reveal",
      expect.objectContaining({
        method: "POST",
        body: "{}",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      }),
    );
  });

  it.each([
    { name: null, can_reveal: true },
    { name: "", can_reveal: true },
    { name: "   ", can_reveal: true },
    { name: "../report.pdf", can_reveal: true },
    { name: "C:\\private\\report.pdf", can_reveal: true },
    { name: "file:///report.pdf", can_reveal: true },
    { name: "x".repeat(256), can_reveal: true },
    { name: "\ud800.pdf", can_reveal: true },
    { name: "report.pdf", can_reveal: "true" },
    { name: "report.pdf", can_reveal: true, reason: "demo_source" },
    { name: null, can_reveal: false, reason: "unknown_reason" },
  ])("rejects unsafe or contradictory metadata %#", async (value) => {
    const { client } = clientFor({ ...meta, ...value });
    await expect(
      client.getLocalFile("workspace", "source", "version"),
    ).rejects.toMatchObject({ kind: "protocol" });
  });

  it("rejects unsafe identity before any network operation", async () => {
    const { client, fetchImpl } = clientFor({ ...meta, status: "revealed" });
    await expect(
      client.getLocalFile("workspace", "../source", "version"),
    ).rejects.toMatchObject({ kind: "protocol" });
    await expect(
      client.revealLocalFile("workspace", "source", "../version"),
    ).rejects.toMatchObject({ kind: "protocol" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("preserves safe action errors and rejects false success statuses", async () => {
    const { client } = clientFor(
      {
        ...meta,
        error: {
          code: "SOURCE_FILE_UNAVAILABLE",
          message: "private stack and file path",
          retryable: false,
          http_status: 409,
        },
      },
      409,
    );
    const failure: unknown = await client
      .revealLocalFile("workspace", "source", "version")
      .catch((error: unknown) => error);
    expect(failure).toMatchObject({
      code: "SOURCE_FILE_UNAVAILABLE",
      httpStatus: 409,
      traceId: "trace-file",
    });
    expect(String(failure)).not.toContain("private stack");
    const malformed = clientFor({ ...meta, status: "queued" });
    await expect(
      malformed.client.revealLocalFile("workspace", "source", "version"),
    ).rejects.toMatchObject({ kind: "protocol" });
  });
});
