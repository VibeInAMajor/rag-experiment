// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AgentsView } from "./AgentsView";
import {
  agentOperationsFixture,
  agentOperationsResponse,
} from "../test/agentOperations";

let fixture: ReturnType<typeof agentOperationsFixture>;
let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
beforeEach(() => {
  fixture = agentOperationsFixture();
  fetchMock = vi.fn<typeof fetch>(async (input, init) =>
    agentOperationsResponse(fixture, input, init),
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function openRunDetails() {
  fireEvent.click(
    await screen.findByRole("button", { name: /^View run from/ }),
  );
}

it("shows only catalog models/reasoning, collapses details, and removes service metadata", async () => {
  const { container } = render(<AgentsView />);
  const model = await screen.findByRole("combobox", {
    name: "Model",
  });
  expect(
    within(model)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["GPT-6.1 Sol", "GPT-6.2 Sol"]);
  expect(
    within(screen.getByRole("combobox", { name: "Reasoning" }))
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Medium"]);
  expect(container.querySelector("details")?.open).toBe(false);
  expect(container.textContent).not.toMatch(
    /Runtime|Qualification revision|Official tariff|Local metadata|Preview and Live|semantic-review|semantic-judge|4 modes/i,
  );
  expect(
    screen.getAllByRole("heading", { name: "Semantic Judge" }),
  ).toHaveLength(1);
  expect(screen.queryByRole("heading", { name: "Latest run" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Run details" })).toBeNull();
  expect(
    fetchMock.mock.calls.every(
      ([, init]) => !init?.method || init.method === "GET",
    ),
  ).toBe(true);
});

it("identifies checkpoint-only history and groups activity without pretending new model requests occurred", async () => {
  render(<AgentsView />);
  await openRunDetails();
  expect(
    await screen.findByText(
      "2 saved results reused. No model requests were recorded.",
    ),
  ).toBeTruthy();
  const activity = screen.getByRole("table", { name: "Run activity" });
  expect(
    within(activity)
      .getAllByRole("columnheader")
      .map((header) => header.textContent),
  ).toEqual(["Time", "Event", "Outcome"]);
  expect(within(activity).getAllByRole("row")).toHaveLength(4);
  expect(within(activity).getByText("2 saved results reused")).toBeTruthy();
  expect(activity.textContent).not.toMatch(/saved-case|Tokens|cost|\d{4}/);
  expect(screen.queryByText(fixture.run.run_id)).toBeNull();
  expect(screen.queryByLabelText("Run totals")).toBeNull();
  await openRunDetails();
  expect(screen.queryByRole("region", { name: "Run details" })).toBeNull();
});

it("shows observed run totals once and no per-request accounting in Activity", async () => {
  fixture.run = {
    ...fixture.run,
    physical_requests: 1,
    reused_cases: 0,
    estimated_cost_usd: "0.010400",
    usage: {
      input_tokens: 1200,
      output_tokens: 400,
      total_tokens: 1600,
      ordinary_input_tokens: null,
      cached_read_tokens: null,
      cached_write_tokens: null,
      reasoning_tokens: null,
    },
    usage_coverage: { known_calls: 1, total_calls: 1 },
    cost_coverage: { known_calls: 1, total_calls: 1 },
  };
  render(<AgentsView />);
  await openRunDetails();
  const totals = await screen.findByLabelText("Run totals");
  expect(totals.textContent).toContain("$0.010400");
  expect(totals.textContent).toContain((1200).toLocaleString());
  expect(totals.textContent).toContain("400");
  expect(
    screen.getByRole("table", { name: "Run activity" }).textContent,
  ).not.toContain("0.010400");
});

it("does not turn missing usage or cost into zero or an estimate", async () => {
  fixture.run = {
    ...fixture.run,
    physical_requests: 1,
    reused_cases: 0,
    usage_coverage: { known_calls: 0, total_calls: 1 },
    cost_coverage: { known_calls: 0, total_calls: 1 },
  };
  render(<AgentsView />);
  await openRunDetails();
  const totals = await screen.findByLabelText("Run totals");
  expect(totals.textContent).toContain("Not reported");
  expect(totals.textContent).not.toContain("$0");
  expect(
    await screen.findByText(/totals include reported values only/),
  ).toBeTruthy();
});

it("keeps an unqualified combination read-only and persists an eligible choice through the API", async () => {
  render(<AgentsView />);
  const model = await screen.findByRole("combobox", {
    name: "Model",
  });
  fireEvent.change(model, { target: { value: "gpt-6.2-sol" } });
  expect(
    (
      screen.getByRole("button", {
        name: "Save selection",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(screen.getByText(/agent qualification is pending/)).toBeTruthy();
  fixture.catalog.agents[0].profiles[1].selectable = true;
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh agent operations" }),
  );
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Save selection",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save selection" }));
  await screen.findByText("Saved for the next eligible run.");
  const writes = fetchMock.mock.calls.filter(
    ([, init]) => init?.method === "PUT",
  );
  expect(writes).toHaveLength(1);
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({
    profile_id: "semantic-review-6.2",
    expected_revision: "selection-test",
  });
  expect(
    screen.getByRole("table", { name: "Agent run history" }).textContent,
  ).toContain("GPT-6.1 Sol");
});

it("offers only the reasoning profiles registered for the chosen model, including a provider default", async () => {
  const primary = fixture.catalog.agents[0].profiles[0];
  fixture.catalog.agents[0].profiles.push({
    ...primary,
    profile_id: "semantic-review-default",
    reasoning_effort: null,
    selectable: false,
  });
  render(<AgentsView />);
  const reasoning = await screen.findByRole("combobox", { name: "Reasoning" });
  expect(
    within(reasoning)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Medium", "Default"]);
  fireEvent.change(reasoning, { target: { value: "semantic-review-default" } });
  expect(
    (
      screen.getByRole("button", {
        name: "Save selection",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.change(screen.getByRole("combobox", { name: "Model" }), {
    target: { value: "gpt-6.2-sol" },
  });
  expect(within(reasoning).getAllByRole("option")).toHaveLength(1);
});

it("renders an empty history from an empty backend without demonstration activity", async () => {
  fixture.runsAvailable = false;
  render(<AgentsView />);
  await screen.findByText("No matching runs.");
  expect(screen.queryByRole("table", { name: "Run activity" })).toBeNull();
  expect(screen.queryByLabelText("Run totals")).toBeNull();
});

it("lists all backend reasoning levels for both models and preserves the inspected effort across model changes", async () => {
  const agent = fixture.catalog.agents[0];
  const base = agent.profiles[0];
  const other = agent.profiles[1];
  for (const profile of [base, other]) {
    for (const effort of ["low", "high", "xhigh", "max"]) {
      agent.profiles.push({
        ...profile,
        profile_id: `${profile.profile_id}-${effort}`,
        reasoning_effort: effort,
        selectable: false,
        qualification: {
          state: "unqualified",
          revision: null,
          verified_at: null,
          reason: "offline_only",
        },
      });
    }
  }
  render(<AgentsView />);
  const reasoning = await screen.findByRole("combobox", { name: "Reasoning" });
  expect(
    within(reasoning)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Low", "Medium", "High", "Xhigh", "Max"]);
  fireEvent.change(reasoning, { target: { value: "semantic-review-max" } });
  expect((reasoning as HTMLSelectElement).value).toBe("semantic-review-max");
  fireEvent.change(screen.getByRole("combobox", { name: "Model" }), {
    target: { value: other.model },
  });
  expect((reasoning as HTMLSelectElement).value).toBe(
    "semantic-review-6.2-max",
  );
  expect(
    within(reasoning)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Low", "Medium", "High", "Xhigh", "Max"]);
  expect(screen.getByText(/agent qualification is pending/)).toBeTruthy();
});

it("withholds a run and activity belonging to a different agent", async () => {
  fixture.run.agent_id = "another-agent";
  render(<AgentsView />);
  await screen.findByText("No matching runs.");
  expect(screen.queryByRole("table", { name: "Run activity" })).toBeNull();
  expect(screen.queryByText(/saved results reused\. No model/)).toBeNull();
});

it("reports an unavailable API without inventing an agent, run or event", async () => {
  fixture.offline = true;
  render(<AgentsView />);
  await screen.findByText("Cannot reach the API. Reconnecting…");
  expect(screen.queryByRole("combobox", { name: "Model" })).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
});

it("marks retained observations as disconnected and disables model selection", async () => {
  render(<AgentsView />);
  await openRunDetails();
  await screen.findByText(
    "2 saved results reused. No model requests were recorded.",
  );
  fixture.offline = true;
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh agent operations" }),
  );
  await screen.findByText("Disconnected · showing last update");
  expect(
    (
      screen.getByRole("combobox", {
        name: "Model",
      }) as HTMLSelectElement
    ).disabled,
  ).toBe(true);
  expect(
    screen.getByText(
      "2 saved results reused. No model requests were recorded.",
    ),
  ).toBeTruthy();
});
