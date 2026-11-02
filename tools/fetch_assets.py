"""Find and download public-domain images for episodes.

    python tools/fetch_assets.py assets/queries.yaml

For every query it searches open-access collections (The Met, Art Institute of Chicago,
NASA Image Library, Wikimedia Commons), keeps only public-domain / CC0 results, saves
them under assets/<group>/<slug>.jpg (max 2000 px) and records title, author, date,
license and source page in assets/credits.json, which the renderer uses for descriptions.
"""
import io
import json
import os
import re
import sys
import time

import requests
import yaml
from PIL import Image

UA = {"User-Agent": "shorts-studio/1.0 (https://github.com/krystofstudio7/shorts-studio; educational videos)"}
CREDITS = "assets/credits.json"
MAX = 2000


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=40, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def met(q, n):
    r = get("https://collectionapi.metmuseum.org/public/collection/v1/search", params={"q": q, "hasImages": "true"})
    out = []
    for oid in ((r and r.json().get("objectIDs")) or [])[:40]:
        o = get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
        if not o:
            continue
        o = o.json()
        if o.get("isPublicDomain") and o.get("primaryImage"):
            out.append({"url": o["primaryImage"], "title": o.get("title"), "author": o.get("artistDisplayName") or o.get("culture"),
                        "date": o.get("objectDate"), "license": "Public domain (The Met Open Access, CC0)", "page": o.get("objectURL")})
        if len(out) >= n:
            break
    return out


def aic(q, n):
    r = get("https://api.artic.edu/api/v1/artworks/search", params={
        "q": q, "query[term][is_public_domain]": "true", "limit": n * 2,
        "fields": "id,title,artist_display,date_display,image_id,is_public_domain"})
    out = []
    for a in (r.json().get("data", []) if r else []):
        if a.get("is_public_domain") and a.get("image_id"):
            out.append({"url": f"https://www.artic.edu/iiif/2/{a['image_id']}/full/1686,/0/default.jpg", "title": a.get("title"),
                        "author": a.get("artist_display"), "date": a.get("date_display"),
                        "license": "Public domain (Art Institute of Chicago, CC0)", "page": f"https://www.artic.edu/artworks/{a['id']}"})
    return out[:n]


def nasa(q, n):
    r = get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "image"})
    out = []
    for it in (r.json()["collection"]["items"] if r else [])[:n * 3]:
        d = it["data"][0]
        text = (d.get("description", "") + " " + str(d.get("secondary_creator", ""))).lower()
        if "copyright" in text or "©" in text:
            continue  # NASA media is public domain unless a third party holds the copyright
        m = get(it["href"])
        if not m:
            continue
        files = [u for u in m.json() if u.lower().endswith((".jpg", ".jpeg", ".png", ".tif"))]
        pick = next((u for u in files if "~large" in u), None) or next((u for u in files if "~orig" in u and not u.endswith(".tif")), None)
        if pick:
            out.append({"url": pick.replace("http://", "https://"), "title": d.get("title"), "author": d.get("center") or "NASA",
                        "date": (d.get("date_created") or "")[:10], "license": "Public domain (NASA)",
                        "page": f"https://images.nasa.gov/details/{d.get('nasa_id')}"})
        if len(out) >= n:
            break
    return out


def commons(q, n):
    r = get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": n * 4, "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": MAX})
    out = []
    for p in sorted((r.json().get("query", {}).get("pages", {}) if r else {}).values(), key=lambda p: p.get("index", 0)):
        ii = p["imageinfo"][0]
        md = ii.get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        if not re.search(r"public domain|^pd|cc0", lic, re.I):
            continue
        clean = lambda k: re.sub("<[^>]+>", "", md.get(k, {}).get("value", "")).strip()[:200]
        out.append({"url": ii.get("thumburl") or ii["url"], "title": clean("ObjectName") or p["title"][5:], "author": clean("Artist"),
                    "date": clean("DateTimeOriginal"), "license": f"{lic} (Wikimedia Commons)", "page": ii.get("descriptionurl")})
        if len(out) >= n:
            break
    return out


SOURCES = {"met": met, "aic": aic, "nasa": nasa, "commons": commons}


def main(path):
    cfg = yaml.safe_load(open(path))
    credits = json.load(open(CREDITS)) if os.path.exists(CREDITS) else {}
    for group, queries in cfg.items():
        for q in queries:
            name, query, srcs, n = q["name"], q["q"], q.get("sources", ["commons"]), q.get("n", 4)
            for src in srcs:
                for i, item in enumerate(SOURCES[src](query, n)):
                    rel = f"assets/{group}/{slug(name)}-{src}-{i + 1}.jpg"
                    if rel in credits:
                        continue
                    img = get(item["url"])
                    if not img:
                        continue
                    try:
                        im = Image.open(io.BytesIO(img.content)).convert("RGB")
                    except Exception:
                        continue
                    im.thumbnail((MAX, MAX))
                    os.makedirs(os.path.dirname(rel), exist_ok=True)
                    im.save(rel, quality=88)
                    credits[rel] = {**item, "query": query}
                    print("saved", rel, "|", item["title"])
    with open(CREDITS, "w") as f:
        json.dump(credits, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
