"""Diagnose Instagram Reels upload failures without publishing anything.

Creates Reels containers (never calls media_publish) with different sources and reports how
Instagram processes each one. Prints no tokens.
"""
import os
import subprocess
import time

import requests

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
    show(ch, get(ig, fields="username,account_type,media_count")[1])
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


ch = "mind-mites" if "mind-mites" in pages else sorted(pages)[0]
ig = pages[ch]["ig_id"]
tests = []
# 1) resumable upload of the tiny clip
try:
    box = um.call("POST", f"{G}/{ig}/media", data={"media_type": "REELS", "upload_type": "resumable",
                                                   "access_token": tok})
    um.push_bytes(box.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{um.VERSION}/{box['id']}", tok, clip)
    tests.append(("resumable tiny clip", box["id"]))
except Exception as e:
    show("resumable tiny clip", f"failed before processing: {e}")
# 2) video_url pointing at a public test clip on this repo's branch
url = "https://raw.githubusercontent.com/krystofstudio7/shorts-studio/ig-debug/tools/ig-sample.mp4"
try:
    cid = um.call("POST", f"{G}/{ig}/media", data={"media_type": "REELS", "video_url": url, "access_token": tok})["id"]
    tests.append(("video_url tiny clip", cid))
except Exception as e:
    show("video_url tiny clip", f"failed before processing: {e}")
# 3) an image container (no video at all)
try:
    cid = um.call("POST", f"{G}/{ig}/media", data={
        "image_url": "https://raw.githubusercontent.com/krystofstudio7/shorts-studio/ig-debug/tools/ig-sample.jpg",
        "access_token": tok})["id"]
    tests.append(("image", cid))
except Exception as e:
    show("image", f"failed before processing: {e}")
for label, cid in tests:
    show(f"{ch} {label}", wait(cid))
print("Nothing was published: containers expire unused after 24 h.")
