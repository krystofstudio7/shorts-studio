"""Daily report: what broke and needs fixing, how today's videos look, and how everything performed.

    python daily_report.py                  # writes reports/daily/<date>/report.md (+ title.txt, stats.json, frames)
    python daily_report.py --videos out     # where today's rendered .mp4 files are (default out/)

Runs after the daily publish (workflow "Daily report", posted as a GitHub issue). Sections, in order:

1. Needs fixing: failed GitHub Actions runs in the last 24 h (publish, renders, quality checks),
   a channel that published nothing today, uploads missing on YouTube/Facebook/Instagram or not public,
   broken YouTube/Meta tokens, quality-check errors, an empty episode queue.
2. Heads-up: smaller things (queue running low, missing permissions, black/frozen/silent stretches
   in a video, a video far outside the 30-45 s target).
3. Today's videos: four frames of each video (hook, 30 %, 60 %, ending) with its hook, length
   and the quality checker's top notes, so the look can keep improving.
4. Performance: views gained in the last 24 h per channel and platform, subscribers, top movers,
   and how yesterday's uploads did after their first day (x channel median).

Day-over-day numbers come from the previous day's reports/daily/<date>/stats.json.
Env vars: the same as performance.py, plus GITHUB_TOKEN + GITHUB_REPOSITORY for the Actions runs.
"""
import argparse
import datetime
import glob
import json
import os
import re
import statistics
import subprocess
import sys

import requests

import performance
from check_episodes import check
from next_episodes import due

CHANNELS = {"what-if-institute": "What If Institute", "stoic-ember": "Stoic Ember", "mind-mites": "Mind Mites"}
PLATFORMS = (("yt", "YouTube"), ("fb", "Facebook"), ("ig", "Instagram"))
META_PERMS = ["pages_manage_posts", "pages_read_engagement", "instagram_basic", "instagram_content_publish",
              "instagram_manage_insights", "read_insights"]
OWN_WORKFLOW = "Daily report"
TODAY = datetime.datetime.now(datetime.timezone.utc).date()
NOW = datetime.datetime.now(datetime.timezone.utc)


class Report:
    def __init__(self):
        self.problems, self.headsup = [], []

    def problem(self, area, what, fix=""):
        self.problems.append((area, what, fix))

    def warn(self, area, what, fix=""):
        self.headsup.append((area, what, fix))


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


# ---------------------------------------------------------------- what was published when

def added_on(day):
    """{(channel, episode): set of record kinds ('yt', 'meta')} added to published/ on that UTC day (git history)."""
    nxt = day + datetime.timedelta(days=1)
    out = sh("git", "log", f"--since={day}T00:00:00Z", f"--until={nxt}T00:00:00Z", "--diff-filter=A",
             "--name-only", "--format=", "--", "published")
    found = {}
    for line in out.split():
        m = re.match(r"published/([^/]+)/(.+?)(\.meta)?\.json$", line)
        if m:
            found.setdefault((m.group(1), m.group(2)), set()).add("meta" if m.group(3) else "yt")
    return found


def queue_left():
    """Episodes still waiting per channel (ignores publish_after dates, so it is the whole backlog)."""
    left = {}
    for ch in CHANNELS:
        n = 0
        for path in glob.glob(f"episodes/{ch}/*.yaml"):
            if not os.path.exists(os.path.join("published", ch, os.path.basename(path)[:-5] + ".json")):
                n += 1
        left[ch] = n
    return left


def check_uploads(rep, today, meta_ok):
    for ch, name in CHANNELS.items():
        eps = sorted(ep for (c, ep), kinds in today.items() if c == ch and "yt" in kinds)
        if not eps:
            rep.problem(name, "nothing was published today.",
                        "Check the Render videos run below; if the queue is empty, the production thread needs to add episodes.")
            continue
        for ep in eps:
            rec = json.load(open(os.path.join("published", ch, ep + ".json")))
            if rec.get("privacy") != "public":
                rep.problem(name, f"`{ep}` is on YouTube as **{rec.get('privacy')}**, not public.",
                            f"Set it to public in YouTube Studio: https://studio.youtube.com/video/{rec['youtube_id']}/edit")
            mpath = os.path.join("published", ch, ep + ".meta.json")
            meta = json.load(open(mpath)) if os.path.exists(mpath) else {}
            if not meta_ok:
                continue
            for k, label in (("facebook_id", "Facebook Reel"), ("instagram_id", "Instagram Reel")):
                if not meta.get(k):
                    rep.problem(name, f"`{ep}` has no {label}.",
                                f"Run **Render videos** manually with episodes `episodes/{ch}/{ep}.yaml` and upload `public`; "
                                "platforms that already have it are skipped.")


# ---------------------------------------------------------------- GitHub Actions

def failed_runs(rep):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        rep.warn("GitHub", "GITHUB_TOKEN not set, failed runs were not checked.")
        return
    api = f"https://api.github.com/repos/{repo}/actions"
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    since = (NOW - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        runs = requests.get(f"{api}/runs", headers=hdr, params={"created": f">={since}", "per_page": 100}, timeout=30).json()
    except requests.RequestException as e:
        rep.warn("GitHub", f"could not list workflow runs: {e}")
        return
    runs = runs.get("workflow_runs", [])
    if not any(r["name"] == "Render videos" and r["event"] == "schedule" for r in runs):
        rep.problem("Publishing", "the daily **Render videos** run did not start in the last 24 h.",
                    "GitHub sometimes skips scheduled runs; start it by hand (Actions, Render videos, Run workflow, `due`).")
    for r in runs:
        if r["name"] == OWN_WORKFLOW or r.get("conclusion") not in ("failure", "timed_out", "startup_failure"):
            continue
        steps = []
        try:
            for job in requests.get(r["jobs_url"], headers=hdr, timeout=30).json().get("jobs", []):
                steps += [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
        except requests.RequestException:
            pass
        where = f" (failed step: {', '.join(steps)})" if steps else ""
        what = r.get("display_title") or r["name"]
        area = "Quality check" if r["name"] == "Check episodes" else r["name"]
        rep.problem(area, f"[{r['name']}: {what}]({r['html_url']}) {r['conclusion']}{where}.",
                    "Open the run log; quality-check errors are listed in its summary." if area == "Quality check" else
                    "Open the run log for the error.")


# ---------------------------------------------------------------- tokens and APIs

def hint(err):
    e = str(err)
    if "invalid_grant" in e:
        return "The refresh token was revoked or expired: run tools/youtube_auth.py for this channel and replace the secret."
    if "quota" in e.lower():
        return "Daily YouTube API quota used up; it resets at midnight Pacific time."
    if "Session has expired" in e or "code 190" in e or "OAuthException" in e:
        return "The Meta token is no longer valid: generate a new system user token and replace META_SYSTEM_USER_TOKEN."
    return ""


def youtube_health(rep):
    """{channel: subscriber count} for channels whose token works; problems for the others."""
    subs = {}
    if not os.environ.get("YT_CLIENT_SECRET_JSON"):
        rep.problem("YouTube", "YT_CLIENT_SECRET_JSON secret is missing.")
        return subs
    from upload_youtube import TOKENS, client
    for ch, name in CHANNELS.items():
        if not os.environ.get(TOKENS[ch]):
            rep.problem(f"YouTube {name}", f"secret {TOKENS[ch]} is missing.")
            continue
        try:
            items = client(ch).channels().list(part="statistics", mine=True).execute().get("items", [])
            subs[ch] = int(items[0]["statistics"].get("subscriberCount", 0)) if items else None
        except Exception as e:  # RefreshError, HttpError, network
            rep.problem(f"YouTube {name}", f"API call failed: `{str(e)[:200]}`", hint(e) or f"Check secret {TOKENS[ch]}.")
            os.environ.pop(TOKENS[ch], None)  # so the stats step skips this channel instead of crashing
            continue
        try:
            client(ch, "youtubeAnalytics", "v2").reports().query(
                ids="channel==MINE", startDate=str(TODAY - datetime.timedelta(days=2)), endDate=str(TODAY), metrics="views").execute()
        except Exception as e:
            rep.warn(f"YouTube {name}", f"YouTube Analytics API not answering (shares and % viewed missing): `{str(e)[:160]}`",
                     "Enable the YouTube Analytics API in Google Cloud project shorts-studio.")
    return subs


def meta_health(rep):
    """Facebook pages per channel (with page tokens), or None if the Meta token does not work."""
    token = os.environ.get("META_SYSTEM_USER_TOKEN")
    if not token:
        rep.problem("Meta", "META_SYSTEM_USER_TOKEN secret is missing; Facebook and Instagram are not checked.")
        return None
    from upload_meta import GRAPH, MetaError, call, discover
    try:
        info = call("GET", f"{GRAPH}/debug_token", params={"input_token": token, "access_token": token}).get("data", {})
        if not info.get("is_valid", True):
            rep.problem("Meta", "the system user token is not valid any more.", hint("code 190"))
            return None
        exp = info.get("expires_at") or 0  # 0 = never expires
        if exp:
            days = (datetime.datetime.fromtimestamp(exp, datetime.timezone.utc) - NOW).days
            if days < 3:
                rep.problem("Meta", f"the system user token expires in {days} days.", hint("code 190"))
            elif days < 14:
                rep.warn("Meta", f"the system user token expires in {days} days.", hint("code 190"))
        missing = [p for p in META_PERMS if p not in info.get("scopes", META_PERMS)]
        if missing:
            rep.warn("Meta", "token is missing permission(s): " + ", ".join(f"`{p}`" for p in missing) + ".",
                     "Regenerate the system user token in Business settings with these permissions ticked.")
    except (MetaError, requests.RequestException) as e:
        rep.warn("Meta", f"could not inspect the token: `{str(e)[:160]}`")
    try:
        pages = discover(token)
    except (MetaError, requests.RequestException) as e:
        rep.problem("Meta", f"could not list the Facebook pages: `{str(e)[:200]}`", hint(e))
        return None
    for ch, name in CHANNELS.items():
        if ch not in pages:
            rep.problem(f"Facebook {name}", "page not found for the system user.", "Assign the page to shorts-bot in Business settings.")
        elif not pages[ch].get("ig_id"):
            rep.problem(f"Instagram {name}", "no Instagram professional account linked to the page.")
    return pages


def facebook_stats(rows, pages, rep):
    from upload_meta import GRAPH, MetaError, call
    failed = 0
    for r in rows:
        page = (pages or {}).get(r["channel"])
        if not (r.get("facebook_id") and page):
            continue
        try:
            data = call("GET", f"{GRAPH}/{r['facebook_id']}/video_insights",
                        params={"metric": "blue_reels_play_count,post_impressions_unique", "access_token": page["page_token"]})
            vals = {m["name"]: (m.get("values") or [{}])[0].get("value", 0) for m in data.get("data", [])}
            r["fb"] = {"views": int(vals.get("blue_reels_play_count", 0)), "reach": int(vals.get("post_impressions_unique", 0))}
        except (MetaError, requests.RequestException) as e:
            failed += 1
            last = e
    if failed:
        rep.warn("Facebook", f"Reel insights failed for {failed} video(s): `{str(last)[:160]}`")


# ---------------------------------------------------------------- how today's videos look

def probe(path):
    out = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path).strip()
    return float(out) if out else 0.0


def scan(path):
    """(black stretches, frozen stretches, silent stretches) as lists of (start, length) seconds."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf",
                          "blackdetect=d=1:pix_th=0.08,freezedetect=n=0.002:d=4", "-af", "silencedetect=n=-45dB:d=2",
                          "-f", "null", "-"], capture_output=True, text=True).stderr

    def pairs(start, length):
        s = [float(x) for x in re.findall(start + r"[:=]\s*([\d.]+)", err)]
        d = [float(x) for x in re.findall(length + r"[:=]\s*([\d.]+)", err)]
        return list(zip(s, d))
    return (pairs("black_start", "black_duration"), pairs("freeze_start", "freeze_duration"),
            pairs("silence_start", "silence_duration"))


def contact_sheet(src, dst, dur):
    """Four frames side by side: the hook (1 s), 30 %, 60 % and the ending."""
    times = [min(1.0, dur / 4), dur * 0.3, dur * 0.6, max(0, dur - 1.5)]
    tmp = []
    for i, t in enumerate(times):
        f = f"{dst}.{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", "scale=270:-2", f], check=False)
        if os.path.exists(f):
            tmp.append(f)
    if not tmp:
        return False
    args = ["ffmpeg", "-y", "-v", "error"]
    for f in tmp:
        args += ["-i", f]
    flt = f"{''.join(f'[{i}:v]' for i in range(len(tmp)))}hstack=inputs={len(tmp)}" if len(tmp) > 1 else "null"
    subprocess.run(args + ["-filter_complex", flt, "-q:v", "4", dst], check=False)
    for f in tmp:
        os.remove(f)
    return os.path.exists(dst)


def youtube_frames(yt_id, dst):
    """Fallback when the rendered file is not available: YouTube's own frames at 25/50/75 %."""
    tmp = []
    for i in (1, 2, 3):
        try:
            r = requests.get(f"https://i.ytimg.com/vi/{yt_id}/hq{i}.jpg", timeout=20)
            if r.ok:
                tmp.append(f"{dst}.{i}.jpg")
                open(tmp[-1], "wb").write(r.content)
        except requests.RequestException:
            pass
    if not tmp:
        return False
    args = ["ffmpeg", "-y", "-v", "error"]
    for f in tmp:
        args += ["-i", f]
    flt = f"{''.join(f'[{i}:v]' for i in range(len(tmp)))}hstack=inputs={len(tmp)}" if len(tmp) > 1 else "null"
    subprocess.run(args + ["-filter_complex", flt, dst], check=False)
    for f in tmp:
        os.remove(f)
    return os.path.exists(dst)


def todays_videos(rep, today, videos_dir, day_dir):
    md = []
    for (ch, ep), kinds in sorted(today.items()):
        if "yt" not in kinds:
            continue
        name = CHANNELS.get(ch, ch)
        rec = json.load(open(os.path.join("published", ch, ep + ".json")))
        md += [f"### {name}: {rec.get('title', ep)}", ""]
        links = [f"[YouTube](https://youtube.com/shorts/{rec['youtube_id']})"]
        mpath = os.path.join("published", ch, ep + ".meta.json")
        meta = json.load(open(mpath)) if os.path.exists(mpath) else {}
        if meta.get("facebook_id"):
            links.append(f"[Facebook](https://www.facebook.com/reel/{meta['facebook_id']})")
        if meta.get("instagram_id"):
            links.append("Instagram")
        mp4 = os.path.join(videos_dir, ch, ep + ".mp4")
        img = os.path.join(day_dir, f"{ch}__{ep}.jpg")
        facts = []
        if os.path.exists(mp4):
            dur = probe(mp4)
            ok = contact_sheet(mp4, img, dur)
            facts.append(f"{dur:.0f} s")
            if not 25 <= dur <= 60:
                rep.warn(name, f"`{ep}` is {dur:.0f} s long (target 30-45 s).")
            black, frozen, silent = scan(mp4)
            for label, found in (("black", black), ("frozen picture", frozen), ("silence", silent)):
                for s, d in found[:2]:
                    rep.warn(name, f"`{ep}`: {d:.1f} s of {label} at {s:.1f} s.", "Watch that moment; it may be on purpose.")
        else:
            ok = youtube_frames(rec["youtube_id"], img)
            facts.append("frames from YouTube (render file not available)")
        if ok:
            md += [f"![{ep}]({{IMG}}/{os.path.basename(img)}{{RAW}})", "",
                   "<sub>hook · 30 % · 60 % · ending</sub>" if os.path.exists(mp4) else "<sub>25 % · 50 % · 75 %</sub>", ""]
        ypath = os.path.join("episodes", ch, ep + ".yaml")
        if os.path.exists(ypath):
            q = check(ypath)
            for e in q["errors"]:
                rep.problem(f"Quality {name}", f"`{ep}`: {e}")
            if q["hook"]:
                facts.append(f"spoken hook {q['hook'][1]:.0f}/100 \"{q['hook'][0]}\"")
                facts.append(f"on-screen hook \"{q['screen'][0]}\"")
                facts.append("loops back to the hook" if q["beats"]["loop"] else "no loop")
            md += ["- " + f for f in facts] + ["- " + " · ".join(links)]
            if q["warnings"]:
                md += ["- To improve next time: " + "; ".join(q["warnings"][:3])]
        else:
            md += ["- " + f for f in facts] + ["- " + " · ".join(links)]
        md.append("")
    return md or ["Nothing was published today.", ""]


# ---------------------------------------------------------------- performance

def snapshot(rows, subs):
    snap = {"date": str(TODAY), "subs": subs, "videos": {}}
    for r in rows:
        v = {p: {k: r[p].get(k) for k in ("views", "likes", "comments", "shares", "reach")} for p, _ in PLATFORMS if r.get(p)}
        if v:
            snap["videos"][f"{r['channel']}/{r['id']}"] = v
    return snap


def previous_snapshot():
    for path in sorted(glob.glob("reports/daily/*/stats.json"), reverse=True):
        if os.path.basename(os.path.dirname(path)) < str(TODAY):
            return json.load(open(path))
    return None


def views(snap, key, p):
    return ((snap or {}).get("videos", {}).get(key, {}).get(p) or {}).get("views") or 0


def performance_md(rows, snap, prev, yesterday):
    md = []
    base = f" (vs {prev['date']})" if prev else " (first report, no earlier numbers to compare yet)"
    md += [f"### Views gained in the last 24 h{base}", "",
           "| channel | YouTube | Facebook | Instagram | YouTube subscribers |", "| --- | --- | --- | --- | --- |"]
    for ch, name in CHANNELS.items():
        cells = []
        for p, _ in PLATFORMS:
            keys = [k for k in snap["videos"] if k.startswith(ch + "/") and p in snap["videos"][k]]
            if not keys:
                cells.append("–")
                continue
            total = sum(views(snap, k, p) for k in keys)
            gain = total - sum(views(prev, k, p) for k in keys) if prev else None
            cells.append(f"+{gain:,} ({total:,} total)" if gain is not None else f"{total:,} total")
        s, ps = snap["subs"].get(ch), ((prev or {}).get("subs") or {}).get(ch)
        sub = "–" if s is None else f"{s:,}" + (f" ({s - ps:+,})" if ps is not None else "")
        md.append(f"| {name} | {' | '.join(cells)} | {sub} |")
    md.append("")

    if prev:
        moves = []
        for k in snap["videos"]:
            gain = sum(views(snap, k, p) - views(prev, k, p) for p, _ in PLATFORMS)
            moves.append((gain, k))
        moves = [m for m in sorted(moves, reverse=True) if m[0] > 0][:5]
        if moves:
            md += ["### Top movers (views gained, all platforms)", "", "| video | +views | YouTube | Facebook | Instagram |",
                   "| --- | --- | --- | --- | --- |"]
            for gain, k in moves:
                cells = [f"{views(snap, k, p):,}" if p in snap["videos"][k] else "–" for p, _ in PLATFORMS]
                md.append(f"| {k} | +{gain:,} | {' | '.join(cells)} |")
            md.append("")

    if yesterday:
        ranked = {p: {(r["channel"], r["id"]): r[p]["outlier"] for r in performance.rank(rows, p)} for p in ("yt", "ig")}
        md += ["### Yesterday's uploads after their first day", "",
               "| video | YouTube views | x median | % viewed | Facebook | Instagram | x median | likes+comments |",
               "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            if (r["channel"], r["id"]) not in yesterday:
                continue
            yt, fb, ig = r.get("yt", {}), r.get("fb", {}), r.get("ig", {})
            eng = (yt.get("likes") or 0) + (yt.get("comments") or 0) + (ig.get("likes") or 0) + (ig.get("comments") or 0)
            pct = f"{yt['view_pct']:.0f}%" if yt.get("view_pct") is not None else ""
            md.append(f"| {CHANNELS.get(r['channel'], r['channel'])}: {r['id']} | {yt.get('views', '–')} "
                      f"| {ranked['yt'].get((r['channel'], r['id']), '')} | {pct} | {fb.get('views', '–')} | {ig.get('views', '–')} "
                      f"| {ranked['ig'].get((r['channel'], r['id']), '')} | {eng} |")
        md += ["", "x median: views divided by that channel's median, so 2.0 means twice a normal video for the channel.", ""]
    md += ["The full ranking with what the best videos have in common is in the weekly "
           "[performance report]({PERF}), every Monday.", ""]
    return md


# ---------------------------------------------------------------- main

def items(rows):
    return [f"- **{a}**: {w}" + (f"  \n  _Fix:_ {f}" if f else "") for a, w, f in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", default="out")
    ap.add_argument("--repo-url", default="", help="e.g. https://github.com/owner/repo: also write issue.md with absolute links")
    a = ap.parse_args()
    day_dir = os.path.join("reports", "daily", str(TODAY))
    os.makedirs(day_dir, exist_ok=True)
    rep = Report()

    failed_runs(rep)
    subs = youtube_health(rep)
    pages = meta_health(rep)
    today = added_on(TODAY)
    yesterday = {k for k, v in added_on(TODAY - datetime.timedelta(days=1)).items() if "yt" in v}
    check_uploads(rep, today, pages is not None)
    left, due_now = queue_left(), {os.path.basename(os.path.dirname(p)) for p in due()}
    for ch, n in left.items():
        if n == 0:
            rep.problem(CHANNELS[ch], "the episode queue is empty, so nothing will be published tomorrow.",
                        "The production thread needs to add episodes.")
        elif n <= 3:
            rep.warn(CHANNELS[ch], f"only {n} episode(s) left in the queue.")
        elif ch not in due_now:
            rep.warn(CHANNELS[ch], "episodes are queued but none is due tomorrow (publish_after dates).")

    look = todays_videos(rep, today, a.videos, day_dir)

    rows = performance.published()
    try:
        performance.youtube_stats(rows, 28)
    except Exception as e:
        rep.problem("YouTube", f"reading video statistics failed: `{str(e)[:200]}`", hint(e))
    try:
        performance.instagram_stats(rows)
    except Exception as e:
        rep.warn("Instagram", f"reading Reel insights failed: `{str(e)[:200]}`")
    if pages:
        facebook_stats(rows, pages, rep)
    snap = snapshot(rows, subs)
    prev = previous_snapshot()
    with open(os.path.join(day_dir, "stats.json"), "w") as f:
        json.dump(snap, f, indent=2)
    perf = performance_md(rows, snap, prev, yesterday)

    n = len(rep.problems)
    title = f"Daily report {TODAY}: " + (f"{n} problem{'s' if n != 1 else ''} to fix" if n else "all good")
    md = [f"# {title}", "", f"Generated {NOW:%Y-%m-%d %H:%M} UTC, after the daily publish.", "",
          "## 1. Needs fixing", ""] + (items(rep.problems) or ["Nothing. Every channel published and every check passed."]) + [""]
    if rep.headsup:
        md += ["## Heads-up", ""] + items(rep.headsup) + [""]
    md += ["## 2. Today's videos", ""] + look + ["## 3. Performance", ""] + perf
    text = "\n".join(md) + "\n"
    # report.md is read in the repo (relative links); issue.md is the same text with absolute links
    with open(os.path.join(day_dir, "report.md"), "w") as f:
        f.write(text.replace("{IMG}", ".").replace("{RAW}", "").replace("{PERF}", "../../performance.md"))
    if a.repo_url:
        base = a.repo_url.rstrip("/") + "/blob/main/"
        text = text.replace("{IMG}", base + day_dir).replace("{RAW}", "?raw=true").replace("{PERF}", base + "reports/performance.md")
        with open(os.path.join(day_dir, "issue.md"), "w") as f:
            f.write(text)
    with open(os.path.join(day_dir, "title.txt"), "w") as f:
        f.write(title + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
