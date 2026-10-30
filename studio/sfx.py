"""Synthesised sound effects, so every sound is our own and free to use."""
import numpy as np

from .core import SR


def _t(sec):
    return np.arange(int(sec * SR)) / SR


def whoosh(sec=0.45):
    t = _t(sec)
    noise = np.random.default_rng(1).standard_normal(len(t))
    # sweep a simple one-pole low-pass from dark to bright and back
    cut = 0.02 + 0.25 * np.sin(np.pi * t / sec)
    out, y = np.zeros_like(noise), 0.0
    for i, x in enumerate(noise):
        y += cut[i] * (x - y)
        out[i] = y
    return (out * np.sin(np.pi * t / sec) ** 2 * 0.9).astype(np.float32)


def pop(sec=0.12, f0=700, f1=1300):
    t = _t(sec)
    f = f0 + (f1 - f0) * t / sec
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * 0.6).astype(np.float32)


def tick():
    t = _t(0.05)
    return (np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 120) * 0.5).astype(np.float32)


def ding():
    t = _t(0.9)
    tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1318.5, 1), (1975.5, 0.5), (2637, 0.25)))
    return (tone * np.exp(-t * 5) * 0.35).astype(np.float32)


def buzz():
    t = _t(0.35)
    sq = np.sign(np.sin(2 * np.pi * 140 * t))
    return (sq * np.exp(-t * 6) * 0.22).astype(np.float32)


def boom():
    t = _t(1.0)
    f = 90 * np.exp(-t * 3) + 35
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4) * 0.9).astype(np.float32)


SOUNDS = {"whoosh": whoosh, "pop": pop, "tick": tick, "ding": ding, "buzz": buzz, "boom": boom}


def track(events, dur, vol=0.5):
    """events: list of (time, name). Returns a mono track of length dur."""
    out = np.zeros(int(dur * SR) + SR, np.float32)
    cache = {}
    for at, name in events:
        if name not in cache:
            cache[name] = SOUNDS[name]()
        s = cache[name]
        i = max(0, int(at * SR))
        n = min(len(s), len(out) - i)
        if n > 0:
            out[i:i + n] += s[:n]
    return out[: int(dur * SR)] * vol
