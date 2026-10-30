"""Turns an episode file into a finished Short: voice, scenes, overlays, captions, metadata."""
import copy
import json
import math
import os

import numpy as np
import yaml
from PIL import Image, ImageDraw

from .core import (W, H, FPS, build_voice, caption_chunks, ease, ease_out, encode, fade, mix, resize, srt,
                   text_block, wrap)


def load_episode(path):
    with open(path) as f:
        ep = yaml.safe_load(f)
    ep["_path"] = path
    return ep


def line_at(tl, t):
    idx = 0
    for i, span in enumerate(tl):
        if t >= span["start"]:
            idx = i
    return idx


def plan_scenes(lines, tl):
    """For each line: the scene it shows, its start time and the merged params at that line."""
    plan, cur, start = [], None, 0.0
    for i, ln in enumerate(lines):
        if "scene" in ln or cur is None:
            cur = copy.deepcopy(ln.get("scene", {}))
            start = 0.0 if i == 0 else tl[i]["start"]
            cur["_line"] = i
        else:
            cur = copy.deepcopy(cur)
        for k, v in ln.get("update", {}).items():
            cur[k] = v
        if "countdown" in ln.get("scene", {}) or "countdown" in ln.get("update", {}):
            cur["_countdown_at"] = tl[i]["end"]
        plan.append({"params": cur, "start": start})
    return plan


# ---------- overlays shared by every channel ----------
def draw_overlays(img, th, p, t, st, ctx):
    d = ImageDraw.Draw(img)
    C, F = th.colors, th.fonts
    if p.get("tag"):
        a = ease_out(st / 0.35)
        f = F["label"]
        tw = d.textlength(p["tag"], font=f)
        y0 = 290 - (1 - a) * 30
        d.rounded_rectangle([(W - tw) / 2 - 28, y0, (W + tw) / 2 + 28, y0 + 64], 32, fill=C["pill_bg"])
        d.text((W / 2, y0 + 32), p["tag"], font=f, fill=C["pill_fg"], anchor="mm")
    if p.get("big"):
        a = ease_out(st / 0.3)
        f = resize(F["display"], p.get("big_size", F["display"].size) * (0.85 + 0.15 * a))
        text_block(d, p["big"], f, W / 2, p.get("big_y", 640), p.get("big_color") and tuple(p["big_color"]) or C["accent"],
                   maxw=920, stroke_width=p.get("big_stroke", 0), stroke_fill=C["bg"])
    if p.get("stat"):
        s = p["stat"]
        k = ease(st / s.get("dur", 1.2))
        v = s.get("from", 0) + (s["to"] - s.get("from", 0)) * k
        dec = s.get("decimals", 0)
        num = f"{v:,.{dec}f}"
        y = p.get("stat_y", 760)
        d.text((W / 2, y), f"{s.get('prefix', '')}{num}{s.get('unit', '')}", font=F["stat"], fill=C["accent"], anchor="mm",
               stroke_width=C.get("stat_stroke_w", 0), stroke_fill=C.get("stat_stroke", C["bg"]))
        if s.get("label"):
            text_block(d, s["label"], F["body"], W / 2, y + F["stat"].size * 0.75, C["text"], maxw=880,
                       stroke_width=C.get("stat_stroke_w", 0) // 2, stroke_fill=C.get("stat_stroke", C["bg"]))
    if p.get("rows"):
        draw_rows(d, th, p, t, ctx)
    if p.get("countdown") and "_countdown_at" in p:
        e = t - p["_countdown_at"]
        n = p["countdown"] - int(e)
        if 0 <= e and n >= 1:
            fr, r, cy = e % 1, 150, p.get("countdown_y", 1520)
            d.ellipse([W / 2 - r, cy - r, W / 2 + r, cy + r], fill=C["accent2"])
            d.arc([W / 2 - r, cy - r, W / 2 + r, cy + r], -90, -90 + 360 * (1 - fr), fill=C["card_fg"], width=16)
            d.text((W / 2, cy + 8), str(n), font=resize(F["stat"], 190), fill=C["card_fg"], anchor="mm")
    if p.get("quote"):
        q = p["quote"]
        a = ease(st / 0.7)
        h = text_block(d, q["text"], F["quote"], W / 2, p.get("quote_y", 860), fade(C["accent"], a), maxw=880, gap=1.2)
        if q.get("source"):
            d.text((W / 2, p.get("quote_y", 860) + h / 2 + 60), q["source"].upper(), font=F["small"],
                   fill=fade(C["muted"], a), anchor="mm")
    if p.get("share"):
        a = ease_out(st / 0.4)
        f = F["label"]
        lines = wrap(d, p["share"].upper(), f, 780)
        hh = 50 * len(lines) + 40
        y0 = p.get("share_y", 1500) + (1 - a) * 60
        d.rounded_rectangle([110, y0, W - 110, y0 + hh], 28, fill=C["pill_bg"])
        for i, l in enumerate(lines):
            d.text((W / 2, y0 + 45 + i * 50), l, font=f, fill=C["pill_fg"], anchor="mm")
    hook = ctx["ep"].get("hook")
    if hook and t < ctx["ep"].get("hook_secs", 2.4):
        a = 1 - ease((t - ctx["ep"].get("hook_secs", 2.4) + 0.3) / 0.3)
        text_block(d, hook.upper(), F["hook"], W / 2, 430, fade(C["hook"], a), maxw=940, stroke_width=8,
                   stroke_fill=fade(C["bg"], a))


def mark(d, kind, x, y, s, col):
    if kind == "ok":
        d.line([x - 28 * s, y, x - 8 * s, y + 24 * s, x + 30 * s, y - 26 * s], fill=col, width=int(12 * s), joint="curve")
    elif kind == "no":
        d.line([x - 26 * s, y - 26 * s, x + 26 * s, y + 26 * s], fill=col, width=int(12 * s))
        d.line([x - 26 * s, y + 26 * s, x + 26 * s, y - 26 * s], fill=col, width=int(12 * s))


def draw_rows(d, th, p, t, ctx):
    C, F = th.colors, th.fonts
    rows = p["rows"][: p.get("rows_shown", len(p["rows"]))]
    y = p.get("rows_y", 760)
    gap = p.get("rows_gap", 150)
    for i, r in enumerate(rows):
        yy = y + i * gap
        fill = C["accent2"] if r.get("mark") == "ok" else C["card_bg"]
        d.rounded_rectangle([90, yy - 62, W - 90, yy + 62], 30, fill=fill)
        d.text((140, yy), r.get("l", ""), font=F["row"], fill=C["card_fg"], anchor="lm")
        right = r.get("r", "")
        if right:
            d.text((W - (210 if r.get("mark") else 140), yy), right, font=F["row"],
                   fill=C["no"] if r.get("hl") else C["card_fg"], anchor="rm")
        if r.get("mark"):
            mark(d, r["mark"], W - 150, yy, 1.0, C["card_fg"] if r["mark"] == "ok" else C["no"])


def draw_caption(img, th, cap, t):
    d = ImageDraw.Draw(img)
    cs = th.caption
    f = th.fonts["caption"]
    pop = 1 + 0.08 * (1 - ease_out((t - cap["start"]) / 0.12))
    f = resize(f, f.size * pop)
    s = cap["text"].upper() if cs.get("upper", True) else cap["text"]
    lines = wrap(d, s, f, 900)
    lh = f.size * 1.08
    y0 = cs["y"] - lh * (len(lines) - 1) / 2
    for i, l in enumerate(lines):
        d.text((W / 2, y0 + i * lh), l, font=f, fill=cs["fill"], anchor="mm", stroke_width=cs["sw"], stroke_fill=cs["stroke"])


# ---------- render ----------
def render_episode(path, out_dir, preview=None):
    from .channels import get_theme
    ep = load_episode(path)
    th = get_theme(ep["channel"])
    lines = ep["lines"]
    voice, tl, dur = build_voice(lines, th.voice, ep.get("speed", th.speed))
    dur += ep.get("tail", 0.4)
    caps = caption_chunks(lines, tl)
    plan = plan_scenes(lines, tl)
    audio = mix(voice, th.music(dur))
    ctx = {"ep": ep, "tl": tl, "dur": dur, "theme": th}

    def frame(t):
        li = line_at(tl, t)
        seg = plan[li]
        p = seg["params"]
        st = t - seg["start"]
        ctx["line"], ctx["lt"] = li, t - tl[li]["start"]
        img = th.background(p, t, st, ctx)
        draw_overlays(img, th, p, t, st, ctx)
        img = th.post(img, t)
        d = ImageDraw.Draw(img)
        d.text((W / 2, 175), th.brand, font=th.fonts["brand"], fill=th.colors["brand"], anchor="mm")
        for c in caps:
            if c["start"] <= t < c["end"] and not p.get("nocaptions"):
                draw_caption(img, th, c, t)
                break
        return img

    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0])
    if preview is not None:
        times = preview or [tl[i]["start"] + 0.8 for i in range(len(tl))]
        ims = [frame(x).resize((270, 480)) for x in times]
        cols = min(len(ims), 6)
        rows_n = math.ceil(len(ims) / cols)
        sheet = Image.new("RGB", (270 * cols, 480 * rows_n), (255, 255, 255))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * 270, (i // cols) * 480))
        sheet.save(base + "_preview.png")
        return base + "_preview.png", dur
    encode(base + ".mp4", dur, frame, audio, crf=th.crf)
    with open(base + ".srt", "w") as f:
        f.write(srt(caps))
    with open(base + ".json", "w") as f:
        json.dump(metadata(ep, th, dur), f, indent=2, ensure_ascii=False)
    return base + ".mp4", dur


def metadata(ep, th, dur):
    tags = ep.get("hashtags", th.hashtags)
    desc = ep.get("description", "").strip()
    if ep.get("sources"):
        desc += "\n\nSources:\n" + "\n".join(f"- {s}" for s in ep["sources"])
    desc += "\n\n" + " ".join(tags)
    return {
        "channel": ep["channel"], "id": ep["id"], "title": ep["title"], "series": ep.get("series"),
        "number": ep.get("number"), "description": desc.strip(), "hashtags": tags,
        "duration": round(dur, 2), "ai_label": ep.get("ai_label", False),
    }
