"""Turns an episode file into a finished Short: voice, scenes, overlays, captions, metadata."""
import copy
import json
import math
import os

import numpy as np
import yaml
from PIL import Image, ImageDraw

from . import sfx
from .core import (W, H, FPS, build_voice, caption_chunks, clamp01, ease, ease_out, encode, fade, mix, resize, srt,
                   text_block, wrap)

TRANSITION = 0.28


def back_out(t, k=1.7):
    """Ease with a small overshoot, for things that pop in."""
    t = clamp01(t) - 1
    return 1 + t * t * ((k + 1) * t + k)


def shade(col, k=0.45):
    return tuple(int(c * k) for c in col)


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
        born = cur.setdefault("_row_born", {})
        for j, r in enumerate(cur.get("rows", [])[: cur.get("rows_shown", len(cur.get("rows", [])))]):
            born.setdefault((j, r.get("l"), r.get("mark")), start if "scene" in ln else tl[i]["start"])
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
        a = back_out(st / 0.35)
        f = resize(F["display"], p.get("big_size", F["display"].size) * (0.7 + 0.3 * a))
        y = p.get("big_y", 640)
        text_block(d, p["big"], f, W / 2 + 6, y + 10, C.get("shadow", shade(C["bg"], 0.35)), maxw=920)
        text_block(d, p["big"], f, W / 2, y, p.get("big_color") and tuple(p["big_color"]) or C["accent"],
                   maxw=920, stroke_width=p.get("big_stroke", 0), stroke_fill=C["bg"])
    if p.get("stat"):
        s = p["stat"]
        k = ease(st / s.get("dur", 1.2))
        v = s.get("from", 0) + (s["to"] - s.get("from", 0)) * k
        dec = s.get("decimals", 0)
        num = f"{v:,.{dec}f}"
        y = p.get("stat_y", 760)
        done = st - s.get("dur", 1.2)
        punch = 1 + (0.12 * (1 - ease_out(done / 0.25)) if done > 0 else 0)
        sf = resize(F["stat"], F["stat"].size * back_out(st / 0.3) * punch)
        txt = f"{s.get('prefix', '')}{num}{s.get('unit', '')}"
        d.text((W / 2 + 8, y + 12), txt, font=sf, fill=C.get("shadow", shade(C["bg"], 0.35)), anchor="mm")
        d.text((W / 2, y), txt, font=sf, fill=C["accent"], anchor="mm",
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
    born = p.get("_row_born", {})
    for i, r in enumerate(rows):
        k = back_out((t - born.get((i, r.get("l"), r.get("mark")), t - 1)) / 0.3)
        dx = (1 - k) * 160
        yy = y + i * gap
        fill = C["accent2"] if r.get("mark") == "ok" else C["card_bg"]
        d.rounded_rectangle([90 + dx + 8, yy - 62 + 12, W - 90 + dx + 8, yy + 62 + 12], 30, fill=C.get("shadow", shade(C["bg"])))
        d.rounded_rectangle([90 + dx, yy - 62, W - 90 + dx, yy + 62], 30, fill=fill)
        d.text((140 + dx, yy), r.get("l", ""), font=F["row"], fill=C["card_fg"], anchor="lm")
        right = r.get("r", "")
        if right:
            d.text((W - (210 if r.get("mark") else 140) + dx, yy), right, font=F["row"],
                   fill=C["no"] if r.get("hl") else C["card_fg"], anchor="rm")
        if r.get("mark"):
            mark(d, r["mark"], W - 150 + dx, yy, 0.6 + 0.4 * k, C["card_fg"] if r["mark"] == "ok" else C["no"])


def draw_caption(img, th, cap, t):
    """Up to three words, the one being spoken highlighted and slightly larger."""
    d = ImageDraw.Draw(img)
    cs = th.caption
    base = th.fonts["caption"]
    pop = 1 + 0.08 * (1 - ease_out((t - cap["start"]) / 0.12))
    f = resize(base, base.size * pop)
    fh = resize(base, base.size * pop * 1.1)
    words = [(w.upper() if cs.get("upper", True) else w, a, b) for w, a, b in cap["words"]]
    space = d.textlength(" ", font=f)
    lines, cur, cw = [], [], 0
    for w in words:
        wl = d.textlength(w[0], font=fh)
        if cur and cw + space + wl > 940:
            lines.append(cur)
            cur, cw = [], 0
        cur.append(w)
        cw += wl + (space if cw else 0)
    lines.append(cur)
    lh = f.size * 1.12
    y0 = cs["y"] - lh * (len(lines) - 1) / 2
    for li, line in enumerate(lines):
        widths = [d.textlength(w, font=fh if a <= t < b else f) for w, a, b in line]
        x = W / 2 - (sum(widths) + space * (len(line) - 1)) / 2
        for (w, a, b), wd in zip(line, widths):
            on = a <= t < b
            d.text((x, y0 + li * lh), w, font=fh if on else f, fill=cs.get("hl", cs["fill"]) if on else cs["fill"],
                   anchor="lm", stroke_width=cs["sw"], stroke_fill=cs["stroke"])
            x += wd + space


def camera(img, p, st, t):
    """Slow push-in on every scene, plus an optional short shake on impact."""
    z = 1 + p.get("push", 0.06) * ease(st / 8)
    ox = oy = 0.0
    if p.get("shake") and st < 0.6:
        amp = 22 * (1 - st / 0.6)
        ox, oy = amp * math.sin(t * 90), amp * math.cos(t * 77)
    if z == 1 and not ox:
        return img
    w, h = W / z, H / z
    x0 = (W - w) / 2 + ox
    y0 = (H - h) / 2 + oy + p.get("pan_y", 0) * ease(st / 8)
    return img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


def sound_events(ep, plan, tl):
    ev = [(0.0, "boom")] if ep.get("hook") else []
    prev = None
    for i, seg in enumerate(plan):
        p = seg["params"]
        new_scene = prev is None or seg["start"] != prev["start"]
        if new_scene and i > 0:
            ev.append((seg["start"] - 0.15, "whoosh"))
        if new_scene and any(k in p for k in ("big", "stat", "quote", "share")):
            ev.append((seg["start"] + 0.05, "pop"))
        if "stat" in p and new_scene:
            ev.append((seg["start"] + p["stat"].get("dur", 1.2), "ding" if p.get("stat_ding") else "pop"))
        if "rows" in p:
            shown = p["rows"][: p.get("rows_shown", len(p["rows"]))]
            before = [] if new_scene else prev["params"]["rows"][: prev["params"].get("rows_shown", len(prev["params"].get("rows", [])))]
            for r in shown[len(before):] if len(shown) > len(before) else []:
                ev.append((tl[i]["start"] + 0.05, {"ok": "ding", "no": "buzz"}.get(r.get("mark"), "pop")))
            if new_scene:
                pass
            elif shown != before and len(shown) == len(before):
                ev.append((tl[i]["start"] + 0.05, "ding"))
        if "_countdown_at" in p and (prev is None or "_countdown_at" not in prev["params"]):
            for k in range(p.get("countdown", 3)):
                ev.append((p["_countdown_at"] + k, "tick"))
        prev = seg
    return ev


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
    audio = mix(voice, th.music(dur), sfx.track(sound_events(ep, plan, tl), dur, getattr(th, "sfx_vol", 0.45)))
    ctx = {"ep": ep, "tl": tl, "dur": dur, "theme": th}
    starts = sorted({seg["start"] for seg in plan})

    def scene_bg(seg, t):
        st = t - seg["start"]
        return camera(th.background(seg["params"], t, st, ctx), seg["params"], st, t)

    def frame(t):
        li = line_at(tl, t)
        seg = plan[li]
        p = seg["params"]
        st = t - seg["start"]
        ctx["line"], ctx["lt"] = li, t - tl[li]["start"]
        img = scene_bg(seg, t)
        if 0 < seg["start"] and st < TRANSITION:
            prev = next(s2 for s2 in reversed(plan[:li]) if s2["start"] < seg["start"])
            k = ease(st / TRANSITION)
            old = scene_bg(prev, t)
            canvas = Image.new("RGB", (W, H))
            canvas.paste(old, (0, int(-H * 0.35 * k)))
            img = Image.blend(canvas, img.transform((W, H), Image.AFFINE, (1, 0, 0, 0, 1, -int(H * 0.35 * (1 - k)))), k)
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
    desc += "\n\nNarration voice and visuals are AI-assisted (text-to-speech and code-drawn animation)."
    desc += "\n\n" + " ".join(tags)
    return {
        "channel": ep["channel"], "id": ep["id"], "title": ep["title"], "series": ep.get("series"),
        "number": ep.get("number"), "description": desc.strip(), "hashtags": tags,
        "duration": round(dur, 2), "ai_label": ep.get("ai_label", False),
    }
