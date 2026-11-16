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


# ---------------------------------------------------------------- Earth being built
# Ages are in billions of years ago (Ga). Each line of the episode sets `ages: [from, to]` and the
# sim sweeps through that span over the line (plus its pause), so consecutive lines join seamlessly.
ERAS = [  # (starts at Ga, name shown in the HUD)
    (4.54, "MOLTEN EARTH"), (4.505, "THEIA HITS"), (4.47, "THE MOON IS BORN"), (4.42, "FIRST OCEANS"),
    (3.7, "FIRST LIFE"), (2.4, "OXYGEN FILLS THE AIR"), (0.72, "SNOWBALL EARTH"), (0.635, "THE ICE MELTS"),
    (0.54, "ANIMALS EXPLODE"), (0.47, "PLANTS REACH LAND"), (0.335, "PANGAEA"), (0.175, "PANGAEA SPLITS"),
    (0.066, "ASTEROID HITS"), (0.06, "AGE OF MAMMALS"), (0.0003, "HUMANS"), (0.0, "TODAY"),
]
# continent blobs: (today lat, lon, radius deg), (Pangaea ~250 Ma lat, lon). A readable sketch, not a plate model.
CONTINENTS = [
    ((50, -100, 22), (35, -40)), ((33, -95, 13), (20, -38)), ((65, -130, 12), (52, -65)), ((72, -42, 11), (60, -15)),
    ((-8, -60, 16), (-15, -20)), ((-30, -64, 11), (-35, -25)), ((-46, -70, 7), (-50, -30)),
    ((10, 17, 18), (0, 10)), ((-6, 24, 14), (-15, 15)), ((-25, 26, 11), (-32, 20)),
    ((55, 60, 24), (45, 35)), ((52, 100, 24), (45, 75)), ((47, 15, 11), (32, 10)), ((22, 79, 10), (-35, 45)),
    ((25, 45, 10), (12, 35)), ((-25, 134, 14), (-55, 75)), ((-82, 10, 14), (-58, 30)), ((-78, 120, 12), (-65, 55)),
    ((-76, -110, 10), (-62, 5)), ((35, 138, 6), (30, 105)), ((0, 113, 8), (15, 100)),
]


def _age_label(a):
    if a <= 0.00002:
        return "TODAY"
    if a >= 1:
        return f"{a:.2f} BILLION"
    if a >= 0.001:
        return f"{a * 1000:,.0f} MILLION"
    return f"{a * 1e6:,.0f} THOUSAND"


def _era(a):
    name = ERAS[0][1]
    for start, n in ERAS:
        if a <= start:
            name = n
    return name


def _bump(a, lo, hi, edge):
    """1 inside [lo, hi] Ga, fading over `edge` Ga outside it."""
    return float(np.clip(min((a - lo) / edge + 1, (hi - a) / edge + 1), 0, 1))


def _earth_fields(h=256, w=512):
    if "earth_fields" not in _cache:
        from .core import fractal_noise
        lat = np.radians(np.linspace(90, -90, h))[:, None] * np.ones((1, w))
        lon = np.radians(np.linspace(-180, 180, w))[None, :] * np.ones((h, 1))
        xyz = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1).astype(np.float32)
        _cache["earth_fields"] = {
            "xyz": xyz, "lat": lat.astype(np.float32),
            "n1": fractal_noise(h, w, 7, 21, wrap=True), "n2": fractal_noise(h, w, 6, 22, wrap=True),
            "cl": fractal_noise(h, w, 6, 23, wrap=True), "cr": fractal_noise(h, w, 7, 24, wrap=True),
            "warp": (fractal_noise(h, w, 5, 25, wrap=True) - 0.5) * 28,
        }
    return _cache["earth_fields"]


def _blob_xyz(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)], np.float32)


def _land(a, F):
    """Height field (>0 is land) for age a in Ga."""
    xyz = F["xyz"]
    h = np.full(xyz.shape[:2], -1.0, np.float32)
    rng = np.random.default_rng(5)
    drift = float(np.clip((0.175 - a) / 0.175, 0, 1))      # Pangaea -> today
    scatter = float(np.clip((a - 0.335) / 0.5, 0, 1))      # older: pieces spread out
    grow = float(np.clip((3.2 - a) / 2.2, 0, 1))           # continents grow out of island arcs
    if grow <= 0:
        # only volcanic islands poke out of the first oceans
        return (F["n1"] - 0.78) * 4
    for (lat0, lon0, r), (lat1, lon1) in CONTINENTS:
        dlon = ((lon0 - lon1 + 180) % 360) - 180
        k = ease(drift)
        la, lo = lat1 + (lat0 - lat1) * k, lon1 + dlon * k
        if scatter:
            la += rng.uniform(-40, 40) * scatter
            lo += rng.uniform(-90, 90) * scatter
        c = _blob_xyz(la, lo)
        ang = np.degrees(np.arccos(np.clip(xyz @ c, -1, 1))) + F["warp"]
        rr = r * (0.35 + 0.65 * grow)
        h = np.maximum(h, 1 - ang / rr)
    h = h + (F["n1"] - 0.5) * 1.1
    return np.maximum(h, (F["n1"] - 0.8) * 4)


def _earth_tex(a, t):
    F = _earth_fields()
    lat = np.abs(F["lat"])[..., None]
    molten = float(np.clip((a - 4.38) / 0.1, 0, 1))
    water = float(np.clip((4.43 - a) / 0.12, 0, 1))
    oxygen = float(np.clip((2.5 - a) / 0.2, 0, 1))
    plants = float(np.clip((0.48 - a) / 0.1, 0, 1))
    ice = max(_bump(a, 0.635, 0.72, 0.02), 0.45 * _bump(a, 2.2, 2.4, 0.04))
    # crust and magma
    crack = np.clip(1 - np.abs(F["cr"] - 0.5) * 14, 0, 1)[..., None]
    crust = np.array([0.16, 0.13, 0.12]) * (0.7 + 0.6 * F["n2"][..., None])
    lava = np.array([1.0, 0.42, 0.08]) * (0.6 + 0.6 * F["n2"][..., None])
    glow = crack * (0.25 + 0.75 * molten)
    base = crust * (1 - glow) + lava * glow
    base = base * (1 - molten * 0.6) + lava * 0.75 * molten * 0.6
    # oceans and land
    hgt = _land(a, F)[..., None]
    sea_col = np.array([0.05, 0.22, 0.25]) * (1 - oxygen) + np.array([0.04, 0.16, 0.42]) * oxygen
    sea_col = sea_col * (0.75 + 0.4 * F["n2"][..., None])
    shallow = np.clip(1 + hgt * 6, 0, 1) * (hgt <= 0)
    sea_col = sea_col + shallow * np.array([0.03, 0.12, 0.10])
    bare = np.array([0.42, 0.30, 0.22]) * (0.75 + 0.5 * F["n1"][..., None])
    green = np.array([0.20, 0.42, 0.16]) * (0.75 + 0.5 * F["n2"][..., None])
    desert = np.clip((F["n2"][..., None] - 0.62) * 4, 0, 1) + np.clip((0.35 - lat) * 2, 0, 0.4) * (F["n1"][..., None] > 0.55)
    land_col = bare * (1 - plants) + (green * (1 - desert * 0.45) + bare * desert * 0.45) * plants
    surf = np.where(hgt > 0, land_col, sea_col)
    tex = base * (1 - water) + surf * water
    # ice: snowball phases, plus small polar caps once the air is oxygen-rich
    caps = np.clip((lat - np.radians(72)) * 6, 0, 1) * oxygen * (1 - molten)
    icek = np.maximum(caps, np.clip(ice * 1.6 - (1 - lat / 1.57) * 0.8 * (1 - ice), 0, 1))
    tex = tex * (1 - icek) + np.array([0.9, 0.94, 1.0]) * icek
    # clouds drift on their own
    shift = int(t * 6) % F["cl"].shape[1]
    cl = np.roll(F["cl"], shift, 1)[..., None]
    cloud = np.clip((cl - 0.58) * 3, 0, 0.8) * water * (1 - ice * 0.5)
    haze = np.array([0.95, 0.75, 0.5]) * (1 - oxygen) + np.array([1, 1, 1]) * oxygen
    tex = tex * (1 - cloud) + haze * cloud
    return np.clip(tex, 0, 1).astype(np.float32)


def _halo(R, col, strength):
    key = ("halo", R)
    if key not in _cache:
        n = int(R * 2.8)
        m = Image.new("L", (n, n))
        ImageDraw.Draw(m).ellipse([n / 2 - R * 1.06, n / 2 - R * 1.06, n / 2 + R * 1.06, n / 2 + R * 1.06], fill=255)
        _cache[key] = np.asarray(m.filter(ImageFilter.GaussianBlur(R * 0.12)), np.float32)[..., None] / 255
    a = _cache[key] * strength
    return Image.fromarray(np.clip(a * np.array(col), 0, 255).astype(np.uint8))


def _disc(R, rgb, light=(-0.6, -0.3, 0.75)):
    y, x = np.mgrid[-R:R, -R:R].astype(np.float32) + 0.5
    r2 = (x * x + y * y) / R ** 2
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    L = np.array(light, np.float32) / np.linalg.norm(light)
    d = np.clip((x / R) * L[0] + (y / R) * L[1] + z * L[2], 0, 1)
    col = np.array(rgb, np.float32)[None, None] * (0.08 + 0.92 * d[..., None])
    a = np.clip((1 - np.sqrt(r2)) * R / 1.5, 0, 1)[..., None] * 255
    return Image.fromarray(np.concatenate([col, a], -1).astype(np.uint8), "RGBA")


def earth_build(img, cfg, t, st):
    from .core import Sphere
    cx, cy, R = cfg.get("x", 540), cfg.get("y", 980), int(cfg.get("r", 360))
    a0, a1 = cfg.get("ages", [4.54, 0])
    w0, w1 = cfg.get("_win", (0, cfg.get("dur", 6.0)))
    k = min(max((t - w0) / max(w1 - w0, 0.1), 0), 1)
    k = ease(k) if cfg.get("ease") else k
    if cfg.get("log"):  # sweep evenly in log time so recent eras get room
        la0, la1 = math.log10(max(a0, 1e-4)), math.log10(max(a1, 1e-4))
        a = 10 ** (la0 + (la1 - la0) * k)
        a = 0.0 if a1 == 0 and k >= 1 else a
    else:
        a = a0 + (a1 - a0) * k
    img = img.copy()
    # atmosphere glow: lava red, then orange haze, then blue once oxygen arrives
    molten = float(np.clip((a - 4.38) / 0.1, 0, 1))
    oxygen = float(np.clip((2.5 - a) / 0.2, 0, 1))
    col = np.array([255, 90, 30]) * molten + (np.array([230, 150, 70]) * (1 - oxygen) + np.array([90, 160, 255]) * oxygen) * (1 - molten)
    hal = _halo(R, col, 0.85)
    img.paste(Image.fromarray(np.maximum(np.asarray(img.crop((int(cx - hal.width / 2), int(cy - hal.height / 2),
              int(cx + hal.width / 2), int(cy + hal.height / 2)))), np.asarray(hal))), (int(cx - hal.width / 2), int(cy - hal.height / 2)))
    sph = _cache.get(("earth_sphere", R))
    if sph is None:
        sph = _cache[("earth_sphere", R)] = Sphere(_earth_tex(a, t), R)
    sph.tex = _earth_tex(a, t)
    globe = sph.render(rot=1.3 + t * cfg.get("spin", 0.35), light=(-0.65, -0.3, 0.7), ambient=0.06 + 0.25 * molten)
    # self-glow of the magma ocean on the night side
    if molten > 0:
        g = np.asarray(globe, np.float32)
        g[..., 0] = np.minimum(255, g[..., 0] + 70 * molten)
        g[..., 1] = np.minimum(255, g[..., 1] + 18 * molten)
        globe = Image.fromarray(g.astype(np.uint8), "RGBA")
    img.paste(globe, (cx - R, cy - R), globe)
    d = ImageDraw.Draw(img)
    # Theia: a Mars-sized body that hits around 4.5 Ga; the debris becomes the Moon
    hit = 4.50
    if hit < a < 4.53:
        p = (4.53 - a) / (4.53 - hit)
        tx, ty = cx + R * (2.4 - 1.65 * p), cy - R * (2.0 - 1.4 * p)
        th = _disc(int(R * 0.45), (150, 110, 90))
        img.paste(th, (int(tx - th.width / 2), int(ty - th.height / 2)), th)
    if 4.44 < a <= hit:
        p = (hit - a) / (hit - 4.44)
        flash = max(0, 1 - p * 4)
        if flash:
            fl = _halo(int(R * (0.6 + p * 3)), (255, 240, 200), flash * 1.6)
            arr = np.maximum(np.asarray(img.crop((int(cx + R * 0.55 - fl.width / 2), int(cy - R * 0.55 - fl.height / 2),
                             int(cx + R * 0.55 + fl.width / 2), int(cy - R * 0.55 + fl.height / 2)))), np.asarray(fl))
            img.paste(Image.fromarray(arr), (int(cx + R * 0.55 - fl.width / 2), int(cy - R * 0.55 - fl.height / 2)))
        rng = np.random.default_rng(9)
        n = int(500 * (1 - p) + 60)
        ang = rng.uniform(0, 2 * np.pi, 560)[:n] + t * 0.9
        rad = R * (1.25 + rng.uniform(0, 0.8, 560)[:n] * (1 - p))
        for x, y in zip(cx + rad * np.cos(ang), cy + rad * np.sin(ang) * 0.32):
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 190, 120))
    if a <= 4.47:
        # the Moon starts close and slowly drifts outward
        far = 1.55 + 0.9 * (1 - a / 4.47)
        ang = t * 0.5 + 2.2
        mx, my = cx + R * far * math.cos(ang), cy + R * far * math.sin(ang) * 0.3
        mr = int(R * (0.34 - 0.08 * (1 - a / 4.47)))
        if math.sin(ang) > 0 or abs(mx - cx) > R + mr:  # behind the globe when it passes back
            m = _disc(mr, (190, 186, 178))
            img.paste(m, (int(mx - mr), int(my - mr)), m)
    # impacts: heavy bombardment early, one famous asteroid at 66 Ma
    rng = np.random.default_rng(int(t * 10))
    if a > 3.8:
        for _ in range(2 if rng.random() < 0.5 else 0):
            u, v = rng.uniform(-0.7, 0.7, 2)
            fx, fy = cx + u * R, cy + v * R
            s2 = rng.uniform(6, 16)
            d.ellipse([fx - s2, fy - s2, fx + s2, fy + s2], fill=(255, 230, 170))
    if 0.064 < a < 0.068:
        p = 1 - abs(a - 0.066) / 0.002
        fl = _halo(int(R * 0.16), (255, 220, 160), p * 1.8)
        x0, y0 = int(cx - R * 0.35 - fl.width / 2), int(cy + R * 0.05 - fl.height / 2)
        arr = np.maximum(np.asarray(img.crop((x0, y0, x0 + fl.width, y0 + fl.height))), np.asarray(fl))
        img.paste(Image.fromarray(arr), (x0, y0))
    # game HUD: age counter, era and a timeline
    hx, hy = 70, cfg.get("hud_y", 1500)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([hx, hy, W - hx, hy + 260], 26, fill=(8, 12, 30), outline=(255, 210, 60), width=4)
    fl_, fv, fe = _hud_font(30), _hud_font(60), _hud_font(38)
    d.text((hx + 40, hy + 24), "YEARS AGO", font=fl_, fill=(170, 180, 210))
    d.text((hx + 40, hy + 62), _age_label(a), font=fv, fill=(255, 255, 255))
    d.text((hx + 40, hy + 142), _era(a), font=fe, fill=(255, 210, 60))
    bx0, bx1, by = hx + 40, W - hx - 40, hy + 212
    d.rounded_rectangle([bx0, by, bx1, by + 16], 8, fill=(30, 36, 70))
    pos = bx0 + (bx1 - bx0) * (1 - a / 4.54)
    d.rounded_rectangle([bx0, by, max(bx0 + 16, pos), by + 16], 8, fill=(255, 140, 60))
    for start, _ in ERAS[1:-1]:
        x = bx0 + (bx1 - bx0) * (1 - start / 4.54)
        d.line([x, by - 6, x, by + 22], fill=(120, 130, 170), width=2)
    d.ellipse([pos - 13, by - 5, pos + 13, by + 21], fill=(255, 255, 255))
    return img


SIMS = {"black_hole": black_hole, "tunnel": tunnel, "earth_build": earth_build}


def draw(img, cfg, t, st):
    return SIMS[cfg["kind"]](img, cfg, t, st)
