"""Diagnose Instagram Reels upload failures without publishing anything.

Creates Reels containers (never calls media_publish) with different sources and reports how
Instagram processes each one. Prints no tokens.
"""
import glob
import os
import subprocess
import time

import requests

url = "https://raw.githubusercontent.com/krystofstudio7/shorts-studio/ig-debug/tools/ig-sample.mp4"

import upload_meta as um

tok = os.environ["META_SYSTEM_USER_TOKEN"]
G = um.GRAPH


def get(path, **p):
    r = requests.get(f"{G}/{path}", params={**p, "access_token": tok}, timeout=60)
    return r.status_code, r.json()


def show(label, x):
    print(f"--- {label}: {x}")


code, dbg = get("debug_token", input_token=tok)
d = dbg.get("data", {})
show("token", {"valid": d.get("is_valid"), "type": d.get("type"), "expires_at": d.get("expires_at"),
               "scopes": d.get("scopes"), "error": d.get("error")})
pages = um.discover(tok)
for ch, p in sorted(pages.items()):
    ig = p["ig_id"]
    show(ch, get(ig, fields="username,media_count")[1])
    show(ch + " publishing limit", get(f"{ig}/content_publishing_limit", fields="config,quota_usage")[1])

# a tiny clean test clip: 5 s, 720x1280, H.264 high, AAC stereo 48k, faststart
clip = "ig-test.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=30:d=5",
                "-f", "lavfi", "-i", "sine=f=440:d=5:sample_rate=48000", "-c:v", "libx264", "-profile:v", "high",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-shortest",
                "-movflags", "+faststart", clip], check=True)


def wait(cid):
    for _ in range(30):
        st = get(cid, fields="status_code,status")[1]
        if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
            return st
        time.sleep(10)
    return st


# round 3: our real renders, in variants, uploaded resumable without caption
src = os.environ.get("VIDEO_DIR", "art")
vids = sorted(glob.glob(f"{src}/**/*.mp4", recursive=True)) if os.path.isdir(src) else []
print("--- videos found:", vids)


def ff(inp, out, *args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", inp, *args, out], check=True)
    return out


def probe(f):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_name,profile,level,width,height,r_frame_rate,avg_frame_rate,bit_rate,sample_rate,channels,pix_fmt,has_b_frames,nb_frames,duration:format=duration,bit_rate,size",
                           "-of", "compact", f], capture_output=True, text=True).stdout.replace("\n", " | ")


def up(ig, f):
    try:
        box = um.call("POST", f"{G}/{ig}/media", data={"media_type": "REELS", "upload_type": "resumable", "access_token": tok})
        um.push_bytes(box.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{um.VERSION}/{box['id']}", tok, f)
        return box["id"]
    except Exception as e:
        return f"failed before processing: {e}"


import glob
tests = []
ig = pages["mind-mites"]["ig_id"]
for v in vids[:1]:
    cp = um.instagram_copy(v)
    show("original", probe(v)); show("ig copy", probe(cp))
    variants = {
        "original": v,
        "ig copy": cp,
        "ig copy first 15 s": ff(cp, "v15.mp4", "-t", "15", "-c", "copy"),
        "ig copy 720x1280": ff(cp, "v720.mp4", "-vf", "scale=720:1280", "-c:v", "libx264", "-crf", "23", "-c:a", "copy"),
        "ig copy no audio": ff(cp, "vna.mp4", "-an", "-c:v", "copy"),
        "audio re-encoded 44.1k": ff(cp, "va44.mp4", "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-b:a", "128k"),
        "main profile, closed GOP": ff(v, "vmain.mp4", "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
                                       "-pix_fmt", "yuv420p", "-r", "30", "-g", "60", "-bf", "0", "-maxrate", "5M",
                                       "-bufsize", "10M", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"),
    }
    for k, f in variants.items():
        tests.append((k, up(ig, f)))
for label, cid in tests:
    show(label, wait(cid) if cid.isdigit() else cid)
print("Nothing was published: containers expire unused after 24 h.")
raise SystemExit(0)
from studio.engine import load_episode, metadata
from studio.channels import get_theme


def fb_source(page, vid):
    return get(vid, fields="source")[1].get("source")


def mk(ig, **data):
    try:
        return um.call("POST", f"{G}/{ig}/media", data={"media_type": "REELS", **data, "access_token": tok})["id"]
    except Exception as e:
        return f"failed before processing: {e}"


import glob, json
tests = []
for ch, ep_path in [("mind-mites", "episodes/mind-mites/brain-test-010.yaml"),
                    ("what-if-institute", "episodes/what-if-institute/what-if-010-leonid-storm.yaml")]:
    page = pages[ch]; ig = page["ig_id"]
    ep = load_episode(ep_path)
    text = um.caption(metadata(ep, get_theme(ep["channel"]), 45))
    stem = os.path.basename(ep_path)[:-5]
    rec = json.load(open(f"published/{ch}/{stem}.meta.json"))
    src = fb_source(page, rec["facebook_id"])
    show(f"{ch} caption", {"chars": len(text), "hashtags": text.count("#"), "lines": text.count("\n")})
    tests += [
        (f"{ch} tiny clip + our caption", mk(ig, video_url=url, caption=text, share_to_feed="true")),
        (f"{ch} tiny clip + share_to_feed only", mk(ig, video_url=url, share_to_feed="true")),
        (f"{ch} our video (FB copy), no caption", mk(ig, video_url=src)),
    ]
for label, cid in tests:
    show(label, wait(cid) if cid.isdigit() else cid)
print("Nothing was published: containers expire unused after 24 h.")
