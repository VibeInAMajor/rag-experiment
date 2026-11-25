import type { ActiveChunkItem } from "../api/contracts";

const metadataCharacterLimit = 6000;

export function boundedDocumentText(value: string, limit = 12000) {
  return value.length > limit
    ? { text: value.slice(0, limit), truncated: true }
    : { text: value, truncated: false };
}

export function documentMetadataText(value: unknown) {
  if (value === undefined || value === null) return "Not reported";
  const serialized = JSON.stringify(value, null, 2);
  const bounded = boundedDocumentText(serialized, metadataCharacterLimit);
  return (
    bounded.text + (bounded.truncated ? "\n… Metadata display truncated." : "")
  );
}

export function documentTimestamp(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("en-GB") : "Not reported";
}

export function documentPage(page: number | null | undefined) {
  return page == null ? "Unavailable" : String(page);
}

export function documentChunkCaption(
  chunk: ActiveChunkItem,
  mediaType?: string,
): string {
  if (mediaType !== "text/markdown")
    return `Order ${chunk.order} · Page ${documentPage(chunk.page)}`;
  const label = `Фрагмент ${chunk.order + 1}`;
  const start = chunk.metadata.start_line;
  const end = chunk.metadata.end_line;
  if (
    typeof start !== "number" ||
    typeof end !== "number" ||
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 1 ||
    end < start
  )
    return label;
  return `${label} · ${start === end ? `Строка ${start}` : `Строки ${start}–${end}`}`;
}
