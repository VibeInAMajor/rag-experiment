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
