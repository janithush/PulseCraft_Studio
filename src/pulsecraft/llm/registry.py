"""Dynamic Model Registry loader (M0 TDD Red stub; M1 implements Green).

Intentionally unimplemented so `tests/test_model_registry.py` FAILS (Red phase).
M1 will parse/validate `config/models.json` (models/v1) here.
"""

from pathlib import Path
from typing import Any


def load_model_registry(config_path: str | Path = "config/models.json") -> dict[str, Any]:
    """Load and validate the model registry. M1 implements; M0 raises."""
    raise NotImplementedError(
        f"TDD Red: load_model_registry not implemented yet (config={config_path}). "
        "M1 (Epic 2) will implement models/v1 parsing + validation."
    )
