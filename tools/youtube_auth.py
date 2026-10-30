"""One-time YouTube login for Shorts Studio.

Run once per channel on your own computer:
    ~/yt-auth/bin/python youtube_auth.py ~/Downloads/client_secret_XXXX.json

A browser window opens. Pick the channel (brand account) you want to connect,
allow access, and the script prints a refresh token. Paste that token into the
matching GitHub secret. Never paste it into a chat.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

if len(sys.argv) != 2:
    sys.exit("Usage: python youtube_auth.py path/to/client_secret.json")

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], scopes=SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

if not creds.refresh_token:
    sys.exit("No refresh token returned. Run the script again.")

print("\nRefresh token (copy everything on the next line):\n")
print(creds.refresh_token)
print("\nStore it as a GitHub secret, then close this window.")
