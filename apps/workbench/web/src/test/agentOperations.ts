import {
  contractRevision,
  type ApiMeta,
  type AgentCatalog,
  type AgentEvent,
  type AgentProfile,
  type AgentRun,
} from "../api/contracts";

const meta: ApiMeta = {
  contract_revision: contractRevision,
  request_id: "test-request",
  trace_id: "test-trace",
};

export function agentOperationsFixture() {
  const profile: AgentProfile = {
    profile_id: "semantic-review",
    provider: "openai",
    model: "gpt-6.1-sol",
    modes: ["judge_evidence"],
    reasoning_effort: "medium",
    max_estimated_input_tokens: 16384,
    max_output_tokens: 32000,
    max_request_bytes: 16384,
    max_response_bytes: 131072,
    timeout_seconds: 45,
    reserve_usd: "0.397056",
    cache_mode: "explicit",
    cache_ttl_seconds: 1800,
    qualification: {
      state: "qualified",
      revision: "test-qualification",
      verified_at: "2026-11-27T00:00:00Z",
      reason: "historical_pass",
    },
    tariff: {
      version: "test-tariff",
      provider: "openai",
      model: "gpt-6.1-sol",
      service_tier: "standard",
      currency: "USD",
      unit: "per_million_tokens",
      ordinary_input: "2.00",
      cached_read: "0.10",
      cached_write: "2.50",
      output: "10",
      source_url: null,
      effective_at: null,
      verified_at: null,
      cache_ttl_seconds: 1800,
      status: "unknown",
    },
    selectable: true,
  };
  const alternate: AgentProfile = {
    ...profile,
    profile_id: "semantic-review-6.2",
    model: "gpt-6.2-sol",
    tariff: null,
    qualification: {
      state: "unqualified",
      revision: null,
      verified_at: null,
      reason: "offline_only",
    },
    selectable: false,
  };
  const catalog: AgentCatalog = {
    ...meta,
    scope: "local-operator",
    history_available: true,
    agents: [
      {
        agent_id: "semantic-judge",
        display_name: "Semantic Judge",
        runtime_revision: "0.3.3",
        modes: ["judge_evidence"],
        default_profile_id: profile.profile_id,
        selection: {
          profile_id: profile.profile_id,
          revision: "selection-test",
        },
        profiles: [profile, alternate],
      },
    ],
  };
  const run: AgentRun = {
    run_id: "11111111111111111111111111111111",
    agent_id: "semantic-judge",
    mode: "batch",
    origin: "evaluation",
    profile_id: profile.profile_id,
    model: profile.model,
    provider: profile.provider,
    runtime_revision: "0.3.1",
    prompt_revision: null,
    schema_revision: null,
    cache_mode: "explicit",
    tariff: profile.tariff,
    selection_revision: null,
    planned_cases: 2,
    budget_usd: "1",
    queued_at: "2026-11-28T00:00:00Z",
    started_at: "2026-11-28T00:00:01Z",
    finished_at: "2026-11-28T00:00:03Z",
    status: "completed",
    stage: "finalizing",
    last_sequence: 4,
    completed_cases: 2,
    reused_cases: 2,
    failed_cases: 0,
    blocked_cases: 0,
    actual_models: [],
    physical_requests: 0,
    pending_calls: 0,
    cache_observed_requests: 0,
    cache_hit_requests: 0,
    cache_hit_percent: null,
    cache_read_percent: null,
    usage: null,
    usage_coverage: { known_calls: 0, total_calls: 0 },
    estimated_cost_usd: null,
    cost_coverage: { known_calls: 0, total_calls: 0 },
    pending_reserve_usd: null,
  };
  const base: AgentEvent = {
    run_id: run.run_id,
    sequence: 1,
    timestamp: run.queued_at,
    kind: "run_started",
    stage: "admission",
    status: null,
    reason: null,
    case_id: null,
    call: null,
  };
  const events: AgentEvent[] = [
    base,
    {
      ...base,
      sequence: 2,
      kind: "checkpoint_reused",
      case_id: "saved-case-one",
      status: "completed",
    },
    {
      ...base,
      sequence: 3,
      kind: "checkpoint_reused",
      case_id: "saved-case-two",
      status: "completed",
    },
    {
      ...base,
      sequence: 4,
      kind: "run_finished",
      stage: "finalizing",
      status: "completed",
    },
  ];
  return { catalog, run, events, offline: false, runsAvailable: true };
}

export function agentOperationsResponse(
  fixture: ReturnType<typeof agentOperationsFixture>,
  input: RequestInfo | URL,
  init?: RequestInit,
): Response {
  if (fixture.offline) throw new TypeError("Test API disconnected");
  const url = new URL(String(input), "http://localhost");
  const json = (value: unknown) =>
    new Response(JSON.stringify(value), {
      headers: { "Content-Type": "application/json" },
    });
  if (url.pathname.endsWith("/selection")) {
    const change = JSON.parse(String(init?.body)) as {
      profile_id: string;
      expected_revision: string;
    };
    const agent = fixture.catalog.agents[0];
    agent.selection = {
      profile_id: change.profile_id,
      revision: "selection-updated",
    };
    return json({
      ...meta,
      scope: "local-operator",
      agent_id: agent.agent_id,
      selection: agent.selection,
    });
  }
  if (url.pathname.endsWith("/agents")) return json(fixture.catalog);
  if (url.pathname.endsWith(`/runs/${fixture.run.run_id}`))
    return json({
      ...meta,
      scope: "local-operator",
      run: fixture.run,
      events: fixture.events.map((event) => ({
        schema_version: 1,
        scope: "local-operator",
        ...event,
      })),
      next_cursor: "test-cursor",
      has_more: false,
    });
  if (url.pathname.endsWith("/runs")) {
    const model = url.searchParams.get("model");
    return json({
      ...meta,
      scope: "local-operator",
      runs:
        fixture.runsAvailable && (!model || fixture.run.model === model)
          ? [fixture.run]
          : [],
      next_cursor: null,
    });
  }
  throw new Error(`Unexpected test request: ${url.pathname}`);
}
