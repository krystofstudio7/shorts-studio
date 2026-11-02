"""Print the episodes due for publishing: per channel, the first episode (by file name) not yet uploaded.

    python next_episodes.py [--per-channel 1]

An episode can hold `publish_after: 2026-11-05` to wait until that date (UTC).
Uploaded episodes are recorded in published/<channel>/<episode>.json by upload_youtube.py.
"""
import datetime
import glob
import os
import sys

import yaml


def due(per_channel=1, today=None):
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    picked = []
    for chdir in sorted(glob.glob("episodes/*/")):
        channel = os.path.basename(chdir.rstrip("/"))
        n = 0
        for path in sorted(glob.glob(os.path.join(chdir, "*.yaml"))):
            stem = os.path.basename(path)[:-5]
            if os.path.exists(os.path.join("published", channel, stem + ".json")):
                continue
            after = yaml.safe_load(open(path)).get("publish_after")
            if after and datetime.date.fromisoformat(str(after)) > today:
                continue
            picked.append(path)
            n += 1
            if n >= per_channel:
                break
    return picked


if __name__ == "__main__":
    k = int(sys.argv[2]) if sys.argv[1:2] == ["--per-channel"] else 1
    print(" ".join(due(k)))
