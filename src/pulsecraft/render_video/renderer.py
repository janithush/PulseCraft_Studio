"""Video reel rendering controller (M3): blueprint + preset + flags + platform → MP4s.

`VideoReelRenderer` orchestrates TTS → timestamps → media/SFX-BGM → Remotion.
Subprocess + network collaborators are injectable so unit tests run headless.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pulsecraft.common.feature_flags import FeatureFlags

logger = logging.getLogger(__name__)

PLATFORM_CANVASES: dict[str, list[str]] = {
    "fb": ["1080x1080", "1080x1920"],
    "ig": ["1080x1350", "1080x1920"],
    "all": ["1080x1080", "1080x1350", "1080x1920"],
}
CANVAS_WH: dict[str, tuple[int, int]] = {
    "1080x1080": (1080, 1080),
    "1080x1350": (1080, 1350),
    "1080x1920": (1080, 1920),
}
PRESETS = ("alex-hormozi", "faceless-docu", "b-roll-centric", "kinetic-bold")

Runner = Callable[[list[str], Path], Any]


class VideoRenderError(RuntimeError):
    """Reel rendering failed (bad blueprint/preset, remotion error, missing MP4)."""


@dataclass
class ReelResult:
    files: dict[str, Path]
    meta_path: Path
    preset: str
    platform: str
    warnings: list[str] = field(default_factory=list)


def _resolve_npx() -> str:
    """Resolve the npx executable.

    On Windows (`os.name == "nt"`) node ships only `npx.CMD`/`npx.ps1`
    (no `npx.exe`), and `CreateProcess` cannot launch a bare ``"npx"``
    with ``shell=False`` (``FileNotFoundError: [WinError 2]``). Passing
    the resolved path (e.g. ``npx.cmd``) lets ``subprocess`` run it
    directly. Non-Windows platforms keep the plain ``"npx"`` lookup.
    """
    if os.name == "nt":
        resolved = shutil.which("npx")
        if resolved:
            return resolved
        node = shutil.which("node")
        if node:
            candidate = Path(node).with_name("npx.cmd")
            if candidate.is_file():
                return str(candidate)
    return "npx"


def default_runner(cmd: list[str], cwd: Path) -> Any:
    if cmd and cmd[0] == "npx":
        cmd = [_resolve_npx(), *cmd[1:]]
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=600)


def audio_data_uri(path: str | Path) -> str:
    """Encode a local audio file as a base64 data URI for Remotion props.

    Remotion's asset downloader only fetches ``http(s)`` URLs, so absolute
    local paths (e.g. ``D:/.../*.wav``) fail in ``downloadAsset``. A
    ``data:audio/wav;base64,...`` URI is written inline by the renderer
    and works on every platform.
    """
    import base64

    file_path = Path(path)
    mime = {".wav": "audio/wav", ".mp3": "audio/mp3"}.get(file_path.suffix.lower(), "audio/wav")
    data = file_path.read_bytes()
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


class VideoReelRenderer:
    """End-to-end reel pipeline; heavy stages degrade per feature flags."""

    def __init__(
        self,
        remotion_root: str | Path = "remotion",
        templates_root: str | Path = "templates",
        brands_root: str | Path = "brands",
        flags: FeatureFlags | None = None,
        tts: Any = None,
        stt: Any = None,
        media: Any = None,
        audio_fetcher: Any = None,
        runner: Runner | None = None,
    ) -> None:
        self._remotion = Path(remotion_root)
        self._templates = Path(templates_root)
        self._brands = Path(brands_root)
        self._flags = flags or FeatureFlags.load()
        self._tts = tts
        self._stt = stt
        self._media = media
        self._audio_fetcher = audio_fetcher
        self._runner = runner or default_runner

    def platform_canvases(self, platform: str) -> list[str]:
        try:
            return list(PLATFORM_CANVASES[platform])
        except KeyError as exc:
            raise VideoRenderError(
                f"unknown platform '{platform}'. Choose: {sorted(PLATFORM_CANVASES)}"
            ) from exc

    def check_preset(self, preset: str) -> Path:
        if preset not in PRESETS:
            raise VideoRenderError(f"unknown preset '{preset}'. Available: {list(PRESETS)}")
        preset_dir = self._templates / "reels" / preset
        if not preset_dir.is_dir():
            raise VideoRenderError(f"preset '{preset}' has no template pack at {preset_dir}")
        return preset_dir

    def render_reel(
        self,
        blueprint: str | Path | dict[str, Any],
        brand: str = "acme",
        preset: str = "alex-hormozi",
        platform: str = "all",
        out_dir: str | Path = "out",
    ) -> ReelResult:
        """Run the full reel pipeline; returns per-canvas MP4 paths + meta.json."""
        if isinstance(blueprint, (str, Path)):
            blueprint = json.loads(Path(blueprint).read_text(encoding="utf-8"))
        if blueprint.get("type") not in (None, "reel"):
            raise VideoRenderError(
                f"render_reel needs a reel blueprint, got {blueprint.get('type')}"
            )
        self.check_preset(preset)
        canvases = self.platform_canvases(platform)
        # Absolute paths: the Remotion child process runs with cwd=remotion/,
        # so project-root-relative paths would not resolve there (WinError-style
        # "--props is neither valid JSON nor a file path" failures).
        out = Path(out_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        cleaned, warnings = self._flags.enforce(blueprint)
        tweaks, warnings = self._apply_tweaks(cleaned, preset, warnings)
        tokens, warnings = self._brand_tokens(brand, warnings)
        voice_path, words, model, estimated, warnings = self._voice_and_words(
            cleaned, brand, out, warnings
        )
        scenes, assets, warnings = self._scenes(cleaned, warnings)
        mix_path, warnings = self._audio_bed(cleaned, voice_path, words, out, warnings)

        files: dict[str, Path] = {}
        started = time.perf_counter()
        for canvas_id in canvases:
            width, height = CANVAS_WH[canvas_id]
            audio_src = mix_path or voice_path or ""
            try:
                audio_arg = audio_data_uri(audio_src) if audio_src else ""
            except OSError as exc:
                warnings.append(f"voiceover audio unreadable ({exc}); rendering without audio")
                audio_arg = ""
            props = {
                "script": cleaned.get("script", []),
                "scenes": scenes,
                # Data URI: Remotion only downloads http(s) assets, so a local
                # path would fail in downloadAsset (use inline audio instead).
                "audioSrc": audio_arg,
                "words": words,
                "brandTokens": tokens.get("colors", {}),
                "preset": preset,
                "presetTweaks": tweaks,
                "canvas": canvas_id,
                "width": width,
                "height": height,
            }
            props_path = out / f"props-{canvas_id}.json"
            props_path.write_text(json.dumps(props, indent=2), encoding="utf-8")
            target = out / f"reel-{canvas_id}.mp4"
            self._remotion_render(preset, props_path, target, width, height, warnings)
            files[canvas_id] = target
        duration_ms = int((time.perf_counter() - started) * 1000)
        meta = {
            "blueprint": cleaned.get("type", "reel"),
            "brand": brand,
            "preset": preset,
            "presetTweaks": tweaks,
            "platform": platform,
            "canvases": canvases,
            "voiceModel": model,
            "timestampsEstimated": estimated,
            "assets": assets,
            "files": {cid: path.name for cid, path in files.items()},
            "durationMs": duration_ms,
            "warnings": warnings,
        }
        meta_path = out / "reel-meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return ReelResult(
            files=files, meta_path=meta_path, preset=preset, platform=platform, warnings=warnings
        )

    def _apply_tweaks(
        self, blueprint: dict[str, Any], preset: str, warnings: list[str]
    ) -> tuple[dict[str, Any], list[str]]:
        allowed = self._preset_tweaks(preset)
        tweaks = blueprint.get("style", {}).get("presetTweaks", {}) or {}
        kept = {k: v for k, v in tweaks.items() if k in allowed}
        for key in tweaks:
            if key not in allowed:
                warnings.append(f"preset '{preset}': ignoring unknown tweak '{key}'")
        return kept, warnings

    def _preset_tweaks(self, preset: str) -> set[str]:
        meta_path = self._templates / "reels" / preset / "meta.json"
        try:
            return set(json.loads(meta_path.read_text(encoding="utf-8")).get("tweaks", []))
        except (OSError, ValueError):
            return set()

    def _brand_tokens(self, brand: str, warnings: list[str]) -> tuple[dict[str, Any], list[str]]:
        from pulsecraft.render_static.renderer import StaticPostRenderer

        tokens, brand_warnings = StaticPostRenderer(brands_root=self._brands).load_brand(brand)
        return tokens, warnings + brand_warnings

    def _voice_and_words(
        self, blueprint: dict[str, Any], brand: str, out: Path, warnings: list[str]
    ) -> tuple[Any, list[dict[str, Any]], str | None, bool, list[str]]:
        script_text = " ".join(s.get("voText", "") for s in blueprint.get("script", []))
        voice = blueprint.get("voice", {})
        voice_id = voice.get("id", "kokoro-default")
        if not self._flags.guard("tts.kokoro", bool(script_text)):
            warnings.append("toggle 'tts.kokoro' disabled: skipping voiceover")
            return None, [], None, True, warnings
        tts = self._tts or self._default_tts()
        from pulsecraft.tts.kokoro import TTSError

        try:
            voice_path, _hit = tts.synthesize(script_text, voice=voice_id)
        except TTSError as exc:
            msg = "voiceover unavailable; proceeding without voiceover"
            logger.warning(msg + f" ({exc})")
            warnings.append(msg)
            return None, [], None, True, warnings
        stt = self._stt or self._default_stt()
        no_whisper = not self._flags.enabled("stt.whisper")
        if no_whisper:
            warnings.append("toggle 'stt.whisper' disabled: using uniform timing (estimated)")
        stamped = stt.transcribe(voice_path, text_hint=script_text, no_whisper=no_whisper)
        if stamped.get("estimated"):
            warnings.append("word timestamps estimated; karaoke may drift")
        return (
            voice_path,
            stamped["words"],
            stamped.get("model"),
            bool(stamped.get("estimated")),
            warnings,
        )

    def _scenes(
        self, blueprint: dict[str, Any], warnings: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        from pulsecraft.assets.media_fetcher import extract_visual_tags, resolve_local_override

        scenes: list[dict[str, Any]] = []
        assets: list[dict[str, Any]] = []
        script_text = " ".join(s.get("voText", "") for s in blueprint.get("script", []))
        for tag in extract_visual_tags(script_text):
            if not self._flags.guard("media.localOverrides", True):
                warnings.append(f"toggle 'media.localOverrides' disabled: ignoring [{tag}]")
                continue
            local = resolve_local_override(tag)
            if local is None:
                warnings.append(
                    f"local visual '{tag}' not found in input/visuals/; provider fallback"
                )
                continue
            scenes.append({"id": tag, "assetUrl": local.as_uri(), "provider": "local"})
            assets.append({"provider": "local", "localPath": str(local)})
        for scene in blueprint.get("scenes", []):
            query = scene.get("assetQuery", "")
            if not query:
                continue
            asset, fetch_warnings = self._media_fetch(query)
            warnings += fetch_warnings
            scenes.append(
                {
                    "id": scene.get("id", query),
                    "assetUrl": asset.get("url", ""),
                    "provider": asset.get("provider", ""),
                }
            )
            assets.append(asset)
        if not scenes:
            warnings.append("no B-roll resolved; preset gradient fallback will be used")
        return scenes, assets, warnings

    def _media_fetch(self, query: str) -> tuple[dict[str, Any], list[str]]:
        if self._media is None:
            from pulsecraft.assets.media_fetcher import MediaFetcher

            self._media = MediaFetcher(flags=self._flags)
        return self._media.fetch_scene(query)

    def _audio_bed(
        self,
        blueprint: dict[str, Any],
        voice_path: Any,
        words: list[dict[str, Any]],
        out: Path,
        warnings: list[str],
    ) -> tuple[Any, list[str]]:
        tags = blueprint.get("audioTags", [])
        if not self._flags.guard("audio.bgm", bool(tags)):
            if tags:
                warnings.append("toggle 'audio.bgm' disabled: skipping BGM bed")
            return None, warnings
        fetcher = self._audio_fetcher or self._default_audio_fetcher()
        hits, fetch_warnings = fetcher.fetch(tags, kind="bgm")
        warnings += fetch_warnings
        if not hits or voice_path is None:
            return None, warnings
        bgm_local = hits[0].get("localPath")
        if not bgm_local:
            warnings.append("BGM has no local file; voice-only mix")
            return None, warnings
        from pulsecraft.audio.mixer import mix_voice_bgm

        ducking = self._flags.enabled("audio.ducking")
        if not ducking:
            warnings.append("toggle 'audio.ducking' disabled: flat BGM bed")
        mix_path = out / "mix-voice-bgm.wav"
        try:
            mix_voice_bgm(voice_path, bgm_local, words, mix_path, ducking=ducking)
        except Exception as exc:
            warnings.append(f"audio mix failed ({exc}); voice-only")
            return None, warnings
        return mix_path, warnings

    def _remotion_render(
        self,
        preset: str,
        props_path: Path,
        target: Path,
        width: int,
        height: int,
        warnings: list[str],
    ) -> None:
        if not self._flags.enabled("render.remotion"):
            raise VideoRenderError("toggle 'render.remotion' disabled")
        # Absolute POSIX argv: immune to the child cwd (remotion/) and to
        # Windows backslash handling in the npx.cmd shim chain.
        # Entry point is explicit (src/index.ts calls registerRoot); the
        # composition id equals the preset (one <Composition> per preset).
        entry_arg = (self._remotion / "src" / "index.ts").resolve().as_posix()
        target_arg = Path(target).resolve().as_posix()
        props_arg = Path(props_path).resolve().as_posix()
        cmd = [
            "npx",
            "remotion",
            "render",
            entry_arg,
            preset,
            target_arg,
            "--props",
            props_arg,
            "--width",
            str(width),
            "--height",
            str(height),
        ]
        completed = self._runner(cmd, self._remotion)
        if getattr(completed, "returncode", 1) != 0:
            stderr = str(getattr(completed, "stderr", ""))[-500:]
            raise VideoRenderError(f"remotion render failed for {target.name}: {stderr}")
        if not target.is_file():
            raise VideoRenderError(f"remotion produced no file: {target}")
        self._probe(target, warnings)

    def _probe(self, target: Path, warnings: list[str]) -> None:
        if shutil.which("ffprobe") is None:
            warnings.append("ffprobe missing: skipping stream asserts")
            return

    def _default_tts(self) -> Any:
        from pulsecraft.tts.kokoro import KokoroVoiceover

        return KokoroVoiceover()

    def _default_stt(self) -> Any:
        from pulsecraft.stt.whisper import WhisperTimestamps

        return WhisperTimestamps()

    def _default_audio_fetcher(self) -> Any:
        from pulsecraft.assets.audio_fetcher import AudioFetcher

        return AudioFetcher(flags=self._flags)
