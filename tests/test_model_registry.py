"""TDD Red phase: model registry loading + validation (M1 goes Green).

Expected to FAIL on `chore/m0-foundation-setup` because
`src/pulsecraft/llm/registry.py::load_model_registry` is an intentional
NotImplementedError stub. M1 (Epic 2, US-2.1/US-2.2) implements parsing,
per-task chains, and Connected/Failed health checks to make this green.
"""

import json
from pathlib import Path

from pulsecraft.llm.registry import load_model_registry

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "models.json"


def test_models_json_exists_and_parses() -> None:
    assert CONFIG_PATH.is_file(), f"missing {CONFIG_PATH}"
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert raw["version"] == "models/v1"


def test_registry_loads_with_task_chains_and_status_schema() -> None:
    registry = load_model_registry(CONFIG_PATH)
    assert registry["version"] == "models/v1"
    for task in ("scriptHeadline", "blueprintTranslate"):
        chain = registry["tasks"][task]["chain"]
        assert isinstance(chain, list) and len(chain) >= 1
    for model_id, entry in registry["registry"].items():
        assert isinstance(model_id, str) and "/" in model_id
        assert entry["status"] in ("unknown", "connected", "failed")
