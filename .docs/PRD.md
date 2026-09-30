# PulseCraft Studio — Product Requirements Document (PRD)

**Project:** PulseCraft Studio — Social Media Content Automation Engine
**Version:** 0.1.0 (Initial Draft)
**Status:** Draft — `docs/prd-setup`
**Owners:** Senior Software Architect / Product Manager
**Date:** 2026-09-30
**Methodology:** Spec-Driven Development (SDD) + Test-Driven Development (TDD)

---

## Table of Contents

- [1. Executive Summary \& Goals](#1-executive-summary--goals)
- [2. User Personas \& Target Audience](#2-user-personas--target-audience)
- [3. Core Functional Requirements](#3-core-functional-requirements)
- [4. Non-Functional Requirements](#4-non-functional-requirements)
- [5. Tech Stack Summary](#5-tech-stack-summary)
- [6. Risk Management \& Mitigations](#6-risk-management--mitigations)
- [Appendix A: Proposed Repository Structure](#appendix-a-proposed-repository-structure)
- [Appendix B: SDD + TDD Workflow](#appendix-b-sdd--tdd-workflow)
- [Appendix C: Milestones \& Acceptance Gates](#appendix-c-milestones--acceptance-gates)
- [Appendix D: Glossary](#appendix-d-glossary)

---

## 1. Executive Summary & Goals

### 1.1 Vision

PulseCraft Studio is a local-first, CLI-driven **Social Media Content Automation Engine** that turns a short text prompt into publish-ready, high-retention content for **Facebook and Instagram** — no designer, video editor, or paid SaaS subscription required.

### 1.2 Target Platforms

| Platform | Surfaces Supported (v1) | Aspect / Spec |
|----------|-------------------------|---------------|
| Facebook | Feed Image Post, Reels | Per Meta Feed + Reels specs |
| Instagram | Feed Image Post, Reels | Per IG Feed + Reels specs |

> Out of scope for v1: TikTok, YouTube Shorts (architecture must not preclude them), paid boosting / scheduling / direct publishing APIs. v1 outputs local files ready for manual upload or Meta Business Suite scheduling.

### 1.3 Output Formats (Normative)

| Output Type | Size | Format | Use |
|-------------|------|--------|-----|
| High-Retention Static Image Post — Square | **1080x1080** | **PNG** | FB + IG Feed |
| High-Retention Static Image Post — Vertical | **1080x1350** (4:5) | **PNG** | FB + IG Feed (max portrait screen real-estate) |
| Reels / Shorts Video | **1080x1920** (9:16) | **MP4** (H.264, AAC, 30fps) | FB Reels + IG Reels |

All outputs must be pixel-exact to spec. Static renderer must pass dimension assertion tests. Video renderer must output 1080x1920, ≤ 60s default (configurable 15/30/60s), with burned-in kinetic captions and mixed voiceover + optional background track.

### 1.4 Core Philosophy (Non-Negotiable)

1. **Brand-Agnostic:** No hardcoded brand. All colors, fonts, logos, tone, and layout variants live in swappable `brand-pack/` configs + modular templates. One engine, N clients.
2. **Zero-Subscription Cost Stack:** $0 recurring infra. Free-tier / open-weight only: OpenRouter free-tier models, Kokoro TTS (local), Faster-Whisper (local), Pexels API (free tier), Playwright + Chromium, Remotion + FFmpeg, GitHub Actions free tier. Paid APIs are forbidden in core path.
3. **Spec-Driven Development (SDD):** No code without a written spec in `.docs/specs/`. JSON layout blueprints are versioned contracts validated by JSON Schema before rendering.
4. **Test-Driven Development (TDD):** Red → Green → Refactor. Unit + contract + snapshot + render-smoke tests must exist before / alongside implementation. CI fails on missing coverage for layout contracts and renderers.

### 1.5 Goals & Success Metrics (v1)

**Product goals:**

- G1: Prompt → 2x PNG (square + vertical) in one CLI command with no manual design step.
- G2: Prompt → 1080x1920 MP4 Reel with synchronized voiceover + word-by-word captions in one CLI command.
- G3: New client brand onboarded in < 30 minutes via template + brand config only (no engine code change).
- G4: Fully reproducible local runs on reference hardware (see §4).

**Measurable acceptance:**

| Metric | Target |
|--------|--------|
| Static post end-to-end (LLM → PNG x2) | Completes in reasonable bounds on ref. hardware, background tabs open |
| Reel end-to-end (LLM → MP4 30s) | **1–3 minutes**, no system freeze / OOM |
| Blueprint schema validity | 100% of LLM outputs pass JSON Schema validation after fallback/retry |
| Visual regression | Zero unintentional pixel diffs on approved template snapshots |
| Brand swap test | Same prompt + 2 brand packs → correctly themed outputs, no code change |

---

## 2. User Personas & Target Audience

Primary audience: **Marketing Agency Owners and Digital Marketers** managing multiple SMB clients with high content velocity and low per-client budget.

### Persona 1: Amara — Marketing Agency Owner

- **Role:** Owns 10-person agency, 15–25 retainer SMB clients (restaurants, gyms, realtors).
- **Goals:** Ship 100+ creatives/week without hiring full-time designer/editor; white-label output per client brand; prove ROI with volume + consistency.
- **Pains:** Designer bottleneck, Canva template fatigue, subscription sprawl (Canva, CapCut, ElevenLabs, stock sites), off-brand freelancer output, Reels editing too slow.
- **Tech comfort:** Medium. Can run CLI / edit YAML/JSON, delegates setup to VA/junior.
- **Jobs-to-be-done:**
  - "Onboard a new client brand once, then generate a month of posts in an afternoon."
  - "Produce on-brand Reels daily without timeline editing."
- **Definition of delight:** `pulsecraft generate --brand client-acme --prompt "..." --formats png,reel` → client-ready files in `out/` with correct fonts/colors/logo.

### Persona 2: Daniel — Freelance / In-House Digital Marketer

- **Role:** Solo marketer running FB/IG for 3–5 brands, lives in Meta Business Suite.
- **Goals:** Daily posting streak, hook-first copy, accessible captions, fast iteration on hooks/CTAs.
- **Pains:** Blank-canvas block, inconsistent caption styling, robotic TTS, hunting free stock, whisper transcription costs, rendering crashes on laptop.
- **Tech comfort:** Medium-high. Comfortable with Node/Python, .env keys, Git pull.
- **Jobs-to-be-done:**
  - "Turn one offer brief into 3 hook variants as images + 1 Reel script with voiceover."
  - "Regenerate only captions/voice without re-fetching stock."
- **Definition of delight:** Cached assets, resumable pipeline stages, clear error messages with fallback action taken.

### 2.1 Secondary / Anti-Personas

- **Secondary:** VA / Junior Creator (runs CLI from runbook, swaps brand packs, QA's output folder).
- **Out of scope:** Enterprise brand teams needing DAM, approvals, direct IG Graph API publishing (v2 consideration).

### 2.2 Core User Journeys

**J1 — Static campaign (Amara):** Create `brands/acme.json` → run static generation → QA 1080x1080 + 1080x1350 PNGs → drop to shared drive / schedule.
**J2 — Daily Reel (Daniel):** One-line brief → LLM expands to script + scene blueprint → Kokoro VO + Pexels B-roll + Whisper timestamps → Remotion render → 1080x1920 MP4 with kinetic typography.
**J3 — Brand onboarding (Amara + VA):** Duplicate `brands/_template/` → set colors/fonts/logo/voice → run `validate-brand` + golden snapshot test → approved.

---

## 3. Core Functional Requirements

> Naming: FR-1 … FR-5. Each FR has user story, requirements (MUST/SHOULD), acceptance criteria, and test notes (TDD).

### FR-1 — Feature 1: Multi-Provider LLM Integration via OpenRouter API

**User story:** As Daniel, I want my raw prompt auto-expanded into a strict JSON layout blueprint so I never hand-write layouts.

**Description:**
Central `llm/` orchestrator calls **OpenRouter API** with prioritized model list — **DeepSeek V3 / R1, Llama 3.3, Gemini 2.0 Flash** — to translate natural-language prompts into versioned, schema-validated JSON blueprints (static layout + reel script/scenes). Includes prompt templating, JSON-mode / structured-output enforcement, retry, and automatic model switching on rate limits / errors.

**MUST:**

- FR-1.1 Support configurable model priority chain, e.g. `deepseek-v3 → llama-3.3 → gemini-2.0-flash`, overridable via CLI flag / env / brand config.
- FR-1.2 System + user prompt templates versioned under `prompts/`; include brand voice tokens, output format constraints, and "JSON only" instruction.
- FR-1.3 Enforce strict JSON output: low temperature, JSON-mode where supported, post-parse + repair (strip fences, JSON repair pass), then validate against `schemas/blueprint.schema.json` (draft 2020-12).
- FR-1.4 Fallback handling: on 429 / 5xx / timeout / invalid JSON after N retries, auto-switch to next provider/model, log switch reason, and surface to CLI. After full chain exhaustion, fail with actionable error + preserve partial output for resume.
- FR-1.5 Support two blueprint types: `static-post` (headline, subcopy, CTA, layout id, palette refs, asset queries) and `reel` (hook, script sentences, per-scene VO text, caption words budget, asset queries, duration target).
- FR-1.6 Secrets via `.env` (`OPENROUTER_API_KEY`); never log keys; per-model cost/latency logging (even if $0).

**Acceptance criteria:**

- AC-1: Given OpenRouter mock returning 429 on primary, engine auto-retries then succeeds on secondary with no user intervention (integration test with stubbed HTTP).
- AC-2: 100% of persisted blueprints in `out/` validate against JSON Schema (contract test).
- AC-3: Malformed LLM output (fences / trailing commas) is repaired or triggers fallback, never crashes renderer.

**Test notes (TDD):** Unit: prompt builder, JSON extractor/repair, model selector. Contract: schema validation fixtures (valid/invalid). Integration: stubbed OpenRouter sequence 429→200, timeout→fallback.

**Example blueprint (static, abbreviated):**

```json
{
  "version": "blueprint/v1",
  "type": "static-post",
  "brand": "acme",
  "layout": "bold-hook-split",
  "canvas": ["1080x1080", "1080x1350"],
  "copy": {
    "hook": "3 Morning Habits That Burn Fat",
    "sub": "No gym. No crash diet.",
    "cta": "Save + Follow for Day 2"
  },
  "style": { "palette": "brand.primary", "font": "brand.display" },
  "assets": { "query": "healthy breakfast bright", "provider": "pexels", "count": 3 }
}
```

### FR-2 — Feature 2: Static Post Rendering Engine (HTML/CSS/Tailwind + Playwright)

**User story:** As Amara, I want pixel-perfect FB & IG PNG exports so posts look designed, not generated.

**Description:**
HTML5 + CSS3 (Tailwind allowed) templates rendered in headless Chromium via **Playwright**, screenshotted to **1080x1080 Square & 1080x1350 Vertical PNG**. Layout components are decoupled from brand tokens (see FR-5).

**MUST:**

- FR-2.1 Template loader resolving `layout` id from blueprint → `templates/static/<layout>/index.html` + `tokens.css` generated from brand pack.
- FR-2.2 Viewport-exact rendering: `1080x1080` and `1080x1350` deviceScaleFactor=2 (or 1 with 1080 CSS px), `waitUntil: networkidle` + font-ready wait, hide scrollbars, deterministic screenshot clip.
- FR-2.3 Text safety: auto-fit / clamp headline (shrink or ellipsis, never overflow), safe-area padding for FB/IG crop, contrast check helper.
- FR-2.4 Asset injection: local cached Pexels image (see FR-4) embedded via file:// with fallback solid/gradient if missing.
- FR-2.5 CLI: `render-static --blueprint out/blueprint.json --brand acme` → writes `out/<run-id>/square-1080x1080.png`, `vertical-1080x1350.png` + `meta.json` (dimensions, hashes, durationMs).
- FR-2.6 Dimension assertion post-export (PNG header check); fail loudly on mismatch.

**Acceptance criteria:**

- AC-1: Both PNGs exist with exact pixel dimensions verified by test (Pillow / sharp).
- AC-2: Snapshot test: approved golden PNGs; intentional template change requires `--update-snapshots` + review.
- AC-3: Long hook (120 chars) does not overflow canvas in either size.

**Test notes:** Unit: token injection, text clamp. Snapshot: Playwright screenshot vs golden. E2E: blueprint fixture → PNGs + dimension assert.

### FR-3 — Feature 3: Short-Form Video Rendering Engine (Remotion + Voiceover + Kinetic Typography)

**User story:** As Daniel, I want Reels with voiceover and word-by-word captions without opening a video editor.

**Description:**
**Remotion (React + Node.js + FFmpeg)** composition renders **1080x1920 MP4** from reel blueprint + voiceover audio + word timestamps. Includes synchronized VO, **kinetic typography (word-by-word captions)**, B-roll/images, progress bar, hook title card, CTA end card.

**MUST:**

- FR-3.1 Remotion project under `remotion/` with `ReelComposition` (1920x1080 portrait: 1080x1920, 30fps), props = `{ script, scenes[], audioSrc, words[], brandTokens }`.
- FR-3.2 Caption engine maps Faster-Whisper word timestamps → active-word highlight (karaoke style), configurable max-words-per-line, safe-area positioning, high-contrast stroke/shadow for readability.
- FR-3.3 Audio sync: Kokoro VO track laid precisely; optional ducked background music (free/local file, default off); loudness normalize (-14 LUFS target, SHOULD).
- FR-3.4 Scene system: per-scene background (Pexels image/video with Ken Burns / zoom pan), crossfade, hook (0–3s) and CTA templates.
- FR-3.5 CLI: `render-reel --blueprint ... --voice ... --words ...` → `reel-1080x1920.mp4` via `npx remotion render`, with progress logs and resumable intermediate artifacts.
- FR-3.6 Post-render assert: resolution, duration within ±0.5s of VO length, has-audio-track check.

**Acceptance criteria:**

- AC-1: 30s script renders to 1080x1920 MP4 with audible VO and visible word-level highlight verified by sampled frame + audio presence probe (ffprobe).
- AC-2: Word timing drift < 150ms vs Whisper timestamps on fixture.
- AC-3: Missing B-roll does not fail render — gradient + title fallback is used and logged.

**Test notes:** Unit: caption pagination, timestamp interpolation. Integration: fixture words+audio → `remotion render --dry` / stills. E2E render-smoke on tiny (3s) fixture in CI.

### FR-4 — Feature 4: Automated Free Asset Supply Pipeline (Kokoro TTS + Faster-Whisper + Pexels)

**User story:** As Daniel, I want voice, subtitles, and visuals auto-supplied for free so I never leave the CLI.

**Description:**
Zero-subscription asset pipeline with three local/free stages + disk cache (` .cache/`), each independently re-runnable:

1. **Kokoro TTS → Voiceover Audio (WAV/MP3).**
2. **Faster-Whisper (INT8 quantized) → word timestamps / subtitles (JSON + SRT).**
3. **Pexels API → graphic/visual assets (images, SHOULD video) with license attribution log.**

**MUST:**

- FR-4.1 TTS: text-chunking (sentence-aware, ≤ ~500 chars), selectable voice + speed per brand, concatenated WAV (16kHz+), per-chunk cache keyed by hash(text+voice+speed). Offline after install.
- FR-4.2 STT/Align: Faster-Whisper `base/small` INT8 on CPU; output `words: [{word, start, end}]` + `srt`; word-level timestamps REQUIRED for FR-3. Provide `--whisper-model` override and `--no-whisper` (fallback: uniform per-word timing from audio duration, flagged as estimated).
- FR-4.3 Pexels: `PEXELS_API_KEY` via .env; query from blueprint, orientation filter (square/portrait/landscape→crop), download + resize/compress to cache; store `assets/manifest.json` with photographer, URL, license. On failure/rate-limit: retry with backoff → fallback to local `assets/fallback/` gradient/stock → log + continue (never hard-fail static or reel on asset miss unless `--strict-assets`).
- FR-4.4 Cache & resume: content-addressed `.cache/` (e.g., `tts/<hash>.wav`, `pexels/<query-hash>/...`); `--reuse-cache` default on; `--refresh-assets` to force.
- FR-4.5 Attribution file auto-generated (`ATTRIBUTION.md` per run).

**Acceptance criteria:**

- AC-1: Airplane-mode re-run (after first cache) succeeds for TTS + whisper stages.
- AC-2: Pexels 429/5xx simulation → fallback asset used, warning logged, render still succeeds.
- AC-3: Whisper fixture produces word timestamps with ≥ 95% words covered and monotonic times.

**Test notes:** Unit: chunker, cache-key, SRT formatter. Integration: stub Pexels HTTP; golden word-timestamp fixture comparison with tolerance.

### FR-5 — Feature 5: Modular Brand Template System

**User story:** As Amara, I want to add a client brand without touching engine code.

**Description:**
Decoupled **layout components + brand tokens + fonts**. `brands/<slug>.json` (colors, fonts, logo path, voice, tone) + `templates/` (static HTML/CSS + Remotion React components). Engine merges blueprint + brand + layout at render time.

**MUST:**

- FR-5.1 Brand schema (`schemas/brand.schema.json`): `name, slug, colors{primary, secondary, accent, bg, text}, fonts{display, body}, logo, voice{id, speed}, tone, ctaDefaults`. JSON Schema validated via `validate-brand` CLI.
- FR-5.2 Static templates: self-contained folders with `index.html`, `style.css` (Tailwind optional via CDN-inlined or built CSS — MUST work offline at render), `preview.png`, `meta.json` (supported layouts, safe areas).
- FR-5.3 Video themes: Remotion theme props derived from same brand tokens (single source of truth).
- FR-5.4 Inheritance: `brands/_base.json` → per-client override; missing token falls back to base with warning, never crash.
- FR-5.5 Scaffolder: `pulsecraft init-brand --slug acme` copies starter pack + runs validation + golden render smoke.

**Acceptance criteria:**

- AC-1: New brand added via config only → both static sizes + 3s reel smoke render pass validation.
- AC-2: Invalid brand (bad hex, missing font) fails `validate-brand` with precise errors.
- AC-3: Swapping brand on same blueprint changes palette/fonts/logo with zero engine diff (snapshot diff test).

**Test notes:** Schema validation tests, token-merge unit tests, brand-swap snapshot tests.

---

## 4. Non-Functional Requirements

### NFR-1 Hardware Optimization (Reference Machine)

- **Reference hardware: Intel i5 11th Gen CPU + 20GB RAM under typical background multitasking (e.g., multiple browser tabs open).** All targets below assume this profile — NOT a clean-room workstation.
- NFR-1.1 CPU-only. No GPU / CUDA requirement. All models (Kokoro, Whisper INT8) must run on CPU.
- NFR-1.2 Memory ceiling: peak RSS ≤ ~12GB during Reel render with browser tabs open; no OOM on 20GB machine. Stream/process audio in chunks; limit Chromium to single instance, one viewport at a time for static.
- NFR-1.3 Disk: cache-aware (evict LRU > 5GB), temp files cleaned on success/fail. Model downloads documented with sizes.
- NFR-1.4 Concurrency: default sequential pipeline stages; optional `--jobs 2` only for static sizes. Reel render is single-job by default.

### NFR-2 Realistic Rendering Speed

- NFR-2.1 **Static Post rendering within reasonable bounds** on reference hardware (target: < 60s end-to-end for LLM + 2 PNGs on warm cache; PNG screenshot itself < 15s per size). Must report per-stage timings in `meta.json`.
- NFR-2.2 **Reel rendering completed comfortably within 1–3 minutes** for a 30s Reel on reference hardware (warm cache, Whisper `base` INT8, Remotion + FFmpeg). 60s Reel SHOULD stay < 5 min. Must not strain system (no sustained 100% CPU lockup without progress logs; user can continue light multitasking).
- NFR-2.3 Pipeline MUST expose `--fast-draft` mode (smaller whisper model, lower render scale / fewer frames for preview) for iteration, and full-quality default for final.

### NFR-3 Quality, Reliability & UX

- NFR-3.1 Determinism: same `--seed` / pinned model + blueprint → byte-comparable blueprint; renders visually stable (font pinning, no random stock rotation unless seed changes).
- NFR-3.2 Offline resilience: after first-run downloads, TTS + STT + static render work offline; Pexels requires network but degrades to cache/fallback.
- NFR-3.3 Observability: structured logs (stage, model, ms, cache hit/miss, fallback taken), `run-manifest.json` per run, actionable error messages ("Pexels 429 → using fallback; retry with --refresh-assets").
- NFR-3.4 Accessibility of output: captions burned-in + SRT sidecar; color-contrast helper warns on < 4.5:1 body text.
- NFR-3.5 Security: `.env` never committed (`.env.example` only); keys redacted in logs; Pexels attribution preserved.

### NFR-4 Maintainability & Engineering Standards

- NFR-4.1 SDD: every FR has spec in `.docs/specs/FR-n-*.md` before code; blueprint/brand schemas versioned.
- NFR-4.2 TDD + CI: pytest (Python) + vitest/jest (Remotion) with coverage gates; Playwright snapshot tests; `ruff` / `ESLint` + `pre-commit` must pass.
- NFR-4.3 Portability: Windows 10/11 first-class (primary dev OS) + Linux CI; paths via `pathlib`, no hard-coded `\` or `/`.

---

## 5. Tech Stack Summary

| Layer | Choice (v1) | Rationale / Notes |
|-------|-------------|-------------------|
| **Core CLI Controller** | **Python 3.12** / Node.js (interop) | Python orchestrates LLM/TTS/STT/assets/static; Node.js owns Remotion render. Click/Typer CLI. |
| **LLM Orchestration** | **OpenRouter API** (DeepSeek V3/R1, Llama 3.3, Gemini 2.0 Flash) | Multi-provider, free-tier, single API surface, fallback switching. |
| **Static Renderer** | **HTML5, CSS3, Playwright (Chromium headless)** | Pixel-exact, designer-friendly templates, PNG screenshots. Tailwind optional (prebuilt, offline-safe). |
| **Video Renderer** | **Remotion (React, Node.js, FFmpeg)** | Code-driven 1080x1920 MP4, kinetic typography, deterministic props. |
| **Audio & Captions** | **Kokoro TTS** (local) + **Faster-Whisper (INT8 quantized)** | Zero-subscription, CPU-friendly, word timestamps for captions. |
| **Visual Assets** | **Pexels API** (free tier) | Free stock images/video, license log. Cached + fallback. |
| **Version Control & CI/CD** | **GitHub Actions, Pre-commit hooks, Ruff / ESLint** | Lint + test + snapshot gates on PR; golden-update workflow. |

**Supporting (implied):** JSON Schema (blueprint/brand contracts), Pillow/sharp (dimension asserts), `ffprobe` (video asserts), pytest + vitest, dotenv.

**Why this stack fits constraints:** Entire render path is local + free after API keys; CPU-quantized models hit the i5/20GB + multitasking budget; HTML/Remotion templates keep brand system modular; OpenRouter abstraction absorbs rate limits via model switching.

---

## 6. Risk Management & Mitigations

| # | Risk | Likelihood / Impact | Mitigation (Owner) |
|---|------|---------------------|---------------------|
| R1 | **Rate Limits on OpenRouter (429) / model downtime** | High / High | Prioritized fallback chain (DeepSeek → Llama → Gemini) with exponential backoff + jitter; per-model timeout; cache last-good blueprint; `--model` override; CI stub tests for 429→switch. |
| R2 | **Asset fetching failures (Pexels 429/5xx, network, empty results)** | High / Medium | Retry + backoff → query relaxation (fewer keywords) → local cache reuse → `assets/fallback/` gradient; `--strict-assets` opt-in hard fail; always log fallback + attribution. |
| R3 | Whisper mistiming / slow on i5 under load | Med / High | Default `base` INT8; `--fast-draft` (tiny) for iteration; uniform-timing fallback flagged; timing tolerance tests (<150ms drift). |
| R4 | Playwright/Chromium flakiness (fonts, networkidle, Windows paths) | Med / Med | Font-ready wait + bundled fonts; file:// assets only; single browser instance; dimension asserts + retry screenshot once. |
| R5 | Remotion/FFmpeg OOM or >3min render on ref. hardware | Med / High | 30s default, chunked audio, single-job default, progress logs, draft mode; CI render-smoke on 3s fixture; document background-tab budget. |
| R6 | Off-brand / overflow layouts (long copy, logo clash) | Med / Med | Text auto-fit/clamp, safe-area + contrast checks, brand-swap snapshot tests, `validate-brand` gate. |
| R7 | Secret leakage / key misuse | Low / High | `.env` + `.env.example`, gitignore + pre-commit secret scan (gitleaks), redacted logs. |
| R8 | Scope creep (publishing API, TikTok, paid voices) | Med / Med | v1 outputs local files only; feature flags; ADRs for deferred items. |

**Fallback decision tree (normative):** `retry same model once → next model → cached blueprint → fail with resume hint`. For assets: `retry → relax query → cache → bundled fallback → fail only if --strict-assets`.

---

## Appendix A: Proposed Repository Structure

```text
PulseCraft_Studio/
  .docs/
    PRD.md
    specs/              # SDD: FR-1..FR-5 detailed specs
    ADRs/
  schemas/
    blueprint.schema.json
    brand.schema.json
  brands/
    _base.json
    _template/
    acme.json
  prompts/
    static-system.md
    reel-system.md
  src/ | pulsecraft/    # Python CLI controller
    llm/
    tts/
    stt/
    assets/
    render_static/
  templates/static/<layout>/
  remotion/             # ReelComposition + themes
  assets/fallback/
  tests/                # pytest + snapshots
  .cache/               # gitignored
  out/                  # gitignored run outputs
  .github/workflows/ci.yml
  .pre-commit-config.yaml
  .env.example
```

## Appendix B: SDD + TDD Workflow

1. Write/update `.docs/specs/FR-n-<name>.md` + JSON Schema change → review.
2. Write failing tests first (contract + unit + snapshot skeleton).
3. Implement minimal code to green.
4. `ruff` / `eslint` + `pre-commit run --all-files`.
5. `pytest` + `npm test` + Playwright snapshot posisi; `remotion` 3s smoke for video changes.
6. PR with spec link + run-manifest + sample outputs (PNG stills, MP4 probe).

Branching: `main` (protected) ← `docs/*`, `feat/*`, `fix/*`. Conventional Commits. Squash merge.

## Appendix C: Milestones & Acceptance Gates

- **M0 — PRD + specs + schemas (this branch):** PRD merged, `blueprint.schema.json` + `brand.schema.json` drafted.
- **M1 — LLM blueprint:** FR-1 with fallback tests green, fixture blueprints checked in.
- **M2 — Static engine:** FR-2 + FR-5 static; 2 PNG sizes exact, golden snapshots approved.
- **M3 — Asset pipeline:** FR-4 TTS→Whisper→Pexels with cache + fallback tests.
- **M4 — Reel engine:** FR-3 30s Reel in 1–3 min on ref. hardware, caption sync verified.
- **M5 — E2E + hardening:** prompt→PNGs+MP4 one command, docs/runbook, CI green.

## Appendix D: Glossary

- **Blueprint:** Versioned JSON layout contract emitted by LLM, validated before render.
- **Brand pack:** Per-client tokens (colors/fonts/logo/voice).
- **Kinetic typography:** Word-by-word caption highlight synced to VO timestamps.
- **Golden snapshot:** Approved reference PNG for visual regression.
- **Run-manifest:** Per-run JSON with models, timings, hashes, fallbacks taken.

---

*End of PRD v0.1.0 — Next: `.docs/specs/FR-1..FR-5` detailed specs + JSON Schemas.*
