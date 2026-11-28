import type { ExecutionMode } from "./types";

const pages = [
  "editor",
  "pipelines",
  "documents",
  "runs",
  "configuration",
  "agents",
  "settings",
] as const;
export type WorkbenchPage = (typeof pages)[number];
export type WorkbenchLocation = { page: WorkbenchPage; mode: ExecutionMode };

export function readWorkbenchLocation(href: string): WorkbenchLocation {
  const url = new URL(href);
  const candidate = url.searchParams.get("page");
  const page =
    pages.find((page) => page === candidate) ??
    (url.hash === "#configuration" ? "configuration" : "editor");
  return {
    page,
    mode: url.searchParams.get("mode") === "live" ? "live" : "preview",
  };
}

export function workbenchLocationUrl(
  href: string,
  location: WorkbenchLocation,
): string {
  const url = new URL(href);
  url.searchParams.set("page", location.page);
  url.searchParams.set("mode", location.mode);
  if (location.page === "configuration") url.hash = "configuration";
  else if (url.hash === "#configuration") url.hash = "";
  return `${url.pathname}${url.search}${url.hash}`;
}
