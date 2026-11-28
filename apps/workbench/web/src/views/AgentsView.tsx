import { useCallback, useState } from "react";
import { Bot, CircleAlert, Radio, RefreshCw } from "lucide-react";
import {
  agentRunStatuses,
  type AgentEvent,
  type AgentMoney,
  type AgentOperationsAgent,
  type AgentProfile,
  type AgentRun,
  type AgentRunStatus,
} from "../api/contracts";
import {
  isAgentRunActive,
  useAgentOperations,
} from "../hooks/useAgentOperations";
import "./agents.css";

const number = (value: number | null | undefined) =>
  value == null ? "Unavailable" : value.toLocaleString();
const money = (value: AgentMoney | undefined) =>
  value == null ? "Unavailable" : `$${value}`;
const title = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
const date = (value: string | number) => new Date(value).toLocaleString();
const percent = (value: number | null) =>
  value == null
    ? "Unavailable"
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
const modelLabel = (model: string) =>
  model === "gpt-6.1-sol"
    ? "GPT-6.1 Sol"
    : model === "gpt-6.2-sol"
      ? "GPT-6.2 Sol"
      : model;

const eventLabels: Record<AgentEvent["kind"], string> = {
  run_queued: "Run planned",
  run_started: "Run started",
  stage_changed: "Stage updated",
  call_pending: "Invocation started",
  call_completed: "Invocation returned",
  case_completed: "Case finished",
  checkpoint_reused: "Checkpoint reused",
  run_finished: "Run finished",
};

function modelEligibility(profile: AgentProfile) {
  const { qualification } = profile;
  if (qualification.reason === "historical_pass") return "Historical v8 pass";
  if (qualification.reason === "offline_only") return "Offline checks only";
  if (qualification.reason) return title(qualification.reason);
  return title(qualification.state);
}

function RunStatus({ status }: { status: AgentRunStatus }) {
  const tone = {
    completed: "success",
    running: "running",
    queued: "neutral",
    failed: "error",
    blocked: "error",
    interrupted: "neutral",
    cancelled: "neutral",
  }[status];
  return <span className={`status ${tone}`}>{title(status)}</span>;
}

function ModelPanel({
  agent,
  profile,
  onInspect,
  onSave,
  saving,
  online,
  message,
}: {
  agent: AgentOperationsAgent;
  profile: AgentProfile;
  onInspect: (profile: string) => void;
  onSave: () => void;
  saving: boolean;
  online: boolean;
  message: string;
}) {
  const tariff = profile.tariff;
  const rates = [
    ["Ordinary input", tariff?.ordinary_input],
    ["Cached input read", tariff?.cached_read],
    ["Cache write (30 min)", tariff?.cached_write],
    ["Output", tariff?.output],
  ] as const;
  return (
    <section
      className="data-panel agents-panel"
      aria-labelledby="agent-model-title"
    >
      <header className="agents-panel-heading">
        <div className="agents-identity">
          <span className="data-file-icon">
            <Bot size={19} />
          </span>
          <div>
            <h2 id="agent-model-title">{agent.display_name}</h2>
            <p className="mono">
              {agent.agent_id} · Runtime {agent.runtime_revision}
            </p>
          </div>
        </div>
        <span className="run-source mono">{agent.modes.length} modes</span>
      </header>
      <div className="agents-models">
        {agent.profiles.map((option) => (
          <button
            type="button"
            key={option.profile_id}
            className="agents-model"
            aria-pressed={profile.profile_id === option.profile_id}
            onClick={() => onInspect(option.profile_id)}
          >
            <strong>{modelLabel(option.model)}</strong>
            <small>{modelEligibility(option)}</small>
            <span className="mono">
              {option.profile_id === agent.selection.profile_id
                ? "Selected"
                : option.selectable
                  ? "Available"
                  : "Selection unavailable"}
            </span>
          </button>
        ))}
      </div>
      <div className="agents-selection">
        <div>
          <strong>{profile.profile_id}</strong>
          <p>
            {profile.profile_id === agent.default_profile_id
              ? "Runtime default · "
              : ""}
            {profile.qualification.verified_at
              ? date(profile.qualification.verified_at)
              : "Live qualification pending"}
          </p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={onSave}
          disabled={
            !online ||
            saving ||
            !profile.selectable ||
            profile.profile_id === agent.selection.profile_id
          }
        >
          {saving ? "Saving…" : "Use for next run"}
        </button>
      </div>
      {message && (
        <p className="agents-caption" role="status">
          {message}
        </p>
      )}
      <dl className="agents-facts">
        <div>
          <dt>Reasoning</dt>
          <dd>{title(profile.reasoning_effort)}</dd>
        </div>
        <div>
          <dt>Input admission units</dt>
          <dd>{number(profile.max_estimated_input_tokens)}</dd>
        </div>
        <div>
          <dt>Generated tokens</dt>
          <dd>{number(profile.max_output_tokens)}</dd>
        </div>
        <div>
          <dt>Request / response</dt>
          <dd>
            {profile.max_request_bytes != null &&
            profile.max_response_bytes != null
              ? `${profile.max_request_bytes / 1024} / ${profile.max_response_bytes / 1024} KiB`
              : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>Deadline</dt>
          <dd>
            {profile.timeout_seconds == null
              ? "Unavailable"
              : `${profile.timeout_seconds} s`}
          </dd>
        </div>
        <div>
          <dt>Reserve per call</dt>
          <dd>{money(profile.reserve_usd)}</dd>
        </div>
        <div>
          <dt>Cache policy</dt>
          <dd>
            {title(profile.cache_mode)} ·{" "}
            {profile.cache_ttl_seconds == null
              ? "TTL unavailable"
              : `${profile.cache_ttl_seconds / 60} min`}
          </dd>
        </div>
        <div>
          <dt>Qualification revision</dt>
          <dd className="agents-wrap">
            {profile.qualification.revision ?? "Unavailable"}
          </dd>
        </div>
      </dl>
      <div className="agents-tariff">
        <div className="agents-inline-heading">
          <h3>Token rates</h3>
          <span>USD / 1M tokens</span>
        </div>
        <dl className="agents-rates">
          {rates.map(([label, rate]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{money(rate)}</dd>
            </div>
          ))}
        </dl>
        <p className="agents-caption">
          {tariff ? (
            <>
              {tariff.version} · {title(tariff.status)}
              {tariff.verified_at ? ` ${date(tariff.verified_at)}` : ""}
              {tariff.source_url && (
                <>
                  {" "}
                  ·{" "}
                  <a href={tariff.source_url} target="_blank" rel="noreferrer">
                    Official tariff
                  </a>
                </>
              )}
            </>
          ) : (
            "Pricing unavailable"
          )}
        </p>
      </div>
    </section>
  );
}

function RunSummary({
  run,
  current,
}: {
  run: AgentRun | null;
  current: boolean;
}) {
  const usage = run?.usage;
  const active = run ? isAgentRunActive(run) : false;
  const elapsed =
    run?.started_at && (active || run.finished_at)
      ? Math.max(
          0,
          Math.floor(
            ((run.finished_at ? Date.parse(run.finished_at) : Date.now()) -
              Date.parse(run.started_at)) /
              1000,
          ),
        )
      : null;
  return (
    <section
      className="data-panel agents-panel"
      aria-labelledby="agent-run-title"
    >
      <header className="agents-panel-heading">
        <div>
          <h2 id="agent-run-title">
            {active ? "Live run" : current ? "Latest run" : "Run details"}
          </h2>
          {run && (
            <p className="mono">
              {title(run.origin)} · {run.run_id}
            </p>
          )}
        </div>
        {run && <RunStatus status={run.status} />}
      </header>
      {!run ? (
        <p className="agents-empty">No recorded runs for this agent.</p>
      ) : (
        <>
          <div className="agents-metrics">
            <div>
              <span>Estimated cost</span>
              <strong>{money(run.estimated_cost_usd)}</strong>
            </div>
            <div>
              <span>Observed tokens</span>
              <strong>{number(usage?.total_tokens)}</strong>
            </div>
            <div>
              <span>Cases finished</span>
              <strong>
                {run.completed_cases} / {run.planned_cases ?? "—"}
              </strong>
            </div>
          </div>
          {run.planned_cases !== null && (
            <progress
              className="agents-progress"
              aria-label="Cases finished"
              max={run.planned_cases}
              value={run.completed_cases}
            />
          )}
          {run.pending_calls > 0 && (
            <div className="agents-pending">
              <Radio size={16} />
              {active
                ? "Awaiting invocation result · Usage pending"
                : "Invocation outcome unavailable"}
            </div>
          )}
          <dl className="agents-facts">
            <div>
              <dt>Requested model</dt>
              <dd>{modelLabel(run.model)}</dd>
            </div>
            <div>
              <dt>Served model</dt>
              <dd data-testid="agent-served-model">
                {run.actual_models.length
                  ? run.actual_models.map(modelLabel).join(", ")
                  : "Unavailable"}
              </dd>
            </div>
            <div>
              <dt>Input</dt>
              <dd>{number(usage?.input_tokens)}</dd>
            </div>
            <div>
              <dt>Output</dt>
              <dd>{number(usage?.output_tokens)}</dd>
            </div>
            <div>
              <dt>Ordinary input</dt>
              <dd>{number(usage?.ordinary_input_tokens)}</dd>
            </div>
            <div>
              <dt>Reasoning (in output)</dt>
              <dd>{number(usage?.reasoning_tokens)}</dd>
            </div>
            <div>
              <dt>Cache read</dt>
              <dd>{number(usage?.cached_read_tokens)}</dd>
            </div>
            <div>
              <dt>Cache write</dt>
              <dd>{number(usage?.cached_write_tokens)}</dd>
            </div>
            <div>
              <dt>Cache read share</dt>
              <dd>{percent(run.cache_read_percent)}</dd>
            </div>
            <div>
              <dt>Request cache hits</dt>
              <dd>
                {percent(run.cache_hit_percent)}
                {run.cache_observed_requests > 0 &&
                  ` · ${run.cache_hit_requests}/${run.cache_observed_requests}`}
              </dd>
            </div>
            <div>
              <dt>Physical requests</dt>
              <dd>{number(run.physical_requests)}</dd>
            </div>
            <div>
              <dt>Reused checkpoints</dt>
              <dd>{number(run.reused_cases)}</dd>
            </div>
            <div>
              <dt>Failed / blocked cases</dt>
              <dd>
                {run.failed_cases} / {run.blocked_cases}
              </dd>
            </div>
            <div>
              <dt>Elapsed</dt>
              <dd>{elapsed == null ? "Unavailable" : `${elapsed} s`}</dd>
            </div>
            <div>
              <dt>Run budget</dt>
              <dd>{money(run.budget_usd)}</dd>
            </div>
            <div>
              <dt>Pending reserve</dt>
              <dd>
                {run.pending_calls > 0
                  ? money(run.pending_reserve_usd)
                  : "None"}
              </dd>
            </div>
            <div>
              <dt>Token coverage</dt>
              <dd>
                {run.usage_coverage.known_calls} /{" "}
                {run.usage_coverage.total_calls} requests
              </dd>
            </div>
            <div>
              <dt>Cost coverage</dt>
              <dd>
                {run.cost_coverage.known_calls} /{" "}
                {run.cost_coverage.total_calls} requests
              </dd>
            </div>
          </dl>
          {run.actual_models.some((model) => model !== run.model) && (
            <p className="agents-alert" role="status">
              <CircleAlert size={16} /> Served model differs from the requested
              model.
            </p>
          )}
          <p className="agents-caption">
            {run.profile_id} · {run.tariff?.version ?? "Tariff unavailable"} ·
            Runtime {run.runtime_revision}
          </p>
        </>
      )}
    </section>
  );
}

function Timeline({ events }: { events: AgentEvent[] }) {
  return (
    <div className="data-panel data-scroll">
      {events.length === 0 ? (
        <p className="agents-empty">No activity recorded.</p>
      ) : (
        <table className="data-table agents-table" aria-label="Run activity">
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>Case / call</th>
              <th>Outcome</th>
              <th>Tokens in / out</th>
              <th>Estimated cost</th>
            </tr>
          </thead>
          <tbody>
            {events
              .slice()
              .reverse()
              .map((event) => (
                <tr key={event.sequence} data-event-sequence={event.sequence}>
                  <td>
                    <time dateTime={event.timestamp}>
                      {date(event.timestamp)}
                    </time>
                  </td>
                  <td>
                    <strong>{eventLabels[event.kind]}</strong>
                    <small>
                      {event.call?.mode
                        ? title(event.call.mode)
                        : event.stage
                          ? title(event.stage)
                          : ""}
                    </small>
                  </td>
                  <td className="mono">
                    {event.call?.case_id ?? event.case_id ?? "—"}
                    {event.call && <small>{event.call.call_id}</small>}
                  </td>
                  <td>
                    {event.status ? <RunStatus status={event.status} /> : "—"}
                    <small>
                      {event.reason && title(event.reason.toLowerCase())}
                      {event.call?.elapsed_ms != null &&
                        ` · ${number(event.call.elapsed_ms)} ms`}
                    </small>
                  </td>
                  <td>
                    {event.call?.usage
                      ? `${number(event.call.usage.input_tokens)} / ${number(event.call.usage.output_tokens)}`
                      : "—"}
                  </td>
                  <td>
                    {event.call?.estimated_cost_usd != null
                      ? money(event.call.estimated_cost_usd)
                      : "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function AgentsView() {
  const [agentId, setAgentId] = useState<string>();
  const [inspected, setInspected] = useState<string>();
  const [status, setStatus] = useState<AgentRunStatus>();
  const [model, setModel] = useState<string>();
  const [cursors, setCursors] = useState<string[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const resetHistory = useCallback(() => setCursors([]), []);
  const ops = useAgentOperations(
    { agentId, status, model, cursor: cursors.at(-1) },
    selectedRunId,
    resetHistory,
  );
  const agent =
    ops.catalog?.agents.find((entry) => entry.agent_id === agentId) ??
    ops.catalog?.agents[0];
  const profile = agent?.profiles.find(
    (entry) => entry.profile_id === (inspected ?? agent.selection.profile_id),
  );
  const run =
    ops.timeline?.run ??
    (selectedRunId
      ? (ops.history?.runs.find((entry) => entry.run_id === selectedRunId) ??
        null)
      : ops.currentRun);
  const connectionLabels = {
    loading: "Connecting",
    connected: "Connected",
    unavailable: "Unavailable",
    disconnected: ops.updatedAt ? "Stale · disconnected" : "Disconnected",
  };
  return (
    <section className="view-page agents-page" aria-labelledby="agents-title">
      <header className="view-heading">
        <div>
          <h1 id="agents-title">Agents</h1>
          <p>Local agent operations · Preview and Live</p>
        </div>
        <div className="agents-connection">
          <button
            type="button"
            className="icon-button"
            title="Refresh agent operations"
            aria-label="Refresh agent operations"
            onClick={ops.refresh}
          >
            <RefreshCw size={17} />
          </button>
          <div>
            <span
              className={`status ${ops.connection === "connected" ? "success" : "neutral"}`}
              role="status"
            >
              {connectionLabels[ops.connection]}
            </span>
            {ops.updatedAt && (
              <time dateTime={new Date(ops.updatedAt).toISOString()}>
                Updated {date(ops.updatedAt)}
              </time>
            )}
          </div>
        </div>
      </header>
      {!agent || !profile ? (
        <div className="data-panel agents-empty">
          {ops.connection === "loading"
            ? "Loading the agent registry…"
            : ops.connection === "disconnected"
              ? "The Workbench API could not be reached. Retrying automatically."
              : ops.catalog
                ? "The local registry has no available agents."
                : "Agent operations are unavailable. The optional local bridge needs a MAF catalog."}
        </div>
      ) : (
        <>
          {ops.catalog && ops.catalog.agents.length > 1 && (
            <label className="view-filter agents-registry">
              Agent
              <select
                className="input"
                value={agent.agent_id}
                onChange={(event) => {
                  setAgentId(event.target.value);
                  setInspected(undefined);
                  setStatus(undefined);
                  setModel(undefined);
                  setCursors([]);
                  setSelectedRunId(null);
                }}
              >
                {ops.catalog.agents.map((entry) => (
                  <option key={entry.agent_id} value={entry.agent_id}>
                    {entry.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(!ops.catalog?.history_available ||
            ops.connection === "unavailable") && (
            <p className="agents-alert">
              Run history is unavailable for the local operator.
            </p>
          )}
          <div className="agents-overview">
            <ModelPanel
              agent={agent}
              profile={profile}
              onInspect={setInspected}
              onSave={() =>
                void ops.selectProfile(
                  agent.agent_id,
                  profile.profile_id,
                  agent.selection,
                )
              }
              online={ops.connection === "connected"}
              saving={ops.saving}
              message={ops.selectionMessage}
            />
            <RunSummary
              run={run}
              current={
                !selectedRunId || (run !== null && isAgentRunActive(run))
              }
            />
          </div>
          <section
            className="agents-section"
            aria-labelledby="agent-history-title"
          >
            <div className="agents-inline-heading">
              <div>
                <h2 id="agent-history-title">Run history</h2>
                <p>
                  Local metadata · 30 days or 100 recent terminal runs · 8 MiB
                  per run
                </p>
              </div>
              <div className="agents-filters">
                <label className="view-filter">
                  <select
                    aria-label="Run status"
                    className="input"
                    value={status ?? ""}
                    onChange={(event) => {
                      setStatus(
                        (event.target.value || undefined) as
                          AgentRunStatus | undefined,
                      );
                      setCursors([]);
                    }}
                  >
                    <option value="">All statuses</option>
                    {agentRunStatuses.map((status) => (
                      <option key={status} value={status}>
                        {title(status)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="view-filter">
                  <select
                    aria-label="Run model"
                    className="input"
                    value={model ?? ""}
                    onChange={(event) => {
                      setModel(event.target.value || undefined);
                      setCursors([]);
                    }}
                  >
                    <option value="">All models</option>
                    {agent.profiles.map((profile) => (
                      <option key={profile.model} value={profile.model}>
                        {modelLabel(profile.model)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            <div className="data-panel data-scroll">
              {!ops.history?.runs.length ? (
                <p className="agents-empty">
                  {ops.history
                    ? "No matching runs."
                    : "Run history is loading or unavailable."}
                </p>
              ) : (
                <table
                  className="data-table agents-table"
                  aria-label="Agent run history"
                >
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Requested model</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Physical requests</th>
                      <th>Estimated cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ops.history.runs.map((item) => (
                      <tr
                        key={item.run_id}
                        className={
                          item.run_id === run?.run_id ? "data-selected" : ""
                        }
                      >
                        <td>
                          <button
                            type="button"
                            className="data-name"
                            aria-pressed={item.run_id === run?.run_id}
                            onClick={() => setSelectedRunId(item.run_id)}
                          >
                            <span>
                              <strong>{title(item.origin)}</strong>
                              <small className="mono">{item.run_id}</small>
                            </span>
                          </button>
                        </td>
                        <td>{modelLabel(item.model)}</td>
                        <td>
                          <RunStatus status={item.status} />
                        </td>
                        <td>{date(item.started_at ?? item.queued_at)}</td>
                        <td>{number(item.physical_requests)}</td>
                        <td className="mono">
                          {money(item.estimated_cost_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {(cursors.length > 0 || ops.history?.next_cursor) && (
              <div className="agents-actions">
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={!cursors.length}
                  onClick={() => setCursors(cursors.slice(0, -1))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={!ops.history?.next_cursor}
                  onClick={() => {
                    if (ops.history?.next_cursor)
                      setCursors([...cursors, ops.history.next_cursor]);
                  }}
                >
                  Next
                </button>
              </div>
            )}
          </section>
          <section
            className="agents-section"
            aria-labelledby="agent-activity-title"
          >
            <div className="agents-inline-heading">
              <h2 id="agent-activity-title">Activity</h2>
              {selectedRunId && (
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => setSelectedRunId(null)}
                >
                  Follow latest run
                </button>
              )}
            </div>
            <Timeline events={ops.timeline?.events ?? []} />
          </section>
        </>
      )}
    </section>
  );
}
