import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const { AGENTS_SMOKE_URL, AGENTS_SMOKE_JOURNAL_DIR, AGENTS_SMOKE_PLAYWRIGHT } =
  process.env;
const baseUrl = new URL(AGENTS_SMOKE_URL);
assert.equal(baseUrl.hostname, "127.0.0.1");
const directory = AGENTS_SMOKE_JOURNAL_DIR;
assert.ok(
  existsSync(join(directory, ".ui005-smoke")),
  "Use an isolated smoke journal",
);
const { chromium } = await import(pathToFileURL(AGENTS_SMOKE_PLAYWRIGHT).href);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
page.setDefaultTimeout(8000);
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const requests = [];
page.on("request", (request) =>
  requests.push({ url: request.url(), method: request.method() }),
);
const catalogPath = join(directory, "catalog.json");
const realCatalog = readFileSync(catalogPath, "utf8");
const selectionPath = join(directory, "selection.json");
const originalSelection = existsSync(selectionPath)
  ? readFileSync(selectionPath)
  : null;
const catalog = JSON.parse(realCatalog.replace(/^\uFEFF/, ""));
const agent = catalog.agents.find(
  (entry) => entry.agent_id === "semantic-judge",
);
const primary = agent.profiles.find(
  (profile) => profile.profile_id === agent.default_profile_id,
);
const alternate = agent.profiles.find(
  (profile) =>
    profile.model !== primary.model &&
    profile.reasoning_effort === primary.reasoning_effort,
);
const runId = randomUUID().replaceAll("-", "");
const runs = join(directory, "runs");
mkdirSync(runs, { recursive: true });
const journal = join(runs, `${runId}.jsonl`);
let sequence = 0;

function emit(kind, fields = {}) {
  sequence += 1;
  const timestamp = new Date().toISOString();
  appendFileSync(
    journal,
    JSON.stringify({
      schema_version: 1,
      scope: "local-operator",
      run_id: runId,
      sequence,
      timestamp,
      kind,
      ...fields,
    }) + "\n",
  );
  return { sequence, timestamp };
}

async function visible(text) {
  await page.getByText(text, { exact: true }).first().waitFor();
}

try {
  await page.goto(new URL("?page=editor&mode=preview", baseUrl).href);
  assert.deepEqual(
    (
      await page
        .getByRole("navigation", { name: "Main navigation" })
        .getByRole("button")
        .allTextContents()
    ).slice(-3),
    ["Configuration", "Agents", "Settings"],
  );
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await visible("Semantic Judge");
  assert.match(page.url(), /page=agents/);
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption(alternate.model);
  assert.equal(
    await page.getByRole("button", { name: "Save selection" }).isDisabled(),
    true,
  );
  await visible(
    "This reasoning level is supported by the model; agent qualification is pending.",
  );
  await page.getByText("Model details", { exact: true }).click();
  await visible("32,000");
  await visible("$2.50");

  emit("run_queued", {
    stage: "queued",
    run: {
      agent_id: agent.agent_id,
      mode: "batch",
      origin: "evaluation",
      profile_id: primary.profile_id,
      model: primary.model,
      provider: primary.provider,
      runtime_revision: agent.runtime_revision,
      prompt_revision: null,
      schema_revision: null,
      cache_mode: primary.cache_mode,
      tariff: primary.tariff,
      planned_cases: 31,
      budget_usd: "12.308736",
    },
  });
  emit("run_started", { stage: "admission" });
  const firstCall = {
    call_id: "synthetic-call-1",
    case_id: "synthetic-case-1",
    mode: "judge_evidence",
  };
  emit("call_pending", {
    stage: "admission",
    call: { ...firstCall, reserve_usd: "0.397056" },
  });
  await page
    .getByRole("table", { name: "Agent run history" })
    .getByRole("button")
    .first()
    .click();
  await visible("Waiting for the model. Usage will appear when it responds.");
  const latencies = [];
  for (let index = 1; index <= 30; index += 1) {
    const call = {
      call_id: `synthetic-call-${index}`,
      case_id: `synthetic-case-${index}`,
      mode: "judge_evidence",
    };
    if (index > 1)
      emit("call_pending", {
        stage: "admission",
        call: { ...call, reserve_usd: "0.397056" },
      });
    const event = emit("call_completed", {
      status: "completed",
      call: {
        ...call,
        actual_model: primary.model,
        requests: 1,
        elapsed_ms: 45,
        usage: {
          input_tokens: 100,
          cached_read_tokens: 20,
          output_tokens: 10,
          reasoning_tokens: 3,
        },
        estimated_cost_usd: "0.0003322",
      },
    });
    emit("case_completed", { case_id: call.case_id, status: "completed" });
    const latency = await page.evaluate(
      ({ sequence, timestamp }) =>
        new Promise((resolve, reject) => {
          const match = () =>
            document.querySelector(`[data-event-sequence='${sequence}']`);
          if (match()) return resolve(Date.now() - Date.parse(timestamp));
          const observer = new MutationObserver(() => {
            if (!match()) return;
            observer.disconnect();
            clearTimeout(timer);
            resolve(Date.now() - Date.parse(timestamp));
          });
          observer.observe(document.body, { childList: true, subtree: true });
          const timer = setTimeout(() => {
            observer.disconnect();
            reject(new Error("Journal event never rendered"));
          }, 5500);
        }),
      event,
    );
    latencies.push(latency);
  }
  emit("checkpoint_reused", {
    reason: "CHECKPOINT_REUSED",
    case_id: "synthetic-reuse",
  });
  emit("run_finished", { status: "completed", stage: "finalizing" });
  await visible("31 / 31");
  await visible("$0.0099660");
  await visible("3,000");
  await visible("1 saved result reused");
  if (process.env.AGENTS_SMOKE_SCREENSHOT) {
    await page.screenshot({ path: process.env.AGENTS_SMOKE_SCREENSHOT });
  }
  assert.equal(
    await page
      .getByRole("region", { name: "Run details" })
      .getByText("GPT-6.1 Sol", { exact: true })
      .first()
      .textContent(),
    "GPT-6.1 Sol",
  );
  assert.equal(
    await page
      .getByText("Waiting for the model. Usage will appear when it responds.", {
        exact: true,
      })
      .count(),
    0,
  );
  await page
    .getByRole("combobox", { name: "Run model" })
    .selectOption(alternate.model);
  await visible("No matching runs.");
  await page.reload();
  await visible("1 saved result reused");
  await page.setViewportSize({ width: 1024, height: 800 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.goto(new URL("?page=agents&mode=live", baseUrl).href);
  await visible("1 saved result reused");

  const qualified = {
    state: "qualified",
    revision: "isolated-smoke-qualification",
    verified_at: primary.qualification.verified_at,
    reason: "joint_pass",
  };
  primary.qualification = qualified;
  alternate.qualification = qualified;
  writeFileSync(catalogPath, JSON.stringify(catalog));
  await page.getByRole("button", { name: "Refresh agent operations" }).click();
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption(alternate.model);
  await page.getByRole("button", { name: "Save selection" }).click();
  await visible("Saved for the next eligible run.");
  await page.reload();
  await page.waitForFunction(
    () => document.querySelector('select[aria-label="Run model"]') !== null,
  );
  assert.equal(
    await page
      .getByRole("combobox", { name: "Model", exact: true })
      .inputValue(),
    alternate.model,
  );
  await page
    .getByRole("table", { name: "Agent run history" })
    .getByRole("button")
    .first()
    .click();
  assert.equal(
    await page
      .getByRole("region", { name: "Run details" })
      .getByText("GPT-6.1 Sol", { exact: true })
      .first()
      .textContent(),
    "GPT-6.1 Sol",
  );

  await page.route("**/api/v1/agents**", (route) => route.abort());
  await page.getByRole("button", { name: "Refresh agent operations" }).click();
  await visible("Disconnected · showing last update");
  await page.unroute("**/api/v1/agents**");
  await page.getByRole("button", { name: "Refresh agent operations" }).click();
  await visible("Connected");
  assert.deepEqual(errors, []);
  assert.equal(
    requests.filter((request) => request.method === "PUT").length,
    1,
  );
  assert.ok(
    requests.every((request) => new URL(request.url).hostname === "127.0.0.1"),
  );
  const sorted = latencies.toSorted((a, b) => a - b);
  const p95 = sorted[Math.ceil(sorted.length * 0.95) - 1];
  assert.ok(
    p95 <= 2000,
    `Local event-to-render p95 ${p95} ms exceeds 2,000 ms`,
  );
  console.log(
    JSON.stringify({
      result: "PASS",
      p95_ms: p95,
      samples_ms: latencies,
      physical_requests: 30,
      tokens: 3300,
      estimated_cost_usd: "0.0099660",
      provider_egress: 0,
    }),
  );
} finally {
  await browser.close();
  writeFileSync(catalogPath, realCatalog);
  if (originalSelection) writeFileSync(selectionPath, originalSelection);
  else rmSync(selectionPath, { force: true });
  rmSync(journal, { force: true });
}
