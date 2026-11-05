"""Performance report: which published Shorts and Reels actually worked, and what they had in common.

    python performance.py                 # writes reports/performance.md and reports/performance.json
    python performance.py --days 28       # analytics window for YouTube shares/retention (default 90)

Metrics follow the ig-audit skill of https://github.com/Jakeschincariol/instagram-agent-skill
(MIT License, see quality/LICENSE-instagram-agent-skill):

* Outlier multiple: views / the channel's own median views on that platform. Raw views mostly
  measure how many followers a channel already has; the multiple says whether a video was a real hit.
* Shares per 1k reach (Instagram) or per 1k views (YouTube): the strongest single signal, a share is
  someone putting their name on the video.
* Retention: average % viewed (YouTube) and average watch time (Instagram).

Videos are ranked by outlier multiple, then the top third and bottom third are compared on hook
score, estimated length and loop (quality/), so the next episodes can copy what worked.

Reads published/<channel>/<episode>.json (YouTube id) and .meta.json (Instagram id).
Env vars (all optional, a missing one just skips that platform):
    YT_CLIENT_SECRET_JSON + YT_REFRESH_TOKEN_{WHATIF,STOIC,MITES}   YouTube Data + Analytics API
    META_SYSTEM_USER_TOKEN   Instagram insights (needs the instagram_manage_insights permission)
"""
import argparse
import datetime
import glob
import json
import os
import statistics
import sys

import yaml

from quality import beats, hooks
from check_episodes import channel_defaults

REPORT_DIR = "reports"
IG_METRICS = ["views", "reach", "shares", "saved", "likes", "comments", "ig_reels_avg_watch_time"]


def published():
    """[{channel, id, youtube_id?, instagram_id?, title}] for every recorded upload."""
    out = {}
    for path in sorted(glob.glob("published/*/*.json")):
        ch = os.path.basename(os.path.dirname(path))
        name = os.path.basename(path)
        ep_id = name[:-len(".meta.json")] if name.endswith(".meta.json") else name[:-5]
        rec = json.load(open(path))
        row = out.setdefault((ch, ep_id), {"channel": ch, "id": ep_id, "title": rec.get("title", ep_id)})
        for k in ("youtube_id", "instagram_id", "facebook_id"):
            if rec.get(k):
                row[k] = rec[k]
    return list(out.values())


def youtube_stats(rows, days):
    if not os.environ.get("YT_CLIENT_SECRET_JSON"):
        print("::warning::YT_CLIENT_SECRET_JSON not set; skipping YouTube")
        return
    from googleapiclient.errors import HttpError
    from upload_youtube import TOKENS, client
    for ch in sorted({r["channel"] for r in rows}):
        vids = [r for r in rows if r["channel"] == ch and r.get("youtube_id")]
        if not vids or not os.environ.get(TOKENS.get(ch, "")):
            continue
        yt = client(ch)
        by_id = {r["youtube_id"]: r for r in vids}
        ids = list(by_id)
        for i in range(0, len(ids), 50):
            res = yt.videos().list(part="statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()
            for v in res.get("items", []):
                s = v["statistics"]
                by_id[v["id"]]["yt"] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                                        "comments": int(s.get("commentCount", 0))}
        try:
            ya = client(ch, "youtubeAnalytics", "v2")
            end = datetime.date.today()
            res = ya.reports().query(ids="channel==MINE", startDate=str(end - datetime.timedelta(days=days)), endDate=str(end),
                                     metrics="views,shares,averageViewPercentage,averageViewDuration,subscribersGained",
                                     dimensions="video", filters="video==" + ",".join(ids[:200]), maxResults=200).execute()
            cols = [c["name"] for c in res.get("columnHeaders", [])]
            for row in res.get("rows", []):
                d = dict(zip(cols, row))
                if d["video"] in by_id:
                    by_id[d["video"]].setdefault("yt", {}).update(
                        shares=int(d["shares"]), view_pct=float(d["averageViewPercentage"]),
                        view_sec=float(d["averageViewDuration"]), subs=int(d["subscribersGained"]))
        except HttpError as e:
            print(f"::warning::YouTube Analytics not available for {ch} (is the YouTube Analytics API enabled?): {e}")


def instagram_stats(rows):
    token = os.environ.get("META_SYSTEM_USER_TOKEN")
    if not token:
        print("::warning::META_SYSTEM_USER_TOKEN not set; skipping Instagram")
        return
    from upload_meta import GRAPH, MetaError, call
    for r in rows:
        if not r.get("instagram_id"):
            continue
        try:
            data = call("GET", f"{GRAPH}/{r['instagram_id']}/insights", params={"metric": ",".join(IG_METRICS), "access_token": token})
        except MetaError as e:
            print(f"::warning::Instagram insights failed for {r['id']}: {e}")
            if "permission" in str(e).lower():
                print("::warning::the system user token needs instagram_manage_insights; skipping the rest of Instagram")
                return
            continue
        r["ig"] = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) for m in data.get("data", [])}


def enrich(rows):
    """Add the episode's hook score, estimated length and loop, so winners and losers can be compared."""
    for r in rows:
        path = os.path.join("episodes", r["channel"], r["id"] + ".yaml")
        if not os.path.exists(path):
            continue
        ep = yaml.safe_load(open(path, encoding="utf-8"))
        speed = ep.get("speed", channel_defaults(r["channel"])[0])
        b = beats.analyse(ep, speed)
        r["episode"] = {"hook": ep["lines"][0]["text"], "hook_score": round(hooks.run(ep["lines"][0]["text"])[1]),
                        "screen_hook": ep.get("hook", ""), "est_seconds": round(b["total"]), "loop": bool(b["loop"])}


def rank(rows, platform):
    """Rows with that platform's views, plus outlier multiple vs the channel median, best first."""
    out = []
    for ch in sorted({r["channel"] for r in rows}):
        mine = [r for r in rows if r["channel"] == ch and r.get(platform, {}).get("views") is not None]
        if not mine:
            continue
        med = statistics.median(r[platform]["views"] for r in mine) or 1
        for r in mine:
            p = r[platform]
            base = p.get("reach") or p["views"]
            p["outlier"] = round(p["views"] / med, 2)
            p["shares_per_1k"] = round(1000 * p.get("shares", 0) / base, 1) if base and "shares" in p else None
            out.append(r)
    return sorted(out, key=lambda r: (-r[platform]["outlier"], -(r[platform]["shares_per_1k"] or 0)))


def compare(ranked, platform):
    """What the top third have that the bottom third do not."""
    with_ep = [r for r in ranked if r.get("episode")]
    if len(with_ep) < 6:
        return ["Not enough published videos yet to compare top and bottom (need 6+)."]
    k = len(with_ep) // 3
    top, bottom = with_ep[:k], with_ep[-k:]

    def avg(group, key):
        return statistics.mean(r["episode"][key] for r in group)

    lines = [f"Top {k} vs bottom {k} by outlier multiple:",
             f"- hook score: {avg(top, 'hook_score'):.0f} vs {avg(bottom, 'hook_score'):.0f}",
             f"- estimated length: {avg(top, 'est_seconds'):.0f}s vs {avg(bottom, 'est_seconds'):.0f}s",
             f"- ending loops back to the hook: {sum(r['episode']['loop'] for r in top)}/{k} vs {sum(r['episode']['loop'] for r in bottom)}/{k}"]
    if platform == "yt" and all("view_pct" in r["yt"] for r in top + bottom):
        lines.append(f"- average % viewed: {statistics.mean(r['yt']['view_pct'] for r in top):.0f}% vs "
                     f"{statistics.mean(r['yt']['view_pct'] for r in bottom):.0f}%")
    return lines


def markdown(rows):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = [f"# Performance report", "", f"Generated {now}. Ranked by outlier multiple (views / the channel's median on that platform), "
          "then shares per 1k reach. A multiple of 2.0 means twice a normal day for that channel.", ""]
    for platform, label in (("yt", "YouTube Shorts"), ("ig", "Instagram Reels")):
        ranked = rank(rows, platform)
        md += [f"## {label}", ""]
        if not ranked:
            md += ["No data (missing credentials or permission, see the workflow log).", ""]
            continue
        if platform == "yt":
            md += ["| # | channel | episode | views | x median | shares/1k | % viewed | likes | comments | hook score |",
                   "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        else:
            md += ["| # | channel | episode | views | reach | x median | shares/1k reach | saves | avg watch s | hook score |",
                   "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for i, r in enumerate(ranked, 1):
            p, e = r[platform], r.get("episode", {})
            spk = "" if p.get("shares_per_1k") is None else p["shares_per_1k"]
            if platform == "yt":
                pct = f"{p['view_pct']:.0f}%" if "view_pct" in p else ""
                md.append(f"| {i} | {r['channel']} | {r['id']} | {p['views']:,} | {p['outlier']} | {spk} | {pct} | {p['likes']} "
                          f"| {p['comments']} | {e.get('hook_score', '')} |")
            else:
                watch = round(p.get("ig_reels_avg_watch_time", 0) / 1000, 1) if p.get("ig_reels_avg_watch_time") else ""
                md.append(f"| {i} | {r['channel']} | {r['id']} | {p['views']:,} | {p.get('reach', '')} | {p['outlier']} | {spk} "
                          f"| {p.get('saved', '')} | {watch} | {e.get('hook_score', '')} |")
        md += [""] + compare(ranked, platform) + [""]
    md += ["Use: write more episodes like the top rows (their hooks are in performance.json), and treat a pattern as real only "
           "when it shows up several times. Hook scores are text heuristics; these numbers are the real judge."]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    rows = published()
    youtube_stats(rows, a.days)
    instagram_stats(rows)
    enrich(rows)
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "performance.json"), "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    md = markdown(rows)
    with open(os.path.join(REPORT_DIR, "performance.md"), "w") as f:
        f.write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
