"""Render episodes to finished Shorts.

    python render.py episodes/mind-mites/brain-test-001.yaml
    python render.py --all                # every episode without an up-to-date render
    python render.py --preview FILE       # contact sheet PNG instead of a video
"""
import argparse
import glob
import os
import sys
import traceback

from studio.engine import render_episode

OUT = "out"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*")
    ap.add_argument("--all", action="store_true", help="render every episode that has no newer video yet")
    ap.add_argument("--preview", action="store_true", help="write a contact sheet instead of a video")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    eps = a.episodes or (sorted(glob.glob("episodes/*/*.yaml")) if a.all else [])
    if not eps:
        ap.error("give episode files or --all")
    failed = []
    for ep in eps:
        channel = os.path.basename(os.path.dirname(ep))
        out_dir = os.path.join(a.out, channel)
        target = os.path.join(out_dir, os.path.splitext(os.path.basename(ep))[0] + ".mp4")
        if a.all and not a.preview and os.path.exists(target) and os.path.getmtime(target) > os.path.getmtime(ep):
            continue
        try:
            path, dur = render_episode(ep, out_dir, preview=[] if a.preview else None)
        except Exception:
            # one broken episode must not stop the others from rendering and publishing
            traceback.print_exc()
            print(f"::error::render failed: {ep}", flush=True)
            failed.append(ep)
            continue
        print(f"{path}  {dur:.1f}s", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
