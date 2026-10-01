"""Dynamic Model Registry (M1 Green): parse, validate, load `config/models.json`.

No hardcoded models: task fallback chains and the model catalog are data.
Health states per model: "unknown" | "connected" | "failed"
(displayed as Connected/Failed in the CLI).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REGISTRY_VERSION = "models/v1"
VALID_STATUSES = ("unknown", "connected", "failed")

CONNECTED = "Connected"
FAILED = "Failed"


class RegistryError(ValueError):
    """Raised when `config/models.json` is missing or schema-invalid."""


class ModelRegistry:
    """In-memory view of `config/models.json` with validation + status tracking."""

    def __init__(self, raw: dict[str, Any], path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._data = _validate(raw)

    @classmethod
    def load(cls, config_path: str | Path = "config/models.json") -> ModelRegistry:
        path = Path(config_path)
        if not path.is_file():
            raise RegistryError(f"model registry not found: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RegistryError(f"model registry is not valid JSON: {path}: {exc}") from exc
        return cls(raw, path)

    @property
    def version(self) -> str:
        return str(self._data["version"])

    @property
    def base_url(self) -> str:
        return str(self._data["openrouter"]["baseUrl"])

    @property
    def timeout_ms(self) -> int:
        return int(self._data["openrouter"]["timeoutMs"])

    @property
    def retries_per_model(self) -> int:
        return int(self._data["openrouter"].get("retriesPerModel", 1))

    def task_names(self) -> list[str]:
        return list(self._data["tasks"].keys())

    def get_chain(self, task: str) -> list[str]:
        try:
            chain = self._data["tasks"][task]["chain"]
        except KeyError as exc:
            raise RegistryError(f"unknown task '{task}'. Known: {self.task_names()}") from exc
        return list(chain)

    def set_chain(self, task: str, chain: list[str]) -> None:
        if task not in self._data["tasks"]:
            raise RegistryError(f"unknown task '{task}'. Known: {self.task_names()}")
        if not chain:
            raise RegistryError(f"chain for task '{task}' must be non-empty")
        self._data["tasks"][task]["chain"] = list(chain)

    def add_model(
        self,
        model_id: str,
        label: str,
        tasks: list[str] | None = None,
        status: str = "unknown",
    ) -> None:
        if "/" not in model_id:
            raise RegistryError(f"model id must be 'vendor/name': got '{model_id}'")
        if status not in VALID_STATUSES:
            raise RegistryError(f"invalid status '{status}'. Valid: {VALID_STATUSES}")
        self._data["registry"].setdefault(
            model_id, {"label": label, "status": status, "lastChecked": None}
        )
        for task in tasks or []:
            if task not in self._data["tasks"]:
                raise RegistryError(f"unknown task '{task}'. Known: {self.task_names()}")
            if model_id not in self._data["tasks"][task]["chain"]:
                self._data["tasks"][task]["chain"].append(model_id)

    def get_status(self, model_id: str) -> str:
        try:
            return str(self._data["registry"][model_id]["status"])
        except KeyError as exc:
            raise RegistryError(f"unknown model '{model_id}'") from exc

    def set_status(self, model_id: str, status: str) -> None:
        if status not in VALID_STATUSES:
            raise RegistryError(f"invalid status '{status}'. Valid: {VALID_STATUSES}")
        if model_id not in self._data["registry"]:
            raise RegistryError(f"unknown model '{model_id}'")
        self._data["registry"][model_id]["status"] = status
        self._data["registry"][model_id]["lastChecked"] = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._data))

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self._path
        if target is None:
            raise RegistryError("no path to save registry (load with a path first)")
        target.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
        self._path = target
        return target


def load_model_registry(config_path: str | Path = "config/models.json") -> dict[str, Any]:
    """Load and validate the registry; returns a plain dict (M0 test contract)."""
    return ModelRegistry.load(config_path).to_dict()


def check_model_status(model_id: str, config_path: str | Path = "config/models.json") -> str:
    """Probe one model's OpenRouter connectivity.

    Returns "Connected" (Green) or "Failed" (Red) and persists the result
    (status + lastChecked) back to `config/models.json`.
    """
    registry = ModelRegistry.load(config_path)
    if model_id not in registry.to_dict()["registry"]:
        raise RegistryError(f"unknown model '{model_id}'")
    ok = _probe_openrouter(registry.base_url, model_id, registry.timeout_ms)
    registry.set_status(model_id, "connected" if ok else "failed")
    registry.save()
    return CONNECTED if ok else FAILED


def _probe_openrouter(base_url: str, model_id: str, timeout_ms: int) -> bool:
    """Minimal OpenRouter ping: GET /models, then a tiny chat completion."""
    import httpx

    headers = {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"}
    timeout_s = max(timeout_ms / 1000.0, 1.0)
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            if resp.status_code != 200:
                return False
            ping = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            return ping.status_code == 200
    except Exception:
        return False


def _validate(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RegistryError("registry root must be an object")
    if raw.get("version") != REGISTRY_VERSION:
        raise RegistryError(
            f"unsupported version '{raw.get('version')}'. Want '{REGISTRY_VERSION}'"
        )
    openrouter = raw.get("openrouter")
    if not isinstance(openrouter, dict) or not openrouter.get("baseUrl"):
        raise RegistryError("registry.openrouter.baseUrl is required")
    tasks = raw.get("tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise RegistryError("registry.tasks must be a non-empty object")
    for name, spec in tasks.items():
        chain = spec.get("chain") if isinstance(spec, dict) else None
        if not isinstance(chain, list) or not chain:
            raise RegistryError(f"tasks.{name}.chain must be a non-empty array")
    catalog = raw.get("registry")
    if not isinstance(catalog, dict) or not catalog:
        raise RegistryError("registry.registry must be a non-empty object")
    for model_id, entry in catalog.items():
        if "/" not in model_id:
            raise RegistryError(f"invalid model id '{model_id}' (want 'vendor/name')")
        if not isinstance(entry, dict) or entry.get("status") not in VALID_STATUSES:
            raise RegistryError(
                f"registry entry '{model_id}'.status must be one of {VALID_STATUSES}"
            )
    return raw


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
