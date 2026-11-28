import type { AgentEvent } from "../api/contracts";

type ActivityEntry = {
  event: AgentEvent;
  title: string;
  detail: string | null;
};

const labels: Record<AgentEvent["kind"], string> = {
  run_queued: "Run queued",
  run_started: "Run started",
  stage_changed: "Stage updated",
  call_pending: "Model request started",
  call_completed: "Model response received",
  case_completed: "Review finished",
  checkpoint_reused: "Saved result reused",
  run_finished: "Run finished",
};

const modes: Record<string, string> = {
  derive_reference: "Reference preparation",
  judge_evidence: "Evidence review",
  judge_context: "Context review",
  judge_answer: "Answer review",
};

const stages: Record<string, string> = {
  queued: "Waiting to start",
  admission: "Checking request limits",
  provider: "Waiting for the model",
  validation: "Validating the response",
  finalizing: "Saving run results",
};

function humanize(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

export function agentActivity(events: AgentEvent[]): ActivityEntry[] {
  const entries: ActivityEntry[] = [];
  let checkpoints: Set<string> | null = null;
  let checkpointGroup: string | null = null;
  for (const event of events) {
    if (event.kind === "checkpoint_reused") {
      const group = JSON.stringify([event.run_id, event.status, event.reason]);
      if (checkpoints === null || checkpointGroup !== group) {
        checkpoints = new Set();
        checkpointGroup = group;
        entries.push({
          event,
          title: labels.checkpoint_reused,
          detail: "Restored from saved checkpoints.",
        });
      }
      checkpoints.add(event.case_id ?? String(event.sequence));
      const entry = entries[entries.length - 1];
      entry.title = `${checkpoints.size} saved ${checkpoints.size === 1 ? "result" : "results"} reused`;
      entry.event = event;
      continue;
    }
    checkpoints = null;
    checkpointGroup = null;
    const mode = event.call?.mode;
    const label = mode ? (modes[mode] ?? humanize(mode)) : null;
    const callTitle =
      label &&
      (event.kind === "call_pending" || event.kind === "call_completed")
        ? `${label} ${event.kind === "call_pending" ? "started" : event.status === "completed" ? "completed" : humanize(event.status ?? "returned").toLowerCase()}`
        : labels[event.kind];
    const detail = event.reason
      ? humanize(event.reason)
      : event.kind !== "run_finished" && event.stage
        ? (stages[event.stage] ?? humanize(event.stage))
        : null;
    entries.push({ event, title: callTitle, detail });
  }
  return entries.reverse();
}
