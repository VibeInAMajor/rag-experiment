import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Check,
  FileCode2,
  RefreshCw,
  Save,
} from "lucide-react";
import {
  createWorkbenchApiClient,
  WorkbenchApiError,
  type WorkbenchApiClient,
} from "../api/client";
import type {
  ConfigurationDocument,
  ConfigurationIssue,
} from "../api/contracts";
import { YamlEditor } from "../components/YamlEditor";
import { useConfirmation } from "../components/ConfirmationDialog";
import "./configuration.css";

type ConfigurationClient = Pick<
  WorkbenchApiClient,
  "getConfiguration" | "validateConfiguration" | "saveConfiguration"
>;
type Operation = "loading" | "validating" | "saving";

function failureMessage(error: WorkbenchApiError): string {
  const messages: Record<string, string> = {
    INVALID_REQUEST:
      "Enter a complete YAML document and validate it before saving.",
    CONFIGURATION_SAME_ORIGIN_REQUIRED:
      "Configuration requires the application’s same-origin API connection. Check the deployment proxy.",
    CONFIGURATION_CONFLICT:
      "Another editor saved a newer revision. Your changes are retained. Copy them if needed, then reload the saved version.",
    SECRET_VALUES_NOT_ALLOWED:
      "Secret values cannot be stored here. Keep credentials outside this configuration.",
    CONFIGURATION_TOO_LARGE:
      "The configuration exceeds the server’s 64 KiB limit.",
    PAYLOAD_TOO_LARGE:
      "The configuration request exceeds the server’s size limit.",
    INVALID_CONFIGURATION:
      "The configuration was not saved. Review the validation errors.",
  };
  return (
    messages[error.code] ??
    (error.kind === "timeout"
      ? "The result could not be confirmed. Reload the saved configuration before retrying a save; your edits are retained."
      : "Configuration is unavailable. Your edits are retained. Check the service, then retry.")
  );
}

export function ConfigurationView({
  onDirtyChange,
  onSavingChange,
  client: suppliedClient,
}: {
  onDirtyChange: (dirty: boolean) => void;
  onSavingChange: (saving: boolean) => void;
  client?: ConfigurationClient;
}) {
  const client = useMemo(
    () => suppliedClient ?? createWorkbenchApiClient(),
    [suppliedClient],
  );
  const { confirm, confirmationDialog } = useConfirmation();
  const [document, setDocument] = useState<ConfigurationDocument | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<Operation | null>("loading");
  const [error, setError] = useState<WorkbenchApiError | null>(null);
  const [issues, setIssues] = useState<ConfigurationIssue[]>([]);
  const [message, setMessage] = useState("");
  const [validated, setValidated] = useState(false);
  const [focusLine, setFocusLine] = useState<number>();
  const inFlight = useRef(false);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const dirty =
    document !== null && (!document.exists || draft !== document.yaml);
  const bytes = new TextEncoder().encode(draft).length;
  const oversized = document !== null && bytes > document.max_bytes;

  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    onSavingChange(busy === "saving");
    return () => onSavingChange(false);
  }, [busy, onSavingChange]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (dirty || busy === "saving") {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty, busy]);

  async function run(
    operation: Operation,
    work: (signal: AbortSignal, current: () => boolean) => Promise<void>,
  ) {
    if (inFlight.current) return;
    inFlight.current = true;
    const token = ++generation.current;
    const controller = new AbortController();
    request.current = controller;
    setBusy(operation);
    setError(null);
    setMessage("");
    const current = () =>
      token === generation.current && !controller.signal.aborted;
    try {
      await work(controller.signal, current);
    } catch (error) {
      if (
        current() &&
        !(error instanceof WorkbenchApiError && error.kind === "cancelled")
      )
        setError(
          error instanceof WorkbenchApiError
            ? error
            : new WorkbenchApiError("Configuration is unavailable.", {
                kind: "transport",
                code: "NETWORK_ERROR",
                retryable: true,
              }),
        );
    } finally {
      if (token === generation.current) {
        inFlight.current = false;
        setBusy(null);
      }
    }
  }

  async function load() {
    if (
      dirty &&
      !(await confirm(
        "Discard your unsaved configuration changes and reload the saved version?",
      ))
    )
      return;
    await run("loading", async (signal, current) => {
      const loaded = await client.getConfiguration({ signal });
      if (!current()) return;
      setDocument(loaded);
      setDraft(loaded.yaml);
      setIssues([]);
      setValidated(false);
      setMessage(
        loaded.exists
          ? "Loaded the saved configuration."
          : "No saved configuration. Review this starter before saving.",
      );
    });
  }

  useEffect(() => {
    void load();
    return () => {
      generation.current++;
      request.current?.abort();
      inFlight.current = false;
    };
  }, [client]);

  async function validate() {
    if (!document || oversized) return;
    await run("validating", async (signal, current) => {
      const result = await client.validateConfiguration(draft, { signal });
      if (!current()) return;
      setIssues(result.errors);
      setValidated(result.valid);
      setMessage(
        result.valid
          ? "Configuration is valid. You can save these changes."
          : "Review the validation errors below.",
      );
    });
  }

  async function save() {
    if (!document || !dirty || oversized) return;
    const submitted = draft;
    await run("saving", async (signal, current) => {
      try {
        const saved = await client.saveConfiguration(
          submitted,
          document.revision,
          { signal },
        );
        if (!current()) return;
        setDocument(saved);
        setDraft(saved.yaml);
        setIssues([]);
        setValidated(true);
        setMessage(
          saved.activation === "requires_restart"
            ? "Saved. Restart the API to activate these settings."
            : "Saved. These settings are already active.",
        );
      } catch (error) {
        if (
          error instanceof WorkbenchApiError &&
          error.code === "INVALID_CONFIGURATION"
        ) {
          const result = await client.validateConfiguration(submitted, {
            signal,
          });
          if (current()) {
            setIssues(result.errors);
            setValidated(false);
          }
        }
        throw error;
      }
    });
  }

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (!busy) void save();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });

  return (
    <section
      className="view-page configuration-page"
      aria-labelledby="configuration-title"
    >
      <header className="view-heading configuration-heading">
        <div>
          <p className="view-eyebrow">Application settings</p>
          <h1 id="configuration-title">Configuration</h1>
          <p>
            One configuration for this application. Changes apply after an API
            restart.
          </p>
        </div>
      </header>
      {error && (
        <div className="configuration-feedback error" role="alert">
          <AlertCircle size={17} aria-hidden="true" />
          <div>
            <strong>{failureMessage(error)}</strong>
            <small className="mono">
              {error.code}
              {error.traceId ? ` · Trace ${error.traceId}` : ""}
            </small>
          </div>
        </div>
      )}
      <div className="configuration-toolbar">
        <div className="configuration-file">
          <FileCode2 size={17} />
          <span className="mono">Application YAML</span>
          <span className={`configuration-state ${dirty ? "dirty" : ""}`}>
            {!document
              ? "Not loaded"
              : !document.exists
                ? "Starter · not saved"
                : dirty
                  ? "Unsaved changes"
                  : "Saved"}
          </span>
        </div>
        <div className="configuration-actions">
          <button
            className="button"
            disabled={busy !== null}
            onClick={() => void load()}
          >
            <RefreshCw size={15} />
            {busy === "loading" ? "Loading…" : "Reload"}
          </button>
          <button
            className="button"
            disabled={!document || busy !== null || oversized}
            onClick={() => void validate()}
          >
            <Check size={15} />
            {busy === "validating" ? "Validating…" : "Validate"}
          </button>
          <button
            className="button primary"
            disabled={!document || !dirty || busy !== null || oversized}
            onClick={() => void save()}
          >
            <Save size={15} />
            {busy === "saving" ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
      {document ? (
        <div className="configuration-editor" aria-busy={busy !== null}>
          <YamlEditor
            value={draft}
            readOnly={busy !== null}
            issues={issues}
            focusLine={focusLine}
            onChange={(value) => {
              setDraft(value);
              setIssues([]);
              setValidated(false);
              setMessage("");
              setError(null);
            }}
          />
        </div>
      ) : (
        <div
          className="configuration-editor configuration-loading"
          role="status"
        >
          {busy === "loading"
            ? "Loading configuration…"
            : "The saved configuration could not be loaded. Retry with Reload."}
        </div>
      )}
      <div className="configuration-editor-footer">
        <span id="configuration-editor-help">
          YAML · UTF-8 · Tab indents; Esc, then Tab moves focus.
        </span>
        <span className={oversized ? "configuration-limit" : ""}>
          {bytes.toLocaleString()} /{" "}
          {document?.max_bytes.toLocaleString() ?? "—"} bytes
        </span>
      </div>
      <div className="configuration-status" role="status" aria-live="polite">
        {message ? (
          <>
            <Check
              size={15}
              className={validated ? "configuration-valid" : ""}
            />
            <span>{message}</span>
          </>
        ) : (
          <span>
            {!document
              ? "Load configuration to inspect its activation status."
              : !document.exists
                ? "Starter configuration has not been saved."
                : document.activation === "requires_restart"
                  ? "Saved settings are pending an API restart."
                  : "The saved settings match the active configuration."}
          </span>
        )}
      </div>
      {oversized && (
        <p className="configuration-feedback error" role="alert">
          This document exceeds the server’s size limit. Shorten it before
          validating or saving.
        </p>
      )}
      {issues.length > 0 && (
        <section
          className="configuration-issues"
          aria-label="Validation errors"
        >
          <h2>
            {issues.length} validation{" "}
            {issues.length === 1 ? "error" : "errors"}
          </h2>
          <ul>
            {issues.map((issue, index) => (
              <li key={index}>
                {issue.line ? (
                  <button
                    onClick={() => setFocusLine(issue.line ?? undefined)}
                    className="configuration-issue-line mono"
                  >
                    Line {issue.line}
                    {issue.column ? `:${issue.column}` : ""}
                    <ArrowRight size={12} />
                  </button>
                ) : null}
                <div>
                  {issue.path && <code>{issue.path}</code>}
                  <span>{issue.message}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      <footer className="configuration-notes">
        <p>
          Existing indexed documents keep their current chunks. Re-ingest them
          explicitly to use a changed processing profile.
        </p>
        {document?.deployment_overrides.length ? (
          <p>
            Deployment policy overrides the default language:{" "}
            <strong>{document.effective_default_language}</strong>.
          </p>
        ) : null}
        <span className="mono">
          {document ? `Revision ${document.revision.slice(7, 19)}` : ""}
        </span>
      </footer>
      {confirmationDialog}
    </section>
  );
}
