// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useAgentOperations } from "./useAgentOperations";
import {
  agentOperationsFixture,
  agentOperationsResponse,
} from "../test/agentOperations";

beforeEach(() => {
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("scopes the default history to the agent returned by the real catalog response", async () => {
  const fixture = agentOperationsFixture();
  fixture.catalog.agents[0].agent_id = "catalog-agent";
  fixture.run.agent_id = "catalog-agent";
  const fetchMock = vi.fn<typeof fetch>(async (input, init) =>
    agentOperationsResponse(fixture, input, init),
  );
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useAgentOperations({}, null, () => {}));
  await waitFor(() => expect(result.current.connection).toBe("connected"));
  const requests = fetchMock.mock.calls.map(
    ([input]) => new URL(String(input), "http://localhost"),
  );
  expect(
    requests
      .find((url) => url.pathname.endsWith("/runs"))
      ?.searchParams.get("agent_id"),
  ).toBe("catalog-agent");
  expect(result.current.timeline?.events).toEqual(fixture.events);
});

it("does not populate any catalog, usage or activity when the API is offline", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(async () => {
      throw new TypeError("Offline test API");
    }),
  );
  const { result } = renderHook(() => useAgentOperations({}, null, () => {}));
  await waitFor(() => expect(result.current.connection).toBe("disconnected"));
  expect(result.current.catalog).toBeNull();
  expect(result.current.currentRun).toBeNull();
  expect(result.current.timeline).toBeNull();
});

it("aborts an outstanding catalog request when leaving Agents", async () => {
  const fetchMock = vi.fn<typeof fetch>(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetchMock);
  const { unmount } = renderHook(() => useAgentOperations({}, null, () => {}));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const signal = fetchMock.mock.calls[0][1]?.signal;
  expect(signal?.aborted).toBe(false);
  unmount();
  expect(signal?.aborted).toBe(true);
});

it("keeps the recorded event list unchanged across a refresh without new events", async () => {
  const fixture = agentOperationsFixture();
  const fetchMock = vi.fn<typeof fetch>(async (input, init) =>
    agentOperationsResponse(fixture, input, init),
  );
  vi.stubGlobal("fetch", fetchMock);
  const reset = vi.fn();
  const { result } = renderHook(() => useAgentOperations({}, null, reset));
  await waitFor(() => expect(result.current.timeline?.events).toHaveLength(4));
  const previous = result.current.updatedAt;
  act(() => result.current.refresh());
  await waitFor(() => expect(result.current.updatedAt).not.toBe(previous));
  expect(result.current.timeline?.events).toEqual(fixture.events);
  expect(
    fetchMock.mock.calls.filter(([input]) =>
      String(input).includes(`/runs/${fixture.run.run_id}`),
    ),
  ).toHaveLength(1);
});
