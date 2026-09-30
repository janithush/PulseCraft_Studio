"""Audio mix helpers (M3): BGM auto-ducking curve + WAV mixing (stdlib only)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from pulsecraft.tts.kokoro import read_wav, write_wav

FRAME_S = 0.01
SPEECH_LEVEL = 0.15
PAUSE_LEVEL = 0.35
SMOOTH_S = 0.2


class MixError(RuntimeError):
    """Mixing failed (missing inputs, rate mismatch)."""


def duck_gains(
    speech: list[tuple[float, float]],
    duration_s: float,
    speech_level: float = SPEECH_LEVEL,
    pause_level: float = PAUSE_LEVEL,
    smooth_s: float = SMOOTH_S,
) -> list[float]:
    """Per-10ms BGM gain: `speech_level` under speech, `pause_level` in pauses.

    `speech` is [(start, end)] VO-active intervals. Edges are linearly smoothed
    over `smooth_s` (attack/release) to avoid pumping artifacts.
    """
    frames = max(int(duration_s / FRAME_S), 1)
    gains = [pause_level] * frames

    def mark(start: float, end: float) -> None:
        first = max(int(start / FRAME_S), 0)
        last = min(int(end / FRAME_S) + 1, frames)
        for i in range(first, last):
            gains[i] = speech_level

    for start, end in speech:
        mark(start, end)
    radius = max(int(smooth_s / FRAME_S), 1)
    smoothed = list(gains)
    for i in range(frames):
        window = gains[max(0, i - radius) : i + radius + 1]
        smoothed[i] = round(sum(window) / len(window), 4)
    return smoothed


def words_to_speech(words: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Merge word timestamps into speech intervals."""
    intervals: list[tuple[float, float]] = []
    for entry in words:
        start, end = float(entry["start"]), float(entry["end"])
        if intervals and start - intervals[-1][1] <= 0.25:
            intervals[-1] = (intervals[-1][0], end)
        else:
            intervals.append((start, end))
    return intervals


def mix_voice_bgm(
    voice_path: str | Path,
    bgm_path: str | Path | None,
    words: list[dict[str, Any]],
    out_path: str | Path,
    ducking: bool = True,
) -> Path:
    """Voice at full volume + ducked BGM bed; no BGM → voice copy-through."""
    from pulsecraft.tts.kokoro import wav_duration_s

    voice = Path(voice_path)
    out = Path(out_path)
    if bgm_path is None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(voice.read_bytes())
        return out
    bgm = Path(bgm_path)
    if not bgm.is_file():
        raise MixError(f"BGM not found: {bgm}")
    voice_pcm, voice_rate = read_wav(voice)
    bgm_pcm, bgm_rate = read_wav(bgm)
    if voice_rate != bgm_rate:
        raise MixError(f"rate mismatch voice={voice_rate} bgm={bgm_rate}")
    duration = wav_duration_s(voice)
    gains = duck_gains(words_to_speech(words), duration) if ducking and words else [PAUSE_LEVEL] * 1
    voice_frames = len(voice_pcm) // 2
    bgm_frames = len(bgm_pcm) // 2
    voice_samples = struct.unpack(f"<{voice_frames}h", voice_pcm)
    bgm_samples = struct.unpack(f"<{bgm_frames}h", bgm_pcm or b"\x00\x00")
    frame_span = max(int(FRAME_S * voice_rate), 1)
    mixed = bytearray()
    for i in range(voice_frames):
        gain = gains[min(i // frame_span, len(gains) - 1)]
        bed = bgm_samples[i % bgm_frames] * gain if bgm_frames else 0.0
        sample = int(max(-32768, min(32767, voice_samples[i] + bed)))
        mixed += struct.pack("<h", sample)
    write_wav(out, bytes(mixed), voice_rate)
    return out
