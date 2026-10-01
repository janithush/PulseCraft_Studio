"""M5 End-to-End Campaign Pipeline Orchestrator.

`CampaignPipeline` wires M1 (LLM) → M4 (assets/cache) → M2 (static)
→ M3 (video) into one deterministic `output/<run-id>/` bundle.
All heavy collaborators are injectable so tests run fully offline.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CampaignError(RuntimeError):
    """A pipeline stage failed unrecoverably (with an actionable hint)."""


@dataclass
class CampaignRequest:
    prompt: str
    brand: str = "acme"
    formats: str = "png,reel"
    preset: str = "alex-hormozi"
    platform: str = "all"
    seed: int = 42
    out_dir: str | Path = "output"
    strict_assets: bool = False
    run_id: str | None = None


@dataclass
class CampaignResult:
    run_dir: Path
    artifacts: dict[str, str] = field(default_factory=dict)
    post_blueprint: dict[str, Any] = field(default_factory=dict)
    reel_blueprint: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)
    manifest_path: Path | None = None


def parse_formats(formats: str) -> tuple[bool, bool]:
    """Return (want_static, want_video) for a `--formats` flag value."""
    tokens = {token.strip().lower() for token in (formats or "").split(",") if token.strip()}
    if not tokens or tokens & {"both", "all"}:
        return True, True
    want_static = bool(tokens & {"png", "post", "static", "image"})
    want_video = bool(tokens & {"reel", "video", "mp4"})
    if not want_static and not want_video:
        raise CampaignError(f"unknown --formats '{formats}'. Use png, reel, or png,reel (both).")
    return want_static, want_video


def fallback_blueprints(
    prompt: str, brand: str, seed: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Deterministic offline blueprints (seeded; no network, no keys)."""
    hook = (prompt.strip() or "Your next habit starts today")[:120]
    query = (prompt.strip() or "morning routine bright")[:60]
    post = {
        "version": "blueprint/v1",
        "type": "static-post",
        "brand": brand,
        "seed": seed,
        "layout": "bold-hook-split",
        "canvas": ["1080x1080", "1080x1350"],
        "copy": {"hook": hook, "sub": "No gym. No crash diet.", "cta": "Save + Follow"},
        "style": {"palette": "brand.primary", "font": "brand.display"},
        "assets": {"query": query, "provider": "pexels", "count": 3, "orientation": "any"},
    }
    reel = {
        "version": "blueprint/v1",
        "type": "reel",
        "brand": brand,
        "seed": seed,
        "layout": "kinetic-bold",
        "durationTargetSec": 30,
        "hook": hook,
        "script": [{"id": "s1", "voText": hook, "captionBudget": 6}],
        "scenes": [
            {
                "id": "scene-1",
                "scriptRef": "s1",
                "assetQuery": query,
                "kind": "image",
                "durationSec": 4,
            }
        ],
        "audio": {"voice": "brand.voice", "speed": 1.0, "sampleRateHz": 22050},
        "captions": {"maxWordsPerLine": 4, "style": "karaoke", "safeAreaPx": 220},
        "assets": {"provider": "pexels", "orientation": "portrait"},
    }
    return post, reel


class CampaignPipeline:
    """Deterministic M1→M4 orchestrator with per-stage timings + manifest."""

    def __init__(
        self,
        llm: Any = None,
        media: Any = None,
        static_renderer: Any = None,
        video_renderer: Any = None,
    ) -> None:
        self._llm = llm
        self._media = media
        self._static = static_renderer
        self._video = video_renderer

    def run(self, request: CampaignRequest) -> CampaignResult:
        if not request.prompt or not request.prompt.strip():
            raise CampaignError("prompt must not be empty (pass --prompt '...').")
        want_static, want_video = parse_formats(request.formats)
        run_id = request.run_id or f"run-{request.seed}-{int(time.time())}"
        run_dir = Path(request.out_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        warnings: list[str] = []
        timings: dict[str, int] = {}
        artifacts: dict[str, str] = {}
        models: list[str] = []

        # 1. LLM expand (M1) -------------------------------------------------
        started = time.perf_counter()
        post_bp, reel_bp = self._expand(request, warnings, models)
        timings["llm_ms"] = int((time.perf_counter() - started) * 1000)

        # 2. Asset resolve (M4) ----------------------------------------------
        started = time.perf_counter()
        assets = self._resolve_assets(request, post_bp, reel_bp, warnings)
        timings["assets_ms"] = int((time.perf_counter() - started) * 1000)
        assets_path = run_dir / "assets.json"
        assets_path.write_text(json.dumps(assets, indent=2), encoding="utf-8")
        artifacts["assets.json"] = str(assets_path)
        attribution_path = run_dir / "ATTRIBUTION.md"
        attribution_path.write_text(self._attribution(assets), encoding="utf-8")
        artifacts["ATTRIBUTION.md"] = str(attribution_path)

        # Persist blueprints ---------------------------------------------------
        post_path = run_dir / "blueprint-post.json"
        reel_path = run_dir / "blueprint-reel.json"
        post_path.write_text(json.dumps(post_bp, indent=2), encoding="utf-8")
        reel_path.write_text(json.dumps(reel_bp, indent=2), encoding="utf-8")
        artifacts["blueprint-post.json"] = str(post_path)
        artifacts["blueprint-reel.json"] = str(reel_path)

        # 3. Static render (M2) ------------------------------------------------
        if want_static:
            started = time.perf_counter()
            try:
                result = self._static_renderer().render_post(
                    post_bp, brand=request.brand, out_dir=str(run_dir)
                )
                for key in ("png_square", "png_vertical", "meta_path"):
                    value = getattr(result, key, None)
                    if value is not None:
                        artifacts[key] = str(value)
                warnings.extend([str(item) for item in getattr(result, "warnings", [])])
            except Exception as exc:
                raise CampaignError(
                    f"static render failed: {exc} (retry or try --layout minimal-type)"
                ) from exc
            timings["static_ms"] = int((time.perf_counter() - started) * 1000)

        # 4. Video render (M3) -------------------------------------------------
        if want_video:
            started = time.perf_counter()
            try:
                result = self._video_renderer().render_reel(
                    reel_bp,
                    brand=request.brand,
                    preset=request.preset,
                    platform=request.platform,
                    out_dir=str(run_dir),
                )
                for canvas_id, path in (getattr(result, "files", {}) or {}).items():
                    artifacts[f"reel-{canvas_id}"] = str(path)
                meta = getattr(result, "meta_path", None)
                if meta is not None:
                    artifacts["reel-meta.json"] = str(meta)
                warnings.extend([str(item) for item in getattr(result, "warnings", [])])
            except Exception as exc:
                raise CampaignError(
                    f"reel render failed: {exc} (try --preset kinetic-bold --platform all)"
                ) from exc
            timings["video_ms"] = int((time.perf_counter() - started) * 1000)

        manifest_path = run_dir / "run-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "brand": request.brand,
                    "seed": request.seed,
                    "prompt": request.prompt,
                    "preset": request.preset,
                    "platform": request.platform,
                    "formats": request.formats,
                    "models": models,
                    "timings_ms": timings,
                    "warnings": warnings,
                    "artifacts": artifacts,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        artifacts["run-manifest.json"] = str(manifest_path)
        logger.info("campaign done run=%s artifacts=%d", run_id, len(artifacts))
        return CampaignResult(
            run_dir=run_dir,
            artifacts=artifacts,
            post_blueprint=post_bp,
            reel_blueprint=reel_bp,
            warnings=warnings,
            timings_ms=timings,
            manifest_path=manifest_path,
        )

    # -- stages -------------------------------------------------------------
    def _expand(
        self, request: CampaignRequest, warnings: list[str], models: list[str]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        llm = self._llm if self._llm is not None else self._default_llm()
        if llm is None:
            warnings.append("llm unavailable: using deterministic offline blueprints")
            return fallback_blueprints(request.prompt, request.brand, request.seed)
        try:
            copy_res = llm.execute("copywriting", request.prompt)
            bp_res = llm.execute("jsonBlueprintConversion", copy_res.text)
            models.append(str(getattr(copy_res, "model_used", "unknown")))
            if getattr(bp_res, "model_used", None) not in (None, models[0]):
                models.append(str(bp_res.model_used))
            return self._split_blueprints(bp_res.text, request)
        except Exception as exc:
            warnings.append(f"llm expand failed ({exc}): using offline blueprints")
            return fallback_blueprints(request.prompt, request.brand, request.seed)

    def _split_blueprints(
        self, raw: str, request: CampaignRequest
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        fallback_post, fallback_reel = fallback_blueprints(
            request.prompt, request.brand, request.seed
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return fallback_post, fallback_reel
        if isinstance(data, dict) and "post" in data and "reel" in data:
            post = data["post"] if isinstance(data["post"], dict) else fallback_post
            reel = data["reel"] if isinstance(data["reel"], dict) else fallback_reel
            return post, reel
        if isinstance(data, dict) and data.get("type") == "static-post":
            return data, fallback_reel
        if isinstance(data, dict) and data.get("type") == "reel":
            return fallback_post, data
        return fallback_post, fallback_reel

    def _resolve_assets(
        self,
        request: CampaignRequest,
        post_bp: dict[str, Any],
        reel_bp: dict[str, Any],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        queries: list[str] = []
        assets_cfg = post_bp.get("assets", {})
        if isinstance(assets_cfg, dict) and assets_cfg.get("query"):
            queries.append(str(assets_cfg["query"]))
        for scene in reel_bp.get("scenes", []) or []:
            if isinstance(scene, dict) and scene.get("assetQuery"):
                queries.append(str(scene["assetQuery"]))
        if not queries:
            queries.append(request.prompt[:60])
        fetcher = self._media if self._media is not None else self._default_media()
        resolved: list[dict[str, Any]] = []
        for query in queries:
            try:
                asset, asset_warnings = fetcher.fetch_scene(query, strict=request.strict_assets)
                warnings.extend([str(item) for item in asset_warnings])
            except Exception as exc:
                if request.strict_assets:
                    raise CampaignError(f"asset resolve failed for '{query}': {exc}") from exc
                warnings.append(f"asset resolve failed for '{query}' ({exc}); using fallback")
                asset = {"url": "", "localPath": "", "provider": "fallback", "query": query}
            asset = dict(asset)
            asset.setdefault("query", query)
            resolved.append(asset)
        return resolved

    @staticmethod
    def _attribution(assets: list[dict[str, Any]]) -> str:
        lines = ["# Attribution", ""]
        for asset in assets:
            provider = asset.get("provider", "unknown")
            url = asset.get("url", "")
            photographer = asset.get("photographer", "")
            license_url = asset.get("license", "")
            lines.append(f"- {provider}: {photographer} <{url}> ({license_url})")
        return "\n".join(lines) + "\n"

    # -- lazy defaults (import here to keep module import side-effect free) --
    def _default_llm(self) -> Any:
        try:
            from pulsecraft.llm.orchestrator import TaskOrchestrator

            return TaskOrchestrator.from_config()
        except Exception as exc:
            logger.debug("campaign llm default unavailable: %s", exc)
            return None

    def _default_media(self) -> Any:
        from pulsecraft.assets.media_fetcher import MediaFetcher

        return MediaFetcher()

    def _static_renderer(self) -> Any:
        if self._static is not None:
            return self._static
        from pulsecraft.render_static.renderer import StaticPostRenderer

        return StaticPostRenderer()

    def _video_renderer(self) -> Any:
        if self._video is not None:
            return self._video
        from pulsecraft.render_video.renderer import VideoReelRenderer

        return VideoReelRenderer()
