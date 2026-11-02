"""Mind Mites: flat 2D pink/mint world, Mite reacts to every test."""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ..characters import mite
from ..core import W, H, font, plucks, ease_out, resize

PINK, INK, MINT, CREAM, SUN, RED = (255, 90, 138), (26, 14, 43), (124, 242, 200), (255, 246, 229), (255, 201, 60), (230, 40, 70)


def icon(d, kind, x, y, s=1.0):
    if kind == "ball":
        r = 70 * s
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255), outline=INK, width=int(5 * s))
        d.arc([x - r * 1.5, y - r * 0.8, x - r * 0.1, y + r * 0.8], -60, 60, fill=RED, width=int(5 * s))
        d.arc([x + r * 0.1, y - r * 0.8, x + r * 1.5, y + r * 0.8], 120, 240, fill=RED, width=int(5 * s))
    elif kind == "bat":
        d.line([x - 160 * s, y + 60 * s, x - 70 * s, y + 25 * s], fill=(120, 72, 40), width=int(34 * s))
        d.line([x - 80 * s, y + 28 * s, x + 160 * s, y - 70 * s], fill=(170, 105, 55), width=int(58 * s))
        d.ellipse([x + 130 * s, y - 100 * s, x + 190 * s, y - 40 * s], fill=(170, 105, 55))
    elif kind == "tag":
        d.polygon([(x - 120 * s, y - 60 * s), (x + 80 * s, y - 60 * s), (x + 140 * s, y), (x + 80 * s, y + 60 * s), (x - 120 * s, y + 60 * s)], fill=SUN)
        d.ellipse([x + 60 * s, y - 12 * s, x + 84 * s, y + 12 * s], fill=INK)


TILE = 180


def radial(top, edge):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.clip(np.hypot((x - W / 2) / W, (y - H * 0.42) / H) * 1.6, 0, 1)[..., None]
    arr = np.array(top, np.float32) * (1 - r) + np.array(edge, np.float32) * r
    return Image.fromarray(arr.astype(np.uint8))


def pattern(col):
    """Little doodles (plus, ring, dot, squiggle) on a grid that tiles every TILE pixels."""
    img = Image.new("RGB", (W + 2 * TILE, H + 2 * TILE), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for gy in range(0, img.height, TILE):
        for gx in range(0, img.width, TILE):
            kind = ((gx // TILE) * 3 + (gy // TILE) * 5) % 4
            x, y = gx + TILE / 2 + ((gy // TILE) % 2) * TILE / 2, gy + TILE / 2
            if kind == 0:
                d.line([x - 16, y, x + 16, y], fill=col, width=8)
                d.line([x, y - 16, x, y + 16], fill=col, width=8)
            elif kind == 1:
                d.ellipse([x - 15, y - 15, x + 15, y + 15], outline=col, width=7)
            elif kind == 2:
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=col)
            else:
                d.arc([x - 22, y - 10, x, y + 10], 180, 360, fill=col, width=7)
                d.arc([x, y - 10, x + 22, y + 10], 0, 180, fill=col, width=7)
    return img


class Theme:
    brand = "MIND MITES"
    voice, speed = "af_heart", 1.1
    crf = 20
    hashtags = ["#psychology", "#brain", "#psychologyfacts", "#cognitivebias", "#mindblown", "#learnontiktok"]

    def __init__(self):
        d = font("Rubik-VF.ttf", 120, 800)
        self.fonts = {
            "display": d, "stat": font("Rubik-VF.ttf", 260, 800), "row": font("Rubik-VF.ttf", 62, 800),
            "label": font("Rubik-VF.ttf", 40, 800), "body": font("Rubik-VF.ttf", 54, 800), "quote": font("Rubik-VF.ttf", 64, 800),
            "small": font("IBMPlexMono-Medium.ttf", 24), "brand": font("Rubik-VF.ttf", 32, 800),
            "caption": font("Rubik-VF.ttf", 82, 800), "hook": font("Rubik-VF.ttf", 88, 800),
        }
        self.colors = {"bg": PINK, "text": CREAM, "accent": INK, "accent2": MINT, "pill_bg": INK, "pill_fg": MINT,
                       "card_bg": CREAM, "card_fg": INK, "no": RED, "muted": (90, 60, 100), "hook": INK, "brand": INK}
        self.caption = {"y": 1280, "fill": CREAM, "stroke": INK, "sw": 10, "hl": SUN}
        self.base = {False: radial((255, 122, 160), (232, 62, 118)), True: radial((52, 30, 80), (18, 9, 30))}
        rng = np.random.default_rng(3)
        self.bits = [(W / 2 + rng.normal(0, 60), rng.normal(0, 420), -900 - rng.random() * 600, rng.random() * 6, rng.integers(0, 4))
                     for _ in range(70)]
        self.pat = {False: pattern((30, 14, 22)), True: pattern((26, 18, 44))}

    def music(self, dur):
        return plucks(dur, vol=0.045)

    def background(self, p, t, st, ctx):
        dark = p.get("bg") == "dark"
        off = int(t * 24) % TILE
        img = ImageChops.add(self.base[dark], self.pat[dark].crop((off, TILE - off, off + W, TILE - off + H)))
        self.colors["accent"] = PINK if dark else INK
        self.colors["text"] = CREAM
        self.colors["brand"] = CREAM if dark else INK
        d = ImageDraw.Draw(img)
        for n, ic in enumerate(p.get("icons", [])):
            bob = 10 * math.sin(t * 2.2 + n * 1.7)
            icon(d, ic["kind"], ic["x"], ic["y"] + bob, ic.get("s", 1.0))
        m = p.get("mite", {"x": W / 2, "y": 1650, "s": 0.8})
        if m:
            grow = ease_out(st / 0.3) if m.get("pop") else 1
            lt = ctx.get("lt", st)
            mood = m.get("mood", "happy")
            # a little hop when Mite reacts, a thought bubble while it waits
            hop = -70 * m.get("s", 0.8) * math.sin(math.pi * min(lt / 0.45, 1)) if mood in ("happy", "shock") and lt < 0.45 else 0
            m = {**m, "y": m.get("y", 1650) + hop}
            sx, sy, ss = m["x"] if "x" in m else W / 2, m["y"], m.get("s", 0.8) * grow
            if mood == "waiting":
                bx, by = sx + 150 * ss, sy - 300 * ss
                for k, (ox, oy, r) in enumerate(((-70, 150, 12), (-40, 100, 20))):
                    d.ellipse([bx + ox * ss - r * ss, by + oy * ss - r * ss, bx + ox * ss + r * ss, by + oy * ss + r * ss], fill=CREAM)
                rr = 70 * ss * (1 + 0.05 * math.sin(t * 4))
                d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=CREAM, outline=INK, width=max(2, int(6 * ss)))
                d.text((bx, by + 4), "?", font=resize(self.fonts["display"], max(20, int(90 * ss))), fill=INK, anchor="mm")
            if not dark:
                d.ellipse([sx - 150 * ss, sy + 120 * ss, sx + 150 * ss, sy + 160 * ss], fill=(196, 50, 100))
            if dark:
                r = 190 * m.get("s", 0.8) * grow
                d.ellipse([m.get("x", W / 2) - r, m.get("y", 1650) - r, m.get("x", W / 2) + r, m.get("y", 1650) + r], fill=PINK)
            mite(d, m.get("x", W / 2), m.get("y", 1650), m.get("s", 0.8) * grow + 0.01, t, m.get("mood", "happy"),
                 tuple(m.get("look", (0, 0))))
        # confetti when a correct answer appears
        for (i, _l, mk), born in p.get("_row_born", {}).items():
            if mk == "ok" and 0 <= t - born < 1.8:
                self.confetti(d, t - born)
        return img

    def confetti(self, d, e):
        cols = (MINT, SUN, CREAM, (120, 180, 255))
        for i, (x, vx, vy, rot, c) in enumerate(self.bits):
            x1 = x + vx * e
            y1 = 700 + vy * e + 900 * e * e
            a = rot + e * 8
            w, h = 22 * math.cos(a), 12
            d.polygon([(x1 - w, y1 - h), (x1 + w, y1 - h * 0.4), (x1 + w, y1 + h), (x1 - w, y1 + h * 0.4)], fill=cols[c])

    def post(self, img, t):
        return img
