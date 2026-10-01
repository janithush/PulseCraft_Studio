"""Memory release hooks (M6 performance engine).

Called after every render/campaign task to auto-purge PyTorch/Whisper
caches on the Intel i5 11th Gen + 20GB RAM reference box.
"""

from __future__ import annotations

import gc
import logging
from contextlib import suppress

logger = logging.getLogger(__name__)


def release_memory() -> int:
    """Run `gc.collect()` + best-effort Torch CUDA purge. Returns objects freed."""
    collected = gc.collect()
    with suppress(Exception):
        import torch

        with suppress(Exception):
            torch.cuda.empty_cache()
    logger.info("web.memory released objects=%d", collected)
    return collected
