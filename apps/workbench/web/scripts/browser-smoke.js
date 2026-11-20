async function smoke(page) {
  page.setDefaultTimeout(5000);
  const check = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  await page.reload();
  await page.getByRole("button", { name: "Run", exact: true }).waitFor();
  check(
    (await page.locator(".react-flow__node").count()) === 6,
    "Expected six template nodes",
  );

  await page.locator(".node-title").filter({ hasText: "BM25 search" }).click();
  await page
    .getByRole("spinbutton", { name: "Candidates", exact: true })
    .fill("12");
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  check(
    (await page
      .getByRole("spinbutton", { name: "Candidates", exact: true })
      .inputValue()) === "20",
    "Undo should restore the parameter",
  );
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  check(
    (await page
      .getByRole("spinbutton", { name: "Candidates", exact: true })
      .inputValue()) === "12",
    "Redo should restore the edit",
  );
  await page.getByRole("button", { name: "Close inspector" }).click();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const download = await downloadPromise;
  await page
    .getByLabel("Import pipeline JSON")
    .setInputFiles(await download.path());
  await page
    .getByRole("status")
    .filter({ hasText: "Pipeline imported." })
    .waitFor();
  check(
    (await page.locator(".react-flow__node").count()) === 6,
    "Import should restore nodes",
  );
  await page.locator(".node-title").filter({ hasText: "BM25 search" }).click();
  check(
    (await page
      .getByRole("spinbutton", { name: "Candidates", exact: true })
      .inputValue()) === "12",
    "Import should restore parameters",
  );
  await page.getByRole("button", { name: "Close inspector" }).click();

  const openComponents = page.getByRole("button", {
    name: "Open components",
    exact: true,
  });
  if (await openComponents.isVisible()) await openComponents.click();
  await page
    .getByRole("button", { name: "Combine results", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Secondary fusion");
  await page
    .getByRole("combobox", {
      name: "Connect Secondary fusion Ranked documents",
      exact: true,
    })
    .selectOption({ label: "Combine results / Combined matches" });
  await page
    .locator(".node-title")
    .filter({ hasText: /^Combine results$/ })
    .click();
  await page
    .getByRole("combobox", {
      name: "Connect Combine results Ranked documents",
      exact: true,
    })
    .selectOption({ label: "Secondary fusion / Combined matches" });
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page
    .locator(".error-list")
    .filter({ hasText: "Preview only:" })
    .waitFor();
  await page.getByRole("button", { name: "Dismiss notification" }).click();
  await page
    .locator(".node-title")
    .filter({ hasText: /^Secondary fusion$/ })
    .click();
  await page.getByRole("button", { name: "Delete node", exact: true }).click();
  check(
    (await page.locator(".react-flow__node").count()) === 6,
    "Deleting the added branch should preserve the original graph",
  );

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page
    .locator(".results-meta .status")
    .filter({ hasText: "Completed" })
    .waitFor({ timeout: 15000 });
  check(
    (await page.locator(".retrieval-result").count()) === 4,
    "Expected sample retrieval results",
  );
  await page.getByRole("button", { name: "Documents", exact: true }).click();
  await page.getByRole("heading", { name: "Documents", exact: true }).waitFor();
  await page.getByRole("button", { name: /RAG platform architecture/ }).click();
  await page.getByRole("tab", { name: "Chunks", exact: true }).click();
  check(
    (await page.locator(".detail-chunk").count()) > 0,
    "Expected chunk previews",
  );
  await page.getByRole("button", { name: "Runs", exact: true }).click();
  check(
    (await page.locator(".data-table tbody tr").count()) === 1,
    "Run should survive navigation",
  );

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("error");
  await page.getByRole("button", { name: "Pipelines", exact: true }).click();
  await page
    .getByRole("button", { name: /Hybrid document search/ })
    .first()
    .click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page
    .locator(".results-meta .status")
    .filter({ hasText: "Failed" })
    .waitFor({ timeout: 15000 });
  await page.getByRole("tab", { name: /^Errors/ }).click();
  check(
    (await page.locator(".error-list").innerText()).includes("Simulated"),
    "Expected a visible preview error",
  );
  return "PASS: edit, undo/redo, JSON roundtrip, branch creation, preview-only cycle restriction, preview success, document chunks, run history, preview failure";
}
