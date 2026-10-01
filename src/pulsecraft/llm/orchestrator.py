"""Task-based orchestrator (M1): ordered multi-tier fallback chains per task.

Failover: Model 1 fails/times out/errors -> mark "failed" (Red) -> try Model 2,
Model 3, ... First success is marked "connected" (Green) and returned.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from pulsecraft.llm.client import ModelCallError, OpenRouterClient, TaskType
from pulsecraft.llm.registry import ModelRegistry


class AllModelsFailedError(RuntimeError):
    """Every model in the task chain failed."""

    def __init__(self, task: TaskType, attempted: list[str], reasons: list[str]) -> None:
        super().__init__(f"task {task.value}: all {len(attempted)} models failed: {attempted}")
        self.task = task
        self.attempted = attempted
        self.reasons = reasons


@dataclass
class OrchestratorResult:
    text: str
    model_used: str
    attempted: list[str] = field(default_factory=list)
    fallback_taken: bool = False


class TaskOrchestrator:
    """Executes one task across its configured fallback chain."""

    def __init__(
        self,
        registry: ModelRegistry,
        client: OpenRouterClient | None = None,
        persist_status: bool = True,
    ) -> None:
        self._registry = registry
        self._client = client or OpenRouterClient(
            base_url=registry.base_url, timeout_s=registry.timeout_ms / 1000.0
        )
        self._persist_status = persist_status

    @classmethod
    def from_config(cls, config_path: str | Path = "config/models.json") -> TaskOrchestrator:
        return cls(ModelRegistry.load(config_path))

    def execute(self, task: TaskType | str, prompt: str) -> OrchestratorResult:
        task = TaskType(task)
        chain = self._registry.get_chain(task.value)
        attempted: list[str] = []
        reasons: list[str] = []
        for model_id in chain:
            attempted.append(model_id)
            try:
                text = self._client.complete(task, prompt, model_id)
            except ModelCallError as exc:
                reasons.append(exc.reason)
                self._mark(model_id, "failed")
                continue
            self._mark(model_id, "connected")
            return OrchestratorResult(
                text=text,
                model_used=model_id,
                attempted=attempted,
                fallback_taken=len(attempted) > 1,
            )
        raise AllModelsFailedError(task, attempted, reasons)

    def _mark(self, model_id: str, status: str) -> None:
        self._registry.set_status(model_id, status)
        if self._persist_status:
            with suppress(Exception):
                self._registry.save()
