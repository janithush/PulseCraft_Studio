"""Dynamic Code Template Engine manager (M2): scan, list, validate, inspect.

Templates are data: `/templates/posts/<layout>/index.html` (Jinja2) + offline-safe
`style.css` + `meta.json`. The core pipeline never changes when packs are added.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment
from jinja2 import meta as jinja_meta

REMOTE_URL_RE = re.compile(r"https?://", re.IGNORECASE)

BADGE_TAGS: dict[str, Any] = {
    "hook": "[Hook Here]",
    "headline": "[Headline Here]",
    "sub": "[Subcopy Here]",
    "cta": "[CTA Here]",
    "badge": "[Badge Here]",
    "bullets": ["[Bullet 1]", "[Bullet 2]", "[Bullet 3]"],
    "hashtags": ["[#tag1]", "[#tag2]"],
    "canvas": "square",
}


class TemplateError(ValueError):
    """Unknown template id or unreadable/invalid template pack."""


@dataclass
class TemplateInfo:
    name: str
    kind: str
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)


class TemplateManager:
    """Scans, lists, validates, hydrates, and inspects template packs."""

    def __init__(self, root: str | Path = "templates") -> None:
        self._root = Path(root)

    def _kind_dir(self, kind: str) -> Path:
        return self._root / kind

    def list(self, kind: str = "posts") -> list[TemplateInfo]:
        kind_dir = self._kind_dir(kind)
        if not kind_dir.is_dir():
            return []
        infos: list[TemplateInfo] = []
        for child in sorted(kind_dir.iterdir()):
            if child.is_dir() and (child / "index.html").is_file():
                infos.append(self._describe(kind, child))
        return infos

    def names(self, kind: str = "posts") -> list[str]:
        return [info.name for info in self.list(kind)]

    def get(self, name: str, kind: str = "posts") -> TemplateInfo:
        candidate = self._kind_dir(kind) / name
        if not candidate.is_dir() or not (candidate / "index.html").is_file():
            raise TemplateError(
                f"unknown {kind} template '{name}'. Available: {self.names(kind) or 'none'}"
            )
        return self._describe(kind, candidate)

    def validate(self, name: str, kind: str = "posts") -> list[str]:
        """Return non-fatal warnings; empty means clean."""
        info = self.get(name, kind)
        warnings: list[str] = []
        if not (info.path / "meta.json").is_file():
            warnings.append(f"{name}: missing meta.json")
        else:
            try:
                json.loads((info.path / "meta.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                warnings.append(f"{name}: meta.json invalid: {exc}")
        for asset in ("index.html", "style.css"):
            asset_path = info.path / asset
            if not asset_path.is_file():
                warnings.append(f"{name}: missing {asset}")
                continue
            if REMOTE_URL_RE.search(asset_path.read_text(encoding="utf-8")):
                warnings.append(f"{name}: {asset} references a remote URL (must be offline-safe)")
        try:
            undeclared = self._undeclared(info)
        except TemplateError as exc:
            return warnings + [f"{name}: {exc}"]
        declared = self._declared_placeholders(info)
        for var in sorted(undeclared - declared - {"canvas"}):
            warnings.append(f"{name}: template uses undeclared variable '{var}'")
        for var in sorted((declared - undeclared) - {"canvas"}):
            warnings.append(f"{name}: meta.json declares unused variable '{var}'")
        return warnings

    def hydrate(
        self, name: str, data: dict[str, Any], kind: str = "posts", canvas: str = "square"
    ) -> str:
        """Render a template with data (L1 conditionals + L2 loops live here)."""
        info = self.get(name, kind)
        source = (info.path / "index.html").read_text(encoding="utf-8")
        template = Environment(autoescape=False).from_string(source)
        context = dict(data)
        context.setdefault("canvas", canvas)
        return template.render(context)

    def inspect_template(self, name: str, kind: str = "posts") -> dict[str, Any]:
        """Badge-tag preview + required/optional placeholder schema.

        Returns {"name", "html", "schema": {"required", "optional"},
        "warnings", "canvas"}. Placeholders are filled with visual badge tags
        (e.g. `[Headline Here]`) so layout/overflow is judged without real copy.
        """
        info = self.get(name, kind)
        undeclared = self._undeclared(info)
        declared_required, declared_optional = self._declared_split(info)
        extra = undeclared - declared_required - declared_optional - {"canvas"}
        required = sorted(declared_required | extra)
        optional = sorted(declared_optional | ({"canvas"} if "canvas" in undeclared else set()))
        badge_data = {
            key: BADGE_TAGS[key] for key in (set(required) | set(optional)) if key in BADGE_TAGS
        }
        html = self.hydrate(info.name, badge_data, kind=kind, canvas="square")
        return {
            "name": info.name,
            "html": html,
            "schema": {"required": required, "optional": optional},
            "warnings": self.validate(info.name, kind),
            "canvas": "square",
        }

    def _describe(self, kind: str, path: Path) -> TemplateInfo:
        meta: dict[str, Any] = {}
        meta_path = path / "meta.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
        return TemplateInfo(name=path.name, kind=kind, path=path, meta=meta)

    def _undeclared(self, info: TemplateInfo) -> set[str]:
        source = (info.path / "index.html").read_text(encoding="utf-8")
        try:
            ast = Environment(autoescape=False).parse(source)
        except Exception as exc:
            raise TemplateError(f"template '{info.name}' does not parse: {exc}") from exc
        return set(jinja_meta.find_undeclared_variables(ast))

    def _declared_placeholders(self, info: TemplateInfo) -> set[str]:
        required, optional = self._declared_split(info)
        return required | optional

    def _declared_split(self, info: TemplateInfo) -> tuple[set[str], set[str]]:
        placeholders = info.meta.get("placeholders", {})
        required = set(placeholders.get("required", []))
        optional = set(placeholders.get("optional", []))
        return required, optional


def lint_offline_safety(html: str, source: str = "template") -> None:
    """Raise TemplateError if rendered HTML pulls remote resources."""
    if REMOTE_URL_RE.search(html):
        raise TemplateError(f"{source} references a remote URL (must be offline-safe)")
