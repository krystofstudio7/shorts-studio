"""What If Institute: night-blue space, Scout lives through each scenario."""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

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


GLOW = {"earth": (70, 140, 255), "jupiter": (230, 170, 100), "mars": (240, 120, 70), "moon": (140, 140, 160)}


def nebula(w, h, seed=7):
    """Faint purple and teal clouds, rendered small and scaled up."""
    a = fractal_noise(h // 4, w // 4, 6, seed)
    b = fractal_noise(h // 4, w // 4, 6, seed + 1)
    ca = np.clip((a - 0.45) * 2.2, 0, 1)[..., None] ** 1.6
    cb = np.clip((b - 0.5) * 2.2, 0, 1)[..., None] ** 1.6
    arr = ca * np.array([90, 40, 140]) + cb * np.array([20, 90, 120])
    return Image.fromarray(arr.astype(np.uint8)).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))


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
        self.caption["fill"], self.caption["hl"] = CREAM, YEL
        self.stars = ImageChops.add(starfield(1300, 2400, 2200, seed=4), nebula(1300, 2400))
        self.near = starfield(1300, 4000, 180, seed=9).filter(ImageFilter.GaussianBlur(1.2))
        self.near = ImageChops.add(self.near, self.near)
        rng = np.random.default_rng(5)
        self.dust = [(rng.random() * W, rng.random(), 2 + rng.random() * 5, 0.5 + rng.random()) for _ in range(70)]
        self._glows = {}
        self.vig = vignette(W, H, 0.7)
        self._spheres = {}

    def sphere(self, kind, R):
        key = (kind, R)
        if key not in self._spheres:
            self._spheres[key] = Sphere(TEXTURES[kind](), R)
        return self._spheres[key]

    def atmosphere(self, img, kind, r, cx, cy):
        """Soft coloured halo around a planet."""
        r = int(r)
        key = (kind, r // 8)
        if key not in self._glows:
            n = int(r * 3.2)
            g = Image.new("RGB", (n, n), (0, 0, 0))
            ImageDraw.Draw(g).ellipse([n / 2 - r * 1.06, n / 2 - r * 1.06, n / 2 + r * 1.06, n / 2 + r * 1.06],
                                      fill=tuple(int(c * 0.75) for c in GLOW.get(kind, (120, 120, 140))))
            self._glows[key] = g.filter(ImageFilter.GaussianBlur(r * 0.22))
        g = self._glows[key]
        x0, y0 = int(cx - g.width / 2), int(cy - g.height / 2)
        box = (max(0, x0), max(0, y0), min(W, x0 + g.width), min(H, y0 + g.height))
        if box[0] >= box[2] or box[1] >= box[3]:
            return img
        region = ImageChops.add(img.crop(box), g.crop((box[0] - x0, box[1] - y0, box[2] - x0, box[3] - y0)))
        img.paste(region, box[:2])
        return img

    def music(self, dur):
        return pad(dur, (98, 146.83, 196, 233.08), vol=0.05)

    def background(self, p, t, st, ctx):
        kind = p.get("bg", "space")
        if kind == "space":
            pan = t * 6
            img = self.stars.crop((int(110 + pan * 0.3), int(190 + pan), int(110 + pan * 0.3) + W, int(190 + pan) + H))
            fast = t * 22
            img = ImageChops.add(img, self.near.crop((int(110 + fast * 0.3), int(400 + fast) % 2000,
                                                       int(110 + fast * 0.3) + W, int(400 + fast) % 2000 + H)))
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
            # speed streaks rushing past the camera
            for (x, y0, w, k) in self.dust:
                y = H - ((y0 * H + st * speed * 2.2 * k) % (H + 300))
                d.line([x, y, x, y + 140 * k], fill=tuple(min(255, int(v * 1.6) + 30) for v in bottom), width=int(w))
        elif kind == "surface":
            sky, ground = p.get("colors", [[200, 120, 80], [150, 70, 40]])
            img = gradient(H, W, sky, sky)
            d = ImageDraw.Draw(img)
            xs = range(0, W + 20, 20)
            far = tuple(int(a * 0.55 + b * 0.45) for a, b in zip(sky, ground))
            d.polygon([(0, H)] + [(x, 1330 + 60 * math.sin(x / 210 + 1) + 25 * math.sin(x / 70) - st * 4) for x in xs] + [(W, H)], fill=far)
            d.polygon([(0, H)] + [(x, 1450 + 40 * math.sin(x / 130) + 20 * math.sin(x / 47)) for x in xs] + [(W, H)], fill=tuple(ground))
            for (x, y0, w, k) in self.dust:
                xx = (x + t * 60 * k) % W
                yy = 300 + y0 * 1200 + 20 * math.sin(t + x)
                d.ellipse([xx - w / 2, yy - w / 2, xx + w / 2, yy + w / 2], fill=tuple(min(255, v + 50) for v in sky))
        else:
            img = Image.new("RGB", (W, H), tuple(p.get("color", NAVY)))
        pl = p.get("planet")
        if pl:
            R = pl.get("r", 340)
            zoom = 1 + pl.get("zoom", 0.0) * ease(st / 6)
            sp = self.sphere(pl["kind"], R).render(rot=t * pl.get("spin", 0.08), light=(-0.7, -0.35, 0.6))
            if zoom != 1:
                sp = sp.resize((int(2 * R * zoom), int(2 * R * zoom)), Image.BILINEAR)
            img = self.atmosphere(img, pl["kind"], sp.width / 2, pl.get("x", 540), pl.get("y", 1050))
            img.paste(sp, (int(pl.get("x", 540) - sp.width / 2), int(pl.get("y", 1050) - sp.height / 2)), sp)
        sc = p.get("scout")
        if sc:
            drift = sc.get("drift", 0) * st
            bob = 14 * math.sin(t * 1.6)
            scout(img, sc.get("x", 760), sc.get("y", 520) + drift + bob, sc.get("s", 0.8), t, sc.get("pose", "float"), sc.get("angle", 0))
        return img

    def post(self, img, t):
        return Image.fromarray((np.asarray(img, np.float32) * self.vig).astype(np.uint8))
