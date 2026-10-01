"""Single-worker background job queue (M6 performance engine).

Max Concurrency = 1 (normative): Playwright/Remotion renders never run in
parallel on the 11th Gen i5 reference box. `enqueue()` returns immediately;
one FIFO worker executes jobs sequentially and always runs the
`gc.collect()` memory hook afterwards — even on failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from pulsecraft.web.memory import release_memory

logger = logging.getLogger(__name__)

Runner = Callable[[str, dict[str, Any]], dict[str, Any]]


class BackgroundJobQueue:
    """FIFO queue with a single worker (concurrency hard-capped at 1)."""

    MAX_CONCURRENCY = 1

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or (lambda kind, params: {"ok": True})
        self._jobs: dict[str, dict[str, Any]] = {}
        self._pending: asyncio.Queue[str] = asyncio.Queue()
        self._sem = asyncio.Semaphore(self.MAX_CONCURRENCY)
        self._pump_task: asyncio.Task[None] | None = None
        self._active = 0
        self._max_active = 0

    async def enqueue(self, kind: str, params: dict[str, Any]) -> str:
        """Queue a job; returns its id immediately (never blocks on renders)."""
        job_id = uuid.uuid4().hex[:12]
        self._jobs[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "params": dict(params),
            "status": "queued",
            "result": None,
            "error": None,
            "enqueued_at": time.time(),
        }
        await self._pending.put(job_id)
        self._ensure_pump()
        logger.info("web.queue enqueue id=%s kind=%s", job_id, kind)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Return the job record, or None for unknown ids."""
        job = self._jobs.get(job_id)
        return dict(job) if job is not None else None

    @property
    def max_active(self) -> int:
        """Peak concurrent executions observed (tests assert <= 1)."""
        return self._max_active

    def _ensure_pump(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = loop.create_task(self.drain())

    async def drain(self) -> None:
        """Execute every pending job sequentially (FIFO, concurrency 1)."""
        while not self._pending.empty():
            job_id = await self._pending.get()
            async with self._sem:
                await self._run_one(job_id)

    async def _run_one(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None or job["status"] != "queued":
            return
        job["status"] = "running"
        job["started_at"] = time.time()
        self._active += 1
        self._max_active = max(self._max_active, self._active)
        try:
            job["result"] = await asyncio.to_thread(self._runner, job["kind"], job["params"])
            job["status"] = "done"
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            logger.warning("web.queue job failed id=%s: %s", job_id, exc)
        finally:
            job["finished_at"] = time.time()
            self._active -= 1
            release_memory()
