"""Task-based OpenRouter chat client (M1): 4 task types, no hardcoded models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

import httpx


class TaskType(StrEnum):
    """The 4 text-LLM execution task types."""

    PROMPT_EXPANSION = "promptExpansion"
    COPYWRITING = "copywriting"
    VISUAL_QUERY_GEN = "visualQueryGen"
    JSON_BLUEPRINT_CONVERSION = "jsonBlueprintConversion"


@dataclass(frozen=True)
class TaskProfile:
    system_prompt: str
    temperature: float
    max_tokens: int
    json_mode: bool


TASK_PROFILES: dict[TaskType, TaskProfile] = {
    TaskType.PROMPT_EXPANSION: TaskProfile(
        system_prompt=(
            "Expand the raw user idea into a detailed English HTML/CSS layout and "
            "visual style prompt for a static post template. Be concrete about "
            "composition, palette roles, typography scale, and safe areas."
        ),
        temperature=0.7,
        max_tokens=800,
        json_mode=False,
    ),
    TaskType.COPYWRITING: TaskProfile(
        system_prompt=(
            "Write engaging headlines, hooks, body text, CTAs, captions, and "
            "hashtags in the brand voice. Hook-first, scannable, no filler."
        ),
        temperature=0.8,
        max_tokens=600,
        json_mode=False,
    ),
    TaskType.VISUAL_QUERY_GEN: TaskProfile(
        system_prompt=(
            "Generate precise Pexels asset search keywords for images and "
            "background videos. Reply with a comma-separated keyword list only."
        ),
        temperature=0.3,
        max_tokens=120,
        json_mode=False,
    ),
    TaskType.JSON_BLUEPRINT_CONVERSION: TaskProfile(
        system_prompt=(
            "Parse the text and visual descriptions into a strict Post/Reel JSON "
            "blueprint (blueprint/v1). Output JSON only. No prose."
        ),
        temperature=0.1,
        max_tokens=1500,
        json_mode=True,
    ),
}


class ModelCallError(RuntimeError):
    """One model attempt failed (network, timeout, non-200, or empty content)."""

    def __init__(self, model_id: str, reason: str) -> None:
        super().__init__(f"{model_id}: {reason}")
        self.model_id = model_id
        self.reason = reason


class OpenRouterClient:
    """Thin OpenRouter `/chat/completions` client; models always come from config."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self._timeout_s = timeout_s

    def complete(self, task: TaskType, prompt: str, model_id: str) -> str:
        profile = TASK_PROFILES[task]
        body: dict = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": profile.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
        }
        if profile.json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                resp = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except Exception as exc:
            raise ModelCallError(model_id, f"request failed: {exc}") from exc
        if resp.status_code != 200:
            raise ModelCallError(model_id, f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ModelCallError(model_id, f"unparseable response: {exc}") from exc
        if not content or not str(content).strip():
            raise ModelCallError(model_id, "empty content")
        return str(content).strip()
