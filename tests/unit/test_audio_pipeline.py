"""M3 unit tests: TTS chunking/cache, Whisper fallback/SRT, ducking mixer."""

from __future__ import annotations

from pathlib import Path

from pulsecraft.audio.mixer import (
    duck_gains,
    mix_voice_bgm,
    words_to_speech,
)
from pulsecraft.stt.whisper import check_monotonic, to_srt, uniform_words
from pulsecraft.tts.kokoro import (
    KokoroVoiceover,
    cache_key,
    split_chunks,
    tone_pcm,
    wav_duration_s,
    write_wav,
)


def test_split_chunks_sentence_aware() -> None:
    text = "Hello world. " + "x" * 600 + " Short tail."
    chunks = split_chunks(text, max_chars=500)
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert len(chunks) >= 2
    assert len(chunks[0]) == 500
    assert split_chunks("") == []


def test_cache_key_stable() -> None:
    assert cache_key("a", "v", 1.0) == cache_key("a", "v", 1.0)
    assert cache_key("a", "v", 1.0) != cache_key("b", "v", 1.0)


def test_synthesize_caches_and_refreshes(tmp_path: Path) -> None:
    tts = KokoroVoiceover(
        cache_dir=tmp_path, synth_backend=lambda text, voice, speed: tone_pcm(0.2)
    )
    first, hit1 = tts.synthesize("hello there", voice="v")
    second, hit2 = tts.synthesize("hello there", voice="v")
    assert (hit1, hit2) == (False, True)
    assert first == second
    assert abs(wav_duration_s(first) - 0.2) < 0.05
    _third, hit3 = tts.synthesize("hello there", voice="v", refresh=True)
    assert hit3 is False


def test_uniform_words_even_spread_and_monotonic() -> None:
    words = uniform_words("one two three four", 4.0)
    assert [entry["word"] for entry in words] == ["one", "two", "three", "four"]
    assert words[0]["start"] == 0.0 and words[-1]["end"] == 4.0
    assert check_monotonic(words) is True
    assert uniform_words("", 4.0) == []
    assert check_monotonic([{"word": "x", "start": 2.0, "end": 1.0}]) is False


def test_to_srt_groups_cues() -> None:
    words = uniform_words("a b c d e f g h", 8.0)
    srt = to_srt(words)
    assert "00:00:00,000 --> " in srt
    assert srt.count("\n\n") >= 2


def test_duck_gains_speech_low_pause_high() -> None:
    gains = duck_gains([(1.0, 2.0)], 4.0)
    assert len(gains) == 400
    assert sum(gains[100:200]) / 100 < 0.2  # speech -> ~15%
    assert sum(gains[250:350]) / 100 > 0.3  # pause -> ~35%


def test_words_to_speech_merges_close_words() -> None:
    words = [
        {"word": "a", "start": 0.0, "end": 0.3},
        {"word": "b", "start": 0.4, "end": 0.7},
        {"word": "c", "start": 2.0, "end": 2.4},
    ]
    assert words_to_speech(words) == [(0.0, 0.7), (2.0, 2.4)]


def test_mix_voice_bgm_ducks_and_copies(tmp_path: Path) -> None:
    voice = tmp_path / "voice.wav"
    write_wav(voice, tone_pcm(1.0, freq_hz=440.0))
    bed = tmp_path / "bgm.wav"
    write_wav(bed, tone_pcm(1.0, freq_hz=110.0))
    words = uniform_words("one two three four", 1.0)
    mixed = mix_voice_bgm(voice, bed, words, tmp_path / "mix.wav", ducking=True)
    assert mixed.is_file()
    assert abs(wav_duration_s(mixed) - 1.0) < 0.05
    flat = mix_voice_bgm(voice, None, words, tmp_path / "flat.wav")
    assert flat.read_bytes() == voice.read_bytes()
