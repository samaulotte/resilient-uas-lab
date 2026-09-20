import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The mandatory end-to-end journey: open Mission Control, start the demo scenario,
 * observe live degradation, wait for completion, read the report, compare two runs.
 * Runs are executed at 10x so the whole journey takes about a minute on the mock adapter.
 */

const TERMINAL = ["COMPLETED", "FAILED", "CANCELLED"];

interface RunRecord {
  id: string;
  state: string;
  result: string | null;
  resilience_score: number | null;
  report_available?: boolean;
}

async function waitForTerminal(request: APIRequestContext, runId: string): Promise<RunRecord> {
  const deadline = Date.now() + 150_000;
  while (Date.now() < deadline) {
    const response = await request.get(`/api/v1/runs/${runId}`);
    expect(response.ok()).toBeTruthy();
    const run = (await response.json()) as RunRecord;
    if (TERMINAL.includes(run.state)) return run;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`run ${runId} did not finish in time`);
}

async function createRun(
  request: APIRequestContext,
  scenario: string,
  speed: number,
): Promise<RunRecord> {
  const response = await request.post("/api/v1/runs", {
    data: { scenario_name: scenario, speed, label: "e2e" },
  });
  expect(response.status()).toBe(202);
  return (await response.json()) as RunRecord;
}

function runIdFromUrl(page: Page): string {
  const url = new URL(page.url());
  const runId = url.searchParams.get("run");
  expect(runId, "mission control should navigate to the new run").toBeTruthy();
  return runId as string;
}

test.describe("Resilient UAS Lab demo journey", () => {
  test("application loads and reports platform status", async ({ page, request }) => {
    const ready = await request.get("/readyz");
    expect(ready.ok()).toBeTruthy();
    await page.goto("/");
    await expect(page).toHaveURL(/\/mission-control/);
    await expect(page.getByRole("link", { name: "Home" })).toContainText("RESILIENT UAS LAB");
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await expect(page.getByTestId("platform-status")).toContainText(
      /PLATFORM NOMINAL|NO RUNNER ONLINE/,
    );
    await expect(page.getByRole("button", { name: /run demo scenario/i }).first()).toBeVisible();
  });

  test("demo scenario runs live to completion with a report", async ({ page, request }) => {
    await page.goto("/mission-control");
    await page
      .getByRole("radio", { name: "10x" })
      .or(page.getByRole("button", { name: "10x" }))
      .first()
      .click();
    // The toolbar and the empty state both offer the demo; either one queues the same run.
    await page
      .getByRole("button", { name: /run demo scenario/i })
      .first()
      .click();
    await expect(page).toHaveURL(/run=/, { timeout: 30_000 });
    const runId = runIdFromUrl(page);

    // Live updates: the connection indicator and the simulation clock.
    await expect(page.getByText(/^LIVE$/)).toBeVisible({ timeout: 60_000 });
    const clock = page.getByTestId("simulation-time");
    await expect(clock).not.toHaveText("T+00:00", { timeout: 60_000 });
    await expect(page.getByText("Mock simulator")).toBeVisible();

    // Degradation appears: GNSS becomes unavailable at T+30 s.
    await expect(page.getByText("GNSS LOST")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByTestId("system-panel")).toContainText("UNAVAILABLE");
    await expect(page.getByTestId("state-timeline")).toBeVisible();

    // Completion and analysis.
    const run = await waitForTerminal(request, runId);
    expect(run.state).toBe("COMPLETED");
    expect(run.result).toBe("passed");
    await expect(page.getByTestId("run-state")).toContainText("COMPLETED", { timeout: 60_000 });
    await expect(page.getByTestId("resilience-score")).toContainText(/\d+\.\d/, {
      timeout: 60_000,
    });
    await expect(page.getByText("CONTAINED").first()).toBeVisible();

    // Report artifacts are available through the API and the report link works.
    const report = await request.get(`/api/v1/runs/${runId}/report`);
    expect(report.ok()).toBeTruthy();
    const body = (await report.json()) as { schema_version: string; result: string };
    expect(body.schema_version).toBe("1.0");
    expect(body.result).toBe("passed");
    const html = await request.get(`/api/v1/runs/${runId}/report.html`);
    expect(html.ok()).toBeTruthy();
    expect(await html.text()).toContain("Resilience Report");

    // Run detail page shows the analyzed outcome.
    await page.goto(`/runs/${runId}`);
    await expect(page.getByText("PASSED").first()).toBeVisible();
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
  });

  test("compare page opens two completed runs", async ({ page, request }) => {
    const baseline = await createRun(request, "mission-compute-restart", 25);
    const candidate = await createRun(request, "mission-compute-restart", 25);
    const first = await waitForTerminal(request, baseline.id);
    const second = await waitForTerminal(request, candidate.id);
    expect(first.state).toBe("COMPLETED");
    expect(second.state).toBe("COMPLETED");

    await page.goto(`/compare?baseline=${baseline.id}&candidate=${candidate.id}`);
    await expect(page.getByTestId("compare-verdict")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("compare-verdict")).toContainText(
      /UNCHANGED|IMPROVEMENT|REGRESSION|MIXED/,
    );
    await expect(page.getByText("Mean time to recovery")).toBeVisible();
    await expect(page.getByText("Resilience score")).toBeVisible();
  });

  test("scenario library and studio validate documents", async ({ page }) => {
    await page.goto("/scenarios");
    await expect(page.getByText("compound-degradation")).toBeVisible();
    await page.goto("/scenarios/compound-degradation");
    await expect(page.getByText("YAML DOCUMENT", { exact: false })).toBeVisible();
    await expect(page.getByText(/valid against the scenario schema/i)).toBeVisible({
      timeout: 30_000,
    });
  });

  test("runs, reports and system pages render", async ({ page }) => {
    await page.goto("/runs");
    await expect(page.getByRole("table")).toBeVisible();
    await page.goto("/reports");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.goto("/system");
    await expect(page.getByText("TOPOLOGY", { exact: false })).toBeVisible();
    await expect(page.getByText("Mock simulator")).toBeVisible();
  });
});
