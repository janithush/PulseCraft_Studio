"""Static post renderer (M2): 4-layer resolution + Playwright dual-PNG export.

Layers: L1 conditionals + L2 loops (Jinja2 hydration) -> L3 pre-built variant ->
L4 full dynamic LLM layout generation (`PROMPT_EXPANSION`) fallback.
Exports pixel-perfect 1080x1080 + 1080x1350 PNGs with `meta.json`.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pulsecraft.templates_mgr.manager import (
    TemplateError,
    TemplateManager,
    lint_offline_safety,
)

CANVASES: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),
    "vertical": (1080, 1350),
}
CANVAS_IDS: dict[str, str] = {"1080x1080": "square", "1080x1350": "vertical"}

FENCE_RE = re.compile(r"```(?:html)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class RenderError(RuntimeError):
    """Rendering failed (unknown brand, lint failure, browser error, dim mismatch)."""


@dataclass
class RenderResult:
    png_square: Path
    png_vertical: Path
    meta_path: Path
    layer: str
    template_id: str
    warnings: list[str] = field(default_factory=list)


class StaticPostRenderer:
    """Renders a static-post blueprint to 1080x1080 + 1080x1350 PNGs."""

    def __init__(
        self,
        templates_root: str | Path = "templates",
        brands_root: str | Path = "brands",
        orchestrator: Any = None,
    ) -> None:
        self._manager = TemplateManager(templates_root)
        self._brands_root = Path(brands_root)
        self._orchestrator = orchestrator

    def resolve_layer(self, blueprint: dict[str, Any]) -> str:
        """L3 when `layout` matches a catalog pack, else L4 (LLM fallback)."""
        layout = str(blueprint.get("layout", ""))
        try:
            self._manager.get(layout, kind="posts")
        except Exception:
            return "L4"
        return "L3"

    def load_brand(self, slug: str) -> tuple[dict[str, Any], list[str]]:
        """Merge `_base.json` + `brands/<slug>.json`; missing slug warns, never crashes."""
        warnings: list[str] = []
        base_path = self._brands_root / "_base.json"
        base: dict[str, Any] = {}
        if base_path.is_file():
            base = json.loads(base_path.read_text(encoding="utf-8"))
        slug_path = self._brands_root / f"{slug}.json"
        if not slug_path.is_file():
            template_path = self._brands_root / "_template" / "brand.json"
            if template_path.is_file():
                warnings.append(f"brand '{slug}' not found; falling back to _base.json")
                return base, warnings
            raise RenderError(f"brand '{slug}' not found and no _base.json fallback")
        override = json.loads(slug_path.read_text(encoding="utf-8"))
        merged = _deep_merge(base, override)
        return merged, warnings

    def hydration_context(
        self, blueprint: dict[str, Any], brand: dict[str, Any], canvas: str
    ) -> dict[str, Any]:
        copy = blueprint.get("copy", {})
        context: dict[str, Any] = {
            "hook": copy.get("hook", ""),
            "sub": copy.get("sub", ""),
            "cta": copy.get("cta", ""),
            "bullets": blueprint.get("bullets", []),
            "hashtags": blueprint.get("hashtags", []),
            "badge": blueprint.get("badge", ""),
            "brand": brand,
            "canvas": canvas,
        }
        assets = blueprint.get("assets", {})
        if isinstance(assets, dict) and assets.get("localPath"):
            context["asset_url"] = assets["localPath"]
        return context

    def generate_dynamic_html(self, blueprint: dict[str, Any], canvas_id: str) -> str:
        """L4: `PROMPT_EXPANSION` generates raw HTML/Tailwind for the canvas."""
        from pulsecraft.llm.client import TaskType

        orchestrator = self._orchestrator
        if orchestrator is None:
            from pulsecraft.llm.orchestrator import TaskOrchestrator

            orchestrator = TaskOrchestrator.from_config()
        width, height = CANVASES[CANVAS_IDS[canvas_id]]
        prompt = (
            f"Generate a standalone raw HTML document (inline <style> only, no external "
            f"URLs) for a {width}x{height} social post. Layout hint: "
            f"{blueprint.get('layout')} / {blueprint.get('variantHint', '')}. "
            f"Copy: {json.dumps(blueprint.get('copy', {}))}. "
            f"Bullets: {json.dumps(blueprint.get('bullets', []))}."
        )
        result = orchestrator.execute(TaskType.PROMPT_EXPANSION, prompt)
        html = _strip_fences(result.text)
        try:
            lint_offline_safety(html, source="L4 dynamic layout")
        except TemplateError as exc:
            raise RenderError(str(exc)) from exc
        self._last_model_used = result.model_used
        return html

    def render_post(
        self,
        blueprint: str | Path | dict[str, Any],
        brand: str = "acme",
        out_dir: str | Path = "out",
    ) -> RenderResult:
        """Render both canvases; returns PNG paths + meta.json location."""
        if isinstance(blueprint, (str, Path)):
            blueprint = json.loads(Path(blueprint).read_text(encoding="utf-8"))
        if blueprint.get("type") not in (None, "static-post"):
            raise RenderError(
                f"render_post needs a static-post blueprint, got {blueprint.get('type')}"
            )
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        brand_tokens, brand_warnings = self.load_brand(brand)
        warnings = list(brand_warnings)
        warnings += self._contrast_warnings(brand_tokens)
        layer = self.resolve_layer(blueprint)
        layout = str(blueprint.get("layout", ""))
        template_id = layout if layer == "L3" else f"dynamic:{layout}"
        model_used: str | None = None
        canvas_ids: list[str] = blueprint.get("canvas", ["1080x1080", "1080x1350"])
        started = time.perf_counter()
        files: dict[str, dict[str, Any]] = {}
        dynamic_html: dict[str, str] = {}
        if layer == "L4":
            for canvas_id in canvas_ids:
                dynamic_html[canvas_id] = self.generate_dynamic_html(blueprint, canvas_id)
            model_used = getattr(self, "_last_model_used", None)
        for canvas_id in canvas_ids:
            canvas = CANVAS_IDS[canvas_id]
            width, height = CANVASES[canvas]
            if layer == "L3":
                context = self.hydration_context(blueprint, brand_tokens, canvas)
                html = self._manager.hydrate(layout, context, kind="posts", canvas=canvas)
                html = self._inline_template_assets(layout, html, brand_tokens)
            else:
                html = self._inline_tokens(dynamic_html[canvas_id], brand_tokens)
            png_name = f"{'square' if canvas == 'square' else 'vertical'}-{canvas_id}.png"
            png_path = out / png_name
            shot_ms = self._screenshot(html, width, height, png_path)
            files[canvas_id] = {
                "file": png_name,
                "width": width,
                "height": height,
                "sha256": _sha256(png_path),
                "shotMs": shot_ms,
            }
        duration_ms = int((time.perf_counter() - started) * 1000)
        meta = {
            "blueprint": blueprint.get("type", "static-post"),
            "brand": brand,
            "templateId": template_id,
            "layer": layer,
            "modelUsed": model_used,
            "dimensions": {
                cid: [CANVASES[CANVAS_IDS[cid]][0], CANVASES[CANVAS_IDS[cid]][1]]
                for cid in canvas_ids
            },
            "files": files,
            "durationMs": duration_ms,
            "warnings": warnings,
        }
        meta_path = out / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        pngs = {cid: out / files[cid]["file"] for cid in canvas_ids}
        return RenderResult(
            png_square=pngs.get("1080x1080", out / "square-1080x1080.png"),
            png_vertical=pngs.get("1080x1350", out / "vertical-1080x1350.png"),
            meta_path=meta_path,
            layer=layer,
            template_id=template_id,
            warnings=warnings,
        )

    def tokens_css(self, brand: dict[str, Any]) -> str:
        colors = brand.get("colors", {})
        fonts = brand.get("fonts", {})

        def var(name: str, value: str) -> str:
            return f"  --brand-{name}: {value};"

        lines = [":root {"]
        for key in ("primary", "secondary", "accent", "bg", "text"):
            if colors.get(key):
                lines.append(var(key, colors[key]))
        if fonts.get("display"):
            lines.append(var("display", fonts["display"]))
        if fonts.get("body"):
            lines.append(var("body", fonts["body"]))
        lines.append("}")
        return "\n".join(lines) + "\n"

    def _inline_template_assets(self, layout: str, html: str, brand: dict[str, Any]) -> str:
        try:
            info = self._manager.get(layout, kind="posts")
        except Exception:
            return self._inline_tokens(html, brand)
        css_parts: list[str] = []
        style_path = info.path / "style.css"
        if style_path.is_file():
            css_parts.append(style_path.read_text(encoding="utf-8"))
        css_parts.append(self.tokens_css(brand))
        bundle = "<style>\n" + "\n".join(css_parts) + "\n</style>"
        html = re.sub(
            r'<link[^>]*rel="stylesheet"[^>]*/?>',
            bundle,
            html,
            count=1,
            flags=re.IGNORECASE,
        )
        if "<style>" not in html:
            html = html.replace("</head>", bundle + "\n</head>")
        return html

    def _inline_tokens(self, html: str, brand: dict[str, Any]) -> str:
        bundle = "<style>\n" + self.tokens_css(brand) + "\n</style>"
        if "</head>" in html:
            return html.replace("</head>", bundle + "\n</head>", 1)
        return bundle + html

    def _screenshot(self, html: str, width: int, height: int, out_path: Path) -> int:
        """Render HTML to an exact-size PNG; returns shot milliseconds."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RenderError(
                "playwright is not installed (pip install playwright && playwright install chromium)"
            ) from exc
        started = time.perf_counter()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_content(html, wait_until="networkidle")
                with suppress(Exception):
                    page.evaluate("document.fonts.ready.then(() => 0)", timeout=5000)
                page.screenshot(path=str(out_path), full_page=False)
            finally:
                browser.close()
        shot_ms = int((time.perf_counter() - started) * 1000)
        self._assert_dimensions(out_path, width, height)
        return shot_ms

    def _assert_dimensions(self, png_path: Path, width: int, height: int) -> None:
        from PIL import Image

        with Image.open(png_path) as image:
            actual = (image.width, image.height)
        if actual != (width, height):
            raise RenderError(
                f"{png_path.name}: got {actual[0]}x{actual[1]}, want {width}x{height}"
            )

    def _contrast_warnings(self, brand: dict[str, Any]) -> list[str]:
        colors = brand.get("colors", {})
        warnings: list[str] = []
        ratio = _contrast_ratio(str(colors.get("text", "")), str(colors.get("bg", "")))
        if ratio is not None and ratio < 4.5:
            warnings.append(f"body text contrast {ratio:.2f}:1 below 4.5:1")
        return warnings


def _strip_fences(text: str) -> str:
    match = FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _luminance(hex_color: str) -> float | None:
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        rgb = [int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return None

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(foreground: str, background: str) -> float | None:
    lum_a, lum_b = _luminance(foreground), _luminance(background)
    if lum_a is None or lum_b is None:
        return None
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)
