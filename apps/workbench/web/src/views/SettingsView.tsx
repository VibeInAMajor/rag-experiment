import { Check } from "lucide-react";
import type { ExecutionMode, WorkbenchSettings } from "../domain/types";
import type { useBackendDiscovery } from "../hooks/useBackendDiscovery";
import "./views.css";

export function SettingsView({
  settings,
  onChange,
  mode,
  discovery,
  onWorkspaceChange,
}: {
  settings: WorkbenchSettings;
  onChange: (settings: WorkbenchSettings) => void;
  mode: ExecutionMode;
  discovery: ReturnType<typeof useBackendDiscovery>;
  onWorkspaceChange: () => void;
}) {
  function update<Key extends keyof WorkbenchSettings>(
    key: Key,
    value: WorkbenchSettings[Key],
  ) {
    onChange({ ...settings, [key]: value });
  }

  return (
    <section
      className="view-page view-settings"
      aria-labelledby="settings-title"
    >
      <header className="view-heading">
        <div>
          <p className="view-eyebrow">Preferences</p>
          <h1 id="settings-title">Settings</h1>
          <p>Changes apply to this browser session.</p>
        </div>
        <span className="view-local-state">
          <Check size={15} />
          Applied locally
        </span>
      </header>
      <section
        className="view-settings-section"
        aria-labelledby="backend-settings"
      >
        <div>
          <h2 id="backend-settings">Backend connection</h2>
          <p>
            {mode === "preview"
              ? "Select Live to check the API."
              : "Run the approved Keyword search graph from the editor."}
          </p>
        </div>
        <div className="view-settings-fields">
          <div className="backend-refresh">
            <button
              className="button small"
              onClick={discovery.refresh}
              disabled={
                mode !== "live" || discovery.state.status === "checking"
              }
            >
              Refresh connection
            </button>
            <span className="view-local-state">
              {discovery.state.lastCheckedAt
                ? `Last checked ${new Date(discovery.state.lastCheckedAt).toLocaleTimeString()}`
                : "Not checked"}
            </span>
          </div>
          {discovery.state.status === "checking" && (
            <p className="live-empty" role="status">
              Checking current API state…
            </p>
          )}
          {discovery.state.error && (
            <div className="backend-error" role="alert">
              <strong className="mono">{discovery.state.error.code}</strong>
              <p>{discovery.state.error.message}</p>
              {discovery.state.error.traceId && (
                <small className="mono">
                  Trace: {discovery.state.error.traceId}
                </small>
              )}
            </div>
          )}
          <label className="view-field">
            Backend workspace
            <select
              className="input"
              value={discovery.state.selectedWorkspaceId ?? ""}
              onChange={(event) => {
                onWorkspaceChange();
                discovery.selectWorkspace(event.target.value);
              }}
              disabled={mode !== "live" || discovery.state.status !== "ready"}
            >
              <option value="" disabled>
                No authorized workspace selected
              </option>
              {discovery.state.workspaces.map((workspace) => (
                <option
                  key={workspace.workspace_id}
                  value={workspace.workspace_id}
                >
                  {workspace.name} · {workspace.workspace_id}
                </option>
              ))}
            </select>
          </label>
          <dl className="backend-diagnostics">
            <div>
              <dt>Database</dt>
              <dd>
                {discovery.state.capabilities?.dependencies.database.status ??
                  "Not checked"}
              </dd>
            </div>
            <div>
              <dt>Profile</dt>
              <dd className="mono">
                {discovery.state.profile?.profile_id ?? "Unavailable"}
              </dd>
            </div>
            <div>
              <dt>Profile revision</dt>
              <dd className="mono">
                {discovery.state.profile?.profile_revision ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Score type</dt>
              <dd className="mono">
                {discovery.state.profile?.score_type ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Documents</dt>
              <dd>
                {discovery.state.capabilities?.features.documents
                  ? "Read-only listing"
                  : "Unavailable"}
              </dd>
            </div>
          </dl>
        </div>
      </section>
      <section
        className="view-settings-section"
        aria-labelledby="workspace-settings"
      >
        <div>
          <h2 id="workspace-settings">Workspace</h2>
          <p>
            Display name and starting point. Backend access is selected above.
          </p>
        </div>
        <div className="view-settings-fields">
          <label className="view-field">
            Workspace name
            <input
              className="input"
              value={settings.workspaceName}
              onChange={(event) => update("workspaceName", event.target.value)}
              maxLength={80}
            />
          </label>
          <label className="view-field">
            Default template
            <select
              className="input"
              value={settings.defaultTemplate}
              onChange={(event) => {
                const value = event.target.value;
                if (
                  value === "blank" ||
                  value === "indexing" ||
                  value === "retrieval" ||
                  value === "keyword"
                ) {
                  update("defaultTemplate", value);
                }
              }}
            >
              <option value="blank">Blank pipeline</option>
              <option value="indexing">Document indexing</option>
              <option value="retrieval">Hybrid retrieval</option>
              <option value="keyword">Keyword search</option>
            </select>
          </label>
        </div>
      </section>
      <section
        className="view-settings-section"
        aria-labelledby="execution-settings"
      >
        <div>
          <h2 id="execution-settings">Preview simulation</h2>
          <p>
            These preferences apply only to Preview. Live uses the smaller of
            the graph's candidate and result limits.
          </p>
        </div>
        <div className="view-settings-fields">
          <label className="view-field">
            Scenario
            <select
              className="input"
              value={settings.previewScenario}
              disabled={mode === "live"}
              onChange={(event) => {
                const value = event.target.value;
                if (value === "success" || value === "error") {
                  update("previewScenario", value);
                }
              }}
            >
              <option value="success">Success</option>
              <option value="error">Error</option>
            </select>
          </label>
          <label className="view-field">
            Step delay <span className="view-field-unit mono">ms</span>
            <input
              className="input mono"
              type="number"
              min={0}
              max={5000}
              step={100}
              value={settings.previewDelay}
              disabled={mode === "live"}
              onChange={(event) => {
                const value = event.target.valueAsNumber;
                if (Number.isFinite(value))
                  update("previewDelay", Math.min(5000, Math.max(0, value)));
              }}
            />
          </label>
          <label className="view-field">
            Result limit
            <input
              className="input mono"
              type="number"
              min={1}
              max={100}
              step={1}
              value={settings.resultLimit}
              disabled={mode === "live"}
              onChange={(event) => {
                const value = event.target.valueAsNumber;
                if (Number.isFinite(value))
                  update(
                    "resultLimit",
                    Math.min(100, Math.max(1, Math.round(value))),
                  );
              }}
            />
          </label>
        </div>
      </section>
      <section
        className="view-settings-section"
        aria-labelledby="appearance-settings"
      >
        <div>
          <h2 id="appearance-settings">Appearance</h2>
          <p>Canvas and motion preferences.</p>
        </div>
        <div className="view-settings-fields">
          <label className="view-checkbox">
            <span>
              <strong>Dot grid</strong>
              <small>Show the canvas alignment grid.</small>
            </span>
            <input
              type="checkbox"
              checked={settings.showGrid}
              onChange={(event) => update("showGrid", event.target.checked)}
            />
          </label>
          <label className="view-checkbox">
            <span>
              <strong>Reduced motion</strong>
              <small>Limit interface animation.</small>
            </span>
            <input
              type="checkbox"
              checked={settings.reducedMotion}
              onChange={(event) =>
                update("reducedMotion", event.target.checked)
              }
            />
          </label>
        </div>
      </section>
    </section>
  );
}
