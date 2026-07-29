"""Deterministic, dependency-free speech synthesis for simulation audio.

Real voice pipelines produce audio; an eval harness that only compares text
misses everything downstream of the LLM (TTS failures, clipped turns, dead
air). This module fakes the *speech* stage deterministically — same text,
same voice, same audio, every run — so a simulation can capture a WAV file
per turn without depending on a paid TTS API or network access.

Swap `synth_speech` for a real provider call and nothing else in the runner
needs to change: the contract is text + voice in, a WAV path + duration out.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 16_000
_MS_PER_CHAR = 55.0
_MIN_DURATION_MS = 350.0
_BASE_FREQ_HZ = 160.0


def _voice_frequency(voice: str) -> float:
    """Derive a stable tone frequency from the voice name."""
    digest = sum(ord(c) for c in voice) if voice else 0
    return _BASE_FREQ_HZ + (digest % 12) * 18.0


def estimate_duration_ms(text: str) -> float:
    """Deterministic stand-in for a TTS engine's speaking-time estimate."""
    return max(_MIN_DURATION_MS, len(text.strip()) * _MS_PER_CHAR)


def synth_speech(text: str, path: Path, voice: str = "default") -> float:
    """Write a mono PCM16 WAV file standing in for synthesized speech.

    Returns the duration in milliseconds. The waveform itself is a simple
    tone envelope, not intelligible audio — its purpose is to give every
    simulated turn a real, playable artifact with a length that tracks
    the text it stands in for.
    """
    duration_ms = estimate_duration_ms(text)
    frequency = _voice_frequency(voice)
    n_samples = int(SAMPLE_RATE * duration_ms / 1000)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for i in range(n_samples):
            # Fade in/out over 20ms to avoid a click at each turn boundary.
            fade_samples = int(SAMPLE_RATE * 0.02)
            envelope = 1.0
            if i < fade_samples:
                envelope = i / fade_samples
            elif i > n_samples - fade_samples:
                envelope = (n_samples - i) / fade_samples
            sample = int(3000 * envelope * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
            frames += struct.pack("<h", sample)
        wav_file.writeframes(bytes(frames))
    return duration_ms
