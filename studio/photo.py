"""Real public-domain images (paintings, statues, NASA photos) as moving backgrounds."""
import json
import os
import re

import numpy as np
from PIL import Image, ImageEnhance

from .core import W, H, ease

CREDITS = "assets/credits.json"
_cache = {}


def load(src, grade=None, contain=False, at=0.5):
    """The image cover-fitted to a frame with room to move, graded once and cached.
    contain=True fits the whole image (e.g. a full planet) on black instead of cropping it."""
    key = (src, grade.__name__ if grade else None, contain, at)
    if key not in _cache:
        im = Image.open(src).convert("RGB")
        k = (min if contain else max)(W * 1.3 / im.width, H * 1.3 / im.height)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
        if contain:
            bg = Image.new("RGB", (int(W * 1.3), int(H * 1.3)))
            bg.paste(im, ((bg.width - im.width) // 2, int((bg.height - im.height) * at)))
            im = bg
        _cache[key] = grade(im) if grade else im
    return _cache[key]


def frame(p, st, grade=None):
    """p: {src, focus: [x, y] 0..1, zoom: [from, to], pan: [dx, dy] in frame widths, dur, fit: contain, at: 0..1 vertical place when contained}."""
    im = load(p["src"], grade, p.get("fit") == "contain", p.get("at", 0.5))
    k = ease(min(st / p.get("dur", 7), 1))
    z0, z1 = p.get("zoom", [1.0, 1.12])
    z = z0 + (z1 - z0) * k
    # visible box in image pixels: the frame shows 1/z of a 1.3x oversized image
    w = im.width / 1.3 / z
    h = im.height / 1.3 / z
    if w / h > W / H:
        w = h * W / H
    else:
        h = w * H / W
    fx, fy = p.get("focus", [0.5, 0.5])
    dx, dy = p.get("pan", [0, 0])
    cx = fx * im.width + dx * w * k
    cy = fy * im.height + dy * h * k
    x0 = min(max(cx - w / 2, 0), im.width - w)
    y0 = min(max(cy - h / 2, 0), im.height - h)
    return im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


def warm_dark(im):
    """Stoic Ember grade: muted, warm, low-key, like the paintings are lit by a fire."""
    im = ImageEnhance.Color(im).enhance(0.55)
    im = ImageEnhance.Contrast(im).enhance(1.15)
    a = np.asarray(im, np.float32) / 255
    a = a ** 1.25 * np.array([1.08, 0.92, 0.72])
    return Image.fromarray((np.clip(a, 0, 1) * 235).astype(np.uint8))


def space(im):
    """What If grade: punchy contrast, slightly cool shadows."""
    im = ImageEnhance.Contrast(im).enhance(1.12)
    return ImageEnhance.Color(im).enhance(1.1)


def credits_for(srcs):
    if not os.path.exists(CREDITS):
        return []
    c = json.load(open(CREDITS))
    out = []
    for s in srcs:
        if s in c:
            e = dict(c[s])
            # Wikimedia metadata sometimes carries wikidata markup; keep the readable part
            t = re.sub(r"label QS:.*", "", e["title"]).strip()
            e["title"] = t.split("\xa0")[-1].strip() or t
            m = re.search(r"\d{4}", e.get("date") or "")
            e["date"] = m.group(0) if m else e.get("date")
            who = f", {e['author']}" if e.get("author") else ""
            when = f" ({e['date']})" if e.get("date") else ""
            out.append(f"{e['title']}{who}{when}. {e['license']}. {e['page']}")
    return out
