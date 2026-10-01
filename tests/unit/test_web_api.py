"""M6 unit tests: FastAPI surface + single-worker queue + gc + WebP thumbs."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pulsecraft.web.memory import release_memory
from pulsecraft.web.queue import BackgroundJobQueue
from pulsecraft.web.thumbs import make_thumbnail

pytestmark = pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient`.*:UserWarning"
)


def _png(path: Path, size: tuple[int, int] = (64, 48)) -> None:
    from PIL import Image

    Image.new("RGB", size, color="red").save(path)


def _client(**overrides):
    from fastapi.testclient import TestClient

    from pulsecraft.web.app import create_app

    defaults = {
        "pipeline": MagicMock(),
        "queue": BackgroundJobQueue(runner=lambda k, p: {"ok": True}),
    }
    defaults.update(overrides)
    return TestClient(create_app(**defaults))


def test_health_and_brands_and_templates() -> None:
    client = _client()
    assert client.get("/api/health").json()["status"] == "ok"
    brands = client.get("/api/brands").json()["brands"]
    assert isinstance(brands, list)
    names = [item["name"] for item in client.get("/api/templates").json()["templates"]]
    assert "bold-hook-split" in names


def test_template_preview_has_badge_placeholders() -> None:
    client = _client()
    preview = client.get("/api/templates/bold-hook-split/preview").json()
    assert "[Hook Here]" in preview["html"]
    assert "hook" in preview["schema"]["required"]
    assert client.get("/api/templates/ghost-pack/preview").status_code == 404


def test_features_get_patch_and_422(tmp_path: Path) -> None:
    import shutil

    source = Path("config/features.json")
    isolated = tmp_path / "features.json"
    shutil.copy(source, isolated)
    client = _client(features_path=isolated)
    assert client.get("/api/features").json()["version"] == "features/v1"
    patched = client.patch("/api/features", json={"path": "media.pexels", "enabled": False}).json()
    assert patched == {"path": "media.pexels", "enabled": False}
    assert client.get("/api/features").json()["media"]["pexels"]["enabled"] is False
    bad = client.patch("/api/features", json={"path": "media.nope", "enabled": True})
    assert bad.status_code == 422
    assert json.loads(isolated.read_text(encoding="utf-8"))["media"]["pexels"]["enabled"] is False


def test_assets_list_and_thumb_proxy(tmp_path: Path) -> None:
    client = _client()
    assert "local" in client.get("/api/assets").json()
    _png(tmp_path / "shot.png", (800, 600))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        resp = client.get("/api/assets/thumb", params={"path": "shot.png"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert resp.content[:4] == b"RIFF"
    assert len(resp.content) > 0


def test_campaign_enqueue_then_poll_done() -> None:
    from fastapi.testclient import TestClient

    from pulsecraft.web.app import create_app

    queue = BackgroundJobQueue(runner=lambda kind, params: {"run_dir": "output/run-1"})
    # NOTE: lifespan-managed client keeps one event loop, so the background
    # pump is never starved between requests (bare TestClient races it).
    with TestClient(create_app(pipeline=MagicMock(), queue=queue)) as client:
        created = client.post("/api/campaigns", json={"prompt": "3 habits", "brand": "acme"}).json()
        job = _wait_done(client, created["job_id"])
        assert job["status"] == "done"
        assert client.get("/api/jobs/nope").status_code == 404
        assert client.post("/api/campaigns", json={"prompt": "  "}).status_code == 422


def test_make_thumbnail_webp_bytes(tmp_path: Path) -> None:
    _png(tmp_path / "big.png", (900, 700))
    data = make_thumbnail(tmp_path / "big.png")
    assert data[:4] == b"RIFF"
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        assert max(img.size) <= 480


def test_release_memory_collects() -> None:
    assert isinstance(release_memory(), int)


def test_queue_runs_gc_hook_after_job() -> None:
    async def scenario() -> None:
        queue = BackgroundJobQueue(runner=lambda kind, params: {"ok": True})
        with patch("pulsecraft.web.queue.release_memory") as hook:
            await queue.enqueue("campaign", {"prompt": "x"})
            await queue.drain()
            assert hook.call_count >= 1

    asyncio.run(scenario())


def test_queue_max_concurrency_is_one() -> None:
    async def scenario() -> int:
        import threading

        active = 0
        peak = 0
        lock = threading.Lock()

        def slow(kind: str, params: dict) -> dict:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return {"ok": True}

        queue = BackgroundJobQueue(runner=slow)
        await queue.enqueue("campaign", {"prompt": "a"})
        await queue.enqueue("campaign", {"prompt": "b"})
        await queue.drain()
        assert queue.max_active <= 1
        return peak

    assert asyncio.run(scenario()) <= 1


# --- M7: brands, models, render playground, artifact serving -----------------


def _brands_dir(tmp_path: Path) -> Path:
    brands = tmp_path / "brands"
    (brands / "_template").mkdir(parents=True)
    base = {
        "name": "Base",
        "slug": "acme",
        "colors": {"primary": "#FF4D00"},
        "fonts": {"display": "Inter", "body": "Inter"},
        "voice": {"id": "kokoro-default", "speed": 1.0},
    }
    (brands / "_base.json").write_text(json.dumps(base), encoding="utf-8")
    (brands / "_template" / "brand.json").write_text(json.dumps(base), encoding="utf-8")
    return brands


def _wait_done(client, job_id: str, timeout_s: float = 10.0) -> dict:
    deadline = time.time() + timeout_s
    status = "queued"
    job: dict = {}
    while status in ("queued", "running") and time.time() < deadline:
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job_id}").json()
        status = job["status"]
    assert status == "done", job
    return job


def _valid_brand(slug: str = "demo") -> dict:
    return {
        "slug": slug,
        "name": "Demo",
        "colors": {"primary": "#A3E635", "bg": "#111111"},
        "fonts": {"display": "Inter", "body": "Inter"},
        "voice": {"id": "kokoro-default", "speed": 1.0},
    }


def test_brand_detail_falls_back_and_create_validates(tmp_path: Path) -> None:
    brands = _brands_dir(tmp_path)
    client = _client(brands_root=brands)
    assert client.get("/api/brands").json() == {"brands": []}
    detail = client.get("/api/brands/acme").json()
    assert detail["brand"]["colors"]["primary"] == "#FF4D00"
    assert any("falling back" in warning for warning in detail["warnings"])

    created = client.post("/api/brands", json=_valid_brand("demo"))
    assert created.status_code == 201
    assert created.json() == {"slug": "demo", "created": True}
    assert (brands / "demo.json").is_file()
    assert client.get("/api/brands").json() == {"brands": ["demo"]}
    again = client.post("/api/brands", json=_valid_brand("demo"))
    assert again.status_code == 200
    assert again.json()["created"] is False

    bad_slug = client.post("/api/brands", json=_valid_brand("Bad Slug!"))
    assert bad_slug.status_code == 422
    bad_hex = _valid_brand("ok-slug")
    bad_hex["colors"]["primary"] = "not-a-color"
    assert client.post("/api/brands", json=bad_hex).status_code == 422
    bad_voice = _valid_brand("ok-2")
    bad_voice["voice"]["speed"] = 9.9
    assert client.post("/api/brands", json=bad_voice).status_code == 422
    missing = dict(_valid_brand("ok-3"))
    del missing["fonts"]
    assert client.post("/api/brands", json=missing).status_code == 422


def test_brand_detail_404_without_base(tmp_path: Path) -> None:
    empty = tmp_path / "brands"
    empty.mkdir()
    assert _client(brands_root=empty).get("/api/brands/ghost").status_code == 404


def test_models_get_and_patch(tmp_path: Path) -> None:
    import shutil

    isolated = tmp_path / "models.json"
    shutil.copy(Path("config/models.json"), isolated)
    client = _client(models_path=isolated)
    data = client.get("/api/models").json()
    assert data["version"] == "models/v1"
    original = list(data["tasks"]["copywriting"]["chain"])
    assert len(original) >= 2

    reversed_chain = list(reversed(original))
    patched = client.patch(
        "/api/models",
        json={"op": "set_chain", "task": "copywriting", "chain": reversed_chain},
    ).json()
    assert patched["ok"] is True
    assert client.get("/api/models").json()["tasks"]["copywriting"]["chain"] == reversed_chain
    assert json.loads(isolated.read_text(encoding="utf-8"))["tasks"]["copywriting"]["chain"] == (
        reversed_chain
    )

    assert (
        client.patch(
            "/api/models", json={"op": "set_chain", "task": "nope", "chain": original}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/models",
            json={"op": "set_chain", "task": "copywriting", "chain": ["ghost/model"]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/models", json={"op": "set_chain", "task": "copywriting", "chain": []}
        ).status_code
        == 422
    )
    added = client.patch(
        "/api/models",
        json={"op": "add_model", "id": "vendor/custom:free", "label": "Custom", "tasks": []},
    ).json()
    assert added["ok"] is True
    assert "vendor/custom:free" in client.get("/api/models").json()["registry"]
    assert (
        client.patch(
            "/api/models", json={"op": "add_model", "id": "bad-id", "label": "x"}
        ).status_code
        == 422
    )
    assert client.patch("/api/models", json={"op": "nope"}).status_code == 422


def test_render_post_and_reel_kinds(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from pulsecraft.web.app import create_app

    def _static_render(blueprint, brand="acme", out_dir="output"):
        from types import SimpleNamespace

        out = Path(out_dir)
        square = out / "square-1080x1080.png"
        square.write_bytes(b"png")
        meta = out / "static-meta.json"
        meta.write_text("{}", encoding="utf-8")
        return SimpleNamespace(png_square=square, png_vertical=square, meta_path=meta, warnings=[])

    static = MagicMock()
    static.render_post.side_effect = _static_render
    video = MagicMock()

    def _video_render(
        blueprint, brand="acme", preset="alex-hormozi", platform="all", out_dir="output"
    ):
        out = Path(out_dir)
        target = out / "reel-1080x1920.mp4"
        target.write_bytes(b"mp4")
        from types import SimpleNamespace

        return SimpleNamespace(files={"1080x1920": target}, meta_path=None, warnings=[])

    video.render_reel.side_effect = _video_render
    out_root = tmp_path / "output"
    # NOTE: lifespan-managed client (see test_campaign_enqueue_then_poll_done).
    with TestClient(
        create_app(
            pipeline=MagicMock(),
            static_renderer=static,
            video_renderer=video,
            output_root=out_root,
        )
    ) as client:
        post_job = _wait_done(
            client,
            client.post(
                "/api/render",
                json={"kind": "render-post", "blueprint": {"type": "static-post"}, "brand": "acme"},
            ).json()["job_id"],
        )
        assert post_job["result"]["artifact_urls"]["png_square"].startswith(
            "/api/artifacts/playground-"
        )
        reel_job = _wait_done(
            client,
            client.post(
                "/api/render",
                json={"kind": "render-reel", "blueprint": {"type": "reel"}, "brand": "acme"},
            ).json()["job_id"],
        )
        assert reel_job["result"]["artifact_urls"]["reel-1080x1920"].endswith(".mp4")
        assert (
            client.post("/api/render", json={"kind": "render-tv", "blueprint": {}}).status_code
            == 422
        )
        assert (
            client.post("/api/render", json={"kind": "render-post", "blueprint": {}}).status_code
            == 422
        )


def test_artifact_serving_and_traversal_guard(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from pulsecraft.web.app import create_app

    out_root = tmp_path / "output"
    (out_root / "run-1").mkdir(parents=True)
    (out_root / "run-1" / "square.png").write_bytes(b"fakepng")
    client = TestClient(create_app(pipeline=MagicMock(), output_root=out_root))
    ok = client.get("/api/artifacts/run-1/square.png")
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/png"
    assert ok.content == b"fakepng"
    assert client.get("/api/artifacts/run-1/missing.png").status_code == 404
    assert client.get("/api/artifacts/%2e%2e/secret.txt").status_code == 403


def test_campaign_result_includes_artifact_urls() -> None:
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pulsecraft.web.app import create_app

    pipeline = MagicMock()
    pipeline.run.return_value = SimpleNamespace(
        run_dir=Path("output/run-9"),
        artifacts={"png_square": str(Path("output/run-9/square.png"))},
        warnings=[],
    )
    with TestClient(create_app(pipeline=pipeline)) as client:
        job = _wait_done(
            client,
            client.post("/api/campaigns", json={"prompt": "hi", "brand": "acme"}).json()["job_id"],
        )
    assert job["result"]["artifact_urls"] == {"png_square": "/api/artifacts/run-9/square.png"}
