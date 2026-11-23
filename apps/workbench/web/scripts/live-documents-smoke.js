// Run only against an explicitly prepared disposable database. Configure
// window.__workbenchDocumentsInput before invoking this Playwright CLI scenario:
// { scope: "isolated_disposable", workspaceId: "development", files: [
//   { format: "txt", path: "C:/fixtures/document.txt", query: "unique marker" },
//   { format: "markdown", path: "C:/fixtures/document.md", query: "unique marker" },
//   { format: "python", path: "C:/fixtures/document.py", query: "unique marker" },
//   { format: "pdf", path: "C:/fixtures/document.pdf", query: "unique marker" }
// ] }. PDF is required only when the actual runtime advertises it as available.
async function liveDocumentsSmoke(page) {
  page.setDefaultTimeout(10000);
  const check = (condition, code) => {
    if (!condition) throw new Error(code);
  };
  const config = await page.evaluate(() => window.__workbenchDocumentsInput);
  check(
    config?.scope === "isolated_disposable" &&
      typeof config.workspaceId === "string" &&
      Array.isArray(config.files),
    "DISPOSABLE_DOCUMENTS_INPUT_REQUIRED",
  );
  for (const format of ["txt", "markdown", "python"])
    check(
      config.files.some((file) => file.format === format),
      `REQUIRED_FIXTURE_MISSING_${format}`,
    );
  const formats = new Set();
  for (const file of config.files) {
    check(
      ["txt", "markdown", "python", "pdf"].includes(file.format) &&
        !formats.has(file.format) &&
        typeof file.path === "string" &&
        /^(?:[A-Za-z]:[\\/]|\/)/.test(file.path) &&
        typeof file.query === "string" &&
        file.query.trim().length > 0,
      "INVALID_DOCUMENT_FIXTURE",
    );
    formats.add(file.format);
  }
  const root = `/api/v1/workspaces/${encodeURIComponent(config.workspaceId)}`;
  const capResponse = await page.request.get(
    new URL("/api/v1/capabilities", page.url()).href,
  );
  const capabilities = await capResponse.json();
  check(
    capResponse.status() === 200 &&
      capabilities.features?.documents === true &&
      capabilities.features?.document_details === true &&
      capabilities.features?.jobs === true &&
      capabilities.features?.upload === true,
    "DOCUMENT_CAPABILITIES_REQUIRED",
  );
  if (capabilities.pdf_ingestion?.available)
    check(formats.has("pdf"), "QUALIFIED_PDF_FIXTURE_REQUIRED");
  const digest = (value) =>
    page.evaluate(async (input) => {
      const bytes = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(input),
      );
      return Array.from(new Uint8Array(bytes), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
    }, value);
  const network = [];
  const cases = [];
  const pageErrors = [];
  const captures = [];
  const onError = () => pageErrors.push("UNCAUGHT_PAGE_ERROR");
  const onResponse = (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith(root)) return;
    const request = response.request();
    captures.push(
      (async () => {
        const headers = await request.allHeaders();
        const operationKey = headers["idempotency-key"];
        const body = await response.json().catch(() => null);
        network.push({
          method: request.method(),
          path: url.pathname,
          status: response.status(),
          request_id: body?.request_id ?? null,
          trace_id: body?.trace_id ?? null,
          corpus_revision: body?.corpus_revision ?? null,
          source_id: body?.source_id ?? null,
          source_version_id:
            body?.source_version_id ?? body?.active_version_id ?? null,
          job_id: body?.job_id ?? body?.error?.job_id ?? null,
          error_code: body?.error?.code ?? null,
          processing_profile_fingerprint:
            body?.processing_profile_fingerprint ?? null,
          source_content_sha256: body?.source_content_sha256 ?? null,
          source_bytes: body?.source_bytes ?? null,
          parser: body?.parser
            ? {
                parser_id: body.parser.parser_id ?? null,
                parser_revision: body.parser.parser_revision ?? null,
              }
            : null,
          ...(url.pathname.endsWith("/chunks") && Array.isArray(body?.items)
            ? {
                chunk_items: body.items.map(
                  ({ chunk_id, content_hash, order, page }) => ({
                    chunk_id,
                    content_hash,
                    order,
                    page: page ?? null,
                  }),
                ),
              }
            : {}),
          ...(operationKey
            ? {
                operation_key_sha256: await digest(operationKey),
                multipart_boundary_present:
                  /^multipart\/form-data;\s*boundary=/.test(
                    headers["content-type"] ?? "",
                  ),
              }
            : {}),
        });
      })(),
    );
  };
  const waitResponse = (method, path, timeout = 10000) =>
    page.waitForResponse(
      (response) =>
        response.request().method() === method &&
        new URL(response.url()).pathname === path,
      { timeout },
    );
  const documents = () =>
    page.getByRole("button", { name: "Documents", exact: true }).click();
  const details = () =>
    page.getByRole("complementary", { name: "Live document details" });
  page.on("response", onResponse);
  page.on("pageerror", onError);
  try {
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    await page
      .getByRole("status", { name: "Execution status" })
      .filter({ hasText: /LIVE.*Ready/ })
      .waitFor();
    await documents();
    await page
      .getByRole("searchbox", { name: "Filter loaded documents" })
      .waitFor();
    for (const file of config.files) {
      if (file.format === "pdf" && !capabilities.pdf_ingestion?.available) {
        cases.push({ format: "pdf", outcome: "SKIPPED_RUNTIME_UNAVAILABLE" });
        continue;
      }
      await page.getByRole("button", { name: "Upload", exact: true }).click();
      const modal = page.getByRole("dialog", { name: "Upload document" });
      const input = modal.getByLabel("Source file");
      check(
        (await input.getAttribute("multiple")) === null,
        "SINGLE_FILE_REQUIRED",
      );
      if (file.format === "pdf")
        check(
          (await input.getAttribute("accept")).includes(".pdf"),
          "PDF_GATE_MISSING",
        );
      await input.setInputFiles(file.path);
      const responseReady = waitResponse("POST", `${root}/documents`, 240000);
      const started = Date.now();
      await modal
        .getByRole("button", { name: "Confirm upload", exact: true })
        .click();
      const response = await responseReady;
      const uploaded = await response.json();
      const browserElapsed = Date.now() - started;
      await response.finished();
      const timing = response.request().timing();
      const networkElapsed =
        timing.requestStart >= 0 && timing.responseEnd >= 0
          ? timing.responseEnd - timing.requestStart
          : null;
      check([200, 201].includes(response.status()), "UPLOAD_NOT_CONFIRMED");
      check(uploaded.status === "completed", "UPLOAD_NOT_TERMINAL");
      await modal.getByText(/Confirmed (created|updated|unchanged)/).waitFor();
      await modal.getByRole("button", { name: "Close", exact: true }).click();
      await details()
        .getByText(uploaded.source_version_id, { exact: true })
        .first()
        .waitFor();
      await details().getByRole("tab", { name: "Chunks", exact: true }).click();
      await details()
        .getByText("Loading active chunks…", { exact: true })
        .waitFor({ state: "hidden" });
      while (
        await details()
          .getByRole("button", { name: "Load more chunks" })
          .count()
      ) {
        const button = details().getByRole("button", {
          name: "Load more chunks",
        });
        const more = waitResponse(
          "GET",
          `${root}/documents/${encodeURIComponent(uploaded.source_id)}/chunks`,
        );
        await button.click();
        await more;
        await details()
          .getByText("Loading active chunks…", { exact: true })
          .waitFor({ state: "hidden" });
      }
      const shownChunks = await details()
        .locator(".documents-chunk")
        .evaluateAll((items) =>
          items.map((item) => ({
            chunk_id: item.dataset.chunkId,
            content_hash: item.dataset.contentHash,
            order: Number(item.dataset.order),
            page: item.dataset.page === "" ? null : Number(item.dataset.page),
          })),
        );
      check(
        shownChunks.length === uploaded.chunk_count,
        "CHUNK_COUNT_DOM_MISMATCH",
      );
      check(
        shownChunks.every((chunk) => chunk.chunk_id && chunk.content_hash),
        "CHUNK_PROVENANCE_MISSING",
      );
      await Promise.all(captures);
      const wireChunks = new Map(
        network
          .filter(
            (event) =>
              event.source_id === uploaded.source_id &&
              event.source_version_id === uploaded.source_version_id &&
              event.chunk_items,
          )
          .flatMap((event) => event.chunk_items)
          .map((item) => [item.chunk_id, item]),
      );
      check(
        shownChunks.every(
          (chunk) =>
            JSON.stringify(wireChunks.get(chunk.chunk_id)) ===
            JSON.stringify(chunk),
        ),
        "CHUNK_HTTP_DOM_MISMATCH",
      );
      await details()
        .getByRole("tab", { name: "Parse report", exact: true })
        .click();
      await details()
        .getByText("Original file bytes are unavailable through this API.")
        .waitFor();
      const jobReady = waitResponse(
        "GET",
        `${root}/jobs/${encodeURIComponent(uploaded.job_id)}`,
      );
      await page
        .getByRole("button", { name: "Inspect confirmed job status" })
        .click();
      const job = await (await jobReady).json();
      check(
        job.job_id === uploaded.job_id &&
          job.source_version_id === uploaded.source_version_id &&
          job.status === "completed",
        "DURABLE_JOB_IDENTITY_MISMATCH",
      );
      await page
        .getByRole("heading", { name: "Last confirmed durable job" })
        .waitFor();
      await details()
        .getByRole("button", { name: "Search this source" })
        .click();
      await page
        .locator(".node-title")
        .filter({ hasText: /^Search query$/ })
        .click();
      await page
        .getByRole("textbox", { name: "Question", exact: true })
        .fill(file.query);
      const searchReady = waitResponse("POST", `${root}/search`);
      await page.getByRole("button", { name: "Run", exact: true }).click();
      const searched = await (await searchReady).json();
      check(
        searched.results?.some(
          (result) =>
            result.source_id === uploaded.source_id &&
            result.source_version_id === uploaded.source_version_id,
        ),
        "LIVE_SOURCE_NOT_DISCOVERABLE",
      );
      await page.waitForFunction(
        ({ sourceId, versionId }) =>
          Array.from(document.querySelectorAll(".live-retrieval-result")).some(
            (element) =>
              element.dataset.sourceId === sourceId &&
              element.dataset.sourceVersionId === versionId,
          ),
        { sourceId: uploaded.source_id, versionId: uploaded.source_version_id },
      );
      cases.push({
        format: file.format,
        outcome: uploaded.outcome,
        replayed: uploaded.replayed,
        http_status: response.status(),
        source_id: uploaded.source_id,
        source_version_id: uploaded.source_version_id,
        job_id: uploaded.job_id,
        chunk_count: uploaded.chunk_count,
        chunks: shownChunks,
        corpus_revision: uploaded.corpus_revision,
        stages: uploaded.stages,
        browser_network_elapsed_ms: networkElapsed,
        browser_upload_action_elapsed_ms: browserElapsed,
        lexical_result_ids: searched.results.map(
          ({ source_id, source_version_id, chunk_id }) => ({
            source_id,
            source_version_id,
            chunk_id,
          }),
        ),
      });
      await documents();
    }
    for (const width of [1440, 1100, 720]) {
      await page.setViewportSize({ width, height: 1000 });
      check(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `DOCUMENT_LAYOUT_OVERFLOW_${width}`,
      );
    }
    await Promise.all(captures);
    check(pageErrors.length === 0, "PAGE_ERRORS_OBSERVED");
    check(
      network
        .filter(
          (item) => item.method === "POST" && item.path === `${root}/documents`,
        )
        .every(
          (item) =>
            item.multipart_boundary_present && item.operation_key_sha256,
        ),
      "MULTIPART_PROVENANCE_MISSING",
    );
    return {
      result: "PASS",
      scope: config.scope,
      cases,
      network,
      pdf_runtime_available: capabilities.pdf_ingestion?.available === true,
      restart_and_sql_parity: "NOT_TESTED_BY_THIS_BROWSER_SCRIPT",
    };
  } finally {
    page.off("response", onResponse);
    page.off("pageerror", onError);
    await Promise.allSettled(captures);
  }
}
