"""Upload rendered videos to YouTube as PRIVATE, so Krystof approves each one in YouTube Studio.

    python upload_youtube.py out/mind-mites/brain-test-001.mp4 [more.mp4 ...]

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


def upload(path):
    meta_path = path[:-4] + ".json"
    done_path = path[:-4] + ".uploaded.json"
    if os.path.exists(done_path):
        print(f"skip {path}: already uploaded")
        return
    meta = json.load(open(meta_path))
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
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(meta.get("ai_label")),
        },
    }
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    json.dump({"youtube_id": resp["id"], "privacy": "private"}, open(done_path, "w"))
    print(f"uploaded {path} -> https://youtu.be/{resp['id']} (private)")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        upload(p)
