"""Faster-Whisper (INT8) word timestamps + uniform-timing fallback (M3).

Engines are lazy-imported; `transcribe()` degrades to uniform timing
(`estimated: True`) when Whisper is unavailable or `--no-whisper` is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class STTError(RuntimeError):
    """Timestamp extraction failed and no fallback was permitted."""


def uniform_words(text: str, duration_s: float) -> list[dict[str, Any]]:
    """Evenly spread words across duration (fallback; flagged estimated)."""
    tokens = [w for w in text.split() if w]
    if not tokens or duration_s <= 0:
        return []
    per_word = duration_s / len(tokens)
    return [
        {"word": word, "start": round(i * per_word, 3), "end": round((i + 1) * per_word, 3)}
        for i, word in enumerate(tokens)
    ]


def to_srt(words: list[dict[str, Any]]) -> str:
    """Group words into ~2s caption cues for the SRT sidecar."""

    def stamp(seconds: float) -> str:
        millis = int(seconds * 1000)
        hours, rem = divmod(millis, 3600000)
        minutes, rem = divmod(rem, 60000)
        secs, millis = divmod(rem, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    cues: list[str] = []
    bucket: list[dict[str, Any]] = []
    for word in words:
        bucket.append(word)
        if word["end"] - bucket[0]["start"] >= 2.0:
            cues.append(bucket)
            bucket = []
    if bucket:
        cues.append(bucket)
    lines: list[str] = []
    for number, cue in enumerate(cues, start=1):
        lines.append(str(number))
        lines.append(f"{stamp(cue[0]['start'])} --> {stamp(cue[-1]['end'])}")
        lines.append(" ".join(w["word"] for w in cue))
        lines.append("")
    return "\n".join(lines)


def check_monotonic(words: list[dict[str, Any]]) -> bool:
    previous = -1.0
    for entry in words:
        if entry["start"] < previous or entry["end"] < entry["start"]:
            return False
        previous = entry["start"]
    return True


class WhisperTimestamps:
    """Word-level timestamps via Faster-Whisper INT8 (CPU)."""

    def __init__(self, model: str = "base") -> None:
        self._model = model

    def transcribe(
        self, audio_path: str | Path, text_hint: str = "", no_whisper: bool = False
    ) -> dict[str, Any]:
        """Returns {"words", "model", "estimated"} (+ writes nothing; caller persists)."""
        from pulsecraft.tts.kokoro import wav_duration_s

        duration = wav_duration_s(Path(audio_path))
        if no_whisper:
            return {
                "words": uniform_words(text_hint, duration),
                "model": "uniform",
                "estimated": True,
            }
        try:
            words = self._whisper_words(Path(audio_path))
        except Exception:
            return {
                "words": uniform_words(text_hint, duration),
                "model": "uniform",
                "estimated": True,
            }
        return {"words": words, "model": f"{self._model}-int8", "estimated": False}

    def _whisper_words(self, audio_path: Path) -> list[dict[str, Any]]:
        from faster_whisper import WhisperModel  # lazy: pip install faster-whisper (CPU INT8)

        model = WhisperModel(self._model, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), word_timestamps=True)
        words: list[dict[str, Any]] = []
        for segment in segments:
            for word in segment.words or []:
                words.append(
                    {
                        "word": word.word.strip(),
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                    }
                )
        if not check_monotonic(words):
            raise STTError("whisper timestamps non-monotonic")
        return words
