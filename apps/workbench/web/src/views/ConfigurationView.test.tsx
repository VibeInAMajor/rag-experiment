// @vitest-environment jsdom
import "../test/dialog";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ConfigurationView } from "./ConfigurationView";
import { WorkbenchApiError, type WorkbenchApiClient } from "../api/client";
import type { ConfigurationDocument } from "../api/contracts";

vi.mock("../components/YamlEditor", () => ({
  YamlEditor: ({
    value,
    readOnly,
    onChange,
  }: {
    value: string;
    readOnly: boolean;
    onChange: (value: string) => void;
  }) => (
    <textarea
      aria-label="YAML configuration"
      value={value}
      readOnly={readOnly}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
const meta = {
  contract_revision: "rag-api-v1.0" as const,
  request_id: "request-1",
  trace_id: "trace-1",
};
const saved: ConfigurationDocument = {
  ...meta,
  scope: "application",
  yaml: "# comment\ndocument_processing: {}\n",
  revision: `config-${"a".repeat(64)}`,
  exists: true,
  activation: "active",
  max_bytes: 65536,
  effective_default_language: "en",
  deployment_overrides: [],
};
function fixture() {
  const client = {
    getConfiguration: vi
      .fn<WorkbenchApiClient["getConfiguration"]>()
      .mockResolvedValue(saved),
    validateConfiguration: vi
      .fn<WorkbenchApiClient["validateConfiguration"]>()
      .mockResolvedValue({ ...meta, valid: true, errors: [], warnings: [] }),
    saveConfiguration: vi
      .fn<WorkbenchApiClient["saveConfiguration"]>()
      .mockResolvedValue({
        ...saved,
        yaml: "# edited\n" + saved.yaml,
        revision: `config-${"b".repeat(64)}`,
        activation: "requires_restart",
      }),
  };
  const dirty = vi.fn(),
    saving = vi.fn();
  return {
    client,
    dirty,
    saving,
    mount: () =>
      render(
        <ConfigurationView
          client={client}
          onDirtyChange={dirty}
          onSavingChange={saving}
        />,
      ),
  };
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("opens YAML immediately without operator access, keys, lock action or Application-wide badge", async () => {
  const { client, mount } = fixture();
  mount();
  const editor = await screen.findByRole("textbox", {
    name: "YAML configuration",
  });
  expect((editor as HTMLTextAreaElement).value).toBe(saved.yaml);
  expect(client.getConfiguration).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("Operator access")).toBeNull();
  expect(screen.queryByLabelText("Operator key")).toBeNull();
  expect(screen.queryByText("Application-wide")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Lock configuration" }),
  ).toBeNull();
});

it("supports multiline edits, validation and revisioned save", async () => {
  const { client, mount, dirty } = fixture();
  mount();
  const editor = await screen.findByRole("textbox", {
    name: "YAML configuration",
  });
  const edited = "# edited\n" + saved.yaml;
  fireEvent.change(editor, { target: { value: edited } });
  expect(dirty).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "Validate" }));
  await screen.findByText(
    "Configuration is valid. You can save these changes.",
  );
  expect(client.validateConfiguration.mock.calls[0][0]).toBe(edited);
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText("Saved. Restart the API to activate these settings.");
  expect(client.saveConfiguration.mock.calls[0].slice(0, 2)).toEqual([
    edited,
    saved.revision,
  ]);
  expect(dirty).toHaveBeenLastCalledWith(false);
});

it("retains edits on conflict and confirms discard inside the page", async () => {
  const { client, mount } = fixture();
  client.saveConfiguration.mockRejectedValue(
    new WorkbenchApiError("conflict", {
      kind: "http",
      code: "CONFIGURATION_CONFLICT",
      httpStatus: 409,
    }),
  );
  mount();
  const editor = await screen.findByRole("textbox", {
    name: "YAML configuration",
  });
  fireEvent.change(editor, { target: { value: "# retain\n" + saved.yaml } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByRole("alert");
  expect((editor as HTMLTextAreaElement).value).toContain("# retain");
  const unload = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Reload" }));
  fireEvent.click(await screen.findByRole("button", { name: "Keep editing" }));
  expect(client.getConfiguration).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Reload" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Discard changes" }),
  );
  await waitFor(() =>
    expect((editor as HTMLTextAreaElement).value).toBe(saved.yaml),
  );
});

it("blocks duplicate pending saves and retains an unconfirmed draft after timeout", async () => {
  const { client, mount } = fixture();
  let rejectSave = (_error: WorkbenchApiError) => {};
  client.saveConfiguration.mockImplementation(
    () =>
      new Promise((_resolve, reject) => {
        rejectSave = reject;
      }),
  );
  mount();
  const editor = await screen.findByRole("textbox", {
    name: "YAML configuration",
  });
  fireEvent.change(editor, { target: { value: "# pending\n" + saved.yaml } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  fireEvent.click(await screen.findByRole("button", { name: "Saving…" }));
  expect(client.saveConfiguration).toHaveBeenCalledTimes(1);
  expect((editor as HTMLTextAreaElement).readOnly).toBe(true);
  rejectSave(
    new WorkbenchApiError("timeout", { kind: "timeout", code: "TIMEOUT" }),
  );
  await screen.findByRole("alert");
  expect((editor as HTMLTextAreaElement).value).toContain("# pending");
});

it("reports server diagnostics and prevents oversized saves", async () => {
  const { client, mount } = fixture();
  client.validateConfiguration.mockResolvedValue({
    ...meta,
    valid: false,
    errors: [
      { message: "Invalid YAML syntax.", line: 2, column: 3, path: null },
    ],
    warnings: [],
  });
  mount();
  const editor = await screen.findByRole("textbox", {
    name: "YAML configuration",
  });
  fireEvent.change(editor, { target: { value: "document_processing: [" } });
  fireEvent.click(screen.getByRole("button", { name: "Validate" }));
  await screen.findByText("Invalid YAML syntax.");
  expect(screen.getByRole("button", { name: /Line 2:3/ })).toBeTruthy();
  fireEvent.change(editor, { target: { value: "a".repeat(65537) } });
  expect(
    (screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});

it("shows an honest load failure and an explicitly unsaved starter", async () => {
  const { client, mount } = fixture();
  client.getConfiguration.mockRejectedValueOnce(
    new WorkbenchApiError("offline", {
      kind: "transport",
      code: "NETWORK_ERROR",
    }),
  );
  mount();
  await screen.findByRole("alert");
  expect(
    screen.queryByRole("textbox", { name: "YAML configuration" }),
  ).toBeNull();
  client.getConfiguration.mockResolvedValue({
    ...saved,
    exists: false,
    revision: "config-missing",
  });
  fireEvent.click(screen.getByRole("button", { name: "Reload" }));
  await screen.findByText("Starter · not saved");
  expect(
    (screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});
