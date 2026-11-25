import type { DocumentItem, UploadLocation } from "../api/contracts";
import type { QueuedDocumentUpload } from "./documentUploadQueue";

export type DocumentFileNode = {
  kind: "file";
  key: string;
  name: string;
  path: string;
  status: "ready" | "processing" | "error" | "pending" | "unknown";
  document?: DocumentItem;
  upload?: QueuedDocumentUpload;
};
export type DocumentFolderNode = {
  kind: "folder";
  key: string;
  name: string;
  path: string;
  children: DocumentTreeNode[];
  expected: number;
  loaded: number;
  ready: number;
  status: DocumentFileNode["status"];
};
export type DocumentTreeNode = DocumentFileNode | DocumentFolderNode;

export function buildDocumentFolders(
  documents: DocumentItem[],
  uploads: QueuedDocumentUpload[],
  snapshotComplete = true,
): DocumentTreeNode[] {
  const roots: DocumentTreeNode[] = [];
  const folders = new Map<string, DocumentFolderNode>();
  const remoteStates = new Map<
    string,
    NonNullable<DocumentItem["folder_states"]>[number]
  >();
  const sources = new Set(documents.map((item) => item.source_id));
  const sessionLocations = new Map<string, UploadLocation>();
  for (const upload of uploads)
    if (upload.response && upload.location)
      sessionLocations.set(upload.response.source_id, upload.location);
  const add = (
    file: DocumentFileNode,
    location?: UploadLocation | null,
    states?: DocumentItem["folder_states"],
  ) => {
    let children = roots;
    const parts = location?.path.split("/").slice(0, -1) ?? [];
    parts.forEach((name, depth) => {
      const path = parts.slice(0, depth + 1).join("/");
      const key = `${location!.group_id}/${path}`;
      if (states?.[depth]) remoteStates.set(key, states[depth]);
      let folder = folders.get(key);
      if (!folder) {
        folder = {
          kind: "folder",
          key,
          name,
          path,
          children: [],
          expected: 0,
          loaded: 0,
          ready: 0,
          status: "pending",
        };
        folders.set(key, folder);
        children.push(folder);
      }
      folder.loaded++;
      if (file.status === "ready") folder.ready++;
      if (file.status === "error") folder.status = "error";
      else if (file.status === "unknown" && folder.status !== "error")
        folder.status = "unknown";
      children = folder.children;
    });
    children.push(file);
  };
  for (const document of documents) {
    const location =
      document.upload_location ?? sessionLocations.get(document.source_id);
    add(
      {
        kind: "file",
        key: document.source_id,
        name: document.title,
        path: location?.path ?? document.title,
        status: document.status,
        document,
      },
      location,
      document.folder_states,
    );
  }
  for (const upload of uploads) {
    if (["failed", "skipped", "unknown"].includes(upload.phase)) continue;
    if (upload.response && sources.has(upload.response.source_id)) continue;
    add(
      {
        kind: "file",
        key: `upload-${upload.id}`,
        name: upload.path.split("/").at(-1)!,
        path: upload.path,
        status:
          upload.phase === "succeeded"
            ? "ready"
            : ["failed", "skipped"].includes(upload.phase)
              ? "error"
              : upload.phase === "unknown"
                ? "unknown"
                : upload.phase === "submitting"
                  ? "processing"
                  : "pending",
        upload,
      },
      upload.location,
    );
  }
  for (const folder of folders.values()) {
    const remote = remoteStates.get(folder.key);
    folder.expected = Math.max(folder.loaded, remote?.file_count ?? 0);
    folder.ready = Math.max(folder.ready, remote?.ready_count ?? 0);
    if (remote?.status === "error") folder.status = "error";
    if (folder.status !== "error")
      folder.status =
        folder.ready === folder.expected && (remote || snapshotComplete)
          ? "ready"
          : "processing";
  }
  const sort = (nodes: DocumentTreeNode[]) => {
    nodes.sort(
      (left, right) =>
        Number(right.kind === "folder") - Number(left.kind === "folder") ||
        left.name.localeCompare(right.name) ||
        left.key.localeCompare(right.key),
    );
    for (const node of nodes) if (node.kind === "folder") sort(node.children);
  };
  sort(roots);
  return roots;
}

export function filterDocumentFolders(
  nodes: DocumentTreeNode[],
  query: string,
  status: string,
  ancestorMatches = false,
): DocumentTreeNode[] {
  const needle = query.trim().toLowerCase();
  return nodes.flatMap<DocumentTreeNode>((node) => {
    const matches =
      ancestorMatches ||
      node.path.toLowerCase().includes(needle) ||
      node.name.toLowerCase().includes(needle);
    if (node.kind === "file")
      return matches && (status === "all" || node.status === status)
        ? [node]
        : [];
    const children = filterDocumentFolders(
      node.children,
      query,
      status,
      matches,
    );
    return children.length ||
      (matches && (status === "all" || node.status === status))
      ? [{ ...node, children }]
      : [];
  });
}
