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
    client = TestClient(create_app(pipeline=MagicMock(), queue=queue))
    created = client.post("/api/campaigns", json={"prompt": "3 habits", "brand": "acme"}).json()
    job_id = created["job_id"]
    deadline = time.time() + 10
    status = "queued"
    while status in ("queued", "running") and time.time() < deadline:
        time.sleep(0.05)
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
    assert status == "done"
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
