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
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

it("places Configuration directly after Runs with a wrench and an active page state", async () => {
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
  fireEvent.click(
    within(navigation).getByRole("button", { name: "Documents" }),
  );
  expect(
    await screen.findByRole("dialog", { name: "Discard unsaved changes?" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(configuration.getAttribute("aria-current")).toBe("page");
  fireEvent.click(
    within(navigation).getByRole("button", { name: "Documents" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Discard changes" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Documents" }),
  ).toBeTruthy();
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
