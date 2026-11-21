const durationFormatter = new Intl.NumberFormat("en-US", {
  useGrouping: false,
  maximumFractionDigits: 3,
});

export function ServerDuration({ durationMs }: { durationMs: number }) {
  return (
    <span
      className="mono"
      aria-label="Server duration"
      data-duration-ms={String(durationMs)}
      title={`${String(durationMs)} ms`}
    >
      {durationFormatter.format(durationMs)} ms
    </span>
  );
}
