async function liveSearchSmoke(page) {
  page.setDefaultTimeout(7000);
  const check = (value, message) => {
    if (!value) throw new Error(message);
  };
  const searchRequests = [];
  const pageErrors = [];
  const observeRequest = (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/search")
    )
      searchRequests.push({
        path: new URL(request.url()).pathname,
        body: request.postDataJSON(),
      });
  };
  const observeError = (error) => pageErrors.push(error.message);
  page.on("request", observeRequest);
  page.on("pageerror", observeError);
  const runButton = () =>
    page.getByRole("button", { name: "Run", exact: true });
  const resultPanel = () =>
    page.getByRole("region", { name: "Pipeline results" });
  const status = () => resultPanel().locator(".results-meta .status");
  const queryField = async (query) => {
    await page
      .locator(".node-title")
      .filter({ hasText: /^Search query$/ })
      .click();
    await page
      .getByRole("textbox", { name: "Question", exact: true })
      .fill(query);
  };
  const samples = [];
  let handler;
  let releasePending;
  let noteDelayed;
  const delayedStarted = new Promise((resolve) => {
    noteDelayed = resolve;
  });
  try {
    await page.reload();
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    await page
      .getByRole("status", { name: "Execution status" })
      .filter({ hasText: /LIVE.*Ready/ })
      .waitFor();
    check(
      await runButton().isDisabled(),
      "The initial Hybrid graph must be unsupported Live",
    );
    check(
      searchRequests.length === 0,
      "Unsupported graph must make no search request",
    );
    const documentsUrl = new URL(
      "/api/v1/workspaces/development/documents",
      page.url(),
    ).href;
    const beforeDocuments = await (await page.request.get(documentsUrl)).json();
    await page.getByRole("button", { name: "Pipelines", exact: true }).click();
    await page
      .getByRole("button", { name: "New pipeline", exact: true })
      .click();
    await page.getByRole("button", { name: /Keyword search/ }).click();
    check(
      (await page.locator(".react-flow__node").count()) === 3,
      "Keyword template must have exactly three nodes",
    );
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export", exact: true }).click();
    const exported = await downloadPromise;
    await page
      .getByLabel("Import pipeline JSON")
      .setInputFiles(await exported.path());
    await page
      .getByRole("status")
      .filter({ hasText: "Pipeline imported." })
      .waitFor();
    check(
      (await page.locator(".react-flow__node").count()) === 3,
      "Keyword schemaVersion 1 must round-trip through the actual UI",
    );
    await page.getByRole("radio", { name: "Preview", exact: true }).check();
    await runButton().click();
    await page
      .locator(".error-list")
      .getByText(/Preview does not simulate this component/)
      .waitFor();
    check(
      searchRequests.length === 0,
      "Preview must refuse Keyword search without network execution",
    );
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    await page
      .getByRole("status", { name: "Execution status" })
      .filter({ hasText: /LIVE.*Ready/ })
      .waitFor();
    await page.getByRole("button", { name: "Validate", exact: true }).click();
    await page.getByText("Unsupported nodes", { exact: true }).waitFor();
    check(
      await runButton().isEnabled(),
      "Constructor unsupported must not veto the approved Live profile",
    );
    for (const query of ["retention", "GIN", "zzzzlexicalnomatch2026"]) {
      await queryField(query);
      const responsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname.endsWith("/search"),
      );
      await runButton().click();
      const response = await responsePromise;
      const body = await response.json();
      check(
        response.status() === 200,
        `Real search failed: ${response.status()}`,
      );
      await status().filter({ hasText: "Completed" }).waitFor();
      await resultPanel()
        .getByRole("tab", { name: "Output", exact: true })
        .click();
      const request = searchRequests.at(-1);
      check(
        JSON.stringify(Object.keys(request.body).sort()) ===
          JSON.stringify(
            [
              "query",
              "top_k",
              "profile_id",
              "expected_profile_revision",
            ].sort(),
          ),
        "Only the four approved fields may be sent",
      );
      check(
        request.body.query === query && request.body.top_k === 5,
        "Graph query and min(topK,limit) must reach the API",
      );
      const shown = await resultPanel()
        .locator(".live-retrieval-result")
        .evaluateAll((items) =>
          items.map((item) => ({
            source_id: item.dataset.sourceId,
            source_version_id: item.dataset.sourceVersionId,
            chunk_id: item.dataset.chunkId,
            rank: Number(item.dataset.rank),
            score: Number(item.dataset.score),
            score_type: item.dataset.scoreType,
            content: item.querySelector(".live-result-body > p").textContent,
          })),
        );
      check(
        JSON.stringify(shown) ===
          JSON.stringify(
            body.results.map(
              ({
                source_id,
                source_version_id,
                chunk_id,
                rank,
                score,
                score_type,
                content,
              }) => ({
                source_id,
                source_version_id,
                chunk_id,
                rank,
                score,
                score_type,
                content,
              }),
            ),
          ),
        "Visible order, provenance, raw score and passage must match the real HTTP response",
      );
      check(
        (await page
          .locator(".pipeline-node.state-success, .pipeline-node.state-running")
          .count()) === 0,
        "Live must not invent canvas-node outcomes",
      );
      if (body.results.length)
        await resultPanel()
          .getByText("Page unavailable", { exact: true })
          .first()
          .waitFor();
      else
        await resultPanel()
          .getByText("No matches for this query.", { exact: true })
          .waitFor();
      check(
        Number(
          await resultPanel()
            .getByLabel("Server duration")
            .getAttribute("data-duration-ms"),
        ) === body.duration_ms,
        "Total duration must be server-measured",
      );
      await resultPanel()
        .getByRole("tab", { name: "Stages", exact: true })
        .click();
      const shownStages = await resultPanel()
        .locator(".live-stage")
        .evaluateAll((items) =>
          items.map((item) => ({
            stage: item.dataset.stage,
            duration_ms: Number(item.dataset.durationMs),
          })),
        );
      check(
        JSON.stringify(shownStages) ===
          JSON.stringify(
            body.stages.map(({ stage, duration_ms }) => ({
              stage,
              duration_ms,
            })),
          ),
        "Server stage durations must match",
      );
      await resultPanel().getByRole("button", { name: "Toggle JSON" }).click();
      check(
        JSON.stringify(
          JSON.parse(
            await resultPanel().getByLabel("Live response JSON").innerText(),
          ),
        ) === JSON.stringify(body),
        "JSON view must preserve the complete API payload",
      );
      await resultPanel().getByRole("button", { name: "Toggle JSON" }).click();
      await resultPanel()
        .getByRole("tab", { name: "Output", exact: true })
        .click();
      samples.push({
        query,
        request,
        http_status: response.status(),
        response: body,
      });
    }
    check(
      samples[0].response.results[0].source_id !==
        samples[1].response.results[0].source_id,
      "Different real queries must return different persisted sources",
    );
    const afterDocuments = await (await page.request.get(documentsUrl)).json();
    check(
      beforeDocuments.corpus_revision === afterDocuments.corpus_revision &&
        JSON.stringify(beforeDocuments.items) ===
          JSON.stringify(afterDocuments.items),
      "Read-only search must not modify the persisted source/version registry",
    );
    await queryField("retention");
    const successful = samples[0].response;
    const failures = [];
    let scenario = { status: 400, code: "INVALID_REQUEST" };
    handler = async (route) => {
      if (scenario.code === "OFFLINE") return route.abort();
      if (scenario.code === "DELAY") {
        noteDelayed();
        await new Promise((resolve) => {
          releasePending = resolve;
        });
        return route
          .fulfill({
            status: 200,
            contentType: "application/json",
            headers: { "X-Request-ID": successful.request_id },
            body: JSON.stringify(successful),
          })
          .catch(() => {});
      }
      if (scenario.code === "MALFORMED")
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...successful, workspace_id: "foreign" }),
        });
      if (scenario.code === "HTML")
        return route.fulfill({
          status: 502,
          contentType: "text/html",
          body: "<html>Bad gateway</html>",
        });
      const body = {
        contract_revision: successful.contract_revision,
        request_id: successful.request_id,
        trace_id: successful.trace_id,
        error: {
          code: scenario.code,
          message: "Controlled negative-path response.",
          http_status: scenario.status,
          retryable: true,
          ...(scenario.status >= 429 ? { run_id: "negative-run" } : {}),
        },
      };
      return route.fulfill({
        status: scenario.status,
        contentType: "application/json",
        headers: { "X-Request-ID": body.request_id },
        body: JSON.stringify(body),
      });
    };
    await page.route("**/api/v1/workspaces/*/search", handler);
    for (const failure of [
      { status: 400, code: "INVALID_REQUEST" },
      { status: 404, code: "WORKSPACE_NOT_FOUND" },
      { status: 409, code: "PROFILE_NOT_AVAILABLE" },
      { status: 429, code: "SEARCH_BUSY" },
      { status: 503, code: "DEPENDENCY_UNAVAILABLE" },
      { status: 504, code: "SEARCH_TIMEOUT" },
      { status: 502, code: "HTML" },
      { status: 0, code: "OFFLINE" },
      { status: 200, code: "MALFORMED" },
    ]) {
      scenario = failure;
      await runButton().waitFor({ state: "visible" });
      await page
        .getByRole("status", { name: "Execution status" })
        .filter({ hasText: /LIVE.*Ready/ })
        .waitFor();
      await runButton().click();
      await status().filter({ hasText: "Failed" }).waitFor();
      await resultPanel()
        .getByRole("tab", { name: /^Errors/ })
        .click();
      const expected =
        failure.code === "HTML"
          ? "INVALID_GATEWAY_RESPONSE"
          : failure.code === "OFFLINE"
            ? "NETWORK_ERROR"
            : failure.code === "MALFORMED"
              ? "INVALID_RESPONSE"
              : failure.code;
      await resultPanel().getByText(expected, { exact: true }).waitFor();
      check(
        (await resultPanel().locator(".retrieval-result").count()) === 0,
        "Errors must never reuse real or Preview hits",
      );
      failures.push({
        injected_http_status: failure.status,
        expected_code: expected,
        visible_error: await resultPanel().locator(".live-error").innerText(),
      });
    }
    scenario = { status: 200, code: "DELAY" };
    await runButton().click();
    await delayedStarted;
    await page.getByRole("button", { name: "Stop", exact: true }).waitFor();
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await status().filter({ hasText: "Interrupted locally" }).waitFor();
    await resultPanel()
      .getByRole("tab", { name: /^Errors/ })
      .click();
    await resultPanel()
      .getByText("Stopped locally. Server cancellation is not confirmed.", {
        exact: true,
      })
      .waitFor();
    releasePending?.();
    releasePending = undefined;
    await page.unroute("**/api/v1/workspaces/*/search", handler);
    handler = undefined;
    await queryField("retention");
    await runButton().click();
    await status().filter({ hasText: "Completed" }).waitFor();
    await resultPanel()
      .getByRole("tab", { name: "Output", exact: true })
      .click();
    const closeInspector = page.getByRole("button", {
      name: "Close inspector",
    });
    if (await closeInspector.isVisible()) await closeInspector.click();
    const collapseLibrary = page.getByRole("button", {
      name: "Collapse components",
    });
    if (await collapseLibrary.isVisible()) await collapseLibrary.click();
    for (const width of [1440, 1100]) {
      await page.setViewportSize({ width, height: 1000 });
      check(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `Live output must fit ${width}px`,
      );
      await page.screenshot({
        path: `../../../output/playwright/workbench-live-search-${width}.png`,
        fullPage: true,
      });
    }
    await page.getByRole("button", { name: "Runs", exact: true }).click();
    check(
      (await page.locator('tr[data-source="live"]').count()) >= samples.length,
      "Live session history must survive navigation",
    );
    check(
      pageErrors.length === 0,
      `Uncaught page errors: ${pageErrors.join(", ")}`,
    );
    return {
      result: "PASS",
      real_searches: samples,
      registry_unchanged: true,
      injected_failures: failures,
      local_stop: "InterruptedLocally; server cancellation unconfirmed",
      screenshots: [1440, 1100],
      search_request_count: searchRequests.length,
    };
  } finally {
    releasePending?.();
    if (handler) await page.unroute("**/api/v1/workspaces/*/search", handler);
    page.off("request", observeRequest);
    page.off("pageerror", observeError);
  }
}
