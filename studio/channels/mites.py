"""Mind Mites: flat 2D pink/mint world, Mite reacts to every test."""
from PIL import Image, ImageDraw

from ..characters import mite
from ..core import W, H, font, plucks, ease_out

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
        self.caption = {"y": 1280, "fill": CREAM, "stroke": INK, "sw": 10}

    def music(self, dur):
        return plucks(dur, vol=0.045)

    def background(self, p, t, st, ctx):
        dark = p.get("bg") == "dark"
        img = Image.new("RGB", (W, H), INK if dark else PINK)
        self.colors["accent"] = PINK if dark else INK
        self.colors["text"] = CREAM
        self.colors["brand"] = CREAM if dark else INK
        d = ImageDraw.Draw(img)
        for ic in p.get("icons", []):
            icon(d, ic["kind"], ic["x"], ic["y"], ic.get("s", 1.0))
        m = p.get("mite", {"x": W / 2, "y": 1650, "s": 0.8})
        if m:
            grow = ease_out(st / 0.3) if m.get("pop") else 1
            if dark:
                r = 190 * m.get("s", 0.8) * grow
                d.ellipse([m.get("x", W / 2) - r, m.get("y", 1650) - r, m.get("x", W / 2) + r, m.get("y", 1650) + r], fill=PINK)
            mite(d, m.get("x", W / 2), m.get("y", 1650), m.get("s", 0.8) * grow + 0.01, t, m.get("mood", "happy"),
                 tuple(m.get("look", (0, 0))))
        return img

    def post(self, img, t):
        return img
