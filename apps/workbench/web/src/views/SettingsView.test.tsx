// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { BackendCapabilities, BackendProfile } from "../api/contracts";
import type { BackendDiscoveryState } from "../domain/backendDiscovery";
import { defaultSettings } from "../domain/fixtures";
import { SettingsView } from "./SettingsView";

const profile: BackendProfile = {
  profile_id: "postgres-fts-baseline",
  profile_revision: "postgres-fts-baseline-r1",
  kind: "lexical_search",
  workspace_ids: ["development"],
  corpus_id: "corpus-live",
  score_type: "postgres_ts_rank_cd",
  parameters: {
    query: { type: "string", min_length: 1, max_length: 4096 },
    top_k: { type: "integer", default: 10, minimum: 1, maximum: 50 },
  },
  limits: {
    max_request_bytes: 32768,
    timeout_ms: 10000,
    max_concurrent_searches: 2,
    max_corpus_chunks: 10000,
    max_corpus_bytes: 52428800,
  },
};
const alternate = {
  ...profile,
  profile_id: "postgres-fts-bounded",
  profile_revision: "bounded-r2",
};
const capabilities: BackendCapabilities = {
  contract_revision: "rag-api-v1.0",
  request_id: "request-1",
  trace_id: "trace-1",
  backend_revision: "workbench-api-lexical-v1",
  deployment_mode: "single_workspace_dev",
  service_state: "running",
  profiles: [
    profile,
    alternate,
    { ...profile, profile_id: "foreign-profile", workspace_ids: ["foreign"] },
  ],
  features: {
    search: true,
    documents: true,
    upload: true,
    document_details: true,
    jobs: true,
  },
  pdf_ingestion: {
    available: false,
    text_layer: false,
    page_provenance: false,
    table_rows: false,
    original_evidence: false,
    ocr: false,
    visual_understanding: false,
    visual_detection_coverage: "unverified",
    max_bytes: 8388608,
    max_pages: 32,
  },
  dependencies: { database: { status: "ready", workspace_id: "development" } },
};

function fixture(state?: BackendDiscoveryState) {
  const selectProfile = vi.fn();
  const onExecutionChange = vi.fn();
  const discovery = {
    state: state ?? {
      status: "ready" as const,
      lastCheckedAt: null,
      selectedWorkspaceId: "development",
      profile,
      capabilities,
      workspaces: [
        {
          workspace_id: "development",
          name: "Development",
          status: "ready" as const,
        },
      ],
    },
    refresh: vi.fn(),
    selectWorkspace: vi.fn(),
    selectProfile,
  };
  return { discovery, selectProfile, onExecutionChange };
}

afterEach(cleanup);

it("selects only qualified profiles for the current workspace and invalidates the previous execution", () => {
  const data = fixture();
  render(
    <SettingsView
      settings={defaultSettings}
      onChange={vi.fn()}
      mode="live"
      discovery={data.discovery}
      onExecutionChange={data.onExecutionChange}
    />,
  );
  const selector = screen.getByRole("combobox", {
    name: "Execution profile",
  }) as HTMLSelectElement;
  expect(selector.disabled).toBe(false);
  expect(Array.from(selector.options, (option) => option.value)).toEqual([
    "",
    profile.profile_id,
    alternate.profile_id,
  ]);
  expect(screen.getByText("postgres-fts-bounded · bounded-r2")).toBeTruthy();
  fireEvent.change(selector, { target: { value: alternate.profile_id } });
  expect(data.onExecutionChange).toHaveBeenCalledOnce();
  expect(data.selectProfile).toHaveBeenCalledWith(alternate.profile_id);
  expect(
    screen.getByText(
      "Approved lexical profiles only. Higher scores rank first.",
    ),
  ).toBeTruthy();
});

it("allows an explicit replacement after the previous profile becomes unavailable", () => {
  const data = fixture({
    status: "awaiting_profile",
    selectedWorkspaceId: "development",
    profile: null,
    capabilities,
    lastCheckedAt: null,
    workspaces: [
      { workspace_id: "development", name: "Development", status: "ready" },
    ],
    error: {
      code: "PROFILE_NOT_AVAILABLE",
      message: "Choose an approved profile.",
    },
  });
  render(
    <SettingsView
      settings={defaultSettings}
      onChange={vi.fn()}
      mode="live"
      discovery={data.discovery}
      onExecutionChange={data.onExecutionChange}
    />,
  );
  const selector = screen.getByRole("combobox", {
    name: "Execution profile",
  }) as HTMLSelectElement;
  expect(selector.disabled).toBe(false);
  expect(selector.value).toBe("");
  fireEvent.change(selector, { target: { value: profile.profile_id } });
  expect(data.selectProfile).toHaveBeenCalledWith(profile.profile_id);
});

it("keeps execution profile selection disabled in Preview", () => {
  const data = fixture();
  render(
    <SettingsView
      settings={defaultSettings}
      onChange={vi.fn()}
      mode="preview"
      discovery={data.discovery}
      onExecutionChange={data.onExecutionChange}
    />,
  );
  expect(
    (
      screen.getByRole("combobox", {
        name: "Execution profile",
      }) as HTMLSelectElement
    ).disabled,
  ).toBe(true);
});
