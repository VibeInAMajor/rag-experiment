async function discoverySmoke(page) {
  page.setDefaultTimeout(7000);
  const check = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const status = page.getByRole("status", { name: "Execution status" });
  const mode = (name) => page.getByRole("radio", { name, exact: true });
  const realResponses = new Map();
  const requests = [];
  const responseTasks = [];
  const pageErrors = [];
  const observePageError = (error) => pageErrors.push(error.message);
  let intercepting = false;
  const observeRequest = (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/"))
      requests.push({ method: request.method(), path });
  };
  const observeResponse = (response) => {
    const path = new URL(response.url()).pathname;
    if (intercepting || !path.startsWith("/api/v1/")) return;
    responseTasks.push(
      response.json().then((body) => {
        realResponses.set(path, { status: response.status(), body });
      }),
    );
  };
  page.on("request", observeRequest);
  page.on("response", observeResponse);
  page.on("pageerror", observePageError);
  let handler;
  let releasePending;
  try {
    await page.reload();
    await mode("Preview").waitFor();
    check(await mode("Preview").isChecked(), "Refresh must start in Preview");
    await mode("Preview").focus();
    await page.keyboard.press("ArrowRight");
    check(
      await mode("Live").isChecked(),
      "Arrow keys must select execution mode",
    );
    check(
      await mode("Live").evaluate((element) =>
        element.matches(":focus-visible"),
      ),
      "Keyboard mode selection must retain visible focus",
    );
    await status.filter({ hasText: /LIVE.*Ready/ }).waitFor();
    await Promise.all(responseTasks);
    const capabilities = realResponses.get("/api/v1/capabilities")?.body;
    const workspacePage = realResponses.get("/api/v1/workspaces")?.body;
    check(
      realResponses.size === 4 && capabilities && workspacePage,
      "The browser must call all four real discovery endpoints",
    );
    const profile = capabilities.profiles.find(
      (item) => item.profile_id === "postgres-fts-baseline",
    );
    check(
      profile,
      "The real API must advertise its PostgreSQL lexical profile",
    );
    const allowed = workspacePage.items.filter((item) =>
      profile.workspace_ids.includes(item.workspace_id),
    );
    check(
      allowed.length > 0,
      "The real API must return an authorized workspace",
    );
    check(
      await page.getByRole("button", { name: "Run", exact: true }).isDisabled(),
      "Live execution must stay disabled before the execution integration task",
    );
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByText(profile.profile_id, { exact: true }).waitFor();
    await page.getByText(profile.profile_revision, { exact: true }).waitFor();
    await page.getByText(profile.score_type, { exact: true }).waitFor();
    await page.getByText("Read-only listing", { exact: true }).waitFor();
    const originalViewport = page.viewportSize();
    for (const width of [1440, 1100]) {
      await page.setViewportSize({ width, height: 1000 });
      check(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        `Settings must fit a ${width}px viewport`,
      );
      await page.screenshot({
        path: `../../../output/playwright/workbench-live-ready-${width}.png`,
        fullPage: true,
      });
    }
    if (originalViewport) await page.setViewportSize(originalViewport);
    const selectedWorkspace = await page
      .getByRole("combobox", { name: "Backend workspace", exact: true })
      .inputValue();
    check(
      allowed.some((item) => item.workspace_id === selectedWorkspace),
      "Selected workspace must belong to the profile and authorized list",
    );
    await page
      .getByRole("textbox", { name: "Workspace name", exact: true })
      .fill("forged-workspace");
    await page
      .getByRole("button", { name: "Refresh connection", exact: true })
      .click();
    await status.filter({ hasText: /LIVE.*Ready/ }).waitFor();
    check(
      (await page
        .getByRole("combobox", { name: "Backend workspace", exact: true })
        .inputValue()) === selectedWorkspace,
      "Editing the workspace display name must not alter authorization",
    );

    const healthy = Object.fromEntries(
      [...realResponses].map(([path, value]) => [path, value]),
    );
    // A second, unconfigured API process supplies the real 503/no-profile sample.
    const unconfigured = {};
    for (const path of Object.keys(healthy)) {
      const response = await page.request.get(`http://127.0.0.1:8012${path}`);
      unconfigured[path] = {
        status: response.status(),
        body: await response.json(),
      };
    }
    check(
      unconfigured["/api/v1/health/ready"].status === 503 &&
        unconfigured["/api/v1/capabilities"].status === 200 &&
        unconfigured["/api/v1/capabilities"].body.profiles.length === 0,
      "The secondary API must provide actual readiness 503 and no profiles",
    );
    const notReady = structuredClone(healthy);
    const meta = healthy["/api/v1/health/ready"].body;
    notReady["/api/v1/health/ready"] = {
      status: 503,
      body: {
        contract_revision: meta.contract_revision,
        request_id: meta.request_id,
        trace_id: meta.trace_id,
        error: {
          code: "NOT_READY",
          message: "The search dependency is unavailable.",
          retryable: true,
          http_status: 503,
        },
      },
    };
    notReady["/api/v1/capabilities"].body.profiles = [];
    notReady["/api/v1/capabilities"].body.features = {
      documents: false,
      search: false,
    };
    notReady["/api/v1/capabilities"].body.dependencies.database.status =
      "unavailable";
    const conflict = structuredClone(healthy);
    conflict["/api/v1/workspaces"].body.items = [
      {
        workspace_id: "different-workspace",
        name: "Different",
        status: "ready",
      },
    ];
    let scenario = "offline";
    let releaseDelayed;
    const delayedRelease = new Promise((resolve) => {
      releaseDelayed = resolve;
      releasePending = resolve;
    });
    let noteDelayed;
    const delayedStarted = new Promise((resolve) => {
      noteDelayed = resolve;
    });
    const delayedTasks = [];
    handler = async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (scenario === "offline") return route.abort();
      const activeScenario = scenario;
      const sample = (
        activeScenario === "unready"
          ? notReady
          : activeScenario === "unconfigured"
            ? unconfigured
            : activeScenario === "conflict"
              ? conflict
              : healthy
      )[path];
      check(sample, `Unexpected execution API operation: ${path}`);
      const fulfill = () =>
        route.fulfill({
          status: sample.status,
          contentType: "application/json",
          headers: { "X-Request-ID": sample.body.request_id },
          body: JSON.stringify(sample.body),
        });
      if (activeScenario === "delayed") {
        noteDelayed();
        const pending = delayedRelease.then(fulfill).catch(() => {
          // The obsolete browser request can already have been cancelled.
        });
        delayedTasks.push(pending);
        return pending;
      }
      return fulfill();
    };
    intercepting = true;
    await page.route("**/api/v1/**", handler);
    const refresh = () =>
      page
        .getByRole("button", { name: "Refresh connection", exact: true })
        .click();

    await refresh();
    await status.filter({ hasText: /LIVE.*Offline/ }).waitFor();
    check(await mode("Live").isChecked(), "An outage must not switch modes");
    check(
      (await page
        .getByRole("combobox", { name: "Backend workspace", exact: true })
        .inputValue()) === "",
      "An outage must clear the authorized selection",
    );
    await page.getByRole("button", { name: "Documents", exact: true }).click();
    check(
      (await page.locator(".data-table tbody tr").count()) === 0,
      "Live Documents must not expose Preview fixtures",
    );
    await page.getByRole("button", { name: "Runs", exact: true }).click();
    check(
      (await page.locator(".data-table tbody tr").count()) === 0,
      "Live Runs must not expose Preview fixtures",
    );
    await page.getByRole("button", { name: "Settings", exact: true }).click();

    scenario = "unconfigured";
    await refresh();
    await status.filter({ hasText: /LIVE.*Not ready/ }).waitFor();
    await page
      .getByText(/NOT_READY/)
      .first()
      .waitFor();
    await page.screenshot({
      path: "../../../output/playwright/workbench-live-not-ready-1440.png",
      fullPage: true,
    });
    scenario = "unready";
    await refresh();
    await status.filter({ hasText: /LIVE.*Not ready/ }).waitFor();
    await page
      .getByText(/NOT_READY/)
      .first()
      .waitFor();
    scenario = "conflict";
    await refresh();
    await status.filter({ hasText: /LIVE.*Incompatible/ }).waitFor();

    scenario = "delayed";
    await refresh();
    await delayedStarted;
    await mode("Preview").check();
    scenario = "unready";
    await mode("Live").check();
    await status.filter({ hasText: /LIVE.*Not ready/ }).waitFor();
    releaseDelayed();
    await Promise.all(delayedTasks);
    check(
      /LIVE.*Not ready/.test(await status.innerText()),
      "An obsolete healthy response must not overwrite newer failure state",
    );

    scenario = "offline";
    await mode("Preview").check();
    await status.filter({ hasText: "PREVIEW" }).waitFor();
    await page.getByRole("button", { name: "Pipelines", exact: true }).click();
    await page
      .getByRole("button", { name: /Hybrid document search/ })
      .first()
      .click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await page
      .locator(".results-meta .status")
      .filter({ hasText: "Completed" })
      .waitFor({ timeout: 15000 });
    check(
      (await page.locator(".retrieval-result").count()) === 4,
      "Explicit Preview must work with API offline",
    );
    check(
      requests.every(
        (request) =>
          request.method === "GET" &&
          [
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/api/v1/capabilities",
            "/api/v1/workspaces",
          ].includes(request.path),
      ),
      "Discovery must never call search or document operations",
    );
    check(
      requests.every((request) => !request.path.includes("forged-workspace")),
      "Display name must never become an API identifier",
    );
    check(
      pageErrors.length === 0,
      "Discovery must not produce uncaught browser errors",
    );
    return {
      result: "PASS",
      checked: [
        "real backend discovery",
        "keyboard mode selection with visible focus",
        "1440px and 1100px layout assertions and screenshots",
        "server-authorized workspace",
        "read-only document capability",
        "Live Run disabled",
        "offline without fallback",
        "real unconfigured API 503 and empty profiles replayed in browser",
        "503 and empty profiles",
        "conflicting workspace",
        "stale response",
        "manual Preview offline",
        "discovery GET operations only",
      ],
      realBackend: Object.fromEntries(realResponses),
      realUnconfiguredBackend: unconfigured,
      requestCount: requests.length,
    };
  } finally {
    releasePending?.();
    if (handler) await page.unroute("**/api/v1/**", handler);
    page.off("request", observeRequest);
    page.off("response", observeResponse);
    page.off("pageerror", observePageError);
  }
}
