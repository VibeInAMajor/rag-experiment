import { expect, it } from "vitest";
import { agentOperationsFixture } from "../test/agentOperations";
import { agentActivity } from "./agentActivity";

it("groups contiguous checkpoint reuse using distinct saved cases and preserves the original time", () => {
  const { events } = agentOperationsFixture();
  const duplicate = { ...events[2], sequence: 4 };
  const rows = agentActivity([
    ...events.slice(0, 3),
    duplicate,
    { ...events[3], sequence: 5 },
  ]);
  expect(rows.map((row) => row.title)).toEqual([
    "Run finished",
    "2 saved results reused",
    "Run started",
  ]);
  expect(rows[1].event).toBe(duplicate);
  expect(events).toHaveLength(4);
});

it("keeps separate checkpoint groups on either side of a real model event", () => {
  const { events } = agentOperationsFixture();
  expect(
    agentActivity([events[1], events[0], events[2]]).map((row) => row.title),
  ).toEqual(["1 saved result reused", "Run started", "1 saved result reused"]);
});

it("keeps failed checkpoint outcomes separate from successful restored results", () => {
  const { events } = agentOperationsFixture();
  const rows = agentActivity([
    events[1],
    { ...events[2], status: "failed", reason: "CONFIGURATION_ERROR" },
  ]);
  expect(rows).toHaveLength(2);
  expect(rows.map((row) => row.event.status)).toEqual(["failed", "completed"]);
});

it("describes the actual mode and failure reason without generating usage or identifiers", () => {
  const { events } = agentOperationsFixture();
  const rows = agentActivity([
    {
      ...events[0],
      kind: "call_completed",
      status: "blocked",
      reason: "BUDGET_EXCEEDED",
      call: {
        call_id: "private-call",
        case_id: "private-case",
        mode: "judge_evidence",
        actual_model: null,
        provider_request_id: null,
        requests: 0,
        elapsed_ms: null,
        usage: null,
        estimated_cost_usd: null,
        reserve_usd: null,
      },
    },
  ]);
  expect(rows[0].title).toBe("Evidence review blocked");
  expect(rows[0].detail).toBe("Budget exceeded");
  expect(agentActivity([])).toEqual([]);
});
