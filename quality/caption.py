"""Caption rules for Facebook and Instagram Reels.

Rules adapted from caption.py in https://github.com/Jakeschincariol/instagram-agent-skill
(MIT License, Copyright (c) 2026 Jake Schincariol, see quality/LICENSE-instagram-agent-skill):

* Instagram allows at most 5 hashtags per post or Reel (since December 2025).
* The feed shows roughly the first 125 characters before "... more", so the hook has to be there.
* Tags that name another platform (#learnontiktok, #shorts) are noise on Reels and are dropped.
"""
import re

from .text import clean

HASHTAG_LIMIT = 5
FEED_WINDOW = 125
OTHER_PLATFORM = re.compile(r"tiktok|shorts|youtube|ytshorts|fyp|foryou", re.I)
TAG_LINE = re.compile(r"^(?:#\w+\s*)+$")


def reels_hashtags(tags):
    out = []
    for t in tags:
        if not OTHER_PLATFORM.search(t) and t.lower() not in (o.lower() for o in out):
            out.append(t)
    return out[:HASHTAG_LIMIT]


def reels_description(desc, tags):
    """The description with typography cleaned and its hashtag line cut to what Reels allow."""
    parts = clean(desc).split("\n\n")
    if parts and TAG_LINE.match(parts[-1].strip()):
        parts = parts[:-1]
    keep = reels_hashtags(tags or re.findall(r"#\w+", desc))
    return "\n\n".join(parts + ([" ".join(keep)] if keep else []))


def feed_window(text):
    """What a scrolling viewer sees before tapping "more"."""
    flat = " ".join(text.split())
    return flat[:FEED_WINDOW], len(flat) > FEED_WINDOW
