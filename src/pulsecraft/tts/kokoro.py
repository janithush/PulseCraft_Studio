"""Kokoro TTS voiceover generator with Edge-TTS fallback (M3).

Heavy engines are lazy-imported; callers may inject a `synth_backend` for tests.
Disk cache is content-addressed: `hash(text+voice+speed)` under `.cache/tts/`.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import struct
import wave
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

SAMPLE_RATE = 22050
CHUNK_MAX_CHARS = 500

PCMBackend = Callable[[str, str, float], bytes]

# kokoro voice id -> Edge-TTS neural voice (Tier B online fallback).
EDGE_VOICE_MAP: dict[str, str] = {
    "kokoro-default": "en-US-AriaNeural",
    "kokoro-af-heart": "en-US-AriaNeural",
    "kokoro-af-bella": "en-US-JennyNeural",
    "kokoro-am-adam": "en-US-GuyNeural",
}
DEFAULT_EDGE_VOICE = "en-US-AriaNeural"


class TTSError(RuntimeError):
    """Voiceover synthesis failed on all backends."""


def split_chunks(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Sentence-aware chunking; hard-splits pathological long sentences."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def cache_key(text: str, voice: str, speed: float) -> str:
    return hashlib.sha256(f"{text}|{voice}|{speed}".encode()).hexdigest()[:16]


def tone_pcm(duration_s: float, freq_hz: float = 220.0, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Deterministic synthetic PCM (fixtures/tests; never shipped as VO)."""
    frames = int(duration_s * sample_rate)
    return b"".join(
        struct.pack("<h", int(10000 * math.sin(2 * math.pi * freq_hz * i / sample_rate)))
        for i in range(frames)
    )


def write_wav(path: Path, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


def wav_duration_s(path: Path) -> float:
    pcm, rate = read_wav(path)
    return len(pcm) / 2 / rate


class KokoroVoiceover:
    """Chunk → synth (Kokoro, Edge-TTS fallback) → concat WAV with resume cache."""

    def __init__(
        self,
        cache_dir: str | Path = ".cache/tts",
        sample_rate: int = SAMPLE_RATE,
        synth_backend: PCMBackend | None = None,
    ) -> None:
        self._cache = Path(cache_dir)
        self._rate = sample_rate
        self._backend = synth_backend or self._default_backend

    def synthesize(
        self,
        text: str,
        voice: str = "kokoro-default",
        speed: float = 1.0,
        refresh: bool = False,
    ) -> tuple[Path, bool]:
        """Returns (wav_path, cache_hit). Raises TTSError when backends fail."""
        key = cache_key(text, voice, speed)
        target = self._cache / f"{key}.wav"
        if target.is_file() and not refresh:
            return target, True
        pcm_parts: list[bytes] = []
        for chunk in split_chunks(text):
            try:
                pcm_parts.append(self._backend(chunk, voice, speed))
            except Exception as exc:
                raise TTSError(f"voiceover failed for voice '{voice}': {exc}") from exc
        write_wav(target, b"".join(pcm_parts), self._rate)
        return target, False

    def _default_backend(self, text: str, voice: str, speed: float) -> bytes:
        if self._flag_enabled("tts.kokoro", default=True):
            try:
                return self._kokoro_backend(text, voice, speed)
            except Exception as exc:
                logger.debug("kokoro backend unavailable, trying edge-tts: %s", exc)
        if self._flag_enabled("tts.edgeFallback", default=True):
            try:
                return self._edge_backend(text, voice, speed)
            except Exception as exc:
                raise TTSError(f"kokoro + edge-tts unavailable: {exc}") from exc
        raise TTSError("all TTS backends disabled by feature flags (tts.kokoro/tts.edgeFallback)")

    @staticmethod
    def _flag_enabled(dotted: str, default: bool = True) -> bool:
        try:
            from pulsecraft.common.feature_flags import FeatureFlags

            return FeatureFlags.load().enabled(dotted)
        except Exception:
            return default

    def _kokoro_backend(self, text: str, voice: str, speed: float) -> bytes:
        """High-quality local offline synthesis (kokoro-onnx preferred, kokoro fallback)."""
        try:
            return self._kokoro_onnx_backend(text, voice, speed)
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("kokoro-onnx backend failed: %s", exc)
        return self._kokoro_package_backend(text, voice, speed)

    def _kokoro_onnx_backend(self, text: str, voice: str, speed: float) -> bytes:
        from kokoro_onnx import Kokoro  # lazy: pip install kokoro-onnx (CPU offline)

        kokoro_voice = voice if voice != "kokoro-default" else "af_heart"
        engine = Kokoro.from_pretrained("kokoro", langs=["en"])
        audio, _rate = engine.create(text, voice=kokoro_voice, speed=speed, is_phonemes=False)
        return self._float_to_pcm16(audio, _rate, self._rate)

    def _kokoro_package_backend(self, text: str, voice: str, speed: float) -> bytes:
        from kokoro import KPipeline  # lazy: pip install kokoro>=0.9.4 (CPU offline)

        kokoro_voice = voice if voice != "kokoro-default" else "af_heart"
        pipeline = KPipeline(lang_code="a")
        pcm_parts: list[bytes] = []
        out_rate = SAMPLE_RATE
        for _, _, audio in pipeline(text, voice=kokoro_voice, speed=speed):
            out_rate = 24000
            pcm_parts.append(self._float_to_pcm16(audio, 24000, self._rate))
        if not pcm_parts:
            raise TTSError("kokoro engine produced no audio")
        return b"".join(pcm_parts) if out_rate else b""

    @staticmethod
    def _float_to_pcm16(audio: object, in_rate: int, out_rate: int) -> bytes:
        import numpy as np

        arr = np.asarray(audio, dtype=np.float64).reshape(-1)
        if arr.size == 0:
            return b""
        if in_rate != out_rate and arr.size > 1:
            # Linear resample (no scipy dependency).
            count = max(1, int(arr.size * out_rate / in_rate))
            positions = np.linspace(0, arr.size - 1, count)
            idx = np.clip(positions.astype(int), 0, arr.size - 1)
            frac = positions - idx
            nxt = np.clip(idx + 1, 0, arr.size - 1)
            arr = arr[idx] * (1.0 - frac) + arr[nxt] * frac
        clipped = np.clip(arr, -1.0, 1.0)
        return (clipped * 32767).astype("<i2").tobytes()

    def _edge_backend(self, text: str, voice: str, speed: float) -> bytes:
        """Online fallback via edge-tts (MP3) transcoded to 16-bit mono PCM."""
        import edge_tts  # lazy: pip install edge-tts (network)

        edge_voice = EDGE_VOICE_MAP.get(voice, voice)
        if "Neural" not in edge_voice:
            edge_voice = DEFAULT_EDGE_VOICE
        rate = self._speed_to_rate(speed)
        return self._edge_synthesize_pcm(edge_tts, text, edge_voice, rate)

    @staticmethod
    def _speed_to_rate(speed: float) -> str:
        pct = int(round((float(speed) - 1.0) * 100))
        pct = max(-90, min(100, pct))
        return f"{pct:+d}%"

    def _edge_synthesize_pcm(self, edge_tts: object, text: str, voice: str, rate: str) -> bytes:
        import tempfile

        async def _save(mp3_path: str) -> None:
            communicate = edge_tts.Communicate(text, voice, rate=rate)  # type: ignore[attr-defined]
            await communicate.save(mp3_path)

        with tempfile.TemporaryDirectory(prefix="pulsecraft-edge-") as tmp:
            mp3_path = str(Path(tmp) / "voice.mp3")
            _run_coro_sync(lambda: _save(mp3_path))
            return _mp3_to_pcm(Path(mp3_path), self._rate)


def _run_coro_sync(factory: Callable[[], object]) -> object:
    """Run an async factory to completion from synchronous pipeline code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())  # type: ignore[arg-type]
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()  # type: ignore[arg-type]


def _mp3_to_pcm(mp3_path: Path, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Transcode an edge-tts MP3 to 16-bit mono PCM at `sample_rate`."""
    data = mp3_path.read_bytes()
    if not data:
        raise TTSError(f"edge-tts produced empty audio: {mp3_path}")
    try:
        return _mp3_to_pcm_ffmpeg(mp3_path, sample_rate)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("ffmpeg transcode failed, trying pydub: %s", exc)
    try:
        return _mp3_to_pcm_pydub(mp3_path, sample_rate)
    except ImportError as exc:
        raise TTSError(
            "edge-tts MP3 transcode needs ffmpeg on PATH or `pip install pydub` "
            f"(and ffmpeg): {exc}"
        ) from exc


def _mp3_to_pcm_ffmpeg(mp3_path: Path, sample_rate: int) -> bytes:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg not on PATH")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(mp3_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        timeout=120,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise TTSError(f"ffmpeg transcode failed: {completed.stderr.decode()[-300:]}")
    return bytes(completed.stdout)


def _mp3_to_pcm_pydub(mp3_path: Path, sample_rate: int) -> bytes:
    from pydub import AudioSegment  # lazy: pip install pydub (needs ffmpeg)

    segment = AudioSegment.from_mp3(str(mp3_path)).set_channels(1).set_frame_rate(sample_rate)
    if segment.sample_width != 2:
        segment = segment.set_sample_width(2)
    return bytes(segment.raw_data)
