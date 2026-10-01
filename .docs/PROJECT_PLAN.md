# PulseCraft Studio — Project Plan & Epics Breakdown

**Project:** PulseCraft Studio — Social Media Content Automation Engine
**Version:** 0.1.0 (Initial Draft)
**Status:** Draft — `docs/project-plan`
**Owners:** Senior Technical Program Manager / Lead Architect
**Date:** 2026-09-30
**Methodology:** Spec-Driven Development (SDD) + Test-Driven Development (TDD)
**Parent Specs:** `.docs/PRD.md` v0.1.0 (FR-1…FR-5, NFR-1…NFR-4, R1…R8) · `.docs/ARCHITECTURE.md` v0.1.0 (§1…§6)

---

## Table of Contents

- [1. Project Milestones & Roadmap](#1-project-milestones--roadmap)
- [2. Epics & Feature Breakdown](#2-epics--feature-breakdown)
- [3. Granular User Stories with Acceptance Criteria](#3-granular-user-stories-with-acceptance-criteria)
- [4. Feature-by-Feature TDD Execution Strategy](#4-feature-by-feature-tdd-execution-strategy)
- [5. Branching, PR & Code Review Rules](#5-branching-pr--code-review-rules)
- [Appendix A: Milestone → Epic → Spec Traceability](#appendix-a-milestone--epic--spec-traceability)
- [Appendix B: Glossary](#appendix-b-glossary)

---

## 1. Project Milestones & Roadmap

Milestones are **acceptance-gated**: a milestone is done only when all mapped epics' user stories pass CI + review + demo on reference hardware (Intel i5 11th Gen + 20GB RAM, background tabs open). Ordering is dependency-driven; M0 unblocks all.

### M0: Project Foundations & CI/CD Pipeline Setup

**Objective:** Reproducible repo that fails loudly on bad code before any feature lands.
**Maps to:** Epic 1. **Gates PRD App. C M0 (part 1).**

| # | Deliverable | Done when |
|---|-------------|-----------|
| M0.1 | Monorepo skeleton per `ARCHITECTURE.md` §2 (`config/`, `schemas/`, `brands/_template/`, `prompts/`, `src/pulsecraft/`, `templates/posts+reels/`, `remotion/`, `tests/`, `assets/fallback/`) | `tree` matches spec; `.cache/` + `out/` gitignored |
| M0.2 | Python 3.12 + Node 20 toolchains (`pyproject.toml`, `remotion/package.json`) | Clean `pip install -e .[dev]` + `npm ci --prefix remotion` on Windows 10/11 and Linux CI |
| M0.3 | Quality gates: Ruff (check+format), ESLint `--max-warnings=0`, Prettier `--check`, gitleaks pre-commit | `pre-commit run --all-files` green; `.env` never committed |
| M0.4 | GitHub Actions `ci.yml` (python / video / render-smoke jobs) + protected `main` + squash merge | Red CI blocks merge; green on scaffold PR |
| M0.5 | `.env.example` (`OPENROUTER_API_KEY`, `PEXELS_API_KEY`) + structured-log + `run-manifest.json` stubs | Keys redacted in logs; manifest schema stub validated |

**Exit demo:** fresh clone → install → `pre-commit run --all-files` + `pytest -q` + `npx vitest run` all green on empty suites.

### M1: Dynamic OpenRouter LLM Orchestration & Model Health Check Registry

**Objective:** Zero-hardcoded-model LLM layer with user-extensible registry and dual fallback chains.
**Maps to:** Epic 2 · PRD FR-1, R1 · ARCH §4.1, §3.

| # | Deliverable | Done when |
|---|-------------|-----------|
| M1.1 | `config/models.json` (`models/v1`) + `registry.py` (tasks `scriptHeadline` + `blueprintTranslate`) | User-added `vendor/custom-model:free` persists without code change |
| M1.2 | `check-models` health probes → `Connected` / `Failed` + latency + `lastChecked` | All registry ids report status; 401/timeout surfaces actionable reason |
| M1.3 | `client.py` (JSON-mode, low-temp, timeouts) + `repair.py` (fence-strip, trailing-comma fix) + `fallback.py` (retry once → next model → cache → fail with resume hint) | Stubbed 429→200 auto-switches with zero user intervention |
| M1.4 | `prompts/*.md` versioning + `blueprint.schema.json` enforcement; golden fixture blueprints checked in | 100% persisted blueprints validate; malformed output never crashes renderer |

**Exit demo:** `models add` custom id → `check-models` Connected → `generate` with primary 429 stub succeeds on secondary; invalid JSON repaired or falls back with logged reason.

### M2: Static Post Renderer (HTML/CSS Templates & Playwright TDD)

**Objective:** Pixel-exact FB/IG PNGs from decoupled templates.
**Maps to:** Epic 3 · PRD FR-2, FR-5 (static), R4, R6 · ARCH §4.2, §4.3, §3.2.

| # | Deliverable | Done when |
|---|-------------|-----------|
| M2.1 | `/templates/posts/<layout>/` (2+ layouts: `bold-hook-split`, `minimal-type`) with `index.html` + offline-safe `style.css` + `preview.png` + `meta.json` | `templates list` resolves both; missing id errors list available ids |
| M2.2 | Token pipeline (`merge.py` `_base.json` inheritance + `tokens.py` → `tokens.css`) + `validate-brand` | Bad hex/missing font fails with precise errors; base fallback warns, never crashes |
| M2.3 | Playwright renderer (single Chromium, 1080×1080 + 1080×1350, font-ready + `networkidle`, `file://` assets, 1 retry) + PNG header asserts | Both PNGs byte-exact dims (Pillow/sharp); 120-char hook never overflows; golden snapshots approved |
| M2.4 | Brand-swap proof: same blueprint × 2 brands → correctly themed outputs, zero engine diff | Snapshot diff test green |
| M2.5 | 4-layer layout strategy (L1 conditionals auto-hide, L2 loops for bullets/hashtags, L3 pre-built variants, L4 `PROMPT_EXPANSION` HTML fallback) + Visual Template Inspector (`templates inspect` with badge-tag preview + required/optional schema) | `inspect bold-hook-split` shows schema table + preview HTML; unknown layout triggers L4 with layer logged in manifest |

**Exit demo:** `render post --blueprint fixture --brand acme` → 2 exact PNGs + `meta.json` (dims, hashes, ms) in <15s/size warm; `templates inspect bold-hook-split` renders badge-tag preview; `init-brand --slug demo` passes smoke.

### M3: Short-Form Video Reel Engine (Remotion, Kokoro TTS, Faster-Whisper Captions)

**Objective:** 1080×1920 MP4 with synced VO + karaoke captions, no editor.
**Maps to:** Epic 4 · PRD FR-3, FR-4 (TTS/STT), R3, R5 · ARCH §4.4, §4.5, §3.3.

| # | Deliverable | Done when |
|---|-------------|-----------|
| M3.1 | Kokoro TTS wrapper (sentence-aware ≤500-char chunks, brand voice+speed, ≥16kHz concat WAV, `hash(text+voice+speed)` cache) | Airplane-mode re-run succeeds from cache |
| M3.2 | Faster-Whisper INT8 (`base` default, `--whisper-model` override, `--fast-draft`→`tiny`, `--no-whisper` uniform fallback `estimated:true`) → `words.json` + `.srt` | Fixture ≥95% coverage, monotonic, drift <150ms |
| M3.3 | Remotion `ReelComposition` (size-parametric 1080×1920/1350/1080 @30fps, `{script,scenes,audioSrc,words,brandTokens,preset,canvas}`) + caption engine (karaoke, `maxWordsPerLine`, safe-area 220px) + hook/CTA cards + Ken Burns B-roll | 3s fixture smoke renders with audible VO + visible highlight |
| M3.4 | Post-render asserts (resolution, duration ±0.5s of VO, `ffprobe` audio track) + `--fast-draft` mode | 30s Reel in 1–3 min warm on ref hw; missing B-roll falls back to gradient with log |
| M3.5 | Style presets (`alex-hormozi`, `faceless-docu`, `b-roll-centric` + hybrid `presetTweaks`) + `--platform fb\|ig\|all` canvases + SFX/BGM auto-ducking (15% speech / 35% pause) + guardrailed `render reel` CLI | `--preset` switches signature styles; `--platform all` emits 1080² + 1080×1350 + 1080×1920; disabled toggles strip requests with warnings |

**Exit demo:** `render reel` on 30s fixture → per-platform MP4s + probe report; frame sample shows active-word highlight.

### M4: Free Asset Supply Pipeline Integration (Pexels API & Decoupled /templates)

**Objective:** Zero-subscription visuals fully integrated with cache/resume and template decoupling.
**Maps to:** Epic 5 · PRD FR-4 (Pexels), FR-5, R2 · ARCH §4.5, §4.2, §4.7–§4.9.

| # | Deliverable | Done when |
|---|-------------|-----------|
| M4.1 | Multi-source fetcher (Pexels → Pixabay → Openverse order, `PEXELS_API_KEY`/`PIXABAY_API_KEY` via `.env`, Openverse keyless; orientation filter, resize/compress, `.cache/<provider>/<query-hash>/`, `assets/manifest.json` + per-run `ATTRIBUTION.md`) + local overrides (`[Visual: file]` → `input/visuals/`, traversal-guarded) | Manifest records photographer/URL/license for every asset; local tag bypasses network |
| M4.2 | Failure tree (backoff retry → relaxed query → cache reuse → `assets/fallback/` → continue; hard fail only `--strict-assets`) + LRU eviction >5GB + `--reuse-cache`/`--refresh-assets` | Simulated 429/5xx still renders via fallback with warning |
| M4.3 | Template manager GA (`templates add/modify/clear/list/preview` for `posts` + `reels`; offline-safety lint: no remote CDN, bundled fonts) | Add→preview→clear round-trip without engine diff; `templates/reels` theme hot-swappable |
| M4.4 | Asset Caching Engine (`src/pulsecraft/assets/cache.py`): disk-backed hash-indexed cache in `.cache/assets/` for Pexels/Pixabay/Freesound/Openverse bytes; `AssetCache` with hit/miss logging, duplicate-request suppression, `index.json`, `clear()`/`evict_lru()`; CLI `pulsecraft assets clear-cache` | Repeat fetch with same `(provider, query, url)` performs zero HTTP GETs; `clear-cache` empties `.cache/assets/` |
| M4.5 | Local Asset Indexer (`src/pulsecraft/assets/local_mgr.py`): auto-index `input/visuals/` + `input/audio/` with Pillow/wave metadata (dims, duration/sample-rate) + traversal-guarded tag matching; CLI `pulsecraft assets list` shows local + cached remote | Dropped `hero.png`/`bed.mp3` appear in `assets list` with correct kind + metadata; `[Visual: ../escape]` → `None` |
| M4.6 | Unified Template Registry (`src/pulsecraft/templates_mgr/registry.py`): single `list_all_templates()` / `get_template_schema(name)` / `validate_all_templates()` over `templates/posts/` + `templates/reels/` with strict `meta.json` JSON-schema validation; CLI `pulsecraft templates validate` | All 2 post + 4 reel packs validate clean; broken manifest fails with precise error + nonzero exit |

**Exit demo:** airplane-mode re-run green; Pexels-outage simulation green via fallback; new theme added live and rendered without code change; `assets list` shows local + cached rows; `templates validate` passes on all packs.

### M5: End-to-End CLI Integration, Quality Assurance, and Final Polish

**Objective:** One-command prompt→outputs, hardened and documented.
**Maps to:** All Epics · PRD NFR-1…NFR-4, App. C M5 · ARCH §4.10–§4.11, §5, §6, App. A.

| # | Deliverable | Done when |
|---|-------------|-----------|
| M5.1 | `pulsecraft generate campaign --prompt ... --brand X --formats png,reel --preset ... --platform all --seed N --out output` (`src/pulsecraft/pipeline/orchestrator.py` `CampaignPipeline`: M1 LLM expand → M4 asset resolve + cache → M2 static 4-layer render → M3 reel TTS/timestamp/ducking/preset render → `output/<run-id>/` bundle + `run-manifest.json` + timings + `--seed` determinism) | Same seed → byte-comparable blueprints; `output/<run-id>/` contains blueprints + assets.json + PNGs + MP4s + manifests with zero manual steps (mocked renderers in CI) |
| M5.2 | QA hardening: contrast <4.5:1 warnings, SRT sidecar + burned-in captions, actionable errors ("Pexels 429 → fallback; retry --refresh-assets"), temp cleanup | E2E on ref hw meets NFR-2 (static <60s warm E2E; 30s Reel 1–3 min) without freeze/OOM |
| M5.3 | Docs/runbook (`README` quickstart, brand onboarding <30 min guide, `--fast-draft` iteration guide, model-download sizes) + CI green + coverage gates | New hire onboards a brand and ships PNGs+MP4 in <30 min following runbook only |
| M5.4 | Unified CLI GA (`generate campaign`, `models status`, `render post|reel`, `templates list|inspect|validate`, `assets list|clear-cache`) + `tests/unit/test_campaign_pipeline.py` + `tests/integration/test_e2e_campaign.py` (mocked collaborators, offline green) | `pulsecraft --help` lists all five groups; new tests green offline |

**Exit demo (release gate):** live prompt → `output/<run-id>/{blueprints,assets,PNGs,MP4s,meta,manifest,ATTRIBUTION}` + CI badge green + runbook followed verbatim.

### M6: Liquid Glass Web UI + Hardware-Optimized Worker Queue

**Objective:** Glass dashboard over the M5 engine that stays smooth on Intel i5 11th Gen + 20GB RAM.
**Maps to:** All Epics · PRD NFR-1/NFR-2 · ARCH §4.12–§4.14.

| # | Deliverable | Done when |
|---|-------------|-----------|
| M6.1 | FastAPI server (`src/pulsecraft/web/`: `app.py` REST wrapping CLI/pipeline, `queue.py` `BackgroundJobQueue` max-concurrency 1, `memory.py` `gc.collect()` release hook, `thumbs.py` WebP proxy) on port 8000 | `GET /api/health` green; two rapid `POST /api/campaigns` serialize (never parallel); `gc.collect()` asserted after each job in `tests/unit/test_web_api.py` |
| M6.2 | Next.js 14 Liquid Glass UI (`web/`: Tailwind + shadcn/ui + Framer Motion `stiffness 300/damping 30`, `#A3E635` glow, `backdrop-blur-xl bg-slate-900/60 border-white/10`) with `CampaignStudio`, `InteractivePreviewGallery` (lazy WebP), `FeatureTogglePanel` (3 categories), `TemplateInspectorModal` (`[Headline Here]`/`[Hook Here]` badges) | `npm run build` clean; gallery scrolls thumbnails before full assets |
| M6.3 | QA: `tests/unit/test_web_api.py` (health, features get/patch, templates, campaign enqueue + job poll, thumb proxy, concurrency-1 proof, gc hook) + `ruff check` + `pytest` 100% backend pass | New tests green offline with mocked pipeline |

**Exit demo:** `uvicorn` :8000 + `npm run dev` :3000 → prompt in CampaignStudio → job completes → glass gallery shows PNGs/MP4 + toggles flip live.

**Roadmap summary:** `M0 (week 1, unblocks all) → M1 + M2 (parallel after M0) → M3 (needs M1) → M4 (needs M2/M3) → M5 (needs all) → M6 (needs M5)`. M1/M2 can run in parallel; M4 integrates M2+M3 outputs.

---

## 2. Epics & Feature Breakdown

Each epic lists **features** (shippable vertical slices), primary specs, and milestone mapping. Epics are worked milestone-ordered but M1/M2 parallelizable after M0.

### Epic 1: Environment & Code Quality Infrastructure (Ruff, ESLint, Prettier, GitHub Actions)

**Goal:** Every later diff is linted, tested, and secret-scanned before review. **Milestone:** M0. **Specs:** PRD NFR-4, R7 · ARCH §6, §2.

| Feature | Description | Key files |
|---------|-------------|-----------|
| E1-F1 Repo skeleton & toolchains | Monorepo layout + Python 3.12 + Node 20 + `pathlib`-only paths | `pyproject.toml`, `remotion/package.json`, `config/pipeline.yaml` |
| E1-F2 Python quality | Ruff `check` + `format`, pytest + coverage gate (≥80%), pre-commit hooks | `.pre-commit-config.yaml`, `pyproject.toml` |
| E1-F3 Video quality | ESLint `--max-warnings=0` + Prettier `--check` + vitest | `remotion/*.{eslintrc,prettierrc}`, `vitest.config.ts` |
| E1-F4 CI/CD + branch protection | `ci.yml` (python/video/render-smoke), protected `main`, squash merge, snapshot-artifact upload | `.github/workflows/ci.yml` |
| E1-F5 Secrets & observability stubs | `.env.example`, gitleaks gate, structured-log + manifest stubs | `.env.example`, `src/pulsecraft/common/{logging,manifest}.py` |

### Epic 2: Dynamic Model Orchestration & Schema Engine (`config/models.json`, status validation, blueprint translation)

**Goal:** User-owned models, provable connectivity, contract-guaranteed blueprints. **Milestone:** M1. **Specs:** PRD FR-1, R1 · ARCH §4.1, §3.

| Feature | Description | Key files |
|---------|-------------|-----------|
| E2-F1 Model Registry | `models/v1` JSON, `registry.py`, `models add/set-chain`, per-task chains (`scriptHeadline`, `blueprintTranslate`) | `config/models.json`, `src/pulsecraft/llm/registry.py` |
| E2-F2 Health checks | `check-models` probes (`Connected`/`Failed` + ms + reason + `lastChecked` persist) | `src/pulsecraft/llm/client.py`, `cli.py` |
| E2-F3 Orchestrated generation + repair + fallback | JSON-mode prompts, fence/comma repair, backoff + chain switching, partial preservation | `llm/{client,prompts,repair,fallback}.py`, `prompts/*.md` |
| E2-F4 Blueprint contracts | `blueprint.schema.json` (envelope + static/reel `if/then`), golden fixtures, 100%-valid gate | `schemas/blueprint.schema.json`, `tests/contract+fixtures/` |

### Epic 3: Static Post Automation (`/templates/posts/`, 1080×1080 / 1080×1350 layouts, Playwright PNG export)

**Goal:** Designer-free pixel-perfect PNGs. **Milestone:** M2. **Specs:** PRD FR-2, FR-5, R4, R6 · ARCH §4.2, §4.3, §3.2.

| Feature | Description | Key files |
|---------|-------------|-----------|
| E3-F1 Post template packs | ≥2 layouts with `index.html` + offline CSS + `preview.png` + `meta.json` | `templates/posts/<layout>/` |
| E3-F2 Brand system (static) | `_base.json` inheritance, `merge.py`, `tokens.css`, `validate-brand` | `brands/`, `schemas/brand.schema.json` |
| E3-F3 Playwright renderer + asserts | Single instance, exact viewports, font-ready wait, `file://` assets, header asserts, `meta.json` | `src/pulsecraft/render_static/` |
| E3-F4 Safety + swap proof | Auto-fit/clamp, safe-area, contrast warn, brand-swap snapshot test | `tests/snapshots/`, `tests/e2e/test_static.py` |
| E3-F5 Dynamic layers + inspector | L1 conditionals, L2 loops, L4 LLM HTML fallback via `PROMPT_EXPANSION`, `inspect_template()` badge-tag preview + placeholder schema | `src/pulsecraft/templates_mgr/manager.py`, `src/pulsecraft/render_static/renderer.py` |

### Epic 4: Short-Form Video Engine (`/templates/reels/`, Remotion React, Kokoro TTS, Faster-Whisper INT8, Kinetic typography)

**Goal:** Editor-free Reels with synced karaoke captions. **Milestone:** M3. **Specs:** PRD FR-3, FR-4 (TTS/STT), R3, R5 · ARCH §4.4, §4.5 (audio), §3.3.

| Feature | Description | Key files |
|---------|-------------|-----------|
| E4-F1 Kokoro VO stage | Chunker (≤500), voice+speed per brand, concat WAV, content-hash cache, resume | `src/pulsecraft/tts/` |
| E4-F2 Whisper timestamp stage | INT8 `base`/`tiny`, `words.json` + `.srt`, `estimated` fallback flag | `src/pulsecraft/stt/` |
| E4-F3 Reel themes + composition | `/templates/reels/<theme>/` + `ReelComposition` 1080×1920@30fps + caption engine + hook/CTA/crossfade/Ken Burns | `templates/reels/`, `remotion/src/` |
| E4-F4 Video asserts + draft mode | Resolution/duration/ffprobe gates, `--fast-draft`, 3s CI smoke | `tests/e2e/test_reel_smoke.py` |

### Epic 5: Asset & Template Management Pipeline (Pexels API fetcher, dynamic template loader)

**Goal:** Free visuals + live template management without engine churn. **Milestone:** M4. **Specs:** PRD FR-4 (Pexels), FR-5, R2 · ARCH §4.5, §4.2.

| Feature | Description | Key files |
|---------|-------------|-----------|
| E5-F1 Pexels fetcher | Search/filter/download/resize, manifest + ATTRIBUTION, `.cache/pexels/` | `src/pulsecraft/assets/pexels.py` |
| E5-F2 Cache & resilience | Backoff→relax→cache→fallback tree, `--strict-assets`, `--reuse-cache`/`--refresh-assets`, LRU >5GB | `src/pulsecraft/assets/cache.py` |
| E5-F3 Template manager GA | `templates {list,add,preview,clear}` for posts+reels, offline-safety lint, hot-swap | `src/pulsecraft/templates_mgr/manager.py` |

---

## 3. Granular User Stories with Acceptance Criteria

Format: **Given-When-Then + explicit acceptance criteria (AC) + mapped epic/feature + test pointer.** IDs are stable (`US-<Epic>.<n>`).

### Epic 1 — Environment & Quality

**US-1.1 Scaffold installs reproducibly**
- **Given** a fresh clone on Windows 10/11 or Linux, **When** I run `pip install -e .[dev]` and `npm ci --prefix remotion`, **Then** both complete with no manual fixes.
- AC: (1) Layout matches ARCH §2; (2) `.cache/`, `out/`, `.env` ignored; (3) empty `pytest -q` + `vitest run` green. *→ E1-F1. Test: CI bootstrap job.*

**US-1.2 Python quality gates block bad diffs**
- **Given** a Python change with lint/format violations, **When** I run `pre-commit run --all-files` or open a PR, **Then** Ruff fails with file:line rules and CI marks the check red.
- AC: (1) `ruff check` + `ruff format --check` must pass; (2) pytest coverage ≥80% or CI fails; (3) no bypass without admin override. *→ E1-F2.*

**US-1.3 Video quality gates block bad diffs**
- **Given** a TSX change with lint/format issues, **When** CI runs, **Then** `eslint --max-warnings=0` or `prettier --check` fails the PR.
- AC: (1) Zero warnings tolerance; (2) `vitest run` green required; (3) `/templates/reels/` linted as source. *→ E1-F3.*

**US-1.4 Secrets never leak**
- **Given** a commit touching `.env` or a key-like string, **When** pre-commit/CI runs gitleaks, **Then** the commit is rejected with a redaction-safe message.
- AC: (1) `.env` untracked; (2) `.env.example` has placeholders only; (3) logs contain no key material (assert via log-scan test). *→ E1-F5. Covers PRD R7.*

### Epic 2 — Model Orchestration & Schemas

**US-2.1 Register a custom model without code change**
- **Given** `config/models.json` exists, **When** I run `pulsecraft models add "vendor/custom-model:free" --for scriptHeadline,blueprintTranslate`, **Then** the id appears in the registry and is selectable via `--model-override` and `set-chain`.
- AC: (1) No `src/` diff required; (2) unknown id persists with `status: unknown`; (3) invalid JSON rejected with schema error. *→ E2-F1.*

**US-2.2 Probe model connectivity**
- **Given** registry entries (incl. one bad key), **When** I run `pulsecraft check-models`, **Then** each row shows `Connected` (with ms) or `Failed` (with reason) and `lastChecked` updates.
- AC: (1) 401/timeout produce actionable text, not traceback; (2) results persist to `config/models.json`; (3) exit code nonzero iff all entries in a task chain Failed. *→ E2-F2.*

**US-2.3 Fallback survives primary outage**
- **Given** primary stubbed to 429/5xx/timeout, **When** I run `generate`, **Then** the engine retries once, switches to next chain entry, logs the reason, and returns a valid blueprint.
- AC: (1) Zero user intervention; (2) switch reason in structured logs + manifest; (3) full-chain exhaustion preserves partial + prints resume hint. *→ E2-F3. Covers PRD R1.*

**US-2.4 Blueprint contracts enforced**
- **Given** raw LLM text (incl. fenced/trailing-comma fixtures), **When** orchestration finishes, **Then** `out/<run-id>/blueprint.json` validates against `blueprint.schema.json` or a fallback path is taken.
- AC: (1) 100% persisted blueprints valid; (2) repair pass attempted before fallback; (3) contract tests cover valid + invalid fixtures per type. *→ E2-F4.*

### Epic 3 — Static Post Automation

**US-3.1 Resolve and render two exact PNGs**
- **Given** a valid `static-post` blueprint with `layout: bold-hook-split`, **When** I run `render-static --blueprint ... --brand acme`, **Then** `square-1080x1080.png` and `vertical-1080x1350.png` are written with exact pixel dims plus `meta.json`.
- AC: (1) Pillow/sharp asserts pass; (2) each PNG <15s warm; (3) unknown layout errors list available ids. *→ E3-F1/F3.*

**US-3.2 Long copy never breaks layout**
- **Given** a 120-char hook, **When** rendering both canvases, **Then** text auto-fits (shrink/ellipsis) inside safe areas with no overflow or crop of CTA.
- AC: (1) Overflow fixture snapshot passes; (2) contrast <4.5:1 emits warning; (3) no silent pass. *→ E3-F4. Covers PRD R6.*

**US-3.3 Onboard a brand with config only**
- **Given** `brands/_template/`, **When** I run `init-brand --slug demo` and edit colors/fonts/logo/voice, **Then** `validate-brand` passes and the golden smoke renders themed outputs with zero engine diff.
- AC: (1) Invalid brand (bad hex/missing font) fails with precise errors; (2) same prompt × 2 brands → themed diff; (3) onboarding <30 min per runbook. *→ E3-F2. Covers PRD G3.*

**US-3.4 Dynamic layers degrade gracefully**
- **Given** a blueprint with empty `sub`/`cta`, a 3-item `bullets[]`, and an unknown `layout` id, **When** I render, **Then** L1 hides the empty sections, L2 iterates the bullets, and L4 generates fallback HTML via `PROMPT_EXPANSION` with `layer: L4` logged in the manifest.
- AC: (1) No empty-section whitespace gaps; (2) all bullets rendered; (3) L4 output passes offline-safety lint + dimension asserts. *→ E3-F5.*

**US-3.5 Inspect template before writing copy**
- **Given** template `bold-hook-split`, **When** I run `templates inspect bold-hook-split`, **Then** I see a badge-tag preview (`[Headline Here]`, …) plus a required/optional placeholder schema table.
- AC: (1) Required vs optional derived from Jinja2 AST + `meta.json`; (2) undeclared/unused vars warn without failing; (3) preview uses production CSS. *→ E3-F5.*

### Epic 4 — Short-Form Video Engine

**US-4.1 Cached voiceover with resume**
- **Given** reel script sentences, **When** I run the TTS stage twice (second offline/airplane-mode), **Then** both produce identical WAVs, the second from cache with `cache: hit`.
- AC: (1) Chunking ≤500 chars sentence-aware; (2) key = `hash(text+voice+speed)`; (3) `--refresh-assets` forces re-synth. *→ E4-F1.*

**US-4.2 Word timestamps drive karaoke captions**
- **Given** a VO WAV, **When** I run the Whisper stage, **Then** `words.json` (monotonic) + `.srt` are written and the Remotion still shows the correct active word.
- AC: (1) Fixture ≥95% words covered; (2) drift <150ms; (3) `--no-whisper` yields `estimated:true` uniform timing + flag in manifest. *→ E4-F2. Covers PRD R3.*

**US-4.3 Reel renders to spec with fallbacks**
- **Given** blueprint + voice + words + preset `alex-hormozi` + `--platform all`, **When** I run `render reel`, **Then** 1080×1080 + 1080×1350 + 1080×1920 MP4s pass resolution, duration ±0.5s, and `ffprobe` audio-track checks.
- AC: (1) 30s fixture in 1–3 min warm on ref hw; (2) missing B-roll uses gradient + log; (3) `--fast-draft` renders faster preview. *→ E4-F3/F4. Covers PRD R5.*

**US-4.4 Presets, ducking, and toggles behave**
- **Given** a blueprint with `audioTags` + `presetTweaks` and `--preset faceless-docu`, **When** I run `render reel --no-bgm`, **Then** BGM/SFX stages are skipped (toggle overrides prompt), VO stays full volume, and warnings list the stripped requests.
- AC: (1) Preset switch changes caption/overlay signature; (2) duck curve 15% speech / 35% pause when enabled; (3) hybrid tweaks never alter geometry. *→ E4-F3 + §4.6.*

### Epic 5 — Assets & Templates

**US-5.1 Licensed visuals with attribution**
- **Given** a blueprint asset query, **When** I run the Pexels stage, **Then** images land in `.cache/pexels/<query-hash>/` with `assets/manifest.json` (photographer, URL, license) and per-run `ATTRIBUTION.md`.
- AC: (1) Orientation filter respected (portrait for reels); (2) every used asset attributed; (3) resized/compressed for render. *→ E5-F1.*

**US-5.2 Outage still ships via fallback**
- **Given** Pexels stubbed to 429/5xx/empty, **When** I run generate/render, **Then** the pipeline retries with backoff, relaxes the query, reuses cache, else uses `assets/fallback/` and logs a warning — render still succeeds.
- AC: (1) No hard fail without `--strict-assets`; (2) fallback + reason in manifest; (3) airplane re-run green from cache. *→ E5-F2. Covers PRD R2.*

**US-5.3 Manage templates live**
- **Given** a new `posts` layout or `reels` theme folder, **When** I run `templates add --kind … --from …` then `preview` then `clear`, **Then** add validates (`meta.json`, offline-safety), preview goldens, and clear prunes without touching engine code.
- AC: (1) Remote CDN/font links rejected; (2) next render can select the new id immediately; (3) add/clear round-trip test green. *→ E5-F3.*

---

## 4. Feature-by-Feature TDD Execution Strategy

Strict **Red → Green → Clean** per feature slice. No production code without a failing test first; CI enforces gates from ARCH §5–§6.

### 4.1 Protocol (normative)

1. **Red — write failing tests first.** For each `US-*`: add unit + contract tests (and snapshot skeleton for renderers) that fail on missing implementation. Example: `test_registry.py::test_custom_model_persisted` fails before `registry.py` supports `models add`.
2. **Green — minimum code to pass.** Implement the smallest change making the new tests (and all prior tests) pass. No gold-plating; fallback/retry logic lands with its stub test in the same slice.
3. **Clean — refactor + format + docs.** Run `ruff check --fix` + `ruff format`, `eslint --fix` + `prettier --write` (video), update `meta.json`/`manifest` fields and fixture docs; re-run full suites. Snapshot changes require `--update-snapshots` + reviewer approval — never silent.
4. **Gate — push through CI.** `pre-commit run --all-files` → `pytest -q` (+ coverage) → `vitest run` → Playwright snapshots → 3s reel smoke (video slices). Merge only on green + review (see §5).

### 4.2 Per-feature test map

| Feature | Red (tests first) | Green (implement) | Clean (refactor/gate) |
|---------|-------------------|-------------------|-----------------------|
| E2-F1 Registry | `test_registry_add/persist/chain` + `models.json` schema test | `registry.py`, `models add/set-chain` CLI | Ruff + contract suite green |
| E2-F2 Health | `test_check_models_connected/failed` with HTTP stubs | Probe + persist `lastChecked` | Log redaction test |
| E2-F3 Fallback | `test_429_then_200_switches`, `test_repair_fences`, `test_exhaustion_resume_hint` | `client/repair/fallback.py` | Manifest reason field |
| E2-F4 Schemas | valid/invalid fixtures per type (static + reel) | `blueprint.schema.json` `if/then` | 100%-valid gate test |
| E3-F1/F2 Templates+brands | `test_template_resolve`, `test_validate_brand_errors`, `test_base_inheritance` | `templates_mgr`, `merge.py`, packs | Snapshot skeleton |
| E3-F3 Renderer | `test_static_dims` (Pillow), overflow fixture, golden skeleton | `playwright_render.py`, `assert.py` | `--update-snapshots` review |
| E4-F1/F2 Audio | `test_chunker`, `test_cache_key`, `test_words_monotonic/coverage`, SRT goldens | `tts/`, `stt/` wrappers | Cache-hit test offline |
| E4-F3/F4 Video | `test_pagination`, `test_interpolation`, 3s smoke skeleton | `ReelComposition`, caption engine | `ffprobe` asserts |
| E5-F1/F2 Pexels | `test_pexels_429_fallback`, `test_manifest_attribution`, LRU test | `pexels.py`, `cache.py` | Airplane re-run test |
| M5 E2E | `test_generate_e2e` (seed determinism), NFR timing capture | `generate` orchestration | Runbook + manifest audit |

### 4.3 Definition of Done (every story)

- Tests written first and green; coverage gate met; `ruff` + `eslint`/`prettier` clean; `pre-commit` clean.
- Contract/snapshot updates reviewed (no drive-by goldens); manifest + logs capture models/timings/fallbacks.
- Docs touched if behavior changed (spec, `meta.json` fields, runbook); Windows + Linux path-safe (`pathlib`).

---

## 5. Branching, PR & Code Review Rules

### 5.1 Branch naming convention (required)

```text
feature/<scope>-<slug>   # e.g. feature/llm-fallback-chain, feature/static-playwright-png
fix/<scope>-<slug>       # e.g. fix/whisper-drift-tolerance, fix/pexels-backoff
docs/<area>-<slug>       # e.g. docs/prd-setup, docs/architecture-spec, docs/project-plan
chore/<slug>             # e.g. chore/ci-snapshot-artifacts
```

- Branch from latest `main` (`checkout main → pull → checkout -b …`); one scope per branch; rebase on `main` if stale >1 day or CI base-check warns.
- Never commit directly to `main`. `main` is protected (see §5.3).

### 5.2 PR template requirements (all boxes required)

```markdown
## Summary
<!-- 1–3 lines: what + why, linked spec (PRD/ARCH section) -->

## Scope
<!-- Epic/Feature IDs (e.g. Epic 2 · E2-F3 · US-2.3) + milestone (M1) -->

## Changes
<!-- files + behavior; schema/manifest field changes called out -->

## Tests (TDD evidence)
<!-- Red→Green: new tests, commands run, coverage/snapshot results -->
- [ ] pytest -q (+ coverage gate)
- [ ] vitest run (video changes)
- [ ] Playwright snapshots (renderer changes; --update-snapshots only with approval)
- [ ] 3s reel smoke (video changes)

## Risks & Fallbacks
<!-- outage paths exercised (429 stubs, fallback assets, estimated timings) -->

## Checklist
- [ ] ruff + eslint/prettier clean, pre-commit green
- [ ] No secrets (.env untouched, logs redacted)
- [ ] Docs updated (spec/runbook/meta fields as needed)
```

- Title uses Conventional Commits: `feat: …`, `fix: …`, `docs: …`, `chore: …`, `test: …`.
- Small PRs preferred (<400 lines excl. goldens); goldens isolated in their own commit with before/after stills.

### 5.3 CI/CD status check gates (must all pass)

| Gate | Check | Enforced by |
|------|-------|-------------|
| Lint/format | `ruff check` + `ruff format --check`; `eslint --max-warnings=0`; `prettier --check` | `ci.yml` python/video + pre-commit |
| Tests | `pytest -q --cov-fail-under=80`; `vitest run`; contract + integration suites | `ci.yml` |
| Render gates | Playwright snapshots; static dim asserts; `remotion --dry-run` + 3s smoke + `ffprobe` | `ci.yml` render-smoke |
| Secrets | gitleaks; `.env` absent; log redaction scan | pre-commit + CI |
| Review | ≥1 approval (Lead Architect or TPM); snapshot changes need explicit golden approval | branch protection |
| Merge | Squash merge only; title Conventional; linked issue/milestone | branch protection |

**Review SLA & etiquette:** first review <24h; comments are actionable with file:line; disagreements resolved via spec link (PRD/ARCH), not opinion; stale branches (>3 days) rebase + re-run smoke before merge.

---

## Appendix A: Milestone → Epic → Spec Traceability

| Milestone | Epics | PRD | Architecture |
|-----------|-------|-----|--------------|
| M0 Foundations & CI | Epic 1 (E1-F1…F5) | NFR-4, R7, App. C M0 | §2 layout, §6 CI/quality |
| M1 LLM + Registry | Epic 2 (E2-F1…F4) | FR-1, R1, App. C M1 | §4.1, §3 envelope+schemas |
| M2 Static Renderer | Epic 3 (E3-F1…F4) | FR-2, FR-5, R4, R6, G1/G3, App. C M2 | §4.2, §4.3, §3.2 |
| M3 Video Engine | Epic 4 (E4-F1…F4) | FR-3, FR-4 (TTS/STT), R3, R5, G2, App. C M3–M4 | §4.4, §4.5, §3.3 |
| M4 Assets + Templates | Epic 5 (E5-F1…F3) | FR-4 (Pexels), FR-5, R2, App. C M3 | §4.5, §4.2 |
| M5 E2E + QA + Polish | All (integration) | NFR-1…NFR-4, G1…G4, App. C M5 | §5 TDD, §6 CI, App. A |

## Appendix B: Glossary

- **Milestone (M0…M5):** acceptance-gated roadmap phase; exit demo required.
- **Epic (Epic 1…5):** feature group shipping a vertical capability.
- **User story (US-x.y):** Given-When-Then slice with explicit AC and test pointer.
- **Red → Green → Clean:** failing tests first → minimum pass → refactor/format/docs.
- **Golden snapshot:** approved Playwright PNG; updates need explicit approval.
- **Run-manifest:** per-run JSON (models, timings, hashes, fallbacks, seed).

---

*End of Project Plan v0.1.0 — Next: execute M0 (Epic 1) slices in `feature/*` branches per §5, starting with repo skeleton + CI gates.*
