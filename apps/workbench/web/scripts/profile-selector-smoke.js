async function profileSelectorSmoke(page) {
  page.setDefaultTimeout(7000);
  const check = (value, message) => {
    if (!value) throw new Error(message);
  };
  const executionStatus = page.getByRole("status", {
    name: "Execution status",
  });
  const selector = () =>
    page.getByRole("combobox", { name: "Execution profile", exact: true });
  const capabilities = await (
    await page.request.get(new URL("/api/v1/capabilities", page.url()).href)
  ).json();
  const focused = capabilities.profiles.find(
    (profile) => profile.profile_id === "postgres-fts-focused",
  );
  if (focused) {
    await page.getByRole("radio", { name: "Live", exact: true }).check();
    await executionStatus.filter({ hasText: /LIVE.*Ready/ }).waitFor();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    check(
      (await selector().inputValue()) === "postgres-fts-baseline",
      "The baseline must remain the initial default",
    );
    await selector().selectOption(focused.profile_id);
    await executionStatus.filter({ hasText: /LIVE.*Ready/ }).waitFor();
    check(
      (await selector().inputValue()) === focused.profile_id,
      "Explicit selection must use the approved focused profile",
    );
    for (const width of [1440, 1100]) {
      await page.setViewportSize({ width, height: 1000 });
      check(
        await page
          .locator("body")
          .evaluate((body) => body.scrollWidth <= window.innerWidth),
        "Profile settings must not overflow the viewport",
      );
      await page.screenshot({
        path: `output/playwright/profile-selector-${width}.png`,
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole("button", { name: "Pipelines", exact: true }).click();
    await page
      .getByRole("button", { name: "New pipeline", exact: true })
      .click();
    await page.getByRole("button", { name: /Keyword search/ }).click();
    await page
      .locator(".node-title")
      .filter({ hasText: /^Keyword search$/ })
      .click();
    await page
      .getByRole("spinbutton", { name: "Maximum results", exact: true })
      .fill(String(focused.parameters.top_k.maximum));
    await page
      .locator(".node-title")
      .filter({ hasText: /^Search results$/ })
      .click();
    await page
      .getByRole("spinbutton", { name: "Results to show", exact: true })
      .fill(String(focused.parameters.top_k.maximum));
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/search"),
    );
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const response = await responsePromise;
    const body = await response.json();
    check(
      response.ok() && body.status === "success",
      "Actual focused search must succeed",
    );
    const request = response.request().postDataJSON();
    check(
      Object.keys(request).length === 4 &&
        request.profile_id === focused.profile_id &&
        request.expected_profile_revision === focused.profile_revision,
      "The request must carry exactly four revision-fenced fields",
    );
    check(
      body.profile_id === focused.profile_id &&
        body.profile_revision === focused.profile_revision,
      "The response must retain the selected immutable profile identity",
    );
    check(
      body.results.length <= focused.parameters.top_k.maximum &&
        body.results.every((hit) => hit.score_type === "postgres_ts_rank_cd"),
      "Results must retain actual lexical semantics and focused bounds",
    );
    await page
      .locator(".results-meta .status")
      .filter({ hasText: "Completed" })
      .waitFor();
    await page.locator("details.live-run-metadata summary").click();
    check(
      (
        await page
          .locator("details.live-run-metadata .live-provenance")
          .innerText()
      ).includes(focused.profile_revision),
      "The submitted profile revision must remain visible in provenance",
    );
    return {
      result: "PASS",
      phase: "qualified-selection",
      profile_id: focused.profile_id,
      profile_revision: focused.profile_revision,
      corpus_revision: body.corpus_revision,
      trace_id: body.trace_id,
      result_count: body.results.length,
      screenshots: [1440, 1100],
      request_fields: Object.keys(request),
    };
  }
  check(
    await page.getByRole("radio", { name: "Live", exact: true }).isChecked(),
    "Run the qualified selection phase before retiring the profile",
  );
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const previousSelection = await selector().inputValue();
  check(
    previousSelection === "postgres-fts-focused" || previousSelection === "",
    "A different profile must not have been substituted",
  );
  if (previousSelection === "postgres-fts-focused")
    await page
      .getByRole("button", { name: "Refresh connection", exact: true })
      .click();
  await executionStatus.filter({ hasText: /LIVE.*Choose profile/ }).waitFor();
  check(
    (await selector().inputValue()) === "",
    "A retired profile must clear selection without substituting another profile",
  );
  await page
    .getByRole("alert")
    .filter({ hasText: "PROFILE_NOT_AVAILABLE" })
    .waitFor();
  await page.getByRole("button", { name: "Pipelines", exact: true }).click();
  await page
    .getByRole("button", {
      name: /^Keyword search Search the persisted corpus/,
    })
    .click();
  check(
    await page.getByRole("button", { name: "Run", exact: true }).isDisabled(),
    "Retirement must disable Live Run",
  );
  check(
    (await page.locator(".retrieval-result").count()) === 0,
    "The old submitted context must not remain visible after retirement",
  );
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await selector().selectOption("postgres-fts-baseline");
  await executionStatus.filter({ hasText: /LIVE.*Ready/ }).waitFor();
  check(
    (await selector().inputValue()) === "postgres-fts-baseline",
    "An explicit baseline selection must recover execution readiness",
  );
  await page.screenshot({
    path: "output/playwright/profile-selector-recovered.png",
    fullPage: true,
  });
  return {
    result: "PASS",
    phase: "actual-retirement",
    no_automatic_substitution: true,
    prior_results_hidden: true,
    explicit_recovery: "postgres-fts-baseline",
  };
}
