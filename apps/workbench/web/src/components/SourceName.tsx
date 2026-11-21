import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createWorkbenchApiClient, WorkbenchApiError } from "../api/client";
import type { LocalSourceFile } from "../api/contracts";
import {
  SourceFilesRequests,
  SourceRevealRequest,
  type SourceFileClient,
  type SourceFileIdentity,
} from "./sourceFiles";
import "./source-name.css";

const SourceFilesContext = createContext<SourceFilesRequests | null>(null);

export function SourceFilesProvider({
  children,
  client,
}: {
  children: ReactNode;
  client?: SourceFileClient;
}) {
  const requests = useMemo(
    () => new SourceFilesRequests(client ?? createWorkbenchApiClient),
    [client],
  );
  useEffect(() => () => requests.clear(), [requests]);
  return <SourceFilesContext value={requests}>{children}</SourceFilesContext>;
}

export function SourceNameLabel({
  fallback,
  file,
  pending = false,
  error,
  onReveal,
}: {
  fallback: string;
  file?: LocalSourceFile;
  pending?: boolean;
  error?: string;
  onReveal: () => void;
}) {
  const name = file?.name ?? fallback;
  return (
    <>
      {file?.can_reveal ? (
        <button
          type="button"
          role="link"
          className="source-name"
          onClick={onReveal}
          disabled={pending}
          aria-busy={pending}
        >
          {name}
        </button>
      ) : (
        <span>{name}</span>
      )}
      {error && (
        <span className="source-name-error" role="status">
          {error}
        </span>
      )}
    </>
  );
}

export function SourceName({
  workspaceId,
  sourceId,
  versionId,
}: SourceFileIdentity) {
  const requests = useContext(SourceFilesContext);
  const [resolved, setResolved] = useState<{
    identity: SourceFileIdentity;
    file: LocalSourceFile;
  }>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const identity = useMemo(
    () => ({ workspaceId, sourceId, versionId }),
    [workspaceId, sourceId, versionId],
  );
  const file = resolved?.identity === identity ? resolved.file : undefined;
  const generation = useRef(0);
  const reveal = useMemo(
    () => (requests ? new SourceRevealRequest(requests, identity) : null),
    [requests, identity],
  );
  useEffect(() => {
    const controller = new AbortController();
    generation.current++;
    setResolved(undefined);
    setError(undefined);
    setPending(false);
    void requests?.lookup(identity, controller.signal).then(
      (value) => {
        if (!controller.signal.aborted) setResolved({ identity, file: value });
      },
      () => {},
    );
    return () => {
      generation.current++;
      controller.abort();
      reveal?.stop();
    };
  }, [requests, identity, reveal]);
  const onReveal = async () => {
    if (!reveal || reveal.busy || !file?.can_reveal) return;
    const current = generation.current;
    setPending(true);
    setError(undefined);
    try {
      await reveal.run();
    } catch (failure) {
      if (current !== generation.current) return;
      if (failure instanceof WorkbenchApiError && failure.kind === "cancelled")
        return;
      const details =
        failure instanceof WorkbenchApiError
          ? ` ${failure.code}${failure.traceId ? ` · ${failure.traceId}` : ""}`
          : "";
      setError(`File could not be shown.${details}`);
      if (
        failure instanceof WorkbenchApiError &&
        [404, 409].includes(failure.httpStatus ?? 0)
      )
        setResolved({ identity, file: { ...file, can_reveal: false } });
    } finally {
      if (current === generation.current) setPending(false);
    }
  };
  return (
    <SourceNameLabel
      fallback={sourceId}
      file={file}
      pending={pending}
      error={error}
      onReveal={() => {
        void onReveal();
      }}
    />
  );
}
