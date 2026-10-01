"""Kokoro TTS voiceover generator with Edge-TTS fallback (M3).

Heavy engines are lazy-imported; callers may inject a `synth_backend` for tests.
Disk cache is content-addressed: `hash(text+voice+speed)` under `.cache/tts/`.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
import wave
from collections.abc import Callable
from pathlib import Path

SAMPLE_RATE = 22050
CHUNK_MAX_CHARS = 500

PCMBackend = Callable[[str, str, float], bytes]


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
        try:
            return self._kokoro_backend(text, voice, speed)
        except Exception:
            pass
        try:
            return self._edge_backend(text, voice, speed)
        except Exception as exc:
            raise TTSError(f"kokoro + edge-tts unavailable: {exc}") from exc

    def _kokoro_backend(self, text: str, voice: str, speed: float) -> bytes:
        import kokoro  # lazy: pip install kokoro-onnx (CPU)

        raise NotImplementedError(f"kokoro engine not wired: {kokoro.__name__} {voice} {speed}")

    def _edge_backend(self, text: str, voice: str, speed: float) -> bytes:
        import edge_tts  # lazy: pip install edge-tts (network)

        raise NotImplementedError(f"edge-tts engine not wired: {edge_tts.__name__} {voice}")
