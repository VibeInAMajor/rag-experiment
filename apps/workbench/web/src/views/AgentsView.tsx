import { useCallback, useState } from "react";
import { CircleAlert, Radio, RefreshCw } from "lucide-react";
import {
  agentRunStatuses,
  type AgentEvent,
  type AgentMoney,
  type AgentOperationsAgent,
  type AgentProfile,
  type AgentRun,
  type AgentRunStatus,
} from "../api/contracts";
import { agentActivity } from "../domain/agentActivity";
import {
  isAgentRunActive,
  useAgentOperations,
} from "../hooks/useAgentOperations";
import "./agents.css";

const number = (value: number | null | undefined) =>
  value == null ? "—" : value.toLocaleString();
const money = (value: AgentMoney | undefined) =>
  value == null ? "Not reported" : `$${value}`;
const title = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
const date = (value: string | number) => new Date(value).toLocaleString();
const shortDate = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
const time = (value: string | number) =>
  new Date(value).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
const modelLabel = (model: string) =>
  model.replace(/^gpt-(.+)-sol$/, "GPT-$1 Sol");

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
  const models = [...new Set(agent.profiles.map((option) => option.model))];
  const reasoning = agent.profiles.filter(
    (option) => option.model === profile.model,
  );
  const rates = [
    ["Input", profile.tariff?.ordinary_input],
    ["Cached input", profile.tariff?.cached_read],
    ["Cache write", profile.tariff?.cached_write],
    ["Output", profile.tariff?.output],
  ] as const;
  return (
    <section
      className="data-panel agents-panel"
      aria-labelledby="agent-model-title"
    >
      <header className="agents-panel-heading">
        <h2 id="agent-model-title">{agent.display_name}</h2>
      </header>
      <div className="agents-model-fields">
        <label className="view-filter">
          Model
          <select
            className="input"
            value={profile.model}
            disabled={saving || !online}
            onChange={(event) => {
              const options = agent.profiles.filter(
                (option) => option.model === event.target.value,
              );
              const next =
                options.find(
                  (option) =>
                    option.reasoning_effort === profile.reasoning_effort,
                ) ??
                options.find((option) => option.selectable) ??
                options[0];
              if (next) onInspect(next.profile_id);
            }}
          >
            {models.map((model) => (
              <option key={model} value={model}>
                {modelLabel(model)}
              </option>
            ))}
          </select>
        </label>
        <label className="view-filter">
          Reasoning
          <select
            className="input"
            value={profile.profile_id}
            disabled={saving || !online}
            onChange={(event) => onInspect(event.target.value)}
          >
            {reasoning.map((option) => (
              <option key={option.profile_id} value={option.profile_id}>
                {title(option.reasoning_effort ?? "default")}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!profile.selectable && (
        <p className="agents-caption" role="status">
          This model and reasoning combination is not enabled for runs.
        </p>
      )}
      {profile.profile_id !== agent.selection.profile_id && (
        <div className="agents-actions">
          <button
            className="button button-primary"
            type="button"
            onClick={onSave}
            disabled={!online || saving || !profile.selectable}
          >
            {saving ? "Saving…" : "Save selection"}
          </button>
        </div>
      )}
      {message && (
        <p className="agents-caption" role="status">
          {message}
        </p>
      )}
      <details className="agents-details">
        <summary>Model details</summary>
        <dl className="agents-facts">
          <div>
            <dt>Input limit</dt>
            <dd>{number(profile.max_estimated_input_tokens)}</dd>
          </div>
          <div>
            <dt>Output limit</dt>
            <dd>{number(profile.max_output_tokens)}</dd>
          </div>
          {profile.timeout_seconds !== null && (
            <div>
              <dt>Timeout</dt>
              <dd>{profile.timeout_seconds} s</dd>
            </div>
          )}
          {profile.reserve_usd !== null && (
            <div>
              <dt>Request reserve</dt>
              <dd>{money(profile.reserve_usd)}</dd>
            </div>
          )}
        </dl>
        <div className="agents-inline-heading agents-rate-heading">
          <h3>Token rates</h3>
          <span>USD / 1M tokens</span>
        </div>
        <dl className="agents-facts">
          {rates.map(([label, rate]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{money(rate)}</dd>
            </div>
          ))}
        </dl>
      </details>
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
  const active = run ? isAgentRunActive(run) : false;
  const restored =
    !!run &&
    run.physical_requests === 0 &&
    run.pending_calls === 0 &&
    run.reused_cases > 0;
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
        <h2 id="agent-run-title">
          {active ? "Active run" : current ? "Latest run" : "Run details"}
        </h2>
        {run && <RunStatus status={run.status} />}
      </header>
      {!run ? (
        <p className="agents-empty">No runs recorded yet.</p>
      ) : (
        <>
          <p className="agents-run-context">
            <span>{modelLabel(run.model)}</span>
            <time
              dateTime={run.started_at ?? run.queued_at}
              title={date(run.started_at ?? run.queued_at)}
            >
              {shortDate(run.started_at ?? run.queued_at)}
            </time>
          </p>
          {restored ? (
            <p className="agents-restored">
              {number(run.reused_cases)} saved results reused. No model requests
              were recorded.
            </p>
          ) : (
            <>
              <dl className="agents-run-totals" aria-label="Run totals">
                <div>
                  <dt>Estimated cost</dt>
                  <dd>{money(run.estimated_cost_usd)}</dd>
                </div>
                <div>
                  <dt>Tokens in</dt>
                  <dd>{number(run.usage?.input_tokens)}</dd>
                </div>
                <div>
                  <dt>Tokens out</dt>
                  <dd>{number(run.usage?.output_tokens)}</dd>
                </div>
              </dl>
              {run.physical_requests > 0 &&
                (run.usage_coverage.known_calls <
                  run.usage_coverage.total_calls ||
                  run.cost_coverage.known_calls <
                    run.cost_coverage.total_calls) && (
                  <p className="agents-caption">
                    Usage or cost is missing for some requests; totals include
                    reported values only.
                  </p>
                )}
            </>
          )}
          {!restored && (
            <div className="agents-run-progress">
              <span>
                {number(run.completed_cases)}
                {run.planned_cases !== null
                  ? ` / ${number(run.planned_cases)}`
                  : ""}{" "}
                results
              </span>
              {elapsed !== null && <span>{elapsed} s</span>}
            </div>
          )}
          {!restored && run.planned_cases !== null && run.planned_cases > 0 && (
            <progress
              className="agents-progress"
              aria-label="Results finished"
              max={run.planned_cases}
              value={run.completed_cases}
            />
          )}
          {run.pending_calls > 0 && (
            <p className="agents-pending">
              <Radio size={15} />
              {active
                ? "Waiting for the model. Usage will appear when it responds."
                : "Request outcome has not been reported."}
            </p>
          )}
          {run.actual_models.some((model) => model !== run.model) && (
            <p className="agents-alert" role="status">
              <CircleAlert size={16} />
              The responding model differs from the selected model.
            </p>
          )}
          {!restored && (
            <details className="agents-details">
              <summary>Run details</summary>
              <dl className="agents-facts">
                <div>
                  <dt>Model requests</dt>
                  <dd>{number(run.physical_requests)}</dd>
                </div>
                <div>
                  <dt>Saved results reused</dt>
                  <dd>{number(run.reused_cases)}</dd>
                </div>
                <div>
                  <dt>Failed / blocked</dt>
                  <dd>
                    {run.failed_cases} / {run.blocked_cases}
                  </dd>
                </div>
                {run.actual_models.length > 0 && (
                  <div>
                    <dt>Responding model</dt>
                    <dd>{run.actual_models.map(modelLabel).join(", ")}</dd>
                  </div>
                )}
                {run.pending_reserve_usd !== null && run.pending_calls > 0 && (
                  <div>
                    <dt>Pending reserve</dt>
                    <dd>{money(run.pending_reserve_usd)}</dd>
                  </div>
                )}
                {run.budget_usd !== null && (
                  <div>
                    <dt>Budget</dt>
                    <dd>{money(run.budget_usd)}</dd>
                  </div>
                )}
                {run.usage?.cached_read_tokens != null && (
                  <div>
                    <dt>Cached input tokens</dt>
                    <dd>{number(run.usage.cached_read_tokens)}</dd>
                  </div>
                )}
                {run.usage?.reasoning_tokens != null && (
                  <div>
                    <dt>Reasoning tokens</dt>
                    <dd>{number(run.usage.reasoning_tokens)}</dd>
                  </div>
                )}
              </dl>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function Timeline({ events }: { events: AgentEvent[] }) {
  const entries = agentActivity(events);
  return (
    <div className="data-panel data-scroll">
      {entries.length === 0 ? (
        <p className="agents-empty">No activity recorded for this run.</p>
      ) : (
        <table className="data-table agents-activity" aria-label="Run activity">
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(({ event, title, detail }) => (
              <tr key={event.sequence} data-event-sequence={event.sequence}>
                <td className="agents-event-time">
                  <time
                    dateTime={event.timestamp}
                    title={date(event.timestamp)}
                  >
                    {time(event.timestamp)}
                  </time>
                </td>
                <td>
                  <strong>{title}</strong>
                  {detail && <small>{detail}</small>}
                </td>
                <td>{event.status && <RunStatus status={event.status} />}</td>
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
  const profile =
    agent?.profiles.find((entry) => entry.profile_id === inspected) ??
    agent?.profiles.find(
      (entry) => entry.profile_id === agent.selection.profile_id,
    );
  const candidate =
    ops.timeline?.run ??
    (selectedRunId
      ? (ops.history?.runs.find((entry) => entry.run_id === selectedRunId) ??
        null)
      : ops.currentRun);
  const run = candidate?.agent_id === agent?.agent_id ? candidate : null;
  const history = ops.history?.runs.filter(
    (entry) => entry.agent_id === agent?.agent_id,
  );
  const connectionLabels = {
    loading: "Connecting",
    connected: "Connected",
    unavailable: "Unavailable",
    disconnected: ops.updatedAt
      ? "Disconnected · showing last update"
      : "Disconnected",
  };
  return (
    <section className="view-page agents-page" aria-labelledby="agents-title">
      <header className="view-heading">
        <h1 id="agents-title">Agents</h1>
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
          <span
            className={`status ${ops.connection === "connected" ? "success" : "neutral"}`}
            role="status"
          >
            {connectionLabels[ops.connection]}
          </span>
          {ops.updatedAt && (
            <time
              dateTime={new Date(ops.updatedAt).toISOString()}
              title={date(ops.updatedAt)}
            >
              {time(ops.updatedAt)}
            </time>
          )}
        </div>
      </header>
      {!agent || !profile ? (
        <div className="data-panel agents-empty">
          {ops.connection === "loading"
            ? "Loading agents…"
            : ops.connection === "disconnected"
              ? "Cannot reach the API. Reconnecting…"
              : ops.catalog
                ? "No agents are configured."
                : "Agent operations are unavailable. Connect an agent journal to see models and runs."}
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
            <p className="agents-alert">Run history is unavailable.</p>
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
            <Timeline
              events={
                run && ops.timeline?.run.run_id === run.run_id
                  ? ops.timeline.events
                  : []
              }
            />
          </section>
          <section
            className="agents-section"
            aria-labelledby="agent-history-title"
          >
            <div className="agents-inline-heading">
              <h2 id="agent-history-title">Run history</h2>
              <div className="agents-filters">
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
                  {agentRunStatuses.map((value) => (
                    <option key={value} value={value}>
                      {title(value)}
                    </option>
                  ))}
                </select>
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
                  {[...new Set(agent.profiles.map((entry) => entry.model))].map(
                    (value) => (
                      <option key={value} value={value}>
                        {modelLabel(value)}
                      </option>
                    ),
                  )}
                </select>
              </div>
            </div>
            <div className="data-panel data-scroll">
              {!history?.length ? (
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
                      <th>Started</th>
                      <th>Model</th>
                      <th>Status</th>
                      <th>Results</th>
                      <th>Estimated cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => (
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
                            aria-label={`View run from ${date(item.started_at ?? item.queued_at)}`}
                            aria-pressed={item.run_id === run?.run_id}
                            onClick={() => setSelectedRunId(item.run_id)}
                          >
                            <time dateTime={item.started_at ?? item.queued_at}>
                              {shortDate(item.started_at ?? item.queued_at)}
                            </time>
                          </button>
                        </td>
                        <td>{modelLabel(item.model)}</td>
                        <td>
                          <RunStatus status={item.status} />
                        </td>
                        <td>
                          {number(item.completed_cases)}
                          {item.reused_cases > 0 && (
                            <small>{number(item.reused_cases)} reused</small>
                          )}
                        </td>
                        <td className="agents-numeric">
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
        </>
      )}
    </section>
  );
}
