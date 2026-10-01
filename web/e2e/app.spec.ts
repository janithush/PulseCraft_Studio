import { expect, test, type Page } from "@playwright/test";
import { promises as fs } from "fs";
import path from "path";

// ---------------------------------------------------------------------------
// PulseCraft Studio — Phase 5 E2E (Node Playwright, live servers).
//
// Servers: FastAPI :8000 (PULSECRAFT_SKIP_PREFLIGHT=1) + Next.js :3000.
// The orchestrator / feature-toggle tests PATCH the real backend files
// (config/models.json, config/features.json), so the suite backs them up
// in beforeAll and restores them in afterAll — the repo tree stays clean.
// Campaign/gallery tests stub the *job runner* at the network layer
// (POST /api/campaigns, GET /api/jobs/*) but render the REAL gallery cards
// and serve REAL artifact bytes from output/e2e/ through the live FastAPI
// artifact endpoint. This box has no media binaries/keys, so a genuine
// end-to-end render is impossible here; the suite asserts the full UI path
// Prompt -> polling -> gallery display instead.
// ---------------------------------------------------------------------------

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const MODELS_PATH = path.join(REPO_ROOT, "config", "models.json");
const FEATURES_PATH = path.join(REPO_ROOT, "config", "features.json");
const FIXTURE_DIR = path.join(REPO_ROOT, "output", "e2e");

// 1x1 transparent PNG (base64) — served verbatim by /api/artifacts.
const PNG_BYTES = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);
// Minimal ftyp box so the URL resolves as video/mp4 (no real frames needed).
const MP4_BYTES = Buffer.from([
  0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d, 0x00,
  0x00, 0x00, 0x00, 0x69, 0x73, 0x6f, 0x6d, 0x69, 0x73, 0x6f, 0x32,
]);

async function backupConfigs() {
  await fs.mkdir(path.join(REPO_ROOT, "output"), { recursive: true });
  await fs.copyFile(MODELS_PATH, MODELS_PATH + ".e2e-bak");
  await fs.copyFile(FEATURES_PATH, FEATURES_PATH + ".e2e-bak");
}

async function restoreConfigs() {
  await fs.copyFile(MODELS_PATH + ".e2e-bak", MODELS_PATH).catch(() => undefined);
  await fs.copyFile(FEATURES_PATH + ".e2e-bak", FEATURES_PATH).catch(() => undefined);
  await fs.rm(MODELS_PATH + ".e2e-bak", { force: true }).catch(() => undefined);
  await fs.rm(FEATURES_PATH + ".e2e-bak", FEATURES_PATH).catch(() => undefined);
  await fs.rm(FIXTURE_DIR, { recursive: true, force: true }).catch(() => undefined);
}

async function writeArtifactFixtures() {
  await fs.mkdir(FIXTURE_DIR, { recursive: true });
  await fs.writeFile(path.join(FIXTURE_DIR, "square.png"), PNG_BYTES);
  await fs.writeFile(path.join(FIXTURE_DIR, "reel-1080x1920.mp4"), MP4_BYTES);
}

/** Stub a campaign job: queued once, then done with real fixture URLs. */
async function stubCampaignJob(page: Page, jobId = "e2e-job-1") {
  let polls = 0;
  await page.route("**/api/campaigns", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: { job_id: jobId } });
    } else {
      await route.continue();
    }
  });
  await page.route(`**/api/jobs/${jobId}`, async (route) => {
    polls += 1;
    if (polls === 1) {
      await route.fulfill({ json: { job_id: jobId, status: "queued", result: null, error: null } });
    } else {
      await route.fulfill({
        json: {
          job_id: jobId,
          status: "done",
          error: null,
          result: {
            artifact_urls: {
              png_square: "/api/artifacts/e2e/square.png",
              "reel-1080x1920": "/api/artifacts/e2e/reel-1080x1920.mp4",
            },
          },
        },
      });
    }
  });
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await backupConfigs();
  await writeArtifactFixtures();
});

test.afterAll(async () => {
  await restoreConfigs();
});

// ------------------------------------------- 1. Brand Selector gating
test("brand selector: generate disabled with tooltip when no brand selected", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("brand-selector")).toBeVisible();
  await expect(page.getByTestId("brand-active")).toContainText("(No Brand Selected)");
  await expect(page.getByTestId("campaign-brand")).toContainText("(No Brand Selected)");

  await page.getByTestId("campaign-prompt").fill("some prompt");
  const generate = page.getByTestId("generate-btn");
  await expect(generate).toBeDisabled();
  await expect(generate).toHaveAttribute("title", "Please select or type a Brand");

  // Combo input accepts a new slug (CEL) locally; dropdown lists existing.
  await page.getByTestId("brand-input").fill("CEL");
  await page.getByTestId("brand-apply-btn").click();
  await expect(page.getByTestId("brand-active")).toContainText("cel");
  await expect(generate).toBeEnabled();
});

test("new campaign reset clears prompt but preserves brand", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("brand-input").fill("acme");
  await page.getByTestId("brand-apply-btn").click();
  await page.getByTestId("campaign-prompt").fill("my first notes");
  await page.getByTestId("new-campaign-btn").click();
  await expect(page.getByTestId("campaign-prompt")).toHaveValue("");
  await expect(page.getByTestId("brand-active")).toContainText("acme");
});

// ------------------------------------------- 2. Orchestrators add/remove
test("orchestrators: custom model add, X removes from that chain only", async ({
  page,
}) => {
  await page.goto("/");
  const panelA = page.getByTestId("orchestrator-a");
  const panelB = page.getByTestId("orchestrator-b");
  await expect(panelA).toBeVisible();
  await expect(panelB).toBeVisible();

  const customId = "e2e/custom-model:free";
  await panelA.getByTestId("orchestrator-a-new-model").fill(customId);
  await panelA.getByTestId("orchestrator-a-add-btn").click();
  await expect(panelA.getByTestId("orchestrator-a-task-promptExpansion")).toContainText(customId);

  // Panel B (JSON conversion) chain untouched by the add.
  const chainBefore = await panelB
    .getByTestId("orchestrator-b-task-jsonBlueprintConversion")
    .innerText();
  expect(chainBefore).not.toContain(customId);

  // X removes from that chain only.
  await panelA.getByTestId(`orchestrator-a-remove-${customId}`).first().click();
  await expect(panelA.getByTestId("orchestrator-a-task-promptExpansion")).not.toContainText(
    customId,
  );
});

// ------------------------------------------- 3. Template Library append
test("template library: Use Template appends on a new line", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("template-library-btn").click();
  const drawer = page.getByTestId("template-drawer");
  await expect(drawer).toBeVisible();
  // Backend templates mapped to id/title/category cards (no schema change).
  await expect(page.getByTestId("template-card-bold-hook-split")).toContainText("post");
  await page.getByTestId("campaign-prompt").fill("notes");
  await page.getByTestId("use-template-bold-hook-split").click();
  await expect(drawer).not.toBeVisible();
  const value = await page.getByTestId("campaign-prompt").inputValue();
  expect(value.startsWith("notes\n")).toBe(true);
  expect(value).toContain("Bold Hook Split");
});

// ------------------------------------------- 4. Style preset toggle
test("style presets: second click deselects and submits preset ''", async ({ page }) => {
  let capturedBody: Record<string, unknown> | null = null;
  await page.route("**/api/campaigns", async (route) => {
    if (route.request().method() === "POST") {
      capturedBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { job_id: "e2e-preset-job" } });
    } else {
      await route.continue();
    }
  });
  await page.route("**/api/jobs/e2e-preset-job", async (route) => {
    await route.fulfill({
      json: { job_id: "e2e-preset-job", status: "done", error: null, result: { artifact_urls: {} } },
    });
  });

  await page.goto("/");
  const preset = page.getByTestId("preset-alex-hormozi");
  await expect(preset).toHaveAttribute("data-selected", "true");
  await preset.click(); // second click deselects
  await expect(preset).toHaveAttribute("data-selected", "false");
  await preset.click(); // re-selects
  await expect(preset).toHaveAttribute("data-selected", "true");
  await preset.click(); // deselect again for submit
  // Platforms stay single-select, default ALL.
  await page.getByTestId("platform-ig").click();

  await page.getByTestId("brand-input").fill("acme");
  await page.getByTestId("brand-apply-btn").click();
  await page.getByTestId("campaign-prompt").fill("preset toggle probe");
  await page.getByTestId("generate-btn").click();
  await expect(page.getByTestId("gallery")).toBeVisible({ timeout: 30000 });
  expect(capturedBody).not.toBeNull();
  expect(capturedBody?.preset).toBe("");
  expect(capturedBody?.platform).toBe("ig");
});

// ------------------------------------------- 5. Feature toggles regrouped
test("feature toggles: three regrouped sections render with switches", async ({ page }) => {
  await page.goto("/");
  for (const title of ["Processing Engines", "Graphics APIs", "Audio Engines"]) {
    await expect(page.getByText(title, { exact: true })).toBeVisible();
  }
  const switches = page.getByRole("switch");
  expect(await switches.count()).toBeGreaterThanOrEqual(3);
  const first = switches.first();
  const before = await first.getAttribute("aria-checked");
  await first.click();
  await expect(first).not.toHaveAttribute("aria-checked", before ?? "");
});

// ------------------------------------------- 6. Status lights three-state
test("status lights: yellow checking settles into a valid three-state badge", async ({
  page,
}) => {
  let first = true;
  await page.route("**/api/models", async (route) => {
    if (route.request().method() === "GET" && first) {
      first = false;
      await new Promise((r) => setTimeout(r, 1200));
    }
    await route.continue();
  });
  await page.goto("/");
  await expect(page.getByText("🟡 Checking").first()).toBeVisible({ timeout: 15000 });
  const panelA = page.getByTestId("orchestrator-a");
  await expect(panelA.getByTestId("orchestrator-a-task-promptExpansion")).toBeVisible({
    timeout: 20000,
  });
  const statuses = await page
    .locator('[data-testid^="orchestrator-"][data-testid*="-status-"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-status")));
  expect(statuses.length).toBeGreaterThan(0);
  for (const s of statuses) {
    expect(["checking", "connected", "failed", "unknown"]).toContain(s);
  }
});

// ------------------------------------------- 7. Playground inject+fallback
test("playground: badges non-clickable, inject appends, fallback alert on failure", async ({
  page,
}) => {
  await page.goto("/");
  const playground = page.getByTestId("playground");
  for (const badge of ["Hooks/Headlines", "Viral Captions", "SEO Hashtags", "Visual/Reel Prompts"]) {
    const el = playground.getByTestId(`playground-badge-${badge}`);
    await expect(el).toBeVisible();
    expect(await el.evaluate((n) => n.tagName)).toBe("SPAN");
  }
  await page.getByTestId("brand-input").fill("acme");
  await page.getByTestId("brand-apply-btn").click();
  await page.getByTestId("campaign-prompt").fill("existing notes");
  await playground.getByTestId("playground-inject").click();
  const value = await page.getByTestId("campaign-prompt").inputValue();
  expect(value.startsWith("existing notes\n")).toBe(true);

  await page.route("**/api/render", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 500, json: { detail: "boom" } });
    } else {
      await route.continue();
    }
  });
  await playground.getByTestId("playground-render").click();
  await expect(playground.getByTestId("playground-fallback")).toContainText("⚠️");
});

// ------------------------------------------- 8. Gallery clean cards+dismiss
test("end-to-end: prompt -> polling -> gallery cards with clean badges", async ({ page }) => {
  await stubCampaignJob(page);
  await page.goto("/");
  await page.getByTestId("brand-input").fill("acme");
  await page.getByTestId("brand-apply-btn").click();
  await page.getByTestId("campaign-prompt").fill("3 morning habits");
  await page.getByTestId("generate-btn").click();

  const gallery = page.getByTestId("gallery");
  await expect(page.getByTestId("gallery-card-0")).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId("gallery-type-0")).toContainText("Post [PNG]");
  await expect(page.getByTestId("gallery-dims-0")).toContainText("1080");
  await expect(page.getByTestId("gallery-type-1")).toContainText("Reel [MP4]");
  await expect(page.getByTestId("gallery-dims-1")).toContainText("9:16");
  const galleryText = (await gallery.innerText()) ?? "";
  expect(galleryText).not.toMatch(/playground-[0-9a-f]{6,}/);
  expect(galleryText).not.toMatch(/e2e-job-1/);

  await page.getByTestId("gallery-close-0").click();
  await expect(page.getByTestId("gallery-card-0")).toContainText("Reel [MP4]");
  await expect(page.getByTestId("gallery-card-1")).toHaveCount(0);
});
