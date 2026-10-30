"""Shared building blocks: fonts, procedural art, voice, captions, music, encoding."""
import hashlib
import math
import os
import subprocess

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 24000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")
MODELS = os.environ.get("KOKORO_DIR", os.path.join(ROOT, "models"))
CACHE = os.path.join(ROOT, ".cache", "tts")
_tts = None


# ---------- fonts ----------
def font(name, size, weight=None):
    f = ImageFont.truetype(os.path.join(FONTS, name), size)
    if weight is not None:
        f.set_variation_by_axes([weight])
    f._w = weight
    return f


def resize(f, size):
    """Same face at another size, keeping the variable-font weight."""
    g = f.font_variant(size=max(8, int(size)))
    if getattr(f, "_w", None) is not None:
        g.set_variation_by_axes([f._w])
    g._w = getattr(f, "_w", None)
    return g


# ---------- easing ----------
def clamp01(t):
    return min(max(t, 0.0), 1.0)


def ease(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def fade(col, a):
    return tuple(int(c * a) for c in col)


# ---------- procedural textures ----------
def fractal_noise(h, w, octaves=6, seed=0, base=4, wrap=False):
    if wrap:
        half = fractal_noise(h, w // 2, octaves, seed, base)
        return np.concatenate([half, half[:, ::-1]], 1)
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gh, gw = base * 2 ** o, base * 2 ** o * w // h
        g = rng.random((max(gh, 2), max(gw, 2))).astype(np.float32)
        img = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        out += amp * np.asarray(img, np.float32) / 255
        total += amp
        amp *= 0.5
    out /= total
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


def gradient(h, w, top, bottom):
    g = np.linspace(0, 1, h)[:, None, None]
    arr = np.array(top, np.float32) * (1 - g) + np.array(bottom, np.float32) * g
    return Image.fromarray(np.repeat(arr, w, 1).astype(np.uint8))


class Sphere:
    """Textured, lit sphere of radius R rendered to an RGBA image."""

    def __init__(self, tex, R):
        self.tex, self.R = tex, R
        y, x = np.mgrid[-R:R, -R:R].astype(np.float32) + 0.5
        x, y = x / R, y / R
        r2 = x * x + y * y
        self.mask = r2 <= 1
        z = np.sqrt(np.clip(1 - r2, 0, 1))
        self.n = np.stack([x, y, z], -1)
        self.lat = np.arcsin(np.clip(y, -1, 1))
        self.lon = np.arctan2(x, z)
        self.edge = np.clip((1 - np.sqrt(r2)) * R / 1.5, 0, 1)

    def render(self, rot=0.0, light=(-0.6, -0.3, 0.75), ambient=0.05):
        th, tw = self.tex.shape[:2]
        ti = ((self.lat / np.pi + 0.5) * (th - 1)).astype(np.int32)
        tj = (((self.lon + rot) / (2 * np.pi)) % 1 * (tw - 1)).astype(np.int32)
        col = self.tex[ti, tj]
        L = np.array(light, np.float32)
        L /= np.linalg.norm(L)
        d = np.clip(self.n @ L, 0, 1)[..., None]
        rgb = col * (ambient + (1 - ambient) * d)
        a = (self.edge * self.mask)[..., None]
        out = np.concatenate([np.clip(rgb, 0, 1), a], -1)
        return Image.fromarray((out * 255).astype(np.uint8), "RGBA")


def starfield(w, h, n=1600, seed=1):
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y = rng.integers(0, w), rng.integers(0, h)
        b = rng.random() ** 3
        r = 1 if b < 0.85 else 2
        c = int(255 * (0.25 + 0.75 * b))
        d.ellipse([x - r / 2, y - r / 2, x + r / 2, y + r / 2], fill=(c, c, c))
    return img


def add(img, other):
    return Image.fromarray(np.clip(np.asarray(img, np.int16) + np.asarray(other, np.int16), 0, 255).astype(np.uint8))


def vignette(w, h, strength=0.6):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = (x / w - 0.5) * 2, (y / h - 0.5) * 2
    return (1 - strength * np.clip((x * x + y * y) / 2, 0, 1))[..., None]


# ---------- voice ----------
def tts(text, voice, speed=1.0, lang="en-us"):
    global _tts
    os.makedirs(CACHE, exist_ok=True)
    key = os.path.join(CACHE, hashlib.md5(f"{text}|{voice}|{speed}".encode()).hexdigest() + ".npy")
    if os.path.exists(key):
        return np.load(key)
    if _tts is None:
        from kokoro_onnx import Kokoro
        _tts = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"), os.path.join(MODELS, "voices-v1.0.bin"))
    s, sr = _tts.create(text, voice=voice, speed=speed, lang=lang)
    assert sr == SR
    idx = np.where(np.abs(s) > 0.01)[0]
    if len(idx):
        s = s[max(idx[0] - 200, 0): idx[-1] + 1200]
    s = s.astype(np.float32)
    np.save(key, s)
    return s


def build_voice(lines, voice, speed=1.0, gap=0.3, lead=0.15):
    """Speak each line; returns audio, per-line timeline and total duration."""
    chunks = [np.zeros(int(lead * SR), np.float32)]
    t, tl = lead, []
    for ln in lines:
        a = tts(ln["text"], voice, speed)
        dur = len(a) / SR
        tl.append({"start": t, "end": t + dur})
        pause = ln.get("pause", gap)
        chunks += [a, np.zeros(int(pause * SR), np.float32)]
        t += dur + pause
    return np.concatenate(chunks), tl, t


def caption_chunks(lines, tl, max_words=3):
    """Split each spoken line into short caption groups, timed by character length."""
    caps = []
    for li, (ln, span) in enumerate(zip(lines, tl)):
        if ln.get("nocap"):
            continue
        words = ln.get("caption", ln["text"]).split()
        groups, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= max_words or w[-1] in ".,?!:;":
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        lens = [sum(len(w) + 1 for w in g) for g in groups]
        t, total = span["start"], sum(lens)
        for g, L in zip(groups, lens):
            d = (span["end"] - span["start"]) * L / total
            words, wt = [], t
            for w in g:
                wd = d * (len(w) + 1) / L
                words.append((w, wt, wt + wd))
                wt += wd
            caps.append({"text": " ".join(g), "start": t, "end": t + d, "words": words})
            t += d
    return caps


def srt(caps):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i + 1}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n" for i, c in enumerate(caps))


# ---------- music ----------
def pad(dur, freqs, vol=0.06, seed=0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    for i, f in enumerate(freqs):
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.05 + 0.03 * i) * t + i)
        out += (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2.003 * t)) * lfo
    noise = np.random.default_rng(seed).standard_normal(n).astype(np.float32)
    noise = np.convolve(noise, np.ones(400) / 400, mode="same") * 3
    out = out / len(freqs) + 0.15 * noise
    env = np.minimum(1, np.minimum(t / 2.0, (dur - t) / 2.0))
    return (out * env * vol).astype(np.float32)


def plucks(dur, bpm=112, scale=(261.63, 293.66, 329.63, 392.0, 440.0, 523.25), vol=0.05, seed=2):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(seed)
    step = 60 / bpm / 2
    tt = np.arange(int(0.6 * SR)) / SR
    env = np.exp(-tt * 9)
    k = 0
    while k * step < dur - 0.6:
        if rng.random() < 0.7:
            f = scale[rng.integers(0, len(scale))]
            note = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 3 * tt) * np.exp(-tt * 20)) * env
            s = int(k * step * SR)
            out[s:s + len(note)] += note.astype(np.float32) * (0.6 + 0.4 * rng.random())
        k += 1
    t = np.arange(n) / SR
    out += 0.25 * np.sin(2 * np.pi * 65.4 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * bpm / 60 / 4 * t))
    env = np.minimum(1, np.minimum(t / 1.0, (dur - t) / 1.5))
    return (out * env * vol).astype(np.float32)


def mix(*tracks):
    n = max(len(a) for a in tracks)
    return np.clip(sum(np.pad(a, (0, n - len(a))) for a in tracks), -1, 1)


# ---------- text ----------
def wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) > maxw and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    return lines + [cur]


def text_block(d, text, f, cx, cy, fill, maxw=900, gap=1.1, **kw):
    lines = wrap(d, text, f, maxw)
    lh = f.size * gap
    y0 = cy - lh * (len(lines) - 1) / 2
    for i, l in enumerate(lines):
        d.text((cx, y0 + i * lh), l, font=f, fill=fill, anchor="mm", **kw)
    return lh * len(lines)


# ---------- encoding ----------
def encode(path, dur, frame_fn, audio, size=(W, H), crf=20, extra_vf=None):
    wav = path + ".wav"
    sf.write(wav, audio, SR)
    vf = ["-vf", extra_vf] if extra_vf else []
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
           "-r", str(FPS), "-i", "-", "-i", wav, *vf, "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-tune", "grain" if crf > 22 else "film", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-shortest", "-movflags", "+faststart", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(math.ceil(dur * FPS))):
        p.stdin.write(frame_fn(i / FPS).convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {path}")
    os.remove(wav)
    return path
