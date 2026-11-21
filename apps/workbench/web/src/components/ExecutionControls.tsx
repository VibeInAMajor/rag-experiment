import type { ExecutionMode } from "../domain/types";
import type { BackendDiscoveryState } from "../hooks/useBackendDiscovery";

const statusLabels: Record<BackendDiscoveryState["status"], string> = {
  unconfigured: "Not checked",
  checking: "Checking",
  ready: "Ready",
  not_ready: "Not ready",
  unavailable: "Offline",
  incompatible: "Incompatible",
};

export function ExecutionControls({
  mode,
  onChange,
  state,
}: {
  mode: ExecutionMode;
  onChange: (mode: ExecutionMode) => void;
  state: BackendDiscoveryState;
}) {
  return (
    <>
      <fieldset className="execution-mode">
        <legend className="sr-only">Execution mode</legend>
        {(["preview", "live"] as const).map((value) => (
          <label key={value}>
            <input
              type="radio"
              name="execution-mode"
              value={value}
              checked={mode === value}
              onChange={() => onChange(value)}
            />
            <span>{value === "preview" ? "Preview" : "Live"}</span>
          </label>
        ))}
      </fieldset>
      <span
        role="status"
        aria-label="Execution status"
        className={`execution-status mono ${mode === "live" ? state.status : "preview"}`}
      >
        <span
          className={`status-dot ${mode === "live" && state.status === "ready" ? "success" : mode === "live" && ["incompatible", "unavailable"].includes(state.status) ? "error" : ""}`}
        />
        {mode === "preview"
          ? "PREVIEW"
          : `LIVE — ${statusLabels[state.status]}`}
      </span>
    </>
  );
}
