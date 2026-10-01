"""FastAPI server (M6): REST endpoints wrapping CLI/pipeline capabilities.

Decoupled topology: FastAPI :8000 owns compute, Next.js :3000 owns glass.
Every endpoint is a thin wrapper over `CampaignPipeline`, `FeatureFlags`,
`UnifiedTemplateRegistry`, `AssetCache`, or `index_local_assets`.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

try:  # opt-in .env auto-ingest (uvicorn entrypoint); never override explicit env
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
except ImportError:
    pass

logger = logging.getLogger(__name__)

BRAND_SLUG_RE = re.compile(r"^[a-z0-9-]{2,32}$")
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
RESERVED_BRAND_SLUGS = frozenset({"_base", "_template"})
RENDER_KINDS = ("render-post", "render-reel")


class CampaignIn(BaseModel):
    prompt: str
    brand: str = "acme"
    formats: str = "png,reel"
    preset: str = "alex-hormozi"
    platform: str = "all"
    seed: int = 42
    strict_assets: bool = False


class FeaturePatch(BaseModel):
    path: str
    enabled: bool


class BrandIn(BaseModel):
    slug: str
    name: str
    colors: dict[str, str]
    fonts: dict[str, str]
    voice: dict[str, Any]


class ModelPatch(BaseModel):
    op: str
    task: str | None = None
    chain: list[str] | None = None
    id: str | None = None
    label: str | None = None
    tasks: list[str] | None = None


class RenderIn(BaseModel):
    kind: str
    blueprint: dict[str, Any]
    brand: str = "acme"
    preset: str = "alex-hormozi"
    platform: str = "all"


def validate_brand_payload(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Validate a brand document. Returns (doc, errors); empty errors means valid."""
    errors: list[str] = []
    slug = data.get("slug", "")
    if (
        not isinstance(slug, str)
        or not BRAND_SLUG_RE.match(slug)
        or Path(slug).name != slug
        or slug in RESERVED_BRAND_SLUGS
    ):
        errors.append("slug must match ^[a-z0-9-]{2,32}$ and not be a reserved name")
    name = data.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        errors.append("name must be a 1-80 char string")
    colors = data.get("colors")
    if not isinstance(colors, dict) or not colors:
        errors.append("colors must be a non-empty object")
    elif not isinstance(colors.get("primary", ""), str) or not HEX_COLOR_RE.match(
        colors.get("primary", "")
    ):
        errors.append("colors.primary must be a #RGB or #RRGGBB hex string")
    fonts = data.get("fonts")
    if (
        not isinstance(fonts, dict)
        or not isinstance(fonts.get("display", ""), str)
        or not fonts.get("display", "")
        or not isinstance(fonts.get("body", ""), str)
        or not fonts.get("body", "")
    ):
        errors.append("fonts must define non-empty display and body strings")
    voice = data.get("voice")
    speed = voice.get("speed", 1.0) if isinstance(voice, dict) else None
    if (
        not isinstance(voice, dict)
        or not isinstance(voice.get("id", ""), str)
        or not voice.get("id", "")
        or not isinstance(speed, (int, float))
        or isinstance(speed, bool)
        or not 0.5 <= float(speed) <= 2.0
    ):
        errors.append("voice must define a non-empty id and a speed in 0.5-2.0")
    if errors:
        return {}, errors
    doc: dict[str, Any] = {
        "slug": slug,
        "name": name,
        "colors": dict(colors),
        "fonts": dict(fonts),
        "voice": dict(voice),
    }
    for extra in ("logo", "tone", "ctaDefaults"):
        if extra in data:
            doc[extra] = data[extra]
    return doc, []


def artifact_urls(artifacts: dict[str, str], root: str | Path) -> dict[str, str]:
    """Map artifact paths to browser-fetchable `/api/artifacts/...` URLs."""
    # Resolve both sides: renderers return absolute paths (needed by Remotion's
    # child cwd) while the root is usually relative; without this, relative_to
    # raises ValueError and URLs degrade to bare filenames (gallery 404s).
    base = Path(root).resolve()
    urls: dict[str, str] = {}
    for key, raw in artifacts.items():
        try:
            rel = Path(raw).resolve().relative_to(base)
        except ValueError:
            rel = Path(Path(raw).name)
        urls[key] = "/api/artifacts/" + rel.as_posix()
    return urls


def create_app(
    pipeline: Any = None,
    queue: Any = None,
    features_path: str | Path = "config/features.json",
    templates_root: str | Path = "templates",
    brands_root: str | Path = "brands",
    models_path: str | Path = "config/models.json",
    output_root: str | Path = "output",
    static_renderer: Any = None,
    video_renderer: Any = None,
) -> Any:
    """Build the FastAPI application with injectable collaborators (for tests)."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, Response

    from pulsecraft.web.queue import BackgroundJobQueue

    features_file = Path(features_path)
    templates_dir = Path(templates_root)
    brands_dir = Path(brands_root)
    models_file = Path(models_path)
    output_dir = Path(output_root)

    def _pipeline() -> Any:
        if pipeline is not None:
            return pipeline
        from pulsecraft.pipeline.orchestrator import CampaignPipeline

        return CampaignPipeline()

    def _static() -> Any:
        if static_renderer is not None:
            return static_renderer
        from pulsecraft.render_static.renderer import StaticPostRenderer

        return StaticPostRenderer(brands_root=brands_dir)

    def _video() -> Any:
        if video_renderer is not None:
            return video_renderer
        from pulsecraft.render_video.renderer import VideoReelRenderer

        return VideoReelRenderer()

    def _run_single(kind: str, params: dict[str, Any]) -> dict[str, Any]:
        run_id = f"playground-{uuid.uuid4().hex[:8]}"
        run_dir = output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, str] = {}
        warnings: list[str] = []
        brand = str(params.get("brand", "acme"))
        if kind == "render-post":
            result = _static().render_post(params["blueprint"], brand=brand, out_dir=str(run_dir))
            for key in ("png_square", "png_vertical", "meta_path"):
                value = getattr(result, key, None)
                if value is not None:
                    artifacts[key] = str(value)
            warnings.extend([str(item) for item in getattr(result, "warnings", [])])
        else:
            result = _video().render_reel(
                params["blueprint"],
                brand=brand,
                preset=str(params.get("preset", "alex-hormozi")),
                platform=str(params.get("platform", "all")),
                out_dir=str(run_dir),
            )
            for canvas_id, path in (getattr(result, "files", {}) or {}).items():
                artifacts[f"reel-{canvas_id}"] = str(path)
            meta = getattr(result, "meta_path", None)
            if meta is not None:
                artifacts["reel-meta.json"] = str(meta)
            warnings.extend([str(item) for item in getattr(result, "warnings", [])])
        return {
            "run_dir": str(run_dir),
            "artifacts": artifacts,
            "artifact_urls": artifact_urls(artifacts, output_dir),
            "warnings": warnings,
        }

    def _runner(kind: str, params: dict[str, Any]) -> dict[str, Any]:
        from pulsecraft.pipeline.orchestrator import CampaignRequest

        if kind == "campaign":
            req = CampaignRequest(**params)
            result = _pipeline().run(req)
            artifacts = {key: str(value) for key, value in result.artifacts.items()}
            return {
                "run_dir": str(result.run_dir),
                "artifacts": artifacts,
                "artifact_urls": artifact_urls(artifacts, req.out_dir),
                "warnings": list(result.warnings),
            }
        if kind in RENDER_KINDS:
            return _run_single(kind, params)
        raise ValueError(f"unknown job kind '{kind}'")

    job_queue: BackgroundJobQueue = (
        queue if queue is not None else BackgroundJobQueue(runner=_runner)
    )

    # Phase 2 — Pre-flight auditor (hard-block on missing deps, per V2 protocol).
    # Bypass with PULSECRAFT_SKIP_PREFLIGHT=1 (tests / local UI dev without keys).
    # Pytest auto-bypasses unless PULSECRAFT_FORCE_PREFLIGHT=1 (keeps unit tests green).
    import sys

    skip = os.environ.get("PULSECRAFT_SKIP_PREFLIGHT", "").strip().lower() in ("1", "true", "yes")
    under_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
    force = os.environ.get("PULSECRAFT_FORCE_PREFLIGHT", "").strip().lower() in ("1", "true", "yes")
    if not skip and not (under_pytest and not force):
        from pulsecraft.common.preflight import PreflightError, run_preflight

        try:
            run_preflight(root=Path.cwd(), strict=True)
        except PreflightError:
            logger.error("❌ Pre-flight Failed: blocking FastAPI startup (see diagnostic above)")
            raise

    # NOTE: endpoint body models (CampaignIn/FeaturePatch) live at module level
    # so FastAPI can resolve annotations on Python 3.14 (PEP 649 lazy eval).
    app = FastAPI(title="PulseCraft Studio", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/brands")
    def list_brands() -> dict[str, list[str]]:
        slugs = sorted(path.stem for path in brands_dir.glob("*.json") if path.stem != "_base")
        return {"brands": slugs}

    @app.get("/api/brands/{slug}")
    def get_brand(slug: str) -> dict[str, Any]:
        try:
            merged, warnings = _static().load_brand(slug)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"slug": slug, "brand": merged, "warnings": warnings}

    @app.post("/api/brands")
    def create_brand(body: BrandIn) -> dict[str, Any]:
        from fastapi.responses import JSONResponse

        doc, errors = validate_brand_payload(body.model_dump())
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))
        target = brands_dir / f"{doc['slug']}.json"
        created = not target.is_file()
        brands_dir.mkdir(parents=True, exist_ok=True)
        import json as jsonlib

        target.write_text(jsonlib.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return JSONResponse(
            status_code=201 if created else 200,
            content={"slug": doc["slug"], "created": created},
        )

    @app.get("/api/templates")
    def list_templates() -> dict[str, list[dict[str, Any]]]:
        from pulsecraft.templates_mgr.registry import UnifiedTemplateRegistry

        entries = UnifiedTemplateRegistry(templates_dir).list_all_templates()
        return {
            "templates": [
                {"name": entry.name, "kind": entry.kind, "manifest": entry.meta}
                for entry in entries
            ]
        }

    @app.get("/api/templates/{name}/preview")
    def template_preview(name: str) -> dict[str, Any]:
        from pulsecraft.templates_mgr.manager import TemplateManager
        from pulsecraft.templates_mgr.registry import RegistryError, UnifiedTemplateRegistry

        try:
            schema = UnifiedTemplateRegistry(templates_dir).get_template_schema(name)
        except RegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        html = ""
        if schema["kind"] == "post":
            try:
                preview = TemplateManager(str(templates_dir)).inspect_template(name, kind="posts")
                html = str(preview.get("html", ""))
            except Exception:
                html = ""
        return {
            "name": name,
            "kind": schema["kind"],
            "html": html,
            "schema": schema["placeholders"],
        }

    @app.get("/api/features")
    def get_features() -> dict[str, Any]:
        from pulsecraft.common.feature_flags import FeatureFlags

        return FeatureFlags.load(features_file).to_dict()

    @app.patch("/api/features")
    def patch_features(patch: FeaturePatch) -> dict[str, Any]:
        import json as jsonlib

        from pulsecraft.common.feature_flags import FeatureFlags, FlagError

        try:
            flags = FeatureFlags.load(features_file)
            flags.set(patch.path, patch.enabled)
        except FlagError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        features_file.parent.mkdir(parents=True, exist_ok=True)
        features_file.write_text(jsonlib.dumps(flags.to_dict(), indent=2), encoding="utf-8")
        return {"path": patch.path, "enabled": patch.enabled}

    @app.get("/api/models")
    def list_models() -> dict[str, Any]:
        from pulsecraft.llm.registry import ModelRegistry, RegistryError

        try:
            return ModelRegistry.load(models_file).to_dict()
        except RegistryError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.patch("/api/models")
    def patch_models(body: ModelPatch) -> dict[str, Any]:
        from pulsecraft.llm.registry import ModelRegistry, RegistryError

        try:
            registry = ModelRegistry.load(models_file)
            if body.op == "set_chain":
                if not body.task or body.chain is None:
                    raise HTTPException(status_code=422, detail="set_chain requires task and chain")
                known = set(registry.to_dict()["registry"])
                unknown = [model for model in body.chain if model not in known]
                if unknown:
                    raise HTTPException(
                        status_code=422,
                        detail=f"unknown model(s) in chain: {unknown}",
                    )
                registry.set_chain(body.task, body.chain)
            elif body.op == "add_model":
                if not body.id or not body.label:
                    raise HTTPException(status_code=422, detail="add_model requires id and label")
                registry.add_model(body.id, body.label, body.tasks)
            else:
                raise HTTPException(
                    status_code=422, detail=f"unknown op '{body.op}' (want set_chain|add_model)"
                )
        except RegistryError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        registry.save()
        return {"ok": True, "op": body.op}

    @app.get("/api/assets")
    def list_assets() -> dict[str, Any]:
        from pulsecraft.assets.cache import AssetCache
        from pulsecraft.assets.local_mgr import index_local_assets

        local = [item.to_dict() for item in index_local_assets("input/visuals", "input/audio")]
        for item in local:
            item["path"] = str(item["path"])
        return {"local": local, "cached": AssetCache().list_cached()}

    @app.post("/api/campaigns", status_code=202)
    async def create_campaign(body: CampaignIn) -> dict[str, str]:
        if not body.prompt.strip():
            raise HTTPException(status_code=422, detail="prompt must not be empty")
        job_id = await job_queue.enqueue("campaign", body.model_dump())
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = job_queue.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
        return job

    @app.post("/api/render", status_code=202)
    async def create_render(body: RenderIn) -> dict[str, str]:
        if body.kind not in RENDER_KINDS:
            raise HTTPException(
                status_code=422, detail=f"unknown kind '{body.kind}' (want render-post|render-reel)"
            )
        if not body.blueprint:
            raise HTTPException(status_code=422, detail="blueprint must be a non-empty object")
        job_id = await job_queue.enqueue(body.kind, body.model_dump())
        return {"job_id": job_id}

    @app.get("/api/artifacts/{path:path}")
    def serve_artifact(path: str) -> FileResponse:
        root = Path(output_root).resolve()
        candidate = (root / path).resolve()
        if root not in candidate.parents and candidate != root:
            raise HTTPException(status_code=403, detail="path escapes output root")
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail=f"artifact not found: {path}")
        media, _ = mimetypes.guess_type(candidate.name)
        return FileResponse(candidate, media_type=media or "application/octet-stream")

    @app.get("/api/assets/thumb")
    def asset_thumb(path: str, w: int = 480) -> Response:
        from pulsecraft.web.thumbs import make_thumbnail

        candidate = (
            (Path.cwd() / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        )
        if Path.cwd().resolve() not in candidate.parents and candidate != Path.cwd().resolve():
            raise HTTPException(status_code=403, detail="path escapes workspace")
        try:
            data = make_thumbnail(candidate, max_px=max(32, min(w, 1024)))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(
            content=data,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    logger.info("web.app ready features=%s templates=%s", features_file, templates_dir)
    return app


app = create_app()
