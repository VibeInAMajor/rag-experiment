import { useCallback, useEffect, useRef, useState } from "react";

function ConfirmationDialog({
  message,
  onDecision,
}: {
  message: string;
  onDecision: (confirmed: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    cancel.current?.focus();
    return () => {
      if (element?.open) element.close();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="confirmation-dialog"
      aria-labelledby="confirmation-title"
      aria-describedby="confirmation-message"
      onCancel={(event) => {
        event.preventDefault();
        onDecision(false);
      }}
    >
      <h2 id="confirmation-title">Discard unsaved changes?</h2>
      <p id="confirmation-message">{message}</p>
      <div className="view-dialog-actions">
        <button
          ref={cancel}
          className="button"
          onClick={() => onDecision(false)}
        >
          Keep editing
        </button>
        <button className="button danger" onClick={() => onDecision(true)}>
          Discard changes
        </button>
      </div>
    </dialog>
  );
}

export function useConfirmation() {
  const [pending, setPending] = useState<{
    message: string;
    resolve: (confirmed: boolean) => void;
  } | null>(null);
  const owned = useRef(pending);
  const confirm = useCallback((message: string) => {
    if (owned.current) return Promise.resolve(false);
    return new Promise<boolean>((resolve) => {
      const next = { message, resolve };
      owned.current = next;
      setPending(next);
    });
  }, []);
  const finish = useCallback((confirmed: boolean) => {
    const current = owned.current;
    owned.current = null;
    setPending(null);
    current?.resolve(confirmed);
  }, []);
  useEffect(
    () => () => {
      owned.current?.resolve(false);
      owned.current = null;
    },
    [],
  );
  return {
    confirm,
    confirmationDialog: pending ? (
      <ConfirmationDialog message={pending.message} onDecision={finish} />
    ) : null,
  };
}
