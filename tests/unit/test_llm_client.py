"""M1 unit tests: 4 task types, multi-tier fallback, health checks, CLI status.

OpenRouter HTTP is mocked (unittest.mock); no network, no keys required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from pulsecraft.cli import main
from pulsecraft.llm.client import ModelCallError, OpenRouterClient, TaskType
from pulsecraft.llm.orchestrator import AllModelsFailedError, TaskOrchestrator
from pulsecraft.llm.registry import (
    ModelRegistry,
    RegistryError,
    check_model_status,
)

MODELS = [
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-001",
]

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "models.json"


def _registry_dict() -> dict:
    return {
        "version": "models/v1",
        "openrouter": {"baseUrl": "https://openrouter.ai/api/v1", "timeoutMs": 5000},
        "tasks": {
            "promptExpansion": {"chain": MODELS},
            "copywriting": {"chain": MODELS},
            "visualQueryGen": {"chain": MODELS},
            "jsonBlueprintConversion": {"chain": MODELS},
        },
        "registry": {
            mid: {"label": mid.split("/")[0], "status": "unknown", "lastChecked": None}
            for mid in MODELS
        },
    }


def _ok_response(text: str = "hello") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    return resp


def _fail_response(status: int = 429) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = "rate limited"
    return resp


def test_registry_loads_repo_config_with_four_task_chains() -> None:
    registry = ModelRegistry.load(REPO_CONFIG)
    for task in (
        "promptExpansion",
        "copywriting",
        "visualQueryGen",
        "jsonBlueprintConversion",
    ):
        chain = registry.get_chain(task)
        assert len(chain) >= 2, task
    assert registry.version == "models/v1"


def test_registry_rejects_bad_version(tmp_path: Path) -> None:
    bad = _registry_dict()
    bad["version"] = "models/v9"
    path = tmp_path / "models.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RegistryError):
        ModelRegistry.load(path)


def test_registry_rejects_empty_chain(tmp_path: Path) -> None:
    bad = _registry_dict()
    bad["tasks"]["copywriting"]["chain"] = []
    path = tmp_path / "models.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RegistryError):
        ModelRegistry.load(path)


@pytest.mark.parametrize(
    "task",
    [
        TaskType.PROMPT_EXPANSION,
        TaskType.COPYWRITING,
        TaskType.VISUAL_QUERY_GEN,
        TaskType.JSON_BLUEPRINT_CONVERSION,
    ],
)
def test_client_each_task_type_posts_correct_model(task: TaskType) -> None:
    client = OpenRouterClient(base_url="https://openrouter.ai/api/v1", api_key="k", timeout_s=5)
    with patch("httpx.Client") as client_cls:
        mocked = client_cls.return_value.__enter__.return_value
        mocked.post.return_value = _ok_response(f"out-{task.value}")
        text = client.complete(task, "prompt", MODELS[0])
    assert text == f"out-{task.value}"
    _, kwargs = mocked.post.call_args
    assert kwargs["json"]["model"] == MODELS[0]
    if task is TaskType.JSON_BLUEPRINT_CONVERSION:
        assert kwargs["json"]["response_format"] == {"type": "json_object"}
    else:
        assert "response_format" not in kwargs["json"]


def test_client_raises_on_http_error() -> None:
    client = OpenRouterClient(api_key="k", timeout_s=5)
    with patch("httpx.Client") as client_cls:
        mocked = client_cls.return_value.__enter__.return_value
        mocked.post.return_value = _fail_response(429)
        with pytest.raises(ModelCallError) as exc_info:
            client.complete(TaskType.COPYWRITING, "prompt", MODELS[0])
    assert exc_info.value.model_id == MODELS[0]


def test_orchestrator_first_model_success_no_fallback() -> None:
    registry = ModelRegistry(_registry_dict())
    client = OpenRouterClient(api_key="k")
    with patch.object(OpenRouterClient, "complete", return_value="ok") as complete:
        orch = TaskOrchestrator(registry, client=client, persist_status=False)
        result = orch.execute(TaskType.COPYWRITING, "prompt")
    assert result.text == "ok"
    assert result.model_used == MODELS[0]
    assert result.attempted == [MODELS[0]]
    assert result.fallback_taken is False
    assert registry.get_status(MODELS[0]) == "connected"
    complete.assert_called_once()


def test_orchestrator_falls_back_when_primary_and_secondary_fail() -> None:
    registry = ModelRegistry(_registry_dict())
    client = OpenRouterClient(api_key="k")
    calls = {"n": 0}

    def flaky(task, prompt, model_id):
        calls["n"] += 1
        if model_id in MODELS[:2]:
            raise ModelCallError(model_id, "HTTP 429")
        return "third-wins"

    with patch.object(OpenRouterClient, "complete", side_effect=flaky):
        orch = TaskOrchestrator(registry, client=client, persist_status=False)
        result = orch.execute(TaskType.PROMPT_EXPANSION, "prompt")

    assert result.text == "third-wins"
    assert result.model_used == MODELS[2]
    assert result.attempted == MODELS
    assert result.fallback_taken is True
    assert registry.get_status(MODELS[0]) == "failed"  # Red
    assert registry.get_status(MODELS[1]) == "failed"  # Red
    assert registry.get_status(MODELS[2]) == "connected"  # Green
    assert calls["n"] == 3


def test_orchestrator_raises_when_all_models_fail() -> None:
    registry = ModelRegistry(_registry_dict())
    client = OpenRouterClient(api_key="k")
    with patch.object(
        OpenRouterClient,
        "complete",
        side_effect=lambda task, prompt, model_id: (_ for _ in ()).throw(
            ModelCallError(model_id, "boom")
        ),
    ):
        orch = TaskOrchestrator(registry, client=client, persist_status=False)
        with pytest.raises(AllModelsFailedError) as exc_info:
            orch.execute(TaskType.VISUAL_QUERY_GEN, "prompt")
    assert exc_info.value.attempted == MODELS
    assert all(registry.get_status(mid) == "failed" for mid in MODELS)


def test_check_model_status_connected_persists(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    with patch("httpx.Client") as client_cls:
        mocked = client_cls.return_value.__enter__.return_value
        mocked.get.return_value = _ok_response()
        mocked.post.return_value = _ok_response()
        state = check_model_status(MODELS[0], path)
    assert state == "Connected"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["registry"][MODELS[0]]["status"] == "connected"
    assert saved["registry"][MODELS[0]]["lastChecked"]


def test_check_model_status_failed_on_http_error(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    with patch("httpx.Client") as client_cls:
        mocked = client_cls.return_value.__enter__.return_value
        mocked.get.return_value = _fail_response(500)
        state = check_model_status(MODELS[1], path)
    assert state == "Failed"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["registry"][MODELS[1]]["status"] == "failed"


def test_cli_models_status_table(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["models", "status", "--config", str(path)])
    assert result.exit_code == 0, result.output
    assert "Registered models:" in result.output
    assert "Task fallback chains:" in result.output
    for mid in MODELS:
        assert mid in result.output
    for task in ("promptExpansion", "copywriting", "visualQueryGen", "jsonBlueprintConversion"):
        assert task in result.output
    assert "Connected" in result.output or "Unknown" in result.output


def test_registry_add_model_set_chain_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    registry = ModelRegistry.load(path)
    registry.add_model("vendor/custom-model:free", label="Custom", tasks=["copywriting"])
    assert "vendor/custom-model:free" in registry.get_chain("copywriting")
    assert registry.get_status("vendor/custom-model:free") == "unknown"
    registry.set_chain("copywriting", ["vendor/custom-model:free"])
    assert registry.get_chain("copywriting") == ["vendor/custom-model:free"]
    registry.save()
    reloaded = ModelRegistry.load(path)
    assert reloaded.get_chain("copywriting") == ["vendor/custom-model:free"]


def test_registry_add_model_errors() -> None:
    registry = ModelRegistry(_registry_dict())
    with pytest.raises(RegistryError):
        registry.add_model("no-slash", label="Bad")
    with pytest.raises(RegistryError):
        registry.add_model("vendor/x:free", label="Bad", status="bogus")
    with pytest.raises(RegistryError):
        registry.add_model("vendor/x:free", label="Bad", tasks=["nope"])
    with pytest.raises(RegistryError):
        registry.set_chain("nope", MODELS)
    with pytest.raises(RegistryError):
        registry.set_chain("copywriting", [])
    with pytest.raises(RegistryError):
        registry.get_chain("nope")
    with pytest.raises(RegistryError):
        registry.get_status("vendor/ghost:free")
    with pytest.raises(RegistryError):
        registry.set_status("vendor/ghost:free", "failed")
    with pytest.raises(RegistryError):
        registry.set_status(MODELS[0], "bogus")
    with pytest.raises(RegistryError):
        ModelRegistry({}).save()


def test_registry_load_errors(tmp_path: Path) -> None:
    with pytest.raises(RegistryError):
        ModelRegistry.load(tmp_path / "missing.json")
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryError):
        ModelRegistry.load(bad_json)
    for raw in (
        [],
        {"version": "models/v1"},
        {**_registry_dict(), "openrouter": {}},
        {**_registry_dict(), "tasks": {}},
        {**_registry_dict(), "registry": {}},
        {**_registry_dict(), "registry": {"bad-id": {"status": "unknown"}}},
        {**_registry_dict(), "registry": {MODELS[0]: {"status": "bogus"}}},
    ):
        with pytest.raises(RegistryError):
            ModelRegistry(raw)


def test_check_model_status_unknown_model_and_probe_exception(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    with pytest.raises(RegistryError):
        check_model_status("vendor/ghost:free", path)
    with patch("httpx.Client", side_effect=TimeoutError("down")):
        assert check_model_status(MODELS[2], path) == "Failed"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["registry"][MODELS[2]]["status"] == "failed"


def test_client_request_exception_empty_and_unparseable() -> None:
    client = OpenRouterClient(api_key="k", timeout_s=5)
    with (
        patch("httpx.Client", side_effect=ConnectionError("down")),
        pytest.raises(ModelCallError),
    ):
        client.complete(TaskType.COPYWRITING, "p", MODELS[0])
    with patch("httpx.Client") as client_cls:
        mocked = client_cls.return_value.__enter__.return_value
        empty = MagicMock()
        empty.status_code = 200
        empty.json.return_value = {"choices": [{"message": {"content": "  "}}]}
        mocked.post.return_value = empty
        with pytest.raises(ModelCallError):
            client.complete(TaskType.COPYWRITING, "p", MODELS[0])
        broken = MagicMock()
        broken.status_code = 200
        broken.json.return_value = {"nope": True}
        mocked.post.return_value = broken
        with pytest.raises(ModelCallError):
            client.complete(TaskType.COPYWRITING, "p", MODELS[0])


def test_orchestrator_from_config_persists_status(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    with patch.object(OpenRouterClient, "complete", return_value="ok"):
        orch = TaskOrchestrator.from_config(path)
        result = orch.execute("copywriting", "prompt")
    assert result.model_used == MODELS[0]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["registry"][MODELS[0]]["status"] == "connected"


def test_cli_check_models_reports_states(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(_registry_dict()), encoding="utf-8")
    runner = CliRunner()
    with patch("pulsecraft.llm.registry._probe_openrouter", return_value=True):
        result = runner.invoke(main, ["check-models", "--config", str(path)])
    assert result.exit_code == 0, result.output
    assert "Connected" in result.output
