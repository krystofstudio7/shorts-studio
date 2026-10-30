"""Stitch finished Shorts into a long-form 16:9 YouTube video with chapter cards.

    python compile.py mind-mites --last 15 --title "15 Brain Tests Most People Fail"
    python compile.py what-if-institute out/what-if-institute/a.mp4 out/what-if-institute/b.mp4 --title "..."
"""
import argparse
import glob
import json
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw

from studio.channels import get_theme
from studio.core import resize, text_block

LW, LH = 1920, 1080
CARD_SECS = 2.5


def run(*cmd):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cmd], check=True)


def card(th, kicker, title, path):
    img = Image.new("RGB", (LW, LH), th.colors["bg"])
    d = ImageDraw.Draw(img)
    d.text((LW / 2, 360), kicker.upper(), font=resize(th.fonts["label"], 44), fill=th.colors["accent2"], anchor="mm")
    text_block(d, title.upper(), resize(th.fonts["display"], 96), LW / 2, 560, th.colors["accent"], maxw=1500)
    d.text((LW / 2, 960), th.brand, font=th.fonts["brand"], fill=th.colors["brand"], anchor="mm")
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel")
    ap.add_argument("videos", nargs="*")
    ap.add_argument("--last", type=int, help="use the N most recent renders of the channel")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", default="out/long")
    a = ap.parse_args()
    th = get_theme(a.channel)
    vids = a.videos or sorted(glob.glob(f"out/{a.channel}/*.mp4"), key=os.path.getmtime)[-(a.last or 10):]
    if len(vids) < 3:
        ap.error("need at least 3 Shorts for chapters")
    os.makedirs(a.out, exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in a.title.lower()).strip("-")[:60]
    tmp = tempfile.mkdtemp()
    parts, chapters, t = [], [], 0.0
    common = ["-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    card(th, th.brand, a.title, f"{tmp}/intro.png")
    run("-loop", "1", "-t", "3", "-i", f"{tmp}/intro.png", "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=48000:cl=stereo",
        *common, "-shortest", f"{tmp}/p000.mp4")
    parts.append(f"{tmp}/p000.mp4")
    t += 3
    for i, v in enumerate(vids, 1):
        meta = json.load(open(v.replace(".mp4", ".json"))) if os.path.exists(v.replace(".mp4", ".json")) else {}
        title = meta.get("title", os.path.basename(v))
        chapters.append((t, title))
        card(th, f"{i} / {len(vids)}", title, f"{tmp}/c{i}.png")
        run("-loop", "1", "-t", str(CARD_SECS), "-i", f"{tmp}/c{i}.png", "-f", "lavfi", "-t", str(CARD_SECS),
            "-i", "anullsrc=r=48000:cl=stereo", *common, "-shortest", f"{tmp}/p{i:03d}a.mp4")
        run("-i", v, "-filter_complex",
            f"[0:v]scale=192:-2,crop=192:108,boxblur=6:2,scale={LW}:{LH},eq=brightness=-0.3[bg];[0:v]scale=-1:{LH}[fg];"
            f"[bg][fg]overlay=(W-w)/2:0", *common, f"{tmp}/p{i:03d}b.mp4")
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                             f"{tmp}/p{i:03d}b.mp4"]).decode())
        parts += [f"{tmp}/p{i:03d}a.mp4", f"{tmp}/p{i:03d}b.mp4"]
        t += CARD_SECS + dur
    with open(f"{tmp}/list.txt", "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    out = os.path.join(a.out, f"{a.channel}_{slug}.mp4")
    run("-f", "concat", "-safe", "0", "-i", f"{tmp}/list.txt", "-c", "copy", "-movflags", "+faststart", out)
    chap = "0:00 Intro\n" + "\n".join(f"{int(s // 60)}:{int(s % 60):02d} {n}" for s, n in chapters)
    with open(out.replace(".mp4", "_chapters.txt"), "w") as f:
        f.write(chap + "\n")
    print(out, f"{t / 60:.1f} min")
    print(chap)


if __name__ == "__main__":
    main()
