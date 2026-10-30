"""Recurring channel characters, drawn in code so every frame is original."""
import math

from PIL import Image, ImageDraw

# ---------- Mite (Mind Mites) ----------
MITE_INK, MITE_MINT, MITE_CREAM = (26, 14, 43), (124, 242, 200), (255, 246, 229)


def mite(d, cx, cy, s=1.0, t=0.0, mood="happy", look=(0, 0)):
    """mood: happy | sad | shock | waiting | smug"""
    speed = 14 if mood == "waiting" else 7
    b = math.sin(t * speed) * (0.07 if mood == "waiting" else 0.04)
    rx, ry = 120 * s * (1 + b), 105 * s * (1 - b)
    if mood == "waiting":
        look = (math.sin(t * 3), -0.3)
    for k in (-1, 1):
        for j in range(3):
            y = cy + ry * (0.1 + j * 0.3)
            x = cx + k * rx * 0.85
            wig = 8 * s * math.sin(t * (18 if mood == "waiting" else 10) + j + k)
            d.line([x, y, x + k * 55 * s, y + 35 * s + wig], fill=MITE_INK, width=max(2, int(12 * s)))
    for k in (-1, 1):
        lift = 25 * s if mood == "shock" else 0
        tip = (cx + k * 70 * s, cy - ry - 80 * s - lift + 6 * math.sin(t * 5 + k))
        d.line([cx + k * 30 * s, cy - ry + 10 * s, tip[0], tip[1]], fill=MITE_INK, width=max(2, int(10 * s)))
        d.ellipse([tip[0] - 16 * s, tip[1] - 16 * s, tip[0] + 16 * s, tip[1] + 16 * s], fill=MITE_MINT)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=MITE_INK)
    blink = (t % 3.2) < 0.12 and mood != "shock"
    eye = 1.25 if mood == "shock" else 1.0
    for k in (-1, 1):
        ex, ey = cx + k * 45 * s, cy - 20 * s
        if blink:
            d.line([ex - 30 * s, ey, ex + 30 * s, ey], fill=MITE_CREAM, width=max(2, int(8 * s)))
            continue
        d.ellipse([ex - 34 * s * eye, ey - 38 * s * eye, ex + 34 * s * eye, ey + 38 * s * eye], fill=MITE_CREAM)
        pr = 15 * s * (0.7 if mood == "shock" else 1)
        px, py = ex + look[0] * 12 * s, ey + look[1] * 12 * s
        d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=MITE_INK)
        if mood == "smug":
            d.rectangle([ex - 36 * s, ey - 40 * s, ex + 36 * s, ey - 8 * s], fill=MITE_INK)
    if mood == "happy":
        d.arc([cx - 35 * s, cy + 15 * s, cx + 35 * s, cy + 60 * s], 10, 170, fill=MITE_MINT, width=max(2, int(9 * s)))
    elif mood == "sad":
        d.arc([cx - 30 * s, cy + 40 * s, cx + 30 * s, cy + 75 * s], 200, 340, fill=MITE_MINT, width=max(2, int(9 * s)))
    elif mood == "shock":
        d.ellipse([cx - 16 * s, cy + 30 * s, cx + 16 * s, cy + 70 * s], fill=MITE_MINT)
    elif mood == "smug":
        d.arc([cx - 10 * s, cy + 20 * s, cx + 40 * s, cy + 55 * s], 20, 160, fill=MITE_MINT, width=max(2, int(9 * s)))
    else:
        d.line([cx - 25 * s, cy + 45 * s, cx + 25 * s, cy + 45 * s], fill=MITE_MINT, width=max(2, int(9 * s)))


# ---------- Scout (What If Institute) ----------
SUIT, SUIT_DARK, VISOR, VISOR_HI, WHITE = (255, 122, 26), (196, 82, 10), (16, 28, 64), (120, 170, 255), (240, 242, 250)


def scout(img, cx, cy, s=1.0, t=0.0, pose="float", angle=0.0):
    """pose: float | fall | wave | stand | sit. Draws onto img (RGB)."""
    S = int(420 * s)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k = s
    c = S / 2
    sw = math.sin(t * 3)
    lw = max(3, int(30 * k))

    def limb(x0, y0, x1, y1, col=SUIT):
        d.line([x0, y0, x1, y1], fill=col, width=lw)
        d.ellipse([x1 - lw * 0.6, y1 - lw * 0.6, x1 + lw * 0.6, y1 + lw * 0.6], fill=WHITE)

    # backpack
    d.rounded_rectangle([c - 62 * k, c - 10 * k, c + 62 * k, c + 95 * k], int(18 * k), fill=(190, 196, 214))
    # legs
    if pose == "fall":
        limb(c - 25 * k, c + 95 * k, c - 55 * k + 6 * k * sw, c + 165 * k)
        limb(c + 25 * k, c + 95 * k, c + 60 * k - 6 * k * sw, c + 160 * k)
    elif pose == "sit":
        limb(c - 25 * k, c + 95 * k, c - 70 * k, c + 110 * k)
        limb(c + 25 * k, c + 95 * k, c + 70 * k, c + 110 * k)
    else:
        swing = 10 * k * sw if pose == "float" else 0
        limb(c - 22 * k, c + 95 * k, c - 30 * k - swing, c + 170 * k)
        limb(c + 22 * k, c + 95 * k, c + 30 * k + swing, c + 170 * k)
    # body
    d.rounded_rectangle([c - 52 * k, c - 15 * k, c + 52 * k, c + 110 * k], int(40 * k), fill=SUIT)
    d.rectangle([c - 52 * k, c + 50 * k, c + 52 * k, c + 62 * k], fill=SUIT_DARK)
    d.rounded_rectangle([c - 20 * k, c + 10 * k, c + 20 * k, c + 38 * k], int(6 * k), fill=WHITE)
    # arms
    if pose == "fall":
        limb(c - 45 * k, c + 5 * k, c - 110 * k, c - 70 * k + 8 * k * sw)
        limb(c + 45 * k, c + 5 * k, c + 110 * k, c - 75 * k - 8 * k * sw)
    elif pose == "wave":
        limb(c - 45 * k, c + 10 * k, c - 85 * k, c + 85 * k)
        limb(c + 45 * k, c + 5 * k, c + 105 * k + 18 * k * math.sin(t * 9), c - 80 * k)
    else:
        limb(c - 45 * k, c + 10 * k, c - 100 * k, c + 40 * k + 10 * k * sw)
        limb(c + 45 * k, c + 10 * k, c + 100 * k, c + 40 * k - 10 * k * sw)
    # helmet
    hr = 78 * k
    hy = c - 70 * k
    d.ellipse([c - hr, hy - hr, c + hr, hy + hr], fill=WHITE)
    d.rounded_rectangle([c - 58 * k, hy - 40 * k, c + 58 * k, hy + 38 * k], int(36 * k), fill=VISOR)
    d.arc([c - 46 * k, hy - 30 * k, c + 10 * k, hy + 20 * k], 200, 260, fill=VISOR_HI, width=max(2, int(8 * k)))
    # eyes behind visor
    for e in (-1, 1):
        ex = c + e * 20 * k
        d.ellipse([ex - 7 * k, hy - 4 * k, ex + 7 * k, hy + 12 * k], fill=WHITE)
    d.rectangle([c - 8 * k, hy - hr - 18 * k, c + 8 * k, hy - hr + 4 * k], fill=SUIT)
    rot = angle + (25 if pose == "fall" else 0) + (6 * sw if pose == "float" else 0)
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC)
    img.paste(layer, (int(cx - S / 2), int(cy - S / 2)), layer)


# ---------- Stoic figures (Stoic Ember) ----------
def stoic_figure(d, x, ground, h, pose="standing", col=(18, 16, 14), rim=(140, 70, 20), t=0.0, facing=1):
    """A robed silhouette with an ember-lit rim. pose: standing | seated | walking | writing | lying"""
    hr = h * 0.085
    if pose == "lying":
        d.ellipse([x - h * 0.45, ground - h * 0.16, x + h * 0.4, ground], fill=col)
        d.ellipse([x + h * 0.38, ground - h * 0.17, x + h * 0.38 + 2 * hr, ground - h * 0.17 + 2 * hr], fill=col)
        return
    seated = pose in ("seated", "writing")
    body_h = h * (0.55 if seated else 0.78)
    top = ground - body_h - 2 * hr
    hx = x + (8 * facing if pose == "writing" else 0)
    d.ellipse([hx - hr - 2, top - 2, hx + hr + 2, top + 2 * hr + 2], fill=rim)
    d.ellipse([hx - hr, top, hx + hr, top + 2 * hr], fill=col)
    sh = top + 2 * hr + h * 0.02
    if seated:
        robe = [(x - h * 0.13, sh), (x + h * 0.13, sh), (x + h * 0.2, ground - h * 0.18), (x + h * 0.32 * facing, ground - h * 0.16),
                (x + h * 0.34 * facing, ground), (x - h * 0.2, ground)]
        d.rectangle([x - h * 0.24, ground - h * 0.2, x + h * 0.24, ground], fill=(30, 26, 22))  # bench
    elif pose == "walking":
        st = math.sin(t * 4) * h * 0.06
        robe = [(x - h * 0.12, sh), (x + h * 0.12, sh), (x + h * 0.2 + st, ground), (x - h * 0.2 - st, ground)]
    else:
        robe = [(x - h * 0.13, sh), (x + h * 0.13, sh), (x + h * 0.19, ground), (x - h * 0.19, ground)]
    rim_robe = [(px + (2 if px > x else -2), py) for px, py in robe]
    d.polygon(rim_robe, fill=rim)
    d.polygon(robe, fill=col)
    # toga drape
    d.line([x - h * 0.12, sh + h * 0.02, x + h * 0.15, sh + h * 0.3], fill=(40, 34, 28), width=max(2, int(h * 0.025)))
    if pose == "writing":
        tx = x + h * 0.32 * facing
        d.rectangle([tx - h * 0.18, ground - h * 0.32, tx + h * 0.18, ground - h * 0.29], fill=(40, 30, 22))
        d.rectangle([tx - h * 0.02, ground - h * 0.29, tx + h * 0.02, ground], fill=(40, 30, 22))
        px = x + h * 0.2 * facing + math.sin(t * 6) * h * 0.02
        d.line([x + h * 0.08 * facing, sh + h * 0.1, px, ground - h * 0.33], fill=col, width=max(2, int(h * 0.035)))
