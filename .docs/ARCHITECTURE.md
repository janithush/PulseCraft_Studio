# PulseCraft Studio — System Architecture Specification

**Project:** PulseCraft Studio — Social Media Content Automation Engine
**Version:** 0.1.0 (Initial Draft)
**Status:** Draft — `docs/architecture-spec`
**Owners:** Senior Software Architect
**Date:** 2026-09-30
**Methodology:** Spec-Driven Development (SDD) + Test-Driven Development (TDD)
**Parent Spec:** `.docs/PRD.md` v0.1.0 (FR-1 … FR-5, NFR-1 … NFR-4, R1 … R8)

---

## Table of Contents

- [1. High-Level Architecture Overview](#1-high-level-architecture-overview)
- [2. Repository Directory Layout](#2-repository-directory-layout)
- [3. Strict JSON Blueprint Schemas](#3-strict-json-blueprint-schemas)
- [4. Subsystem Deep Dives](#4-subsystem-deep-dives)
  - [4.1 Dynamic OpenRouter LLM Orchestration & Model Registry](#41-dynamic-openrouter-llm-orchestration--model-registry)
  - [4.2 Dynamic Code Template Engine](#42-dynamic-code-template-engine)
  - [4.3 Static Post Renderer (Playwright)](#43-static-post-renderer-playwright)
  - [4.4 Short-Form Video Renderer (Remotion)](#44-short-form-video-renderer-remotion)
  - [4.5 Audio & Asset Supply Pipeline](#45-audio--asset-supply-pipeline)
  - [4.6 Feature Toggles & API Guardrails Engine](#46-feature-toggles--api-guardrails-engine)
- [5. Testing Strategy (TDD Framework)](#5-testing-strategy-tdd-framework)
- [6. CI/CD & Code Quality Pipeline](#6-cicd--code-quality-pipeline)
- [Appendix A: End-to-End Sequence & Interfaces](#appendix-a-end-to-end-sequence--interfaces)
- [Appendix B: Traceability to PRD](#appendix-b-traceability-to-prd)
- [Appendix C: Glossary](#appendix-c-glossary)

---

## 1. High-Level Architecture Overview

### 1.1 Design Principles (from PRD §1.4)

1. **Brand-agnostic:** no hardcoded brand; tokens + templates are swappable config.
2. **Zero-subscription core path:** OpenRouter free-tier, Kokoro (local), Faster-Whisper INT8 (local CPU), Pexels free-tier, Playwright + Chromium, Remotion + FFmpeg. Paid APIs forbidden in core path.
3. **Contract-first:** LLM output is a versioned JSON Blueprint validated by JSON Schema (draft 2020-12) before any render.
4. **Local-first, resumable, cache-aware:** every pipeline stage is independently re-runnable with content-addressed disk cache; reference hardware is Intel i5 11th Gen + 20GB RAM with background tabs open (PRD NFR-1).

### 1.2 System Block Diagram

```text
┌──────────────┐   ┌──────────────────────────────┐   ┌────────────────────┐
│ Dynamic      │   │ OpenRouter LLM Orchestration │   │ JSON Blueprint     │
│ Prompt Input │──▶│ + Dynamic Model Registry     │──▶│ (versioned,        │
│ CLI / config │   │ Script/Headline Gen (a)      │   │ schema-validated)  │
│ brand pack   │   │ Blueprint Translation (b)    │   │ static-post|reel   │
└──────────────┘   └──────────────────────────────┘   └────────┬───────────┘
                                                               │
                                                               ▼
┌──────────────┐   ┌──────────────────────────────┐   ┌────────────────────┐
│ Final Export │   │ Render Engine                │   │ Asset Pipeline     │
│ out/<run-id>/│◀──│ Static: Playwright+Chromium  │◀──│ Kokoro TTS (VO)    │
│ 2×PNG + MP4  │   │ Video: Remotion+FFmpeg       │   │ Whisper INT8 (ts)  │
│ meta/manifest│   │ + Dynamic Template Engine    │   │ Pexels (img/video) │
└──────────────┘   └──────────────────────────────┘   └────────────────────┘
        ▲                         ▲                              ▲
        │         ┌───────────────┴───────────────┐              │
        └─────────│ Brand packs + Template packs  │──────────────┘
                  │ brands/*.json + templates/    │
                  │ schemas/*.schema.json         │
                  └───────────────────────────────┘
```

Mermaid equivalent (for docs renderers supporting it):

```mermaid
flowchart LR
  A[Dynamic Prompt Input<br/>CLI + brand pack] --> B[OpenRouter LLM Orchestration<br/>Model Registry<br/>(a) Script/Headline (b) Blueprint]
  B --> C[JSON Blueprint<br/>blueprint/v1<br/>schema-validated]
  C --> D[Asset Pipeline<br/>Kokoro TTS + Whisper INT8 + Pexels]
  D --> E[Render Engine<br/>Playwright PNG + Remotion MP4<br/>Dynamic Template Engine]
  E --> F[Final Export<br/>out/run-id: PNGx2 + MP4 + meta]
```

### 1.3 End-to-End Data Flow (normative)

`Dynamic Prompt Input → OpenRouter LLM Orchestration → JSON Blueprint → Asset Pipeline → Render Engine → Final Export`

| # | Stage | Input | Output | Failover |
|---|-------|-------|--------|----------|
| 0 | **Dynamic Prompt Input** | `pulsecraft generate --brand acme --prompt "..." --formats png,reel`; `brands/<slug>.json`; `config/models.json` | Normalized `GenerateRequest {prompt, brand, formats, seed, modelOverrides}` | `validate-brand` gate; precise schema errors |
| 1 | **OpenRouter LLM Orchestration** | `GenerateRequest` + `prompts/*.md` | `blueprint/v1` JSON (static-post or reel) | Retry same model once → next fallback model → cached blueprint → fail with resume hint (PRD R1) |
| 2 | **JSON Blueprint** | Raw LLM text | Validated `out/<run-id>/blueprint.json` + `blueprint.hash` | JSON repair pass (strip fences, trailing commas); full-chain exhaustion = actionable error + partial preserved |
| 3 | **Asset Pipeline** | Blueprint `assets.query`, `script sentences` | `.cache/tts/<hash>.wav`, `words.json` + `.srt`, `.cache/pexels/...` + `assets/manifest.json`, `ATTRIBUTION.md` | Retry → relax query → cache reuse → bundled `assets/fallback/` → fail only on `--strict-assets` (PRD R2) |
| 4 | **Render Engine** | Blueprint + brand tokens + layout id + assets + audio/words | `square-1080x1080.png`, `vertical-1080x1350.png`, `reel-1080x1920.mp4` | Fallback gradient renders; dimension/audio asserts fail loudly |
| 5 | **Final Export** | Render artifacts | `out/<run-id>/{*.png,*.mp4,meta.json,run-manifest.json}` | Temp cleanup; LRU cache eviction >5GB |

**Canonical CLI:**

```bash
pulsecraft generate --brand acme --prompt "3 morning habits..." --formats png,reel
pulsecraft render-static --blueprint out/<run-id>/blueprint.json --brand acme
pulsecraft render-reel --blueprint out/<run-id>/blueprint.json --voice out/<run-id>/voice.wav --words out/<run-id>/words.json
pulsecraft init-brand --slug acme
pulsecraft validate-brand --brand acme
pulsecraft check-models --config config/models.json
```

All stages emit structured logs `{stage, model, ms, cache, fallback}` and per-stage timings into `meta.json` / `run-manifest.json` (PRD NFR-3.3).

---

## 2. Repository Directory Layout

Clean modular separation: Python owns orchestration/assets/static; Node.js owns video; `/templates` is fully decoupled code-as-config; tests mirror sources; caches and outputs are gitignored.

```text
PulseCraft_Studio/
  .docs/
    PRD.md
    ARCHITECTURE.md              # this file
    specs/                       # SDD: FR-1..FR-5 detailed specs
      FR-1-llm-orchestration.md
      FR-2-static-render.md
      FR-3-video-render.md
      FR-4-asset-pipeline.md
      FR-5-brand-templates.md
    ADRs/
  config/
    models.json                  # Dynamic Model Registry (no hardcoded models)
    pipeline.yaml                # stage defaults, timeouts, retries, --jobs, --fast-draft
  schemas/
    blueprint.schema.json        # blueprint/v1 (static-post + reel)
    brand.schema.json
  brands/
    _base.json                   # fallback tokens
    _template/                   # scaffolder source
    acme.json
  prompts/
    static-system.md
    reel-system.md
    headline-system.md
  src/pulsecraft/                # Python 3.12 CLI controller (Click/Typer)
    cli.py                       # generate / render-static / render-reel / init-brand / validate-brand / check-models
    llm/
      client.py                  # OpenRouter HTTP, JSON-mode, timeouts
      registry.py                # loads config/models.json, priority chains (a) + (b)
      prompts.py                 # template loader + versioning
      repair.py                  # fence-strip, JSON repair
      fallback.py                # retry + backoff + model switching
    tts/                         # Kokoro wrapper: chunker, synth, concat
    stt/                         # Faster-Whisper INT8 wrapper: words.json + .srt
    assets/
      pexels.py                  # search/download/resize, manifest, attribution
      cache.py                   # content-addressed .cache/, LRU evict
    render_static/
      tokens.py                  # brand → tokens.css
      playwright_render.py       # single Chromium instance, viewport-exact shots
      assert.py                  # PNG header dimension asserts
    brands/
      validate.py                # brand.schema validation
      merge.py                   # _base.json inheritance + warnings
    templates_mgr/               # Dynamic Code Template Engine manager
      manager.py                 # add/modify/clear/list, integrity checks
    common/
      logging.py                 # structured logs
      manifest.py                # run-manifest.json builder
      paths.py                   # pathlib-only, no hardcoded separators
  templates/                     # DECOUPLED code templates (no engine code here)
    posts/                       # HTML/CSS/Tailwind static layouts
      bold-hook-split/
        index.html
        style.css
        preview.png
        meta.json
      minimal-type/
        ...
    reels/                       # Remotion React components (video themes)
      kinetic-bold/
        ReelComposition.tsx
        theme.ts
        preview.png
        meta.json
      calm-caption/
        ...
  remotion/                      # Node.js/Remotion engine shell (imports from templates/reels/)
    package.json
    remotion.config.ts
    src/
      index.ts                   # registers compositions dynamically
      captioning/                # word-timestamp → karaoke pagination
      themes/                    # brand-token → theme props adapter
  tests/
    unit/                        # pytest: chunker, cache-key, repair, selector, token-merge
    contract/                    # schema fixtures valid/invalid (blueprint + brand)
    integration/                 # stubbed OpenRouter 429→200, stub Pexels, Whisper fixture
    e2e/                         # blueprint fixture → PNGs + asserts; 3s reel smoke
    snapshots/                   # golden PNGs + --update-snapshots workflow
    fixtures/
      blueprints/
      words/
      brands/
  assets/fallback/               # bundled gradients / stock (offline fallback)
  .cache/                        # gitignored: tts/<hash>.wav, pexels/<query-hash>/...
  out/                           # gitignored run outputs
  .github/workflows/ci.yml
  .pre-commit-config.yaml
  .env.example                   # OPENROUTER_API_KEY, PEXELS_API_KEY (never commit .env)
  pyproject.toml                 # ruff, pytest, coverage gates
```

**Dependency rules (enforced by review, not just convention):**

- `src/pulsecraft/**` never imports from `templates/**` as Python modules — it *loads* them as data (HTML/CSS/TSX paths + `meta.json`). Rendering pipeline code is immutable to template add/modify/clear.
- `remotion/src/**` never hardcodes a theme — it receives `{script, scenes, audioSrc, words, brandTokens}` props (PRD FR-3.1).
- `tests/**` mirrors `src/**`; no production code imports from `tests/`.
- `.cache/` and `out/` are never committed; model downloads documented with sizes (PRD NFR-1.3).

---

## 3. Strict JSON Blueprint Schemas

All LLM output MUST validate against `schemas/blueprint.schema.json` (JSON Schema draft 2020-12, `version: "blueprint/v1"`) before render. Two blueprint `type`s share an envelope and diverge in payload.

### 3.1 Envelope (common)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pulsecraft.studio/schemas/blueprint.schema.json",
  "title": "Blueprint",
  "type": "object",
  "required": ["version", "type", "brand", "seed"],
  "properties": {
    "version": { "const": "blueprint/v1" },
    "type": { "enum": ["static-post", "reel"] },
    "brand": { "type": "string", "pattern": "^[a-z0-9-]{2,32}$" },
    "seed": { "type": "integer" },
    "layout": { "type": "string" },
    "style": {
      "type": "object",
      "properties": {
        "palette": { "type": "string" },
        "font": { "type": "string" }
      }
    }
  },
  "allOf": [
    { "$ref": "#/$defs/staticPost" },
    { "$ref": "#/$defs/reel" }
  ],
  "$defs": { "...": "see below (if/then on .type)" }
}
```

Validation uses `if: {properties: {type: {const: ...}}}` / `then: required [...]`. Persisted blueprints MUST pass at 100% (PRD AC FR-1).

### 3.2 Post Blueprint — `type: "static-post"` (1080×1080 Square & 1080×1350 Vertical)

One blueprint drives **both** canvases. Renderer produces two PNGs; per-canvas overrides are optional.

```json
{
  "version": "blueprint/v1",
  "type": "static-post",
  "brand": "acme",
  "seed": 42,
  "layout": "bold-hook-split",
  "canvas": ["1080x1080", "1080x1350"],
  "copy": {
    "hook": "3 Morning Habits That Burn Fat",
    "sub": "No gym. No crash diet.",
    "cta": "Save + Follow for Day 2"
  },
  "style": { "palette": "brand.primary", "font": "brand.display" },
  "assets": { "query": "healthy breakfast bright", "provider": "pexels", "count": 3, "orientation": "any" },
  "constraints": { "maxHookChars": 120, "safeAreaPx": 80, "minContrast": 4.5 }
}
```

Normative schema fragment (`$defs.staticPost`, applied when `type == "static-post"`):

- `layout` (required, string): MUST match `templates/posts/<layout>/meta.json::layoutId`.
- `canvas` (required): `{"type":"array","minItems":1,"items":{"enum":["1080x1080","1080x1350"]}}`. Default `["1080x1080","1080x1350"]`.
- `copy.hook` (required, 1–120 chars), `copy.sub` (≤140), `copy.cta` (≤60).
- `assets.provider` const `"pexels"` in v1; `count` 1–6; `orientation` enum `any|square|portrait|landscape`.
- `constraints.minContrast` default `4.5`; renderer warns (never silently passes) on violation.

Renderer asserts (PRD FR-2.6): PNG headers exactly `1080×1080` and `1080×1350`; long-hook (120 chars) MUST NOT overflow (auto-fit/clamp).

### 3.3 Reel Blueprint — `type: "reel"` (1080×1920 MP4 with audio tracks & word-level caption timestamps)

```json
{
  "version": "blueprint/v1",
  "type": "reel",
  "brand": "acme",
  "seed": 7,
  "layout": "kinetic-bold",
  "durationTargetSec": 30,
  "hook": "Stop skipping breakfast",
  "script": [
    { "id": "s1", "voText": "Stop skipping breakfast.", "captionBudget": 4 },
    { "id": "s2", "voText": "Three protein mornings change everything.", "captionBudget": 6 }
  ],
  "scenes": [
    { "id": "scene-1", "scriptRef": "s1", "assetQuery": "oatmeal bowl bright", "kind": "image", "durationSec": 4 },
    { "id": "scene-2", "scriptRef": "s2", "assetQuery": "gym sunrise run", "kind": "image", "durationSec": 5 }
  ],
  "audio": { "voice": "brand.voice", "speed": 1.0, "sampleRateHz": 22050, "backgroundMusic": null },
  "captions": { "maxWordsPerLine": 4, "style": "karaoke", "safeAreaPx": 220 },
  "assets": { "provider": "pexels", "orientation": "portrait" }
}
```

Normative schema fragment (`$defs.reel`):

- `layout` MUST match `templates/reels/<theme>/meta.json::themeId` (e.g. `kinetic-bold`).
- `durationTargetSec` enum `15|30|60` (default 30); post-render assert duration within ±0.5s of VO length (PRD FR-3.6).
- `script[].voText` 1–500 chars each (aligns with TTS chunking); `captionBudget` bounds words per sentence.
- `scenes[].kind` enum `image|video`; `durationSec` > 0; sum SHOULD cover `durationTargetSec` (tolerance + VO stretch).
- `audio.sampleRateHz` minimum 16000; `speed` 0.5–2.0.
- **Word-level timestamps are NOT in the blueprint** — they are produced by Faster-Whisper as `words.json`:

```json
{ "words": [{ "word": "Stop", "start": 0.12, "end": 0.34 }], "model": "base-int8", "estimated": false }
```

`estimated: true` flags the `--no-whisper` uniform-timing fallback. Caption engine requires monotonic times, ≥95% word coverage on fixtures, drift <150ms (PRD FR-4 AC-3, FR-3 AC-2). Video composition props = `{script, scenes, audioSrc, words, brandTokens}` at fixed `1080×1920 @30fps` (PRD FR-3.1). Post-render asserts: resolution, audio-track presence via `ffprobe`, duration tolerance.

---

## 4. Subsystem Deep Dives

### 4.1 Dynamic OpenRouter LLM Orchestration & Model Registry

**Goal (PRD FR-1):** no hardcoded models. Users register custom model identifiers, probe connectivity, and set independent fallback chains for (a) Script/Headline Generation and (b) JSON Blueprint Translation.

**Config — `config/models.json` (versioned, user-editable):**

```json
{
  "version": "models/v1",
  "openrouter": { "baseUrl": "https://openrouter.ai/api/v1", "timeoutMs": 30000, "retriesPerModel": 1 },
  "tasks": {
    "scriptHeadline": { "chain": ["deepseek/deepseek-chat-v3-0324:free", "meta-llama/llama-3.3-70b-instruct:free"] },
    "blueprintTranslate": { "chain": ["deepseek/deepseek-chat-v3-0324:free", "google/gemini-2.0-flash-001"] }
  },
  "registry": {
    "deepseek/deepseek-chat-v3-0324:free": { "label": "DeepSeek V3", "status": "unknown", "lastChecked": null },
    "meta-llama/llama-3.3-70b-instruct:free": { "label": "Llama 3.3", "status": "unknown", "lastChecked": null },
    "google/gemini-2.0-flash-001": { "label": "Gemini 2.0 Flash", "status": "unknown", "lastChecked": null }
  }
}
```

**CLI UI (also editable as raw JSON):**

```bash
pulsecraft models add "vendor/custom-model:free" --label "Custom" --for scriptHeadline,blueprintTranslate
pulsecraft check-models                 # probes each id via OpenRouter /models + minimal chat ping
# ✔ deepseek/... Connected (812ms)   ✘ vendor/broken Failed (401 unauthorized)
pulsecraft models set-chain --task scriptHeadline --chain "vendor/custom-model:free,deepseek/...,meta-llama/..."
pulsecraft generate --prompt "..." --model-override "vendor/custom-model:free"   # one-shot override
```

- `src/pulsecraft/llm/registry.py` loads and validates `models.json`; unknown ids allowed (user-entered) but flagged `status: unknown` until `check-models` reports `Connected`/`Failed` with latency + reason; results persisted with `lastChecked`.
- `client.py` enforces JSON-mode/structured output, low temperature, prompt versions from `prompts/` (brand voice tokens + "JSON only"); `repair.py` strips fences/trailing commas; `fallback.py` does exponential backoff + jitter, auto-switch with logged reason, preserves partials.
- Secrets: `OPENROUTER_API_KEY` from `.env` only; keys never logged; per-model cost/latency logged even if $0 (PRD FR-1.6).
- Default seed chain mirrors PRD (`deepseek-v3 → llama-3.3 → gemini-2.0-flash`) but ships as *data*, replaceable without code change.
- Tests: stubbed HTTP sequence 429→200 proves auto-switch (PRD AC-1); contract tests reject unrepaired malformed output; golden blueprint fixtures checked in at M1.

### 4.2 Dynamic Code Template Engine

**Goal (PRD FR-5 + renderer decoupling):** users add/modify/clear code templates dynamically; core pipeline never changes.

**Locations:**

- `/templates/posts/<layout>/` — `index.html` + `style.css` (Tailwind allowed only as prebuilt/offline-safe CSS) + `preview.png` + `meta.json {layoutId, displayName, safeAreas, supportedCanvas, version}`.
- `/templates/reels/<theme>/` — `ReelComposition.tsx` + `theme.ts` + `preview.png` + `meta.json {themeId, displayName, fps, size, version}`.

**Manager — `src/pulsecraft/templates_mgr/manager.py`:**

```bash
pulsecraft templates list --kind posts|reels
pulsecraft templates add --kind posts --from ./my-layout/ --id bold-hook-split-v2
pulsecraft templates preview --kind posts --id bold-hook-split-v2 --brand acme   # renders golden still
pulsecraft templates clear --kind reels --id calm-caption --force
```

- `add` validates `meta.json` + required files + offline safety (no remote `<link>`/CDN scripts; fonts bundled); `modify` is file-edit + `preview` re-gold; `clear` removes dir + prunes references in manifests (never deletes engine code).
- Engine resolves `blueprint.layout` → template dir at runtime; missing id = actionable error listing available ids; brand tokens injected as `tokens.css` (static) / `theme props` (video) from single source of truth (`brands/<slug>.json` + `_base.json` inheritance).
- `init-brand --slug acme` scaffolds from `brands/_template/` + runs `validate-brand` + golden smoke; `validate-brand` enforces `brand.schema.json` (bad hex/missing font = precise errors).
- Tests: brand-swap snapshot (same blueprint × 2 brands → themed diff, zero engine diff), invalid-brand rejection, template add/clear round-trip.

#### 4.2.1 Four-Layer Dynamic Layout Strategy (M2)

Pre-built templates cover the common cases; the LLM covers the long tail. Layer resolution order is fixed and logged per render:

| Layer | Name | Mechanism | When used |
|-------|------|-----------|-----------|
| L1 | Conditionals | Jinja2 `{% if %}` blocks auto-hide empty/optional fields (sub, cta, bullets, badge, image) — missing data collapses without trace | Every render |
| L2 | Loops / Arrays | Jinja2 `{% for %}` over `bullets[]` / `hashtags[]` with per-item clamp | Bullet lists, hashtag rows |
| L3 | Pre-built Variants | `blueprint.layout` → `templates/posts/<layout>/` selected from the validated catalog | Layout id matches a catalog pack |
| L4 | Full Dynamic LLM Layout Generation (fallback) | `PROMPT_EXPANSION` task generates raw HTML/Tailwind for the blueprint's canvas sizes; rendered through the same sandboxed Playwright pipeline, optionally promoted via `templates add` | No catalog layout satisfies `layout` / `variantHint`, or L3 validation fails |

Rules (normative): L1–L3 are pure data hydration — no LLM at render time, deterministic for a fixed blueprint + brand. L4 output MUST pass the same offline-safety lint (no remote URLs, bundled fonts), dimension asserts, and contrast-warn gate as L3. The used layer + `model_used` (L4) are recorded in `run-manifest.json` for audit.

#### 4.2.2 Visual Template Inspector & Tag Previewer (M2)

`pulsecraft templates inspect <name>` hydrates a template's placeholders with visual badge tags (`[Headline Here]`, `[Hook Here]`, `[CTA Here]`, `[Bullet 1..n]`, `[Image Here]`) so authors judge layout/overflow without real copy:

- `inspect_template(name: str)` (in `templates_mgr/manager.py`) returns `{html, schema}` where `schema = {required: [...], optional: [...]}` derived from the Jinja2 AST plus `meta.json` placeholder declarations. Required = referenced without a default or `{% if %}` guard; optional = guarded or defaulted.
- Preview HTML is the real template rendered with badge-tag values (identical CSS, both canvas sizes); the CLI prints the placeholder schema table and writes the preview HTML (PNG preview via the static renderer is optional).
- Mismatches (template uses an undeclared variable, `meta.json` declares an unused one) surface as warnings in the inspect output — never hard errors.

### 4.3 Static Post Renderer (Playwright)

**Goal (PRD FR-2):** pixel-perfect FB & IG PNGs from dynamic HTML/CSS templates.

- `render_static/renderer.py` (`StaticPostRenderer`, Playwright Python API): single Chromium instance, one viewport at a time (memory ceiling, PRD NFR-1.2); viewports `1080×1080` and `1080×1350` (deviceScaleFactor 2 or 1080 CSS px), `waitUntil: networkidle` + font-ready wait, scrollbars hidden, deterministic clip; `file://` cached Pexels assets only (offline-safe); fallback solid/gradient if missing (logged).
- `tokens.py` merges `brands/<slug>.json` over `_base.json` → `tokens.css` (colors, fonts, logo path); `assert.py` checks PNG headers post-export, fails loudly on mismatch.
- Text safety: headline auto-fit/clamp (shrink or ellipsis, never overflow), safe-area padding per `meta.json`, contrast helper warns on <4.5:1 body.
- 4-layer resolution (see §4.2.1): hydrate L1–L3 from the blueprint; on unknown `layout` / `variantHint` mismatch, trigger the `PROMPT_EXPANSION` LLM task (L4) to generate raw HTML/Tailwind, lint it offline-safe, and render through the identical pipeline.
- CLI: `pulsecraft render post --blueprint out/blueprint.json --brand acme --out out/<run-id>` → `square-1080x1080.png`, `vertical-1080x1350.png`, `meta.json {dimensions, hashes, durationMs, templateId, brandSlug, layer}`.
- Perf (PRD NFR-2.1): warm-cache E2E <60s target; PNG shot <15s/size; per-stage timings recorded. Flakiness guards (PRD R4): bundled fonts, single instance, one screenshot retry.

### 4.4 Short-Form Video Renderer (Remotion)

**Goal (PRD FR-3):** 1080×1920 MP4 with synchronized VO + word-by-word kinetic typography, no video editor.

- `remotion/` shell: size-parametric compositions (1080×1920@30fps default; also 1080×1350, 1080×1080 per §4.4.2); props `{script, scenes, audioSrc, words, brandTokens, preset, canvas}`; preset components imported dynamically from `/templates/reels/<preset>`; per-scene B-roll (multi-source §4.5) with Ken Burns, crossfades, 0–3s hook card + CTA end card + progress bar (preset-dependent).
### 4.4 Short-Form Video Renderer (Remotion)

**Goal (PRD FR-3):** 1080×1920 MP4 with synchronized VO + word-by-word kinetic typography, no video editor.

- `render_video/renderer.py` (`VideoReelRenderer`, M3): accepts `{blueprint, preset, flags, platform}`; resolves platform canvases (§4.4.2), enforces guardrails (§4.6), builds Remotion input props `{script, scenes, audioSrc, words, brandTokens, preset, canvas}`, shells `npx remotion render`, asserts MP4 (resolution, duration ±0.5s of VO, `ffprobe` audio track), writes `meta.json`.
- Caption engine (`remotion/src/captioning/`): Faster-Whisper `words[]` → karaoke active-word highlight, `maxWordsPerLine` pagination, safe-area (default 220px) + stroke/shadow for contrast; drift <150ms vs fixture.

#### 4.4.1 Video Style Presets (M3)

Three preset components under `templates/reels/<preset>/` (`ReelComposition.tsx` + `theme.ts` + `preview.png` + `meta.json {themeId, sizes, version}`), selected via `--preset`:

| Preset | Style | Signature |
|--------|-------|-----------|
| `alex-hormozi` | Fast kinetic typography | Word-by-word yellow/green highlight, punchy pop animations, progress bar |
| `faceless-docu` | Cinematic documentary | Dark gradient overlay, elegant serif typography, slow-zoom (Ken Burns) B-roll |
| `b-roll-centric` | Visual-first | Content-matching full-bleed background layers, clean bottom-aligned subtitles |

**Hybrid Prompt Customization:** `blueprint.style.presetTweaks` (e.g. `{highlight: "green", pace: "calm"}`) may adjust preset tokens (colors, pacing, caption position) within guardrails — tweaks never change composition geometry, audio routing, or canvas sizes. Unknown tweak keys are ignored with a warning.

#### 4.4.2 Multi-Platform Aspect Ratios (M3)

`--platform` selects canvases; `all` renders every size in one command:

| Flag | Canvases | Use |
|------|----------|-----|
| `--platform fb` | 1080×1080 (1:1) + 1080×1920 (9:16) | Facebook Feed + Reels |
| `--platform ig` | 1080×1350 (4:5) + 1080×1920 (9:16) | Instagram Feed + Reels |
| `--platform all` | 1080×1080 + 1080×1350 + 1080×1920 | Both feeds + Reels simultaneously |

Preset components are size-parametric (`width`/`height` props); caption safe-areas scale per canvas. Per-canvas outputs + asserts land in `out/<run-id>/<canvas>/`.
- Audio: Kokoro VO laid precisely; BGM auto-ducked (see §4.5); SHOULD normalize −14 LUFS.
- CLI: `pulsecraft render reel --blueprint ... --preset alex-hormozi --platform all --brand acme --out out/<run-id>` → per-canvas MP4s via `npx remotion render` with progress logs + resumable intermediates; asserts: resolution, duration ±0.5s of VO, `ffprobe` audio-track presence; missing B-roll → gradient fallback (logged, PRD AC-3).
- Perf (PRD NFR-2.2): 30s Reel in 1–3 min warm on ref hardware; 60s SHOULD <5min; single-job default; `--fast-draft` (tiny whisper, reduced scale) for iteration; 3s render-smoke in CI (PRD R5).

### 4.5 Audio & Asset Supply Pipeline

**Goal (PRD FR-4):** zero-subscription, cache-first, independently resumable stages under `.cache/`.

1. **Kokoro TTS → VO:** sentence-aware chunking (≤~500 chars), per-brand voice+speed, concat WAV (≥16kHz), cache key `hash(text+voice+speed)` at `.cache/tts/`; offline after install; `--reuse-cache` default on, `--refresh-assets` to force.
2. **Faster-Whisper INT8 → timestamps:** `base` default (`--whisper-model` override; `--fast-draft` → `tiny`), CPU INT8; emits `words.json {words:[{word,start,end}], model, estimated}` + `.srt`; `--no-whisper` fallback = uniform timing flagged `estimated:true`; fixture bar ≥95% coverage + monotonic.
3. **Pexels → visuals:** `PEXELS_API_KEY` via `.env`; blueprint query + orientation filter (portrait preferred for reels), download + resize/compress to `.cache/pexels/<query-hash>/`; `assets/manifest.json {photographer, url, license}` + per-run `ATTRIBUTION.md`; failure path: backoff retry → relaxed query → cache reuse → `assets/fallback/` → continue (hard fail only with `--strict-assets`).
4. **SFX/BGM + auto-ducking (M3):** CC0 SFX from Freesound API (`FREESOUND_API_KEY`) and BGM from Pixabay Audio API (`PIXABAY_API_KEY`), keyed by blueprint `audioTags[]`; ducking curve — BGM at **15%** under speech, **35%** during pauses (200ms attack/release smoothing); mixed track cached at `.cache/audio/mix-<hash>.wav`. Disabled → stage skipped (see §4.6).
5. **Multi-source B-roll + local overrides (M3):** providers tried in order Pexels → Pixabay (`PIXABAY_API_KEY`) → Openverse (no key), first hit wins per scene; `[Visual: my-product.png]` script tags load verbatim from `input/visuals/` (path-traversal guarded, missing file = warning + provider fallback).
- Airplane-mode re-run (post-first-cache) MUST succeed for TTS+Whisper (PRD AC-1); Pexels 429/5xx simulation MUST still render via fallback (PRD AC-2).

### 4.6 Feature Toggles & API Guardrails Engine (M3)

**Rule (normative): system toggles strictly override LLM prompts.** If a feature/API is disabled, blueprint or prompt requests for it are ignored — with a logged warning — never executed.

- `config/features.json` (versioned `features/v1`): `{tts: {kokoro, edgeFallback}, stt: {whisper}, audio: {sfx, bgm, ducking}, media: {pexels, pixabay, openverse, localOverrides}, render: {remotion, dynamicL4}}`, each `{enabled: bool}`; CLI flags (`--no-bgm`, `--no-sfx`, `--no-ducking`, `--feature key=value`) override file values for the run only.
- `common/feature_flags.py`: `FeatureFlags.load()` + `from_cli(overrides)`; `enabled("audio.bgm")`; `guard(feature, requested) -> bool` (= enabled AND requested); `enforce(blueprint) -> (blueprint, warnings)` strips disabled requests (e.g. `audioTags` dropped when SFX/BGM off, `layout` forced L3-only when `render.dynamicL4` off).
- Cost/key guardrails: providers without configured keys are auto-treated as disabled (warning, no crash); `--strict-assets` re-escalates to hard fail.

### 4.7 M4 Asset Caching & Hash Indexing Architecture (`.cache/assets/`)

**Goal (PRD FR-4, R2):** disk-backed, content-addressed cache for every remote media/audio byte so repeat runs never re-hit the network.

- `src/pulsecraft/assets/cache.py` — `AssetCache(cache_dir=".cache/assets/")`:
  - **Hash-indexed layout:** `key = sha256("provider|query|url")[:16]`; bytes stored at `.cache/assets/<provider>/<key><ext>`; sidecar index at `.cache/assets/index.json` mapping `key → {provider, query, url, path, size_bytes, sha256, fetched_at}`.
  - **Providers covered:** Pexels, Pixabay, Freesound, Openverse (media + audio). `fetch_or_download(provider, query, url, downloader)` checks the index + file existence first (cache **hit** → return path, log `cache: hit`); on **miss** it calls `downloader()` once, writes bytes atomically, updates `index.json`, logs `cache: miss`.
  - **Duplicate-request prevention:** identical `(provider, query, url)` tuples resolve to the same key; concurrent in-process callers share the on-disk entry — no second HTTP GET.
  - **Eviction/clearing:** `clear() → int` deletes the whole `.cache/assets/` tree (exposed as `pulsecraft assets clear-cache`); `evict_lru(max_bytes)` drops oldest `fetched_at` entries first (5GB default budget, LRU). `list_cached()` returns index rows for `pulsecraft assets list`.
  - **Resilience:** corrupt/missing index is rebuilt by directory scan; partial downloads use temp-file + rename; every hit/miss is structured-logged `{stage: "assets.cache", provider, key, hit, ms}`.

### 4.8 M4 Local Asset Directory Indexer (`input/visuals/` + `input/audio/`)

**Goal:** creator-dropped files override remote fetch with zero config; the indexer makes them discoverable + attributable.

- `src/pulsecraft/assets/local_mgr.py` — `index_local_assets(visuals_dir="input/visuals", audio_dir="input/audio")`:
  - **Auto-index:** recursive scan of both dirs (created with `.gitkeep`; gitignored content). Each file yields `{name, path, kind: image|video|audio, size_bytes, width?, height?, duration_sec?, sample_rate_hz?}`.
  - **Metadata extraction:** images/video thumbnails via Pillow (`Image.open` → `width/height`); WAV via `wave` (`frames/rate` → `duration_sec/sample_rate_hz`); MP3/OGG/M4A report `duration_sec=None` unless probed (no hard fail — `None` + warning). Unknown extensions are skipped with a warning, never an exception.
  - **Tag/file matching:** `find_for_tag(tag)` strips `[Visual: ...]` wrappers, matches case-insensitively by basename (`hero.png` == `input/visuals/hero.png`), traversal-guarded (`Path(name).name` containment check — `../escape.png` → `None`). `resolve_local_override()` in `media_fetcher.py` delegates here.
  - **CLI surfacing:** `pulsecraft assets list` prints indexed local assets (name, kind, dims/duration) alongside cached remote assets from `AssetCache.list_cached()`.

### 4.9 M4 Unified Template Manager Registry (Posts + Reels)

**Goal (PRD FR-5):** one registry interface for Static Post (HTML/Jinja2) and Video Reel (Remotion React) packs with strict manifest contracts.

- `src/pulsecraft/templates_mgr/registry.py` — `UnifiedTemplateRegistry(root="templates")` wraps the M2 `TemplateManager`:
  - **`list_all_templates() → list[TemplateEntry]`** scans `templates/posts/` (kind `post`) + `templates/reels/` (kind `reel`); each entry `{name, kind, path, meta}` sorted by `(kind, name)`.
  - **`get_template_schema(name) → dict`** resolves `name` across both kinds (exact match; ambiguous names prefer `post` with a warning); returns `{"name", "kind", "manifest": <meta.json>, "placeholders": {required, optional}}` — for posts from Jinja2 AST + `meta.json`, for reels from `meta.json` (`themeId`, `sizes`/`size`, `tweaks`).
  - **`validate_all_templates() → dict[str, list[str]]`** runs strict JSON-schema validation (via `jsonschema`, draft 2020-12) on every `meta.json`:
    - Post manifest: requires `layoutId, displayName, version, engine==jinja2, supportedCanvas[1..], safeAreas, placeholders{required[], optional[]}`.
    - Reel manifest: requires `themeId, displayName, version, fps>=1` plus `size` or `sizes[]` matching `^\d+x\d+$`.
    - Plus M2 checks: `index.html`/`style.css` presence (posts) or `ReelComposition.tsx`/`theme.ts` presence (reels), offline-safety (no `https?://`), placeholder declared-vs-used warnings. Clean pack → `[]`; failures are precise (`"<name>: meta.json invalid: 'layoutId' is required"`).
  - **CLI:** `pulsecraft templates validate` prints per-template PASS/FAIL + warnings and exits nonzero iff any manifest fails strict validation.

### 4.10 M5 End-to-End Campaign Orchestrator (`src/pulsecraft/pipeline/orchestrator.py`)

**Goal (PRD App. C M5):** one deterministic prompt→outputs run wiring M1→M4 with per-stage timings, resume-friendly artifacts, and a clean output bundle.

- `CampaignPipeline` connects all sub-systems (collaborators injectable for headless tests):
  1. **LLM expand (M1):** `TaskOrchestrator.execute(COPYWRITING, prompt)` → campaign copy, then `execute(JSON_BLUEPRINT_CONVERSION, copy)` → post/reel JSON blueprints. LLM failure → deterministic offline fallback blueprint (seeded hook/sub/cta + script/scenes) so `generate campaign` never hard-crashes without keys; `model_used` + `fallback_taken` recorded.
  2. **Asset resolve (M4):** every `assets.query` / `scenes[].assetQuery` / `[Visual: ...]` tag goes through `MediaFetcher.fetch_scene()` (Pexels→Pixabay→Openverse→fallback, local `input/visuals/` override first) backed by `AssetCache` (`.cache/assets/`, hit/miss logged). Results land in `assets.json` + `ATTRIBUTION.md`; failures degrade to bundled fallback with warnings (hard fail only if caller passes `strict=True`).
  3. **Static render (M2):** `StaticPostRenderer.render_post()` with 4-layer resolution (L1 conditionals/L2 loops → L3 catalog `layout` → L4 `PROMPT_EXPANSION` fallback); emits `square-1080x1080.png`, `vertical-1080x1350.png` + `static-meta.json`.
  4. **Video render (M3):** `VideoReelRenderer.render_reel()` (Kokoro TTS → Whisper timestamps → BGM/SFX ducking 15%/35% → Remotion preset per `--preset`/`--platform`); emits per-canvas MP4s + `reel-meta.json`. Disabled toggles skip stages with warnings (guardrails §4.6).
  5. **Bundle:** clean `output/<run-id>/` tree — `{blueprint-post.json, blueprint-reel.json, assets.json, ATTRIBUTION.md, *.png, *.mp4, *-meta.json, run-manifest.json}`. `run-manifest.json` = `{run_id, brand, seed, prompt, models, timings_ms, warnings, artifacts}`; `--seed` makes blueprint bytes deterministic.
- **Failure semantics:** per-stage try/except → warnings + fallback artifacts; full-run failure raises `CampaignError` with actionable hint (`--strict-assets`, `--refresh-assets`, resume path). All paths `pathlib`; all network calls timeout + retry + log.

### 4.11 M5 Unified CLI Architecture

**Rule:** one `pulsecraft` entrypoint; nouns are groups, verbs are commands; every run is reproducible from flags + config.

```bash
pulsecraft generate campaign --prompt "..." --brand acme --formats png,reel \
  --preset alex-hormozi --platform all --seed 42 --out output
pulsecraft models status            # registry + task chains (M1)
pulsecraft render post --blueprint ... --brand acme --out output/<run-id>
pulsecraft render reel --blueprint ... --preset ... --platform all
pulsecraft templates list|inspect|validate
pulsecraft assets list|clear-cache
pulsecraft check-models
```

- `src/pulsecraft/cli.py` — `main` group + `generate` group (`campaign` command builds `CampaignRequest` from flags and runs `CampaignPipeline().run()`); `models`, `render`, `templates`, `assets` groups unchanged from M1–M4. `--formats png|reel|both` selects static/video/both; `--seed` seeds fallback blueprints; `--strict-assets` re-escalates asset fallback to hard fail.
- `src/pulsecraft/pipeline/` owns orchestration; `cli.py` owns parsing/echo only (thin-wrapper rule, enforced by review).

---

## 5. Testing Strategy (TDD Framework)

Red → Green → Refactor. No FR code without failing contract/unit tests first (PRD NFR-4.2). Coverage gates fail CI on layout contracts and renderers.

| Layer | Runner | Scope | Examples |
|-------|--------|-------|----------|
| **Unit (Python)** | `pytest` | chunker, cache-key, JSON repair, model selector/chain, token merge, SRT format, pagination/interpolation | `tests/unit/test_repair.py`, `test_registry.py`, `test_token_merge.py` |
| **Unit (Video)** | `vitest` | caption pagination, timestamp interpolation, theme adapter | `remotion/src/captioning/*.test.ts` |
| **Contract** | `pytest` + `ajv`/`check-jsonschema` | `blueprint.schema.json` + `brand.schema.json` valid/invalid fixtures | `tests/contract/`, `tests/fixtures/blueprints/` |
| **Integration** | `pytest` | stubbed OpenRouter 429→200 fallback; stub Pexels 429→fallback; Whisper golden fixture (±tolerance) | `tests/integration/` |
| **Visual regression** | **Playwright** | screenshot vs golden PNGs; intentional change requires `--update-snapshots` + review | `tests/snapshots/`, `tests/e2e/test_static.py` |
| **Render smoke** | Playwright + `remotion render --dry`/stills + `ffprobe` | blueprint fixture → exact PNG dims (Pillow/sharp); 3s reel → res/audio/duration asserts | `tests/e2e/test_reel_smoke.py` |
| **Fixtures/mocks** | checked-in | OpenRouter transcripts, `words.json`, brand packs, Pexels stubs | `tests/fixtures/` |

**Commands:**

```bash
pytest -q                                    # Python unit+contract+integration
pytest tests/e2e/test_static.py -q           # static E2E + dimension asserts
npx vitest run                               # Remotion unit
npx playwright test snapshots -q             # visual regression
pytest --update-snapshots                    # explicit golden refresh (review required)
npx remotion render ReelComp --dry-run       # video dry-run / stills
```

Determinism (PRD NFR-3.1): same `--seed` + pinned models + blueprint → byte-comparable blueprint; stock rotation seeded. Offline resilience, structured logs, and `run-manifest.json` asserted in E2E. Windows 10/11 first-class (`pathlib` only) + Linux CI (PRD NFR-4.3).

---

## 6. CI/CD & Code Quality Pipeline

**GitHub Actions — `.github/workflows/ci.yml` (spec):**

```yaml
name: ci
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt  # or pip install -e .[dev]
      - run: ruff check . && ruff format --check .
      - run: pytest -q --cov=src --cov-fail-under=80
  video:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci --prefix remotion
      - run: npx --prefix remotion eslint . --max-warnings=0
      - run: npx --prefix remotion prettier --check .
      - run: npx --prefix remotion vitest run
  render-smoke:
    runs-on: ubuntu-latest
    needs: [python, video]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - uses: microsoft/playwright-github-action@v1
      - run: pytest tests/contract tests/e2e/test_static.py -q
      - run: npx remotion render --dry-run  # + 3s reel smoke where feasible
```

Plus `validate-brand` + `check-jsonschema` for `schemas/*.schema.json` and golden-snapshot job with artifact upload on failure; golden updates ONLY via explicit `--update-snapshots` PR + reviewer approval. Branching: `main` (protected) ← `docs/*`, `feat/*`, `fix/*`; Conventional Commits; squash merge (per PRD App. B).

**Pre-commit — `.pre-commit-config.yaml` (spec):**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks  # .env never committed; keys redacted (PRD R7)
```

**Linters/formatters:**

- **Ruff (Python):** `ruff check` + `ruff format` via `pyproject.toml`; `pre-commit run --all-files` MUST pass before push; line length / isort rules pinned in repo.
- **ESLint + Prettier (TypeScript/React):** `eslint --max-warnings=0` + `prettier --check` under `remotion/`; templates under `/templates/reels/` linted as source (no build artifacts committed).
- Secrets: `.env.example` only; `gitleaks` gate; Pexels attribution preserved; logs redact keys.

---

## Appendix A: End-to-End Sequence & Interfaces

```text
User CLI → registry.py (chains a/b) → client.py (OpenRouter) → repair.py → schema validate
  → blueprint.json → tts/ (Kokoro) → stt/ (Whisper → words.json/srt)
  → assets/pexels.py (manifest + ATTRIBUTION) → templates_mgr (resolve layout/theme)
  → render_static (Playwright PNGs + asserts) / remotion (MP4 + ffprobe asserts)
  → out/<run-id>/ + run-manifest.json
```

Key interfaces: `GenerateRequest`, `ModelChain {task, chain[]}`, `Blueprint v1`, `Words {words[], estimated}`, `BrandTokens`, `TemplateMeta`, `RunManifest {models, timings, hashes, fallbacks}`. All paths `pathlib`; all network calls timeout + retry + log.

## Appendix B: Traceability to PRD

| PRD | Architecture |
|-----|--------------|
| FR-1 LLM | §4.1 registry + chains (a)/(b), `config/models.json`, `check-models` Connected/Failed |
| FR-2 Static | §4.3 Playwright, §3.2 post schema (1080×1080/1080×1350) |
| FR-3 Video | §4.4 Remotion 1080×1920 + karaoke, §3.3 reel schema + words.json |
| FR-4 Assets | §4.5 Kokoro + Whisper INT8 + Pexels, cache/resume |
| FR-5 Brands/Templates | §4.2 `/templates/posts` + `/templates/reels`, brand inheritance |
| NFR-1..4 | §1.1 ref hw, §4.3–4.5 budgets, §5 TDD, §6 CI |
| R1..R8 | Fallback trees §1.3, per-subsystem mitigations §4 |

Milestones align to PRD App. C: M0 (this spec + PRD) → M1 LLM → M2 static → M3 assets → M4 reel → M5 E2E.

## Appendix C: Glossary

- **Blueprint:** versioned LLM-emitted JSON contract (`blueprint/v1`), validated before render.
- **Model Registry:** `config/models.json` + CLI UI; chains for (a) script/headline and (b) blueprint translation; `Connected`/`Failed` probes.
- **Template pack:** layout (posts) or theme (reels) under `/templates/` with `meta.json`; managed without engine change.
- **Kinetic typography:** word-by-word karaoke captions synced to Whisper timestamps.
- **Golden snapshot:** approved PNG for Playwright regression.
- **Run-manifest:** per-run JSON (models, timings, hashes, fallbacks).

---

*End of Architecture v0.1.0 — Next: `.docs/specs/FR-1..FR-5` detailed specs + `schemas/*.schema.json` + `config/models.json`.*
