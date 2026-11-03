"""Game-like physics simulations drawn on top of a What If background.

A scene opts in with `sim: {kind: ..., ...}`. Each sim is a small, readable model of the event
(not a precise physics engine) so viewers can see what the narration explains.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .characters import scout
from .core import W, H, ease, font

_cache = {}


def _hud_font(size):
    key = ("hud", size)
    if key not in _cache:
        _cache[key] = font("IBMPlexMono-Medium.ttf", size)
    return _cache[key]


def scout_sprite(s, t, pose, sx=1.0, sy=1.0, angle=0.0, tint=None, alpha=1.0):
    """Scout as an RGBA sprite that can be stretched, rotated, tinted and faded."""
    S = int(420 * s) + 4
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    scout(layer, S / 2, S / 2, s, t, pose, 0)
    if sx != 1 or sy != 1:
        layer = layer.resize((max(2, int(S * sx)), max(2, int(S * sy))), Image.BICUBIC)
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    if tint or alpha < 1:
        a = np.asarray(layer, np.float32)
        if tint:
            k, col = tint
            a[..., :3] = a[..., :3] * (1 - k) + np.array(col, np.float32) * k * (a[..., :3].mean(-1, keepdims=True) / 255 + 0.3)
        a[..., 3] *= alpha
        layer = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return layer


def paste_center(img, sprite, x, y):
    img.paste(sprite, (int(x - sprite.width / 2), int(y - sprite.height / 2)), sprite)


# ---------------------------------------------------------------- black hole
def _bh_static(R):
    """Glow, lensed ring and shadow for a black hole of horizon radius R (cached)."""
    key = ("bh", R)
    if key not in _cache:
        n = int(R * 10)
        c = n / 2
        glow = Image.new("RGB", (n, n))
        d = ImageDraw.Draw(glow)
        d.ellipse([c - R * 3.2, c - R * 3.2, c + R * 3.2, c + R * 3.2], fill=(60, 22, 6))
        glow = glow.filter(ImageFilter.GaussianBlur(R * 1.1))
        ring = Image.new("RGB", (n, n))
        d = ImageDraw.Draw(ring)
        # light from the far side of the disk bent over and under the hole
        d.ellipse([c - R * 1.55, c - R * 1.55, c + R * 1.55, c + R * 1.55], outline=(255, 190, 110), width=max(3, int(R * 0.16)))
        ring = ring.filter(ImageFilter.GaussianBlur(R * 0.08))
        thin = Image.new("RGB", (n, n))
        ImageDraw.Draw(thin).ellipse([c - R * 1.1, c - R * 1.1, c + R * 1.1, c + R * 1.1], outline=(255, 215, 160), width=max(2, int(R * 0.06)))
        ring = Image.fromarray(np.clip(np.asarray(ring, np.int16) + np.asarray(thin.filter(ImageFilter.GaussianBlur(R * 0.03)), np.int16), 0, 255).astype(np.uint8))
        rng = np.random.default_rng(12)
        npart = 4200
        r = R * (1.7 + 3.0 * rng.random(npart) ** 1.6)
        th0 = rng.random(npart) * 2 * math.pi
        size = 1 + rng.random(npart) * 2.4
        # smooth glowing band under the particles, split into the halves behind and in front of the hole
        tilt = 0.26
        y, x = np.mgrid[0:n, 0:n].astype(np.float32)
        re = np.hypot(x - c, (y - c) / tilt) / R
        heat = np.clip((4.7 - re) / 3.0, 0, 1) * (re > 1.55)
        band = np.stack([255 * (0.7 + 0.3 * heat), 110 + 120 * heat, 30 + 160 * heat ** 2], -1) * (heat ** 1.5 * 0.55)[..., None]
        band *= (1 + 0.5 * np.clip((c - x) / (R * 4.7), -1, 1))[..., None]  # approaching side brighter
        band = np.asarray(Image.fromarray(np.clip(band, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(R * 0.05)), np.float32)
        bfront = band * (y > c)[..., None]
        bback = band * (y <= c)[..., None]
        _cache[key] = (glow, ring, r, th0, size, bback, bfront)
    return _cache[key]


def black_hole(img, cfg, t, st):
    cx, cy, R = cfg.get("x", 540), cfg.get("y", 900), int(cfg.get("r", 120))
    tilt = cfg.get("tilt", 0.26)
    glow, ring, r, th0, size, bback, bfront = _bh_static(R)
    n = glow.width
    box = (int(cx - n / 2), int(cy - n / 2))
    base = np.asarray(img, np.float32)

    def add_layer(layer, x0, y0):
        a = layer if isinstance(layer, np.ndarray) else np.asarray(layer, np.float32)
        xs, ys = max(0, x0), max(0, y0)
        xe, ye = min(W, x0 + a.shape[1]), min(H, y0 + a.shape[0])
        if xs < xe and ys < ye:
            base[ys:ye, xs:xe] += a[ys - y0:ye - y0, xs - x0:xe - x0]

    add_layer(glow, *box)
    # orbiting gas: faster near the hole (Kepler, w ~ r^-1.5)
    w = 2.2 * (R * 1.7 / r) ** 1.5
    th = th0 + w * t * cfg.get("spin", 1.0)
    px = cx + r * np.cos(th)
    py = cy + r * np.sin(th) * tilt
    heat = np.clip((R * 4.7 - r) / (R * 3.0), 0, 1)
    doppler = 1 + 0.6 * np.sin(th)  # the side moving toward us looks brighter
    col = np.stack([255 * (0.75 + 0.25 * heat), 120 + 120 * heat, 40 + 170 * heat ** 2], -1) * (0.35 + 0.65 * heat)[:, None] * doppler[:, None]
    # splat the gas into a band of rows around the hole (numpy, much faster than drawing ellipses)
    y0b, y1b = max(0, int(cy - R * 1.8)), min(H, int(cy + R * 1.8))
    back = np.zeros((y1b - y0b, W, 3), np.float32)
    front = np.zeros_like(back)
    xi, yi = np.round(px).astype(int), np.round(py).astype(int) - y0b
    ok = (xi >= 1) & (xi < W - 1) & (yi >= 1) & (yi < y1b - y0b - 1)
    isf = np.sin(th) > 0
    for tgt, sel in ((front, ok & isf), (back, ok & ~isf)):
        for dx, dy, wgt in ((0, 0, 1.0), (1, 0, .5), (-1, 0, .5), (0, 1, .35), (0, -1, .35)):
            np.add.at(tgt, (yi[sel] + dy, xi[sel] + dx), col[sel] * wgt)
    def soft(a):
        return np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.4)), np.float32)
    back, front = soft(back * 3.2), soft(front * 3.6)
    base[y0b:y1b] += back
    add_layer(bback, *box)
    add_layer(ring, *box)
    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(out)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(0, 0, 0))
    a = np.asarray(out, np.float32).copy()
    a[y0b:y1b] += front
    xs, ys = max(0, box[0]), max(0, box[1])
    xe, ye = min(W, box[0] + n), min(H, box[1] + n)
    a[ys:ye, xs:xe] += bfront[ys - box[1]:ye - box[1], xs - box[0]:xe - box[0]]
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    fall = cfg.get("fall")
    if fall:
        dur = cfg.get("dur", 5.0)
        k = ease(min(st / dur, 1))
        a0 = cfg.get("start_angle", -50)
        dist0 = cfg.get("start_dist", 5.2)
        if fall == "small":
            # tidal stretch grows fast near the hole: the noodle
            dist = R * (dist0 - (dist0 - 1.05) * k ** 1.4)
            ang = math.radians(a0 + 200 * k)
            x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang) * 0.7
            stretch = 1 + 5.0 * k ** 3
            sp = scout_sprite(cfg.get("s", 0.4) * (1 - 0.35 * k), t, "fall", sx=1 / math.sqrt(stretch), sy=stretch,
                              angle=-math.degrees(math.atan2(cy - y, cx - x)) - 90)
            paste_center(out, sp, x, y)
        else:
            # giant hole: smooth fall, then the far-away view slows, reddens and fades
            slow = 1 - math.exp(-3 * k) if fall == "frozen" else k
            dist = R * (dist0 - (dist0 - 1.15) * slow)
            ang = math.radians(a0)
            x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
            red = min(1, slow * 1.1) if fall == "frozen" else 0
            sp = scout_sprite(cfg.get("s", 0.5) * (1 - 0.15 * slow), t * (1 - 0.9 * red), "float",
                              tint=(red, (255, 40, 20)) if red else None, alpha=1 - 0.55 * red)
            paste_center(out, sp, x, y)
    return out


# ---------------------------------------------------------------- tunnel through Earth
LAYERS = [  # (fraction of radius, colour) from the surface inward
    (1.00, (52, 120, 190)), (0.985, (96, 70, 48)), (0.96, (190, 70, 30)), (0.55, (240, 140, 40)), (0.19, (255, 236, 170)),
]
LABELS = [(0.78, "MANTLE"), (0.38, "OUTER CORE"), (0.0, "INNER CORE")]


def _earth_cut(R):
    key = ("cut", R)
    if key not in _cache:
        n = 2 * R + 8
        c = n / 2
        im = Image.new("RGB", (n, n))
        d = ImageDraw.Draw(im)
        for f, col in LAYERS:
            d.ellipse([c - R * f, c - R * f, c + R * f, c + R * f], fill=col)
        im = im.filter(ImageFilter.GaussianBlur(R * 0.025))
        # radial shading so the layers read as a ball, plus a little texture
        y, x = np.mgrid[0:n, 0:n].astype(np.float32)
        rr = np.hypot(x - c, y - c) / R
        shade = (0.75 + 0.35 * np.clip(1 - rr, 0, 1))[..., None]
        rng = np.random.default_rng(3)
        noise = rng.normal(0, 6, (n // 4, n // 4)).repeat(4, 0).repeat(4, 1)[:n, :n, None]
        a = np.clip(np.asarray(im, np.float32) * shade + noise, 0, 255)
        mask = Image.fromarray(((rr <= 1.0) * 255).astype(np.uint8))
        im = Image.fromarray(a.astype(np.uint8))
        d = ImageDraw.Draw(im)
        f = _hud_font(int(R * 0.07))
        for fr, txt in LABELS:
            d.text((c + R * 0.11, c - R * fr - (R * 0.12 if fr else -R * 0.06)), txt, font=f, fill=(40, 20, 10))
        _cache[key] = (im, mask)
    return _cache[key]


def tunnel(img, cfg, t, st):
    cx, cy, R = cfg.get("x", 540), cfg.get("y", 1020), int(cfg.get("r", 380))
    cut, mask = _earth_cut(R)
    img = img.copy()
    img.paste(cut, (int(cx - cut.width / 2), int(cy - cut.height / 2)), mask)
    d = ImageDraw.Draw(img)
    d.rectangle([cx - 13, cy - R - 30, cx + 13, cy + R + 30], fill=(16, 10, 8))
    d.rectangle([cx - 13, cy - R - 30, cx + 13, cy + R + 30], outline=(255, 210, 120), width=2)
    # trip fraction: 0 = top, 0.5 = other side, 1 = back at top (uniform-density swing)
    a, b = cfg.get("trip", [0.0, 0.5])
    k = ease(min(st / cfg.get("dur", 6.0), 1)) if cfg.get("ease", True) else min(st / cfg.get("dur", 6.0), 1)
    f = a + (b - a) * k
    ph = 2 * math.pi * f
    y = cy - R * math.cos(ph)
    v = abs(math.sin(ph))
    for i in range(1, 9):  # motion trail
        fp = f - (b - a) * 0.012 * i * (1 if b > a else -1)
        yy = cy - R * math.cos(2 * math.pi * fp)
        rr = 9 - i
        d.ellipse([cx - rr, yy - rr, cx + rr, yy + rr], fill=(255, 220 - i * 15, 120 - i * 10))
    sp = scout_sprite(cfg.get("s", 0.26), t, "fall" if v > 0.15 else "float")
    paste_center(img, sp, cx - 62, y)
    # game HUD
    one_way = cfg.get("minutes", 38)
    minutes = one_way * 2 * f
    depth = 6371 * (1 - math.cos(ph))  # km from the entrance, measured along the tunnel
    hx, hy = 90, cfg.get("hud_y", 1530)
    d.rounded_rectangle([hx, hy, W - hx, hy + 230], 26, fill=(8, 12, 30), outline=(255, 210, 60), width=4)
    fl, fv = _hud_font(30), _hud_font(56)
    d.text((hx + 40, hy + 26), "FROM ENTRANCE", font=fl, fill=(170, 180, 210))
    d.text((hx + 40, hy + 66), f"{depth:,.0f} KM", font=fv, fill=(255, 255, 255))
    d.text((W / 2 + 40, hy + 26), "TIME", font=fl, fill=(170, 180, 210))
    d.text((W / 2 + 40, hy + 66), f"{int(minutes):02d}:{int(minutes * 60) % 60:02d}", font=fv, fill=(255, 255, 255))
    d.text((hx + 40, hy + 150), "SPEED", font=fl, fill=(170, 180, 210))
    bx0, bx1 = hx + 180, W - hx - 40
    d.rounded_rectangle([bx0, hy + 152, bx1, hy + 184], 14, fill=(30, 36, 70))
    d.rounded_rectangle([bx0, hy + 152, bx0 + max(28, (bx1 - bx0) * v), hy + 184], 14,
                        fill=(255, int(210 - 120 * v), 60))
    return img


SIMS = {"black_hole": black_hole, "tunnel": tunnel}


def draw(img, cfg, t, st):
    return SIMS[cfg["kind"]](img, cfg, t, st)
