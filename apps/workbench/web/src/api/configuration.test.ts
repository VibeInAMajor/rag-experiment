import { expect, it, vi } from "vitest";
import { createWorkbenchApiClient } from "./client";

const meta = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-1",
  trace_id: "trace-1",
};
const document = {
  ...meta,
  scope: "application",
  yaml: "document_processing: {}\n",
  revision: `config-${"b".repeat(64)}`,
  exists: true,
  activation: "active",
  max_bytes: 65536,
  effective_default_language: "en",
  deployment_overrides: [],
};
function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": "request-1",
    },
  });
}
it("loads directly with local request intent and no cookies, keys or session call", async () => {
  const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(response(document));
  await createWorkbenchApiClient({ fetchImpl }).getConfiguration();
  expect(fetchImpl).toHaveBeenCalledTimes(1);
  expect(fetchImpl.mock.calls[0][0]).toBe("/api/v1/configuration");
  expect(fetchImpl.mock.calls[0][1]?.credentials).toBe("omit");
  expect(fetchImpl.mock.calls[0][1]?.headers).toMatchObject({
    "X-Workbench-Request": "configuration",
  });
});
it("sends exact YAML and revision for an independently validated server save", async () => {
  const fetchImpl = vi
    .fn<typeof fetch>()
    .mockResolvedValue(response({ ...document, status: "saved" }));
  await createWorkbenchApiClient({ fetchImpl }).saveConfiguration(
    document.yaml,
    document.revision,
  );
  const request = fetchImpl.mock.calls[0][1];
  expect(request?.method).toBe("PUT");
  expect(JSON.parse(String(request?.body))).toEqual({
    yaml: document.yaml,
    expected_revision: document.revision,
  });
  expect(request?.headers).not.toHaveProperty("X-CSRF-Token");
});
it("rejects cross-origin configuration routing before any request", async () => {
  const fetchImpl = vi.fn<typeof fetch>();
  vi.stubGlobal("window", {
    location: {
      href: "http://127.0.0.1:4173/",
      origin: "http://127.0.0.1:4173",
    },
  });
  try {
    await expect(
      createWorkbenchApiClient({
        fetchImpl,
        baseUrl: "https://foreign.invalid/api/v1",
      }).getConfiguration(),
    ).rejects.toMatchObject({ code: "CONFIGURATION_SAME_ORIGIN_REQUIRED" });
    expect(fetchImpl).not.toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});
