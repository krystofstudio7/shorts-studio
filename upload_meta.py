"""Publish rendered videos as Facebook Reels and Instagram Reels, next to YouTube.

    python upload_meta.py [--only facebook|instagram] [--dry-run] out/mind-mites/brain-test-001.mp4 [more.mp4 ...]

Pages, page tokens and Instagram accounts are discovered at run time from the system user token:
/me/accounts lists the Facebook pages assigned to the system user, and each page's
instagram_business_account is the linked Instagram professional account. Pages are matched to
channels by name ("What If Institute" -> what-if-institute, ...).

Every upload is recorded in published/<channel>/<episode>.meta.json (separate from the YouTube
record, so a Meta failure never blocks or repeats YouTube and vice versa). A platform that already
has an id there is skipped.

Needs env var (GitHub Actions secret): META_SYSTEM_USER_TOKEN
Optional: META_GRAPH_VERSION (default v23.0)
"""
import json
import os
import re
import sys
import time

import requests

VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{VERSION}"
CHANNELS = {"whatifinstitute": "what-if-institute", "stoicember": "stoic-ember", "mindmites": "mind-mites"}
CAPTION_LIMIT = 2200  # Instagram's caption limit; Facebook allows more, but one caption keeps them the same


class MetaError(Exception):
    pass


def call(method, url, **kw):
    r = requests.request(method, url, timeout=kw.pop("timeout", 120), **kw)
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:500]}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", data)
        raise MetaError(f"{method} {url.split('?')[0]} -> {r.status_code}: {err.get('message', err) if isinstance(err, dict) else err}")
    return data


def slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def discover(token):
    """{channel: {"page_id", "page_token", "page_name", "ig_id"}} for every page we can match."""
    found, url = {}, f"{GRAPH}/me/accounts"
    params = {"fields": "id,name,access_token,instagram_business_account", "limit": 100, "access_token": token}
    while url:
        data = call("GET", url, params=params)
        for p in data.get("data", []):
            s = slug(p["name"])
            ch = next((c for k, c in CHANNELS.items() if k in s), None)
            if not ch:
                continue
            found[ch] = {"page_id": p["id"], "page_token": p.get("access_token"), "page_name": p["name"],
                         "ig_id": (p.get("instagram_business_account") or {}).get("id")}
        url, params = data.get("paging", {}).get("next"), None
    return found


def caption(meta, limit=CAPTION_LIMIT):
    """Title + description; if too long, drop the image credits first, then the sources (they stay on YouTube)."""
    desc = meta["description"]
    full = f"{meta['title']}\n\n{desc}"
    if len(full) <= limit:
        return full
    parts = desc.split("\n\n")
    keep = [p for p in parts if not p.startswith("Images:")]
    full = f"{meta['title']}\n\n" + "\n\n".join(keep)
    if len(full) <= limit:
        return full
    keep = [p for p in keep if not p.startswith("Sources:")]
    keep.insert(1, "Sources and image credits are in the YouTube description.")
    full = f"{meta['title']}\n\n" + "\n\n".join(keep)
    if len(full) <= limit:
        return full
    # last resort: hook paragraph, the AI disclosure and the hashtags always survive
    tail = "\n\n".join(p for p in keep[1:] if p.startswith("Narration") or p.startswith("#"))
    head = f"{meta['title']}\n\n{keep[0]}"
    return head[:max(0, limit - len(tail) - 2)] + "\n\n" + tail


def push_bytes(upload_url, token, path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        return call("POST", upload_url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                    data=f, timeout=900)


def facebook_reel(page, path, text):
    tok = page["page_token"]
    start = call("POST", f"{GRAPH}/{page['page_id']}/video_reels", data={"upload_phase": "start", "access_token": tok})
    vid = start["video_id"]
    push_bytes(start.get("upload_url") or f"https://rupload.facebook.com/video-upload/{VERSION}/{vid}", tok, path)
    call("POST", f"{GRAPH}/{page['page_id']}/video_reels",
         data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED", "description": text, "access_token": tok})
    return vid


def instagram_reel(page, token, path, text):
    ig = page["ig_id"]
    box = call("POST", f"{GRAPH}/{ig}/media", data={"media_type": "REELS", "upload_type": "resumable", "caption": text,
                                                   "share_to_feed": "true", "access_token": token})
    cid = box["id"]
    push_bytes(box.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{cid}", token, path)
    for _ in range(60):  # Instagram processes the video before it can be published (usually under a minute)
        st = call("GET", f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token})
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise MetaError(f"Instagram could not process {path}: {st.get('status')}")
        time.sleep(10)
    else:
        raise MetaError(f"Instagram still processing {path} after 10 minutes")
    return call("POST", f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token})["id"]


def upload(path, pages, token, only=None, dry=False):
    meta = json.load(open(path[:-4] + ".json"))
    ch = meta["channel"]
    rec_path = os.path.join("published", ch, os.path.basename(path)[:-4] + ".meta.json")
    rec = json.load(open(rec_path)) if os.path.exists(rec_path) else {"title": meta["title"]}
    page = pages.get(ch)
    if not page:
        print(f"::warning::no Facebook page found for {ch}; is it assigned to the system user?")
        return True
    text = caption(meta)
    ok = True
    for platform in ("facebook", "instagram"):
        if only and platform != only:
            continue
        if rec.get(f"{platform}_id"):
            print(f"skip {platform} {path}: already {rec[platform + '_id']}")
            continue
        if platform == "instagram" and not page.get("ig_id"):
            print(f"::warning::page '{page['page_name']}' has no linked Instagram professional account; skipping Instagram")
            continue
        if dry:
            print(f"[dry run] would post {path} to {platform} ({page['page_name']}), caption {len(text)} chars")
            continue
        try:
            rid = facebook_reel(page, path, text) if platform == "facebook" else instagram_reel(page, token, path, text)
            rec[f"{platform}_id"] = rid
            print(f"posted {path} -> {platform} {rid}")
        except (MetaError, requests.RequestException) as e:
            ok = False
            print(f"::error::{platform} upload failed for {path}: {e}")
        finally:
            if any(k.endswith("_id") for k in rec):
                os.makedirs(os.path.dirname(rec_path), exist_ok=True)
                with open(rec_path, "w") as f:
                    json.dump(rec, f, indent=2)
    return ok


def main(argv):
    only, dry = None, False
    while argv and argv[0].startswith("--"):
        if argv[0] == "--only":
            only, argv = argv[1], argv[2:]
        elif argv[0] == "--dry-run":
            dry, argv = True, argv[1:]
        else:
            sys.exit(f"unknown option {argv[0]}")
    token = os.environ.get("META_SYSTEM_USER_TOKEN")
    if not token:
        print("::warning::META_SYSTEM_USER_TOKEN is not set; skipping Facebook and Instagram")
        return 0
    try:
        pages = discover(token)
    except (MetaError, requests.RequestException) as e:
        print(f"::error::could not list Facebook pages: {e}")
        return 1
    print("pages: " + ", ".join(f"{c} = {p['page_name']} (IG {'yes' if p['ig_id'] else 'no'})" for c, p in sorted(pages.items())))
    results = [upload(p, pages, token, only, dry) for p in argv]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
