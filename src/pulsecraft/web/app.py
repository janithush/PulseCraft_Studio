"""FastAPI server (M6): REST endpoints wrapping CLI/pipeline capabilities.

Decoupled topology: FastAPI :8000 owns compute, Next.js :3000 owns glass.
Every endpoint is a thin wrapper over `CampaignPipeline`, `FeatureFlags`,
`UnifiedTemplateRegistry`, `AssetCache`, or `index_local_assets`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


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


def create_app(
    pipeline: Any = None,
    queue: Any = None,
    features_path: str | Path = "config/features.json",
    templates_root: str | Path = "templates",
    brands_root: str | Path = "brands",
) -> Any:
    """Build the FastAPI application with injectable collaborators (for tests)."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response

    from pulsecraft.web.queue import BackgroundJobQueue

    features_file = Path(features_path)
    templates_dir = Path(templates_root)
    brands_dir = Path(brands_root)

    def _pipeline() -> Any:
        if pipeline is not None:
            return pipeline
        from pulsecraft.pipeline.orchestrator import CampaignPipeline

        return CampaignPipeline()

    def _runner(kind: str, params: dict[str, Any]) -> dict[str, Any]:
        from pulsecraft.pipeline.orchestrator import CampaignRequest

        if kind != "campaign":
            raise ValueError(f"unknown job kind '{kind}'")
        result = _pipeline().run(CampaignRequest(**params))
        return {
            "run_dir": str(result.run_dir),
            "artifacts": {key: str(value) for key, value in result.artifacts.items()},
            "warnings": list(result.warnings),
        }

    job_queue: BackgroundJobQueue = (
        queue if queue is not None else BackgroundJobQueue(runner=_runner)
    )

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
