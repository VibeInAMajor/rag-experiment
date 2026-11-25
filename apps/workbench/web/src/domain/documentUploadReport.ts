import type { QueuedDocumentUpload } from "./documentUploadQueue";

export function uploadIssues(items: QueuedDocumentUpload[]) {
  return items.filter((item) =>
    ["failed", "unknown", "skipped"].includes(item.phase),
  );
}

export function documentUploadReport(
  items: QueuedDocumentUpload[],
  generatedAt = new Date(),
): string {
  const issues = uploadIssues(items);
  const lines = [
    "Document upload report",
    `Generated (UTC): ${generatedAt.toISOString()}`,
    `Files requiring attention: ${issues.length}`,
    "",
  ];
  for (const item of issues) {
    const reason =
      item.error?.code === "PAYLOAD_TOO_LARGE"
        ? "The upload exceeds the server's file or request byte limit."
        : (item.error?.message ??
          (item.phase === "unknown"
            ? "The server outcome is unconfirmed. This file may already have been published; retry the same operation to confirm it."
            : "No error details were returned."));
    lines.push(
      `File: ${item.path}`,
      `Status: ${item.phase}`,
      `Reason: ${reason}`,
    );
    if (item.error?.code) lines.push(`Code: ${item.error.code}`);
    if (item.error?.jobId) lines.push(`Job: ${item.error.jobId}`);
    lines.push("");
  }
  return lines.join("\r\n");
}
