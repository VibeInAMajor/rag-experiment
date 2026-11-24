async function denseSearchSmoke(page) {
  page.setDefaultTimeout(10000);
  const check = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  await page.unrouteAll({ behavior: "wait" });
  const apiPort = new URL(page.url()).searchParams.get("dense_api_port");
  check(
    apiPort === null ||
      (/^\d{1,5}$/.test(apiPort) &&
        Number(apiPort) >= 1 &&
        Number(apiPort) <= 65535),
    "Only a bounded loopback API port may be selected",
  );
  const apiOrigin = apiPort
    ? `http://127.0.0.1:${apiPort}`
    : new URL(page.url()).origin;
  const forward = async (route) => {
    const requestUrl = new URL(route.request().url());
    const response = await route.fetch({
      url: `${apiOrigin}${requestUrl.pathname}${requestUrl.search}`,
    });
    await route.fulfill({ response });
  };
  if (apiPort) await page.route("**/api/v1/**", forward);
  await page.reload();
  const capabilities = await (
    await page.request.get(`${apiOrigin}/api/v1/capabilities`)
  ).json();
  const profile = capabilities.profiles.find(
    (item) => item.profile_id === "postgres-dense-exact",
  );
  check(
    profile,
    "A real qualified Dense capability is required for this smoke",
  );
  const requests = [];
  const observe = (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/search")
    )
      requests.push(request.postDataJSON());
  };
  page.on("request", observe);
  try {
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    const status = page.getByRole("status", { name: "Execution status" });
    await status
      .filter({ hasText: /LIVE.*(?:Ready|Choose profile)/ })
      .waitFor();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page
      .getByRole("combobox", { name: "Execution profile", exact: true })
      .selectOption(profile.profile_id);
    await status.filter({ hasText: /LIVE.*Ready/ }).waitFor();
    await page
      .getByText("Exact cosine distance. Lower distances rank first.", {
        exact: true,
      })
      .waitFor();
    await page.getByRole("button", { name: "Pipelines", exact: true }).click();
    await page
      .getByRole("button", { name: "New pipeline", exact: true })
      .click();
    await page
      .getByRole("button", { name: /Dense search Requires a qualified Live/ })
      .click();
    check(
      (await page.locator(".react-flow__node").count()) === 4,
      "Dense graph must have four components",
    );
    await page.evaluate(() => {
      window.__denseUiSamples = [];
      const original = Response.prototype.text;
      window.__denseOriginalResponseText = original;
      Response.prototype.text = async function () {
        const text = await original.call(this);
        if (
          this.ok &&
          this.url &&
          new URL(this.url).pathname.endsWith("/search")
        ) {
          const body = JSON.parse(text);
          if (
            body.profile_id === "postgres-dense-exact" &&
            body.results?.length
          ) {
            const bodyReady = performance.now();
            const observer = new MutationObserver(() => {
              if (
                !document.querySelector(".live-retrieval-result") ||
                !document
                  .querySelector(".results-meta .status")
                  ?.textContent.includes("Completed")
              )
                return;
              observer.disconnect();
              const domCommit = performance.now();
              requestAnimationFrame(() =>
                requestAnimationFrame(() => {
                  window.__denseUiSamples.push({
                    run_id: body.run_id,
                    trace_id: body.trace_id,
                    response_body_ready_to_result_dom_commit_ms:
                      domCommit - bodyReady,
                    response_body_ready_to_second_animation_frame_ms:
                      performance.now() - bodyReady,
                  });
                }),
              );
            });
            observer.observe(document.body, {
              childList: true,
              subtree: true,
              characterData: true,
            });
          }
        }
        return text;
      };
    });
    const bodies = [];
    const queries = [
      "How long are backups retained?",
      "What is the backup retention period?",
      "When do old backups expire?",
      "How many days are backups kept?",
      "Explain the rules for keeping backup copies.",
      "Как долго хранятся резервные копии?",
      "Когда удаляют старые резервные копии?",
      "Скільки часу зберігаються резервні копії?",
      "Коли видаляють старі резервні копії?",
      "What policy controls stored backups?",
    ];
    for (const [index, query] of queries.entries()) {
      await page
        .locator(".node-title")
        .filter({ hasText: /^Search query$/ })
        .click();
      await page
        .getByRole("textbox", { name: "Question", exact: true })
        .fill(query);
      await page
        .getByRole("button", { name: "Close inspector", exact: true })
        .click();
      const responsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname.endsWith("/search"),
      );
      await page.getByRole("button", { name: "Run", exact: true }).click();
      const response = await responsePromise;
      const body = await response.json();
      check(
        response.ok(),
        `Dense search failed with HTTP ${response.status()}`,
      );
      await page
        .locator(".results-meta .status")
        .filter({ hasText: "Completed" })
        .waitFor();
      await page.waitForFunction(
        (count) => window.__denseUiSamples.length === count,
        index + 1,
      );
      bodies.push(body);
    }
    const body = bodies[0];
    check(
      body.results.length > 0,
      "Real Dense smoke requires persisted matches",
    );
    check(
      body.results.every(
        (hit, index) =>
          hit.score_type === "cosine_distance" &&
          (index === 0 || hit.score >= body.results[index - 1].score),
      ),
      "Raw distances must rank in ascending order",
    );
    check(
      requests.length === queries.length &&
        Object.keys(requests[0]).length === 4 &&
        requests[0].expected_profile_revision === profile.profile_revision,
      "Only the four-field revision-fenced search request may be sent",
    );
    check(
      body.embedding_profile_revision === profile.embedding_profile_revision &&
        body.index_generation === profile.index_generation,
      "Displayed results must match advertised model/generation provenance",
    );
    check(
      (await page.locator(".live-score").first().innerText()).includes(
        "Lower is better",
      ),
      "Distance direction must be visible",
    );
    await page.getByRole("tab", { name: /^Stages/ }).click();
    for (const stage of ["query_embedding", "vector_search", "projection"])
      await page.locator(`.live-stage[data-stage="${stage}"]`).waitFor();
    const beforeInvalid = requests.length;
    const openComponents = page.getByRole("button", {
      name: "Open components",
      exact: true,
    });
    if (await openComponents.isVisible()) await openComponents.click();
    await page
      .locator("button.library-item")
      .filter({ hasText: "Dense search" })
      .click();
    check(
      await page.getByRole("button", { name: "Run", exact: true }).isDisabled(),
      "An extra component must disable Live Run",
    );
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    check(
      requests.length === beforeInvalid,
      "Unsupported graphs must send zero search HTTP requests",
    );
    await page
      .getByRole("button", { name: "Delete node", exact: true })
      .click();
    const fail = (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          contract_revision: "rag-api-v1.0",
          request_id: "browser-injected-request",
          trace_id: "browser-injected-trace",
          error: {
            code: "DEPENDENCY_UNAVAILABLE",
            message: "Injected local provider outage",
            retryable: true,
            http_status: 503,
          },
        }),
      });
    await page.route("**/api/v1/workspaces/*/search", fail);
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await page
      .locator(".results-meta .status")
      .filter({ hasText: "Failed" })
      .waitFor();
    check(
      (await page.locator(".live-retrieval-result").count()) === 0,
      "Provider outage must clear results without Preview fallback",
    );
    await page.unroute("**/api/v1/workspaces/*/search", fail);
    const uiSamples = await page.evaluate(() => window.__denseUiSamples);
    const percentile = (values, fraction) =>
      [...values].sort((left, right) => left - right)[
        Math.ceil(values.length * fraction) - 1
      ];
    const timings = Object.fromEntries(
      [
        "response_body_ready_to_result_dom_commit_ms",
        "response_body_ready_to_second_animation_frame_ms",
      ].map((metric) => {
        const values = uiSamples.map((sample) => sample[metric]);
        return [
          metric,
          {
            samples: values.length,
            p50: percentile(values, 0.5),
            p95: percentile(values, 0.95),
          },
        ];
      }),
    );
    return {
      result: "PASS",
      evidence: "real qualified API plus explicitly injected HTTP 503",
      profile_id: profile.profile_id,
      profile_revision: profile.profile_revision,
      embedding_profile_revision: body.embedding_profile_revision,
      index_generation: body.index_generation,
      trace_id: body.trace_id,
      results: body.results.map(
        ({ chunk_id, source_id, source_version_id, score }) => ({
          chunk_id,
          source_id,
          source_version_id,
          score,
        }),
      ),
      exact_request_fields: Object.keys(requests[0]),
      provider_failure_no_fallback: true,
      unsupported_graph_search_requests: requests.length - beforeInvalid - 1,
      browser_timing_scope:
        "Response body consumption to observed React result DOM commit and second animation-frame callback; excludes provider/SQL/network and includes JSON decode, React scheduling and frame scheduling. Not pure component CPU or guaranteed paint duration.",
      ui_timings: timings,
      ui_samples: uiSamples,
      server_samples: bodies.map((sample) => ({
        run_id: sample.run_id,
        trace_id: sample.trace_id,
        stages: sample.stages,
      })),
    };
  } finally {
    page.off("request", observe);
    if (apiPort) await page.unrouteAll({ behavior: "wait" });
    await page.evaluate(() => {
      if (window.__denseOriginalResponseText) {
        Response.prototype.text = window.__denseOriginalResponseText;
        delete window.__denseOriginalResponseText;
      }
    });
  }
}
