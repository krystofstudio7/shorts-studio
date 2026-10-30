"""Stoic Ember: illustrated true stories, silhouettes in ember light, film grain."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..characters import stoic_figure
from ..core import W, H, add, ease, font, gradient, pad, vignette

BLACK, CREAM, GOLD, EMBER, SEA = (12, 12, 12), (233, 227, 214), (176, 141, 87), (255, 130, 40), (20, 30, 38)


class Theme:
    brand = "STOIC EMBER"
    voice, speed = "bm_george", 0.95
    crf = 26
    hashtags = ["#stoicism", "#history", "#seneca", "#marcusaurelius", "#philosophy", "#discipline"]

    def __init__(self):
        self.fonts = {
            "display": font("Cinzel-VF.ttf", 104, 800), "stat": font("Cinzel-VF.ttf", 220, 800), "row": font("Cinzel-VF.ttf", 56, 800),
            "label": font("Cinzel-VF.ttf", 34, 800), "body": font("Cinzel-VF.ttf", 52, 700), "quote": font("Cinzel-VF.ttf", 68, 700),
            "small": font("IBMPlexMono-Medium.ttf", 24), "brand": font("Cinzel-VF.ttf", 30, 700),
            "caption": font("Cinzel-VF.ttf", 72, 800), "hook": font("Cinzel-VF.ttf", 84, 800),
        }
        self.colors = {"bg": BLACK, "text": CREAM, "accent": CREAM, "accent2": GOLD, "pill_bg": GOLD, "pill_fg": BLACK,
                       "card_bg": (40, 36, 30), "card_fg": CREAM, "no": (180, 50, 40), "muted": (170, 150, 120), "hook": CREAM,
                       "brand": (150, 125, 85)}
        self.caption = {"y": 1300, "fill": CREAM, "stroke": (0, 0, 0), "sw": 6}
        rng = np.random.default_rng(11)
        self.rain = [(rng.random() * W, rng.random() * H, 900 + rng.random() * 700, 30 + rng.random() * 60) for _ in range(170)]
        self.embers = [(rng.random() * W, rng.random() * H, 40 + rng.random() * 90, 1.5 + rng.random() * 3.5, rng.random() * 6) for _ in range(90)]
        g = [rng.normal(0, 9, (H // 2, W // 2)).astype(np.int16) for _ in range(4)]
        self.grain = [np.repeat(np.repeat(x, 2, 0), 2, 1)[..., None] for x in g]
        self.vig = vignette(W, H, 0.9)
        self._glow = {}

    def music(self, dur):
        return pad(dur, (73.42, 110, 146.83, 174.61), vol=0.07, seed=4)

    def glow(self, x, y, r):
        key = (int(x), int(y), int(r))
        if key not in self._glow:
            g = Image.new("RGB", (W, H), (0, 0, 0))
            ImageDraw.Draw(g).ellipse([x - r, y - r, x + r, y + r], fill=(150, 60, 12))
            self._glow[key] = g.filter(ImageFilter.GaussianBlur(r * 0.6))
        return self._glow[key]

    def setting(self, img, d, kind, t, st):
        ground = 1640
        if kind in ("sea", "island", "shipwreck"):
            hz = 1180
            d.rectangle([0, hz, W, H], fill=SEA)
            for i in range(24):
                y = hz + 20 + i * 30
                off = (t * 40 * (1 + i * 0.1)) % 120
                for x in range(-120, W, 120):
                    d.arc([x + off, y, x + off + 120, y + 30], 200, 340, fill=(45, 60, 70), width=3)
            if kind == "island":
                d.polygon([(300, hz + 4), (420, hz - 170), (520, hz - 120), (650, hz - 230), (820, hz + 4)], fill=(26, 24, 22))
            if kind == "shipwreck":
                tilt = 8 + 4 * math.sin(t * 0.8) + 25 * ease(st / 6)
                ship = Image.new("RGBA", (700, 700), (0, 0, 0, 0))
                sd = ImageDraw.Draw(ship)
                sd.polygon([(80, 470), (620, 470), (540, 560), (160, 560)], fill=(30, 26, 22, 255))
                sd.rectangle([342, 120, 358, 470], fill=(30, 26, 22, 255))
                sd.polygon([(360, 140), (560, 420), (360, 420)], fill=(60, 52, 44, 255))
                ship = ship.rotate(tilt, resample=Image.BICUBIC)
                img.paste(ship, (190, hz - 520 + int(60 * ease(st / 6))), ship)
            return hz + 40
        if kind == "city":
            for x in (120, 330, 750, 960):
                d.rectangle([x - 70, 900, x + 70, 930], fill=(34, 31, 28))
                d.rectangle([x - 55, 930, x + 55, ground - 30], fill=(34, 31, 28))
                for k in range(-2, 3):
                    d.line([x + k * 20, 940, x + k * 20, ground - 40], fill=BLACK, width=3)
            d.polygon([(40, 900), (540, 640), (1040, 900)], fill=(30, 28, 25))
        elif kind == "camp":
            d.polygon([(0, 1250), (220, 1000), (420, 1180), (640, 960), (900, 1200), (W, 1080), (W, ground), (0, ground)], fill=(22, 22, 26))
            for x, s in ((200, 1.0), (520, 1.3), (860, 0.9)):
                d.polygon([(x - 150 * s, ground), (x, ground - 230 * s), (x + 150 * s, ground)], fill=(40, 34, 28))
                d.line([x, ground - 230 * s, x, ground - 300 * s], fill=(40, 34, 28), width=6)
        elif kind == "room":
            d.rectangle([0, 0, W, ground], fill=(26, 22, 18))
            d.rectangle([680, 520, 940, 900], fill=(14, 16, 24))
            d.line([810, 520, 810, 900], fill=(26, 22, 18), width=10)
            d.line([680, 710, 940, 710], fill=(26, 22, 18), width=10)
        elif kind == "night":
            rng = np.random.default_rng(2)
            for _ in range(160):
                x, y = rng.integers(0, W), rng.integers(200, 1300)
                c = int(60 + 120 * rng.random())
                d.point((x, y), fill=(c, c, c))
        if kind != "black":
            d.rectangle([0, ground, W, H], fill=(20, 18, 16))
        return ground

    def background(self, p, t, st, ctx):
        img = gradient(H, W, (10, 10, 12), (24, 18, 14)) if p.get("setting", "black") != "black" else Image.new("RGB", (W, H), BLACK)
        d = ImageDraw.Draw(img)
        ground = self.setting(img, d, p.get("setting", "black"), t, st)
        if p.get("fire", True) and p.get("setting", "black") != "black":
            img = add(img, self.glow(p.get("fire_x", 540), ground - 40, 300))
            d = ImageDraw.Draw(img)
        for f in p.get("figures", []):
            stoic_figure(d, f.get("x", 540) + f.get("walk", 0) * st, f.get("ground", ground), f.get("h", 520), f.get("pose", "standing"),
                         t=t, facing=f.get("facing", 1))
        ra = p.get("rain", 0.0)
        if ra:
            for (x, y, sp, ln) in self.rain:
                yy = (y + sp * t) % (H + 100) - 100
                xx = x - 0.12 * (yy % H)
                c = int(70 * ra)
                d.line([xx, yy, xx - ln * 0.12, yy + ln], fill=(c, c, c + 6), width=2)
        ea = p.get("embers", 0.8)
        for (x, y, sp, r, ph) in self.embers:
            yy = H - ((H - y + sp * t) % (H + 40))
            xx = x + 25 * math.sin(t * 0.8 + ph)
            k = ea * (0.6 + 0.4 * math.sin(t * 6 + ph * 3))
            d.ellipse([xx - r * 2.4, yy - r * 2.4, xx + r * 2.4, yy + r * 2.4], fill=(int(60 * k), int(18 * k), 0))
            d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(int(255 * k), int(130 * k), int(40 * k)))
        return img

    def post(self, img, t):
        from ..core import FPS
        arr = np.asarray(img, np.int16) + self.grain[int(t * FPS) % 4]
        return Image.fromarray((np.clip(arr, 0, 255) * self.vig).astype(np.uint8))
