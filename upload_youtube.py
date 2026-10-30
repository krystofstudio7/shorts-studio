"""Upload rendered videos to YouTube, public by default.

    python upload_youtube.py [--privacy public|private|unlisted] out/mind-mites/brain-test-001.mp4 [more.mp4 ...]

Every upload is recorded in published/<channel>/<episode>.json, which the workflow commits back,
so the same episode is never uploaded twice. Until Google approves the API audit, YouTube locks
API uploads to private whatever we ask for; the script prints the status YouTube actually set.

Needs env vars (GitHub Actions secrets):
    YT_CLIENT_SECRET_JSON      OAuth client JSON (Desktop app)
    YT_REFRESH_TOKEN_WHATIF / YT_REFRESH_TOKEN_STOIC / YT_REFRESH_TOKEN_MITES
"""
import json
import os
import sys

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKENS = {
    "what-if-institute": "YT_REFRESH_TOKEN_WHATIF",
    "stoic-ember": "YT_REFRESH_TOKEN_STOIC",
    "mind-mites": "YT_REFRESH_TOKEN_MITES",
}
EDUCATION = "27"


def client(channel):
    secret = json.loads(os.environ["YT_CLIENT_SECRET_JSON"])
    app = secret.get("installed") or secret.get("web")
    creds = Credentials(None, refresh_token=os.environ[TOKENS[channel]], client_id=app["client_id"],
                        client_secret=app["client_secret"], token_uri=app.get("token_uri", "https://oauth2.googleapis.com/token"))
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(path, privacy):
    meta = json.load(open(path[:-4] + ".json"))
    done_path = os.path.join("published", meta["channel"], os.path.basename(path)[:-4] + ".json")
    if os.path.exists(done_path):
        print(f"skip {path}: already uploaded as {json.load(open(done_path))['youtube_id']}")
        return
    yt = client(meta["channel"])
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:5000],
            "tags": [t.lstrip("#") for t in meta["hashtags"]],
            "categoryId": EDUCATION,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(meta.get("ai_label")),
        },
    }
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    got = resp.get("status", {}).get("privacyStatus", privacy)
    os.makedirs(os.path.dirname(done_path), exist_ok=True)
    with open(done_path, "w") as f:
        json.dump({"youtube_id": resp["id"], "title": meta["title"], "requested": privacy, "privacy": got}, f, indent=2)
    note = "" if got == privacy else f" (asked for {privacy}; YouTube keeps API uploads private until the API audit passes)"
    print(f"uploaded {path} -> https://youtu.be/{resp['id']} [{got}]{note}")


if __name__ == "__main__":
    args = sys.argv[1:]
    privacy = os.environ.get("YT_PRIVACY") or "public"
    if args[:1] == ["--privacy"]:
        privacy, args = args[1], args[2:]
    assert privacy in ("public", "private", "unlisted"), privacy
    for p in args:
        upload(p, privacy)
