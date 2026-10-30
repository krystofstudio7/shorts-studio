"""What If Institute: night-blue space, Scout lives through each scenario."""
import math

import numpy as np
from PIL import Image, ImageDraw

from ..characters import scout
from ..core import W, H, Sphere, add, ease, font, fractal_noise, gradient, pad, starfield, vignette

NAVY, YEL, CREAM, ORANGE = (11, 23, 54), (255, 210, 63), (242, 245, 255), (255, 107, 53)


def tex_earth(h=512, w=1024, seed=3):
    n = fractal_noise(h, w, 7, seed, wrap=True)
    lat = np.abs(np.linspace(-1, 1, h))[:, None]
    sea = n < 0.55
    t = np.clip((0.55 - n) / 0.55, 0, 1)[..., None]
    tex = np.array([18, 60, 140]) / 255 * (1 - t) + np.array([8, 30, 85]) / 255 * t
    dd = np.clip((n - 0.55) / 0.3, 0, 1)[..., None]
    land = np.array([60, 120, 60]) / 255 * (1 - dd) + np.array([170, 150, 95]) / 255 * dd
    tex = np.where(sea[..., None], tex, land)
    tex = np.where(((lat > 0.85) | ((lat > 0.75) & ~sea))[..., None], np.array([235, 240, 250]) / 255, tex)
    cl = np.clip((fractal_noise(h, w, 6, seed + 11, wrap=True) - 0.55) * 3, 0, 0.85)[..., None]
    return tex * (1 - cl) + cl


def tex_jupiter(h=512, w=1024, seed=8):
    lat = np.linspace(-1, 1, h)[:, None]
    n = fractal_noise(h, w, 6, seed, wrap=True)
    warp = lat + 0.04 * (n - 0.5)
    band = 0.5 + 0.5 * np.sin(warp * 26)
    light, dark = np.array([236, 222, 196]) / 255, np.array([176, 120, 82]) / 255
    tex = light * band[..., None] + dark * (1 - band[..., None])
    tex *= (0.9 + 0.2 * n)[..., None]
    yy, xx = np.mgrid[0:h, 0:w]
    spot = ((xx - w * 0.3) / (w * 0.05)) ** 2 + ((yy - h * 0.62) / (h * 0.04)) ** 2
    tex = np.where((spot < 1)[..., None], np.array([196, 90, 60]) / 255, tex)
    return np.clip(tex, 0, 1)


def tex_mars(h=512, w=1024, seed=4):
    n = fractal_noise(h, w, 7, seed, wrap=True)
    tex = np.array([190, 90, 50]) / 255 * (0.7 + 0.5 * n[..., None])
    lat = np.abs(np.linspace(-1, 1, h))[:, None]
    return np.clip(np.where((lat > 0.9)[..., None], np.array([240, 235, 230]) / 255, tex), 0, 1)


def tex_moon(h=256, w=512, seed=5):
    n = fractal_noise(h, w, 6, seed, wrap=True)
    tex = 0.45 + 0.35 * n
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(60):
        cy, cx, r = rng.integers(0, h), rng.integers(0, w), rng.integers(3, 22)
        dd = ((yy - cy) ** 2 + (xx - cx) ** 2) / r ** 2
        tex -= 0.12 * np.exp(-dd * 2) * (dd < 1.4)
    tex = np.clip(tex, 0, 1)
    return np.stack([tex, tex, tex * 0.97], -1)


TEXTURES = {"earth": tex_earth, "jupiter": tex_jupiter, "mars": tex_mars, "moon": tex_moon}


class Theme:
    brand = "WHAT IF INSTITUTE"
    voice, speed = "am_michael", 1.0
    crf = 20
    hashtags = ["#whatif", "#science", "#space", "#physics", "#didyouknow", "#learnontiktok"]

    def __init__(self):
        self.fonts = {
            "display": font("Anton-Regular.ttf", 130), "stat": font("Anton-Regular.ttf", 210), "row": font("Anton-Regular.ttf", 62),
            "label": font("IBMPlexMono-Medium.ttf", 34), "body": font("Anton-Regular.ttf", 58), "quote": font("Anton-Regular.ttf", 70),
            "small": font("IBMPlexMono-Medium.ttf", 24), "brand": font("IBMPlexMono-Medium.ttf", 26),
            "caption": font("Anton-Regular.ttf", 96), "hook": font("Anton-Regular.ttf", 110),
        }
        self.colors = {"bg": NAVY, "text": CREAM, "accent": YEL, "accent2": YEL, "pill_bg": YEL, "pill_fg": NAVY,
                       "card_bg": CREAM, "card_fg": NAVY, "no": ORANGE, "muted": (170, 180, 210), "hook": YEL, "brand": (200, 210, 240),
                       "stat_stroke": (0, 0, 0), "stat_stroke_w": 8}
        self.caption = {"y": 1280, "fill": YEL, "stroke": (0, 0, 0), "sw": 9}
        self.stars = starfield(1300, 2400, 2200, seed=4)
        self.vig = vignette(W, H, 0.7)
        self._spheres = {}

    def sphere(self, kind, R):
        key = (kind, R)
        if key not in self._spheres:
            self._spheres[key] = Sphere(TEXTURES[kind](), R)
        return self._spheres[key]

    def music(self, dur):
        return pad(dur, (98, 146.83, 196, 233.08), vol=0.05)

    def background(self, p, t, st, ctx):
        kind = p.get("bg", "space")
        if kind == "space":
            pan = t * 6
            img = self.stars.crop((int(110 + pan * 0.3), int(190 + pan), int(110 + pan * 0.3) + W, int(190 + pan) + H))
            img = add(img, Image.new("RGB", (W, H), (4, 8, 22)))
        elif kind == "descent":
            top, bottom = p.get("colors", [[40, 30, 20], [120, 70, 40]])
            img = gradient(H, W, top, bottom)
            d = ImageDraw.Draw(img)
            speed = p.get("speed", 900)
            for i in range(14):
                y = (i * 170 - st * speed) % (H + 200) - 100
                c = tuple(min(255, int(v * 1.25)) for v in bottom)
                wob = [(x, y + 18 * math.sin(x / 90 + i)) for x in range(0, W + 40, 40)]
                d.line(wob, fill=c, width=26)
        elif kind == "surface":
            sky, ground = p.get("colors", [[200, 120, 80], [150, 70, 40]])
            img = gradient(H, W, sky, sky)
            d = ImageDraw.Draw(img)
            xs = range(0, W + 20, 20)
            d.polygon([(0, H)] + [(x, 1450 + 40 * math.sin(x / 130) + 20 * math.sin(x / 47)) for x in xs] + [(W, H)], fill=tuple(ground))
        else:
            img = Image.new("RGB", (W, H), tuple(p.get("color", NAVY)))
        pl = p.get("planet")
        if pl:
            R = pl.get("r", 340)
            zoom = 1 + pl.get("zoom", 0.0) * ease(st / 6)
            sp = self.sphere(pl["kind"], R).render(rot=t * pl.get("spin", 0.08), light=(-0.7, -0.35, 0.6))
            if zoom != 1:
                sp = sp.resize((int(2 * R * zoom), int(2 * R * zoom)), Image.BILINEAR)
            img.paste(sp, (int(pl.get("x", 540) - sp.width / 2), int(pl.get("y", 1050) - sp.height / 2)), sp)
        sc = p.get("scout")
        if sc:
            drift = sc.get("drift", 0) * st
            bob = 14 * math.sin(t * 1.6)
            scout(img, sc.get("x", 760), sc.get("y", 520) + drift + bob, sc.get("s", 0.8), t, sc.get("pose", "float"), sc.get("angle", 0))
        return img

    def post(self, img, t):
        return Image.fromarray((np.asarray(img, np.float32) * self.vig).astype(np.uint8))
