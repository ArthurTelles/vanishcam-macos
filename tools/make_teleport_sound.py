"""Gera assets/teleport.wav: um "zip" sintetizado, sem áudio de terceiros."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


SAMPLE_RATE = 44100
DURATION = 0.6
OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "teleport.wav"


def synthesize() -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * DURATION)) / SAMPLE_RATE
    # Varredura rápida para o agudo e queda suave depois do pico.
    frequency = np.where(t < 0.18, 260.0 * 9.0 ** (t / 0.18), 2340.0 * np.exp(-(t - 0.18) * 2.5))
    phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    tone = np.sin(phase) + 0.45 * np.sin(2 * phase) + 0.2 * np.sin(3.01 * phase)
    tone *= 0.65 + 0.35 * np.sin(2 * np.pi * 42 * t)
    noise = np.diff(np.random.default_rng(31).normal(size=len(t) + 1))
    noise *= np.exp(-t / 0.05) * 0.5
    envelope = (1 - np.exp(-t / 0.006)) * np.exp(-t / 0.17)
    signal = tone * envelope + noise
    fade_out = np.clip((DURATION - t) / 0.05, 0, 1)
    signal *= fade_out
    return (signal / np.abs(signal).max() * 0.8 * 32767).astype(np.int16)


def main() -> None:
    with wave.open(str(OUTPUT), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(synthesize().tobytes())
    print(f"Gerado: {OUTPUT}")


if __name__ == "__main__":
    main()
