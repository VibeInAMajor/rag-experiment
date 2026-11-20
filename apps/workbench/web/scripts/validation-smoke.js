async function validationSmoke(page) {
  page.setDefaultTimeout(5000);
  await page.reload();
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await page.getByText("Unsupported nodes", { exact: true }).waitFor();
  await page.locator(".node-title").filter({ hasText: "BM25 search" }).click();
  await page
    .getByRole("spinbutton", { name: "Candidates", exact: true })
    .fill("12");
  await page.getByText("Not checked", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Close inspector" }).click();
  await page.route("**/api/pipelines/validate", (route) => route.abort());
  try {
    await page.getByRole("button", { name: "Validate", exact: true }).click();
    await page
      .getByText("Validator unavailable · retry", { exact: true })
      .waitFor();
  } finally {
    await page.unroute("**/api/pipelines/validate");
  }
  const node = (kind, id, parameters) => ({
    id,
    type: "workbench",
    position: { x: 0, y: 0 },
    data: { kind, label: id, parameters },
  });
  const requestId = "browser-contract";
  const response = await page.request.post(
    new URL("/api/pipelines/validate", page.url()).href,
    {
      data: {
        schemaVersion: 1,
        mode: "complete",
        requestId,
        graph: {
          nodes: [
            node("bm25", "lexical", { collection: "Sample", topK: 10 }),
            node("joiner", "fusion", { topK: 5 }),
          ],
          edges: [
            {
              id: "link",
              source: "lexical",
              sourceHandle: "documents",
              target: "fusion",
              targetHandle: "documents",
              type: "smoothstep",
            },
          ],
        },
        inputs: { lexical: { query: "A validation input; never executed" } },
      },
    },
  );
  const value = await response.json();
  if (
    !response.ok() ||
    value.status !== "valid" ||
    value.validator !== "haystack" ||
    value.requestId !== requestId ||
    value.mode !== "complete" ||
    value.capabilityVersion !== "workbench-components-v1"
  )
    throw new Error("Real supported pipeline contract failed");
  return "PASS: actual Haystack valid/unsupported, edit invalidation, unavailable and matching browser/server contract";
}
