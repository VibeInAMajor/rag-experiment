import { Check } from "lucide-react";
import type { WorkbenchSettings } from "../domain/types";
import "./views.css";

export function SettingsView({
  settings,
  onChange,
}: {
  settings: WorkbenchSettings;
  onChange: (settings: WorkbenchSettings) => void;
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
        aria-labelledby="workspace-settings"
      >
        <div>
          <h2 id="workspace-settings">Workspace</h2>
          <p>Name and starting point for new pipelines.</p>
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
                  value === "retrieval"
                ) {
                  update("defaultTemplate", value);
                }
              }}
            >
              <option value="blank">Blank pipeline</option>
              <option value="indexing">Document indexing</option>
              <option value="retrieval">Hybrid retrieval</option>
            </select>
          </label>
        </div>
      </section>
      <section
        className="view-settings-section"
        aria-labelledby="execution-settings"
      >
        <div>
          <h2 id="execution-settings">Execution</h2>
          <p>Configure simulated runs and retrieval results.</p>
        </div>
        <div className="view-settings-fields">
          <label className="view-field">
            Scenario
            <select
              className="input"
              value={settings.previewScenario}
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
