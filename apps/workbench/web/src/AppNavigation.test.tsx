// @vitest-environment jsdom
import "./test/dialog";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { App } from "./App";
import {
  readWorkbenchLocation,
  workbenchLocationUrl,
} from "./domain/workbenchLocation";

vi.mock("./components/PipelineEditor", () => ({
  PipelineEditor: () => <div>Pipeline workspace</div>,
}));
vi.mock("./views/ConfigurationView", () => ({
  ConfigurationView: ({
    onDirtyChange,
    onSavingChange,
  }: {
    onDirtyChange: (value: boolean) => void;
    onSavingChange: (value: boolean) => void;
  }) => (
    <section aria-label="Configuration workspace">
      <button onClick={() => onDirtyChange(true)}>Change configuration</button>
      <button onClick={() => onSavingChange(true)}>Begin save</button>
    </section>
  ),
}));
vi.mock("./views/AgentsView", () => ({
  AgentsView: () => <h1>Agents</h1>,
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

it.each([
  "pipelines",
  "documents",
  "runs",
  "configuration",
  "agents",
  "settings",
] as const)("keeps %s and the explicit mode after a remount", async (page) => {
  window.history.replaceState(null, "", `/?page=${page}&mode=live`);
  const first = render(<App />);
  const label =
    page === "configuration"
      ? "Configuration workspace"
      : page[0].toUpperCase() + page.slice(1);
  if (page === "configuration")
    await screen.findByRole("region", { name: label });
  else await screen.findByRole("heading", { name: label, level: 1 });
  expect(
    (screen.getByRole("radio", { name: "Live" }) as HTMLInputElement).checked,
  ).toBe(true);
  first.unmount();
  render(<App />);
  if (page === "configuration")
    await screen.findByRole("region", { name: label });
  else await screen.findByRole("heading", { name: label, level: 1 });
  expect(
    (screen.getByRole("radio", { name: "Live" }) as HTMLInputElement).checked,
  ).toBe(true);
  fireEvent.click(screen.getByRole("radio", { name: "Preview" }));
  expect(new URL(window.location.href).searchParams.get("mode")).toBe(
    "preview",
  );
  expect(new URL(window.location.href).searchParams.get("page")).toBe(page);
});

it("round-trips the editor URL without consuming content anchors or unrelated query parameters", () => {
  const href = workbenchLocationUrl(
    "http://localhost/?other=value#main-content",
    { page: "editor", mode: "live" },
  );
  expect(href).toContain("other=value");
  expect(href).toContain("#main-content");
  expect(readWorkbenchLocation(new URL(href, "http://localhost").href)).toEqual(
    { page: "editor", mode: "live" },
  );
  expect(
    readWorkbenchLocation("http://localhost/?page=invalid&mode=invalid"),
  ).toEqual({ page: "editor", mode: "preview" });
});

it("places Configuration and Agents after Runs and preserves the dirty navigation guard", async () => {
  render(<App />);
  const navigation = screen.getByRole("navigation", {
    name: "Main navigation",
  });
  const buttons = within(navigation).getAllByRole("button");
  expect(buttons.map((button) => button.textContent)).toEqual([
    "Pipelines",
    "Documents",
    "Runs",
    "Configuration",
    "Agents",
    "Settings",
  ]);
  const configuration = within(navigation).getByRole("button", {
    name: "Configuration",
  });
  expect(configuration.querySelector(".lucide-wrench")).toBeTruthy();
  fireEvent.click(configuration);
  await screen.findByRole("region", { name: "Configuration workspace" });
  expect(configuration.getAttribute("aria-current")).toBe("page");
  expect(window.location.hash).toBe("#configuration");
  fireEvent.click(screen.getByRole("button", { name: "Change configuration" }));
  const agents = within(navigation).getByRole("button", { name: "Agents" });
  fireEvent.click(agents);
  expect(
    await screen.findByRole("dialog", { name: "Discard unsaved changes?" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(configuration.getAttribute("aria-current")).toBe("page");
  fireEvent.click(agents);
  fireEvent.click(
    await screen.findByRole("button", { name: "Discard changes" }),
  );
  expect(await screen.findByRole("heading", { name: "Agents" })).toBeTruthy();
  expect(agents.getAttribute("aria-current")).toBe("page");
  expect(window.location.search).toContain("page=agents");
});

it("opens a refreshed configuration URL and keeps navigation in place during a save", async () => {
  window.history.replaceState(null, "", "/#configuration");
  render(<App />);
  await screen.findByRole("region", { name: "Configuration workspace" });
  fireEvent.click(screen.getByRole("button", { name: "Begin save" }));
  fireEvent.click(screen.getByRole("button", { name: "Pipelines" }));
  expect(
    screen.getByRole("region", { name: "Configuration workspace" }),
  ).toBeTruthy();
  expect(
    screen.getByText("Wait for the configuration save to finish."),
  ).toBeTruthy();
});
