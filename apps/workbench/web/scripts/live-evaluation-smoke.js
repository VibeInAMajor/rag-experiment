async function liveEvaluationSmoke(page) {
  page.setDefaultTimeout(10000);
  const config = await page.evaluate(() => window.__workbenchEvaluationInput);
  const check = (condition, code) => {
    if (condition) return;
    const error = new Error(code);
    error.evaluationCode = code;
    throw error;
  };
  check(
    config &&
      /^[a-z0-9_-]{1,32}$/.test(config.phase) &&
      config.fixture?.corpus === "development-corpus-v1" &&
      config.fixture.score_type === "postgres_ts_rank_cd" &&
      config.fixture.gated_exact_queries?.length === 10 &&
      config.fixture.diagnostic_paraphrases?.length === 3,
    "CANONICAL_EVALUATION_INPUT_REQUIRED",
  );
  const hash = (text) =>
    page.evaluate(async (value) => {
      const digest = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(value),
      );
      return Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
    }, text);
  const failureCode = (error) =>
    error.evaluationCode ??
    (error.name === "TimeoutError"
      ? "BROWSER_TIMEOUT"
      : "BROWSER_CHECK_FAILED");
  const percentile = (values, fraction) => {
    if (!values.length) return null;
    const ordered = values.slice().sort((left, right) => left - right);
    return ordered[Math.ceil(fraction * ordered.length) - 1];
  };
  const distribution = (values) => ({
    sample_count: values.length,
    convention: "nearest-rank: sorted[ceil(p*n)-1]",
    p50: percentile(values, 0.5),
    p95: percentile(values, 0.95),
    max: values.length ? Math.max(...values) : null,
  });
  const summarize = (cases) => {
    const successful = cases.filter((item) => item.outcome === "success");
    const hits = cases.reduce((total, item) => total + item.hit_at_5, 0);
    const zeroHits = successful.filter(
      (item) => item.returned_results.length === 0,
    ).length;
    return {
      required_cases: cases.length,
      successful_cases: successful.length,
      failed_or_missing_cases: cases.length - successful.length,
      expected_source_hits_at_5: hits,
      expected_source_hit_rate_at_5: hits / cases.length,
      recall_at_5_single_relevant_source: hits / cases.length,
      mrr_at_5:
        cases.reduce((total, item) => total + item.reciprocal_rank, 0) /
        cases.length,
      zero_hit_successes: zeroHits,
      zero_hit_response_denominator: successful.length,
      zero_hit_rate: successful.length ? zeroHits / successful.length : null,
      server_latency_ms: distribution(
        successful.map((item) => item.server_duration_ms),
      ),
      browser_network_elapsed_ms: distribution(
        successful.map((item) => item.browser_network_elapsed_ms),
      ),
    };
  };
  const makeCase = async (item, group, index) => ({
    query_id: `${group}-${String(index + 1).padStart(2, "0")}`,
    query_sha256: await hash(item.query),
    expected_source_id: item.expected_source_id ?? null,
    outcome: "not_executed",
    hit_at_5: 0,
    reciprocal_rank: 0,
    returned_results: [],
  });
  const report = {
    captured_at_utc: new Date().toISOString(),
    phase: config.phase,
    run_mode: "real_browser_api_postgres",
    lane: "real-service",
    fixture_corpus: config.fixture.corpus,
    fixture_sha256: config.fixture_sha256 ?? null,
    fixture_semantic_sha256: await hash(JSON.stringify(config.fixture)),
    sample_state:
      config.sample_state ??
      "sequential requests; service cache state unclassified",
    exact_cases: await Promise.all(
      config.fixture.gated_exact_queries.map((item, index) =>
        makeCase(item, "exact", index),
      ),
    ),
    paraphrase_cases: await Promise.all(
      config.fixture.diagnostic_paraphrases.map((item, index) =>
        makeCase(item, "paraphrase", index),
      ),
    ),
    no_match_case: await makeCase(
      { query: "zzzzlexicalnomatch2026" },
      "no-match",
      0,
    ),
    error_cases: [],
    screenshots: [],
    regressions: [],
    limitations: [
      "Eight synthetic development sources; one expected relevant source per labeled query.",
      "Native PostgreSQL ts_rank_cd scores; lexical paraphrase hits are diagnostic.",
      "Sequential small samples are not a production latency SLO or a cold-start benchmark.",
      "Real error requests modify outbound fields or workspace URL; no response is fabricated.",
      "API/database outage and restart supervision are separate operator-run evidence.",
    ],
  };
  const runButton = () =>
    page.getByRole("button", { name: "Run", exact: true });
  const resultPanel = () =>
    page.getByRole("region", { name: "Pipeline results" });
  const status = () => resultPanel().locator(".results-meta .status");
  const executionStatus = () =>
    page.getByRole("status", { name: "Execution status" });
  const isSearch = (response) =>
    response.request().method() === "POST" &&
    new URL(response.url()).pathname.endsWith("/search");
  const pageErrors = [];
  const observeError = (error) => pageErrors.push(error.message);
  let searchRequests = 0;
  const observeRequest = (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/search")
    )
      searchRequests += 1;
  };
  page.on("pageerror", observeError);
  page.on("request", observeRequest);
  const queryField = async (query) => {
    await page
      .locator(".node-title")
      .filter({ hasText: /^Search query$/ })
      .click();
    await page
      .getByRole("textbox", { name: "Question", exact: true })
      .fill(query);
  };
  const metadata = () =>
    resultPanel()
      .locator(".live-run-metadata .live-provenance")
      .evaluate((element) =>
        Object.fromEntries(
          Array.from(element.querySelectorAll("div"), (item) => [
            item.querySelector("dt").textContent,
            item.querySelector("dd").textContent,
          ]),
        ),
      );
  const readProbe = async () => {
    const origin = new URL(page.url()).origin;
    const [health, capabilities, documents] = await Promise.all([
      page.request.get(`${origin}/api/v1/health/live`),
      page.request.get(`${origin}/api/v1/capabilities`),
      page.request.get(
        `${origin}/api/v1/workspaces/development/documents?limit=25`,
      ),
    ]);
    check(
      [health, capabilities, documents].every(
        (response) => response.status() === 200,
      ),
      "REAL_SERVICE_PROBE_FAILED",
    );
    const healthBody = await health.json();
    const caps = await capabilities.json();
    const docs = await documents.json();
    const profile = caps.profiles.find(
      (item) => item.profile_id === "postgres-fts-baseline",
    );
    check(
      profile &&
        profile.workspace_ids.includes("development") &&
        caps.features.search &&
        caps.dependencies.database.status === "ready" &&
        docs.next_cursor === null &&
        docs.items.length === 8,
      "QUALIFIED_EIGHT_SOURCE_CORPUS_REQUIRED",
    );
    return {
      backend_revision: healthBody.backend_revision,
      contract_revision: caps.contract_revision,
      profile_id: profile.profile_id,
      profile_revision: profile.profile_revision,
      score_type: profile.score_type,
      database_schema_revision: caps.dependencies.database.schema_revision,
      database_source_count: caps.dependencies.database.source_count,
      database_chunk_count: caps.dependencies.database.chunk_count,
      corpus_revision: docs.corpus_revision,
      registry: docs.items.map((item) => ({
        source_id: item.source_id,
        active_version_id: item.active_version_id,
        chunk_count: item.chunk_count,
        status: item.status,
        updated_at: item.updated_at,
      })),
    };
  };
  const setJson = async (enabled) => {
    const button = resultPanel().getByRole("button", { name: "Toggle JSON" });
    if ((await button.getAttribute("aria-pressed")) !== String(enabled))
      await button.click();
  };
  const verifyMetadata = async (body) => {
    await resultPanel()
      .locator(".live-run-metadata dd")
      .filter({ hasText: body.request_id })
      .waitFor({ state: "attached" });
    const shown = await metadata();
    check(
      shown["Request ID"] === body.request_id &&
        shown["Trace ID"] === body.trace_id &&
        shown["Server run ID"] ===
          (body.run_id ?? body.error?.run_id ?? "Not received"),
      "VISIBLE_CORRELATION_PARITY_FAILED",
    );
    if (body.status === "success")
      check(
        shown.Workspace === body.workspace_id &&
          shown.Profile === body.profile_id &&
          shown["Profile revision"] === body.profile_revision &&
          shown["Corpus revision"] === body.corpus_revision,
        "VISIBLE_PROFILE_CORPUS_PARITY_FAILED",
      );
  };
  const successfulCase = async (query, entry) => {
    let response;
    try {
      await executionStatus()
        .filter({ hasText: /LIVE.*Ready/ })
        .waitFor();
      await queryField(query);
      const started = Date.now();
      [response] = await Promise.all([
        page.waitForResponse(isSearch),
        runButton().click(),
      ]);
      entry.http_status = response.status();
      check(response.status() === 200, "REAL_SEARCH_HTTP_FAILED");
      const body = await response.json();
      await response.finished();
      const request = response.request();
      const wire = request.postDataJSON();
      const url = new URL(response.url());
      entry.server_run_id = body.run_id;
      entry.request_id = body.request_id;
      entry.trace_id = body.trace_id;
      entry.corpus_revision = body.corpus_revision;
      entry.server_duration_ms = body.duration_ms;
      entry.browser_network_elapsed_ms = request.timing().responseEnd;
      check(
        url.origin === new URL(page.url()).origin &&
          url.pathname === "/api/v1/workspaces/development/search" &&
          !response.fromServiceWorker() &&
          response.headers()["content-type"]?.includes("application/json") &&
          response.headers()["x-request-id"] === body.request_id,
        "SAME_ORIGIN_REAL_HTTP_ENVELOPE_REQUIRED",
      );
      check(
        body.contract_revision === "rag-api-v1.0" &&
          body.mode === "live" &&
          body.status === "success" &&
          body.workspace_id === "development" &&
          body.profile_id === report.service_before.profile_id &&
          body.profile_revision === report.service_before.profile_revision &&
          body.corpus_revision === report.service_before.corpus_revision,
        "LIVE_RESPONSE_IDENTITY_MISMATCH",
      );
      check(
        JSON.stringify(Object.keys(wire).sort()) ===
          JSON.stringify(
            [
              "query",
              "top_k",
              "profile_id",
              "expected_profile_revision",
            ].sort(),
          ) &&
          wire.query === query &&
          wire.top_k === 5 &&
          wire.profile_id === body.profile_id &&
          wire.expected_profile_revision === body.profile_revision,
        "FOUR_FIELD_REQUEST_PARITY_FAILED",
      );
      check(
        Number.isFinite(body.duration_ms) &&
          body.duration_ms >= 0 &&
          Number.isFinite(entry.browser_network_elapsed_ms) &&
          entry.browser_network_elapsed_ms >= 0 &&
          body.stages.reduce((total, stage) => total + stage.duration_ms, 0) <=
            body.duration_ms + 0.001,
        "REAL_TIMING_SAMPLE_INVALID",
      );
      await verifyMetadata(body);
      await status().filter({ hasText: "Completed" }).waitFor();
      await setJson(false);
      await resultPanel()
        .getByRole("tab", { name: "Output", exact: true })
        .click();
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
            title: item.querySelector(".result-title strong").textContent,
            page: item.querySelector(".result-title > span").textContent,
            content: item.querySelector(".live-result-body > p").textContent,
            shown_score: item.querySelector(".result-score").textContent,
            provenance: Object.fromEntries(
              Array.from(
                item.querySelectorAll(".live-source-provenance > div"),
                (field) => [
                  field.querySelector("dt").textContent,
                  field.querySelector("dd").textContent,
                ],
              ),
            ),
          })),
        );
      const expected = body.results.map((item) => ({
        source_id: item.source_id,
        source_version_id: item.source_version_id,
        chunk_id: item.chunk_id,
        rank: item.rank,
        score: item.score,
        score_type: item.score_type,
        title: item.title,
        page: item.page == null ? "Page unavailable" : `Page ${item.page}`,
        content: item.content,
        shown_score: String(item.score),
        provenance: {
          Source: item.source_id,
          "Source version": item.source_version_id,
          Chunk: item.chunk_id,
        },
      }));
      check(
        JSON.stringify(shown) === JSON.stringify(expected),
        "VISIBLE_RESULT_RAW_SCORE_PROVENANCE_PARITY_FAILED",
      );
      check(
        body.results.length <= 5 &&
          body.results.every(
            (item, index) =>
              item.rank === index + 1 &&
              item.score_type === "postgres_ts_rank_cd",
          ) &&
          (await resultPanel()
            .locator('.retrieval-result:not([data-source="live"])')
            .count()) === 0 &&
          (await page
            .locator(
              ".pipeline-node.state-success, .pipeline-node.state-running",
            )
            .count()) === 0,
        "LIVE_RANK_OR_FIXTURE_ISOLATION_FAILED",
      );
      if (!body.results.length)
        await resultPanel()
          .getByText("No matches for this query.", { exact: true })
          .waitFor();
      check(
        Number(
          await resultPanel()
            .getByLabel("Server duration")
            .getAttribute("data-duration-ms"),
        ) === body.duration_ms,
        "SERVER_TOTAL_TIMING_PARITY_FAILED",
      );
      await resultPanel()
        .getByRole("tab", { name: "Stages", exact: true })
        .click();
      const stages = await resultPanel()
        .locator(".live-stage")
        .evaluateAll((items) =>
          items.map((item) => ({
            stage: item.dataset.stage,
            duration_ms: Number(item.dataset.durationMs),
            status: item.querySelector(".status").textContent,
          })),
        );
      check(
        JSON.stringify(stages) ===
          JSON.stringify(
            body.stages.map(({ stage, duration_ms, status: stageStatus }) => ({
              stage,
              duration_ms,
              status: stageStatus,
            })),
          ),
        "SERVER_STAGE_TIMING_PARITY_FAILED",
      );
      await setJson(true);
      const displayedJson = JSON.parse(
        await resultPanel().getByLabel("Live response JSON").innerText(),
      );
      check(
        JSON.stringify(displayedJson) === JSON.stringify(body),
        "EXPORTED_JSON_FULL_PAYLOAD_PARITY_FAILED",
      );
      await setJson(false);
      await resultPanel()
        .getByRole("tab", { name: "Output", exact: true })
        .click();
      entry.click_to_verified_render_ms = Date.now() - started;
      entry.returned_results = await Promise.all(
        body.results.map(async (item) => ({
          source_id: item.source_id,
          source_version_id: item.source_version_id,
          chunk_id: item.chunk_id,
          rank: item.rank,
          score: item.score,
          score_type: item.score_type,
          page: item.page ?? null,
          page_was_present: Object.hasOwn(item, "page"),
          content_sha256: await hash(item.content),
        })),
      );
      entry.stages = body.stages;
      entry.request_fields = Object.keys(wire).sort();
      entry.dom_json_score_timing_provenance_parity = true;
      entry.no_fixture_fallback = true;
      entry.outcome = "success";
      const relevant = body.results.find(
        (item) => item.source_id === entry.expected_source_id && item.rank <= 5,
      );
      entry.hit_at_5 = relevant ? 1 : 0;
      entry.reciprocal_rank = relevant ? 1 / relevant.rank : 0;
    } catch (error) {
      entry.outcome = "failed";
      entry.failure_code = failureCode(error);
      report.regressions.push(`${entry.query_id}:${entry.failure_code}`);
    }
  };
  const captureLayouts = async () => {
    if (config.capture_screenshots === false) return;
    for (const name of ["Close inspector", "Collapse components"]) {
      const button = page.getByRole("button", { name, exact: true });
      if (await button.isVisible()) await button.click();
    }
    for (const width of [1440, 1100]) {
      await page.setViewportSize({ width, height: 1000 });
      check(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        "LIVE_LAYOUT_HORIZONTAL_OVERFLOW",
      );
      const path = `../../../output/playwright/workbench-live-evaluation-${config.phase}-${width}.png`;
      await page.screenshot({ path, fullPage: true });
      report.screenshots.push({ width, path });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  };
  const realFailure = async (scenario) => {
    const entry = {
      scenario: scenario.name,
      lane: "real-service-request-mutation",
      expected_http_status: scenario.status,
      expected_error_code: scenario.code,
      outcome: "not_executed",
    };
    report.error_cases.push(entry);
    let handler;
    try {
      await executionStatus()
        .filter({ hasText: /LIVE.*Ready/ })
        .waitFor();
      await queryField("retention");
      handler = async (route) => {
        const request = route.request();
        const body = request.postDataJSON();
        const url = new URL(request.url());
        if (scenario.name === "invalid-body") body.top_k = 0;
        if (scenario.name === "unavailable-workspace")
          url.pathname = "/api/v1/workspaces/evaluation-unavailable/search";
        if (scenario.name === "stale-profile")
          body.expected_profile_revision = "postgres-fts-baseline-stale";
        await route.continue({
          url: url.href,
          postData: JSON.stringify(body),
        });
      };
      await page.route("**/api/v1/workspaces/*/search", handler);
      const [response] = await Promise.all([
        page.waitForResponse(isSearch),
        runButton().click(),
      ]);
      entry.http_status = response.status();
      const body = await response.json();
      entry.error_code = body.error?.code;
      entry.request_id = body.request_id;
      entry.trace_id = body.trace_id;
      entry.server_run_id = body.error?.run_id ?? null;
      check(
        response.status() === scenario.status &&
          body.error?.code === scenario.code &&
          body.error.http_status === scenario.status &&
          response.headers()["x-request-id"] === body.request_id,
        "REAL_ERROR_ENVELOPE_MISMATCH",
      );
      await status().filter({ hasText: "Failed" }).waitFor();
      await verifyMetadata(body);
      await setJson(false);
      await resultPanel()
        .getByRole("tab", { name: /^Errors/ })
        .click();
      await resultPanel().getByText(scenario.code, { exact: true }).waitFor();
      await resultPanel()
        .getByText(`HTTP ${scenario.status}`, { exact: true })
        .waitFor();
      check(
        (await resultPanel().locator(".retrieval-result").count()) === 0 &&
          (await page
            .getByRole("radio", { name: "Live", exact: true })
            .isChecked()),
        "REAL_ERROR_FALSE_SUCCESS_OR_FIXTURE_FALLBACK",
      );
      await setJson(true);
      const shown = JSON.parse(
        await resultPanel().getByLabel("Live response JSON").innerText(),
      );
      check(
        shown.status === "Failed" &&
          shown.request_id === body.request_id &&
          shown.trace_id === body.trace_id &&
          shown.error.code === body.error.code &&
          shown.error.httpStatus === scenario.status,
        "ERROR_JSON_CORRELATION_PARITY_FAILED",
      );
      await setJson(false);
      entry.no_fixture_fallback = true;
      entry.visible_correlation_and_error_parity = true;
      entry.outcome = "success";
    } catch (error) {
      entry.outcome = "failed";
      entry.failure_code = failureCode(error);
      report.regressions.push(`${scenario.name}:${entry.failure_code}`);
    } finally {
      if (handler) await page.unroute("**/api/v1/workspaces/*/search", handler);
    }
  };
  try {
    await page.reload();
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    await executionStatus()
      .filter({ hasText: /LIVE.*Ready/ })
      .waitFor();
    check(
      await runButton().isDisabled(),
      "UNSUPPORTED_HYBRID_MUST_NOT_EXECUTE",
    );
    check(searchRequests === 0, "UNSUPPORTED_GRAPH_SENT_SEARCH");
    report.service_before = await readProbe();
    if (config.expected_corpus_revision)
      check(
        report.service_before.corpus_revision ===
          config.expected_corpus_revision,
        "RESTART_CORPUS_REVISION_CHANGED",
      );
    await page.getByRole("button", { name: "Pipelines", exact: true }).click();
    await page
      .getByRole("button", { name: "New pipeline", exact: true })
      .click();
    await page.getByRole("button", { name: /Keyword search/ }).click();
    check(
      (await page.locator(".react-flow__node").count()) === 3,
      "APPROVED_KEYWORD_TOPOLOGY_REQUIRED",
    );
    for (
      let index = 0;
      index < config.fixture.gated_exact_queries.length;
      index++
    ) {
      await successfulCase(
        config.fixture.gated_exact_queries[index].query,
        report.exact_cases[index],
      );
      if (index === 0 && report.exact_cases[index].outcome === "success")
        await captureLayouts();
    }
    for (
      let index = 0;
      index < config.fixture.diagnostic_paraphrases.length;
      index++
    )
      await successfulCase(
        config.fixture.diagnostic_paraphrases[index].query,
        report.paraphrase_cases[index],
      );
    await successfulCase("zzzzlexicalnomatch2026", report.no_match_case);
    check(
      report.no_match_case.outcome === "success" &&
        report.no_match_case.returned_results.length === 0,
      "EXPLICIT_NO_MATCH_NOT_PROVEN",
    );
    if (config.run_real_errors !== false)
      for (const scenario of [
        { name: "invalid-body", status: 400, code: "INVALID_REQUEST" },
        {
          name: "unavailable-workspace",
          status: 404,
          code: "WORKSPACE_NOT_FOUND",
        },
        { name: "stale-profile", status: 409, code: "PROFILE_NOT_AVAILABLE" },
      ])
        await realFailure(scenario);
    report.service_after = await readProbe();
    check(
      JSON.stringify(report.service_before) ===
        JSON.stringify(report.service_after),
      "READ_ONLY_REGISTRY_OR_PROFILE_CHANGED",
    );
    report.registry_unchanged = true;
    check(
      report.exact_cases[1].returned_results[0]?.source_id !==
        report.exact_cases[2].returned_results[0]?.source_id,
      "DIFFERENT_QUERY_RESULT_IDENTITY_NOT_PROVEN",
    );
    await page.getByRole("button", { name: "Runs", exact: true }).click();
    for (const entry of [
      ...report.exact_cases,
      ...report.paraphrase_cases,
      report.no_match_case,
    ])
      if (entry.server_run_id)
        await page
          .locator('tr[data-source="live"]')
          .filter({ hasText: entry.server_run_id })
          .waitFor();
    report.live_session_history_survived_navigation = true;
  } catch (error) {
    report.regressions.push(failureCode(error));
  } finally {
    page.off("pageerror", observeError);
    page.off("request", observeRequest);
  }
  report.search_request_count = searchRequests;
  const completedRequests = [
    ...report.exact_cases,
    ...report.paraphrase_cases,
    report.no_match_case,
    ...report.error_cases,
  ].filter((entry) => entry.outcome === "success");
  for (const field of ["request_id", "trace_id"])
    if (
      new Set(completedRequests.map((entry) => entry[field])).size !==
      completedRequests.length
    )
      report.regressions.push(`REUSED_SERVER_CORRELATION:${field}`);
  const completedSearches = completedRequests.filter(
    (entry) => entry.server_run_id,
  );
  if (
    new Set(completedSearches.map((entry) => entry.server_run_id)).size !==
    completedSearches.length
  )
    report.regressions.push("REUSED_SERVER_RUN_ID");
  report.page_error_count = pageErrors.length;
  report.page_error_hashes = await Promise.all(pageErrors.map(hash));
  if (pageErrors.length) report.regressions.push("UNCAUGHT_BROWSER_ERRORS");
  report.summary = {
    exact: summarize(report.exact_cases),
    paraphrase: summarize(report.paraphrase_cases),
    latency_sample_set:
      "all successful, parity-validated UI queries: 10 exact + 3 paraphrases + 1 explicit no-match; errors separate",
    server_latency_ms: distribution(
      [...report.exact_cases, ...report.paraphrase_cases, report.no_match_case]
        .filter((entry) => entry.outcome === "success")
        .map((entry) => entry.server_duration_ms),
    ),
    browser_network_elapsed_ms: distribution(
      [...report.exact_cases, ...report.paraphrase_cases, report.no_match_case]
        .filter((entry) => entry.outcome === "success")
        .map((entry) => entry.browser_network_elapsed_ms),
    ),
  };
  if (report.summary.exact.expected_source_hits_at_5 < 10)
    report.regressions.push("EXACT_BASELINE_REGRESSED_FROM_10_OF_10");
  report.development_quality_gate_passed =
    report.summary.exact.successful_cases === 10 &&
    report.summary.exact.expected_source_hits_at_5 >= 9 &&
    report.summary.paraphrase.successful_cases === 3;
  report.result =
    report.development_quality_gate_passed && report.regressions.length === 0
      ? "PASS"
      : "FAIL";
  await page.evaluate((value) => {
    window.__workbenchEvaluationReport = value;
  }, report);
  check(report.result === "PASS", `LIVE_EVALUATION_FAILED:${config.phase}`);
  return report;
}
