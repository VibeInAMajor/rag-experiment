async function sourceNameSmoke(page) {
  page.setDefaultTimeout(10000);
  const check = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const originalName = "Retention original, проверка.txt";
  const nativePath =
    "/api/v1/workspaces/development/sources/browser-original/versions/browser-original-v1/local-file/reveal";
  const observations = [];
  const pageErrors = [];
  const onError = (error) => pageErrors.push(error.message);
  page.on("pageerror", onError);
  let handler;
  let releaseReveal;
  let nativeDone;
  const nativeResponseReady = new Promise((resolve) => {
    nativeDone = resolve;
  });
  const enterKeyword = async () => {
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    await page
      .getByRole("status", { name: "Execution status" })
      .filter({ hasText: /LIVE.*Ready/ })
      .waitFor();
    await page.getByRole("button", { name: "Pipelines", exact: true }).click();
    await page
      .getByRole("button", { name: "New pipeline", exact: true })
      .click();
    await page.getByRole("button", { name: /Keyword search/ }).click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await page
      .locator(".results-meta .status")
      .filter({ hasText: "Completed" })
      .waitFor();
    await page
      .locator(".react-flow__node")
      .first()
      .waitFor({ state: "visible" });
    check(
      (await page.locator(".react-flow__node").count()) === 3,
      "Immediate Run must preserve all keyword nodes",
    );
    check(
      await page
        .locator(".react-flow__node")
        .evaluateAll((nodes) =>
          nodes.every((node) => getComputedStyle(node).visibility !== "hidden"),
        ),
      "Runtime measurements must survive execution state changes",
    );
  };
  try {
    await page.reload();
    const documentsPath = new URL(
      "/api/v1/workspaces/development/documents",
      page.url(),
    ).href;
    const before = await (await page.request.get(documentsPath)).json();
    const demoMetadataPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname.endsWith("/demo-backup-v1/local-file"),
    );
    await enterKeyword();
    const demoMetadata = await demoMetadataPromise;
    const demoBody = await demoMetadata.json();
    check(
      demoMetadata.status() === 200 &&
        demoBody.can_reveal === false &&
        demoBody.reason === "demo_source",
      "Actual demo registration must be unavailable",
    );
    check(
      (await page.locator(".source-name").count()) === 0,
      "Demo Source must be plain text, not a disabled link/action",
    );
    await page.getByText("demo-backup", { exact: true }).waitFor();
    let scenario = "native";
    handler = async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname === nativePath && scenario === "failure") {
        const body = {
          contract_revision: "rag-api-v1.0",
          request_id: "source-reveal-failure",
          trace_id: "source-reveal-trace",
          error: {
            code: "FILE_REVEAL_FAILED",
            message: "Controlled native failure.",
            retryable: true,
            http_status: 503,
          },
        };
        observations.push({
          injected: true,
          method: request.method(),
          path: url.pathname,
          body: request.postDataJSON(),
          status: 503,
          response: body,
        });
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          headers: { "X-Request-ID": body.request_id },
          body: JSON.stringify(body),
        });
      }
      const response = await route.fetch({
        url: `http://127.0.0.1:8014${url.pathname}${url.search}`,
      });
      if (
        url.pathname.endsWith("/local-file") ||
        url.pathname.endsWith("/local-file/reveal")
      ) {
        const body = await response.json();
        observations.push({
          injected: false,
          method: request.method(),
          path: url.pathname,
          ...(request.method() === "POST"
            ? { body: request.postDataJSON() }
            : {}),
          status: response.status(),
          response: body,
        });
        if (url.pathname === nativePath) {
          nativeDone();
          await new Promise((resolve) => {
            releaseReveal = resolve;
          });
        }
      }
      await route.fulfill({ response });
    };
    await page.route("**/api/v1/**", handler);
    await page.reload();
    await enterKeyword();
    const sourceLink = page.getByRole("link", {
      name: originalName,
      exact: true,
    });
    await sourceLink.waitFor();
    check(
      (await page.locator(".source-name").count()) === 1,
      "Only the source filename must be interactive",
    );
    check(
      (await page
        .locator(
          '.source-name svg, .source-name [role="menu"], .source-name + button',
        )
        .count()) === 0,
      "Source must have no action icons, menu or extra button",
    );
    await sourceLink.focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    check(
      await sourceLink.evaluate(
        (element) =>
          element === document.activeElement &&
          element.matches(":focus-visible"),
      ),
      "Filename must be keyboard-focused visibly",
    );
    await page.keyboard.press("Enter");
    await nativeResponseReady;
    check(
      await sourceLink.isDisabled(),
      "Pending native dispatch must guard repeated activation",
    );
    await sourceLink.dispatchEvent("click");
    check(
      observations.filter((event) => event.path === nativePath).length === 1,
      "One activation must dispatch once",
    );
    const native = observations.find((event) => event.path === nativePath);
    check(
      native.status === 200 && native.response.status === "revealed",
      "Actual HTTP/native Explorer dispatch must succeed",
    );
    check(
      JSON.stringify(native.body) === "{}",
      "Browser must send no file path or extra command",
    );
    releaseReveal();
    releaseReveal = undefined;
    await sourceLink.waitFor({ state: "visible" });
    await page.waitForFunction(
      () => !document.querySelector(".source-name")?.disabled,
    );
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
      await page
        .getByRole("button", { name: "Fit graph", exact: true })
        .click();
      check(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `Source name must fit ${width}px`,
      );
      await page.screenshot({
        path: `../../../output/playwright/source-name-${width}.png`,
        fullPage: true,
      });
    }
    scenario = "failure";
    await sourceLink.click();
    await page
      .locator(".source-name-error")
      .filter({ hasText: "FILE_REVEAL_FAILED" })
      .waitFor();
    check(
      !(await page.locator(".source-name-error").innerText()).includes(
        "Controlled native failure",
      ),
      "Server text must not become an unsafe error",
    );
    const safe = observations.every(
      (event) =>
        !JSON.stringify(event.response).includes("relative_path") &&
        !JSON.stringify(event.response).includes("sha256") &&
        !JSON.stringify(event.response).includes("C:\\"),
    );
    check(safe, "HTTP must not disclose local filesystem registration");
    await page.unroute("**/api/v1/**", handler);
    handler = undefined;
    const after = await (await page.request.get(documentsPath)).json();
    check(
      before.corpus_revision === after.corpus_revision &&
        JSON.stringify(before.items) === JSON.stringify(after.items),
      "Main demo registry must remain untouched",
    );
    check(
      pageErrors.length === 0,
      `Uncaught page errors: ${pageErrors.join(", ")}`,
    );
    return {
      result: "PASS",
      demo: {
        status: demoMetadata.status(),
        response: demoBody,
        interactive_names: 0,
      },
      isolated_real_original: true,
      actual_native_dispatch: true,
      visible_name: originalName,
      observations,
      main_corpus_unchanged: true,
      screenshots: [1440, 1100],
    };
  } finally {
    releaseReveal?.();
    if (handler) await page.unroute("**/api/v1/**", handler);
    page.off("pageerror", onError);
  }
}
