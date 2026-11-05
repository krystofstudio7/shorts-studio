"""Quality check for episodes before they are rendered and published.

    python check_episodes.py episodes/what-if-institute/what-if-010-*.yaml
    python check_episodes.py --all
    python check_episodes.py --summary report.md FILES   # also write a Markdown report (GitHub step summary)

For each episode it scores the spoken hook (first line) and the on-screen hook, times the script
the way our narration will say it, and looks for AI-sounding wording and invisible characters.

Errors (exit code 1) are only things that should never ship: invisible characters, a missing
hook or first line, a greeting or "stop scrolling"/"follow for more" style line. Everything else
is a warning to improve the episode, not to block it.

Needs only PyYAML, so it runs in a few seconds on every pull request.
"""
import argparse
import ast
import glob
import os
import re
import sys

import yaml

from quality import beats, hooks, text

CHANNEL_FILES = {"what-if-institute": "whatif", "stoic-ember": "stoic", "mind-mites": "mites"}
NEVER = [  # (regex on spoken text, why)
    (re.compile(r"(?i)^\s*(?:hey|hi|hello|what'?s up|welcome)\b"), "opens with a greeting"),
    (re.compile(r"(?i)\b(?:stop scrolling|don'?t scroll)\b"), "\"stop scrolling\""),
    (re.compile(r"(?i)\bin (?:this|today'?s) (?:video|reel|short)\b"), "video preamble"),
    (re.compile(r"(?i)\b(?:follow for more|smash (?:that|the) like|tag someone who|double tap if)\b"), "follow/like bait"),
    (re.compile(r"(?i)\bas an ai\b|\bas a language model\b"), "model self-reference"),
]


def channel_defaults(channel):
    """Narration speed and default hashtags, read from the channel theme without importing it (no numpy/PIL)."""
    src = open(os.path.join("studio", "channels", CHANNEL_FILES[channel] + ".py"), encoding="utf-8").read()
    speed = re.search(r"voice,\s*speed\s*=\s*\"[^\"]+\",\s*([\d.]+)", src)
    tags = re.search(r"hashtags\s*=\s*(\[[^\]]*\])", src)
    return float(speed.group(1)) if speed else 1.0, ast.literal_eval(tags.group(1)) if tags else []


def texts(ep):
    """(where, text, spoken?) for every piece of text that reaches a viewer."""
    yield "title", ep.get("title", ""), False
    yield "hook", ep.get("hook", ""), False
    yield "description", ep.get("description", ""), False
    for i, ln in enumerate(ep.get("lines", []), 1):
        yield f"line {i}", ln.get("text", ""), True
        if ln.get("caption"):
            yield f"line {i} caption", ln["caption"], False


def check(path):
    ep = yaml.safe_load(open(path, encoding="utf-8"))
    errors, warnings = [], []
    channel = ep.get("channel") or os.path.basename(os.path.dirname(path))
    if channel not in CHANNEL_FILES:
        return {"path": path, "errors": [f"unknown channel '{channel}'"], "warnings": [], "hook": None, "screen": None, "beats": None}
    speed, _ = channel_defaults(channel)
    speed = ep.get("speed", speed)
    if not ep.get("lines"):
        return {"path": path, "errors": ["episode has no lines"], "warnings": [], "hook": None, "screen": None, "beats": None}

    for where, t, spoken in texts(ep):
        for name, n in text.invisible(str(t)):
            errors.append(f"{where}: {n}x invisible character ({name})")
        if spoken:
            for rx, why in NEVER:
                if rx.search(t):
                    errors.append(f"{where}: {why}: \"{t}\"")
        if "—" in str(t):
            warnings.append(f"{where}: em dash. It reads as machine-written in captions and gets swapped for a comma on Reels.")
        slop = text.scan(str(t), spoken=spoken)
        if slop:
            warnings.append(f"{where}: sounds generated: " + "; ".join(f"\"{w}\" ({s})" for _, w, s in slop[:4]))

    first = ep["lines"][0]["text"]
    if not ep.get("hook"):
        errors.append("no on-screen `hook`")
    h_res, h_score, h_verdict, h_flags = hooks.run(first)
    s_score = hooks.run(ep["hook"])[1] if ep.get("hook") else 0
    if h_score < 50:
        weakest = min(hooks.CHECKS, key=lambda c: h_res[c][0])
        warnings.append(f"spoken hook scores {h_score:.0f}/100 (weak). Weakest: {weakest.lower()}, {h_res[weakest][1]}.")
    for f in h_flags:
        if "Emoji" not in f:  # the spoken line never shows an emoji; the title is checked separately
            warnings.append(f"spoken hook: {f}")

    b = beats.analyse(ep, speed)
    warnings += b["warnings"]

    return {"path": path, "errors": errors, "warnings": warnings, "hook": (first, h_score, h_verdict),
            "screen": (ep.get("hook", ""), s_score), "beats": b}


def report(results):
    out = ["## Episode quality check", "",
           "| episode | spoken hook | on-screen hook | length | loop | errors | warnings |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        name = os.path.basename(r["path"])[:-5]
        if r["hook"] is None:
            out.append(f"| {name} | | | | | {len(r['errors'])} | |")
            continue
        loop = ", ".join(r["beats"]["loop"][:2]) or "none"
        out.append(f"| {name} | {r['hook'][1]:.0f} {r['hook'][2]} | {r['screen'][1]:.0f} | ~{r['beats']['total']:.0f}s | {loop} "
                   f"| {len(r['errors'])} | {len(r['warnings'])} |")
    for r in results:
        if not r["errors"] and not r["warnings"]:
            continue
        out += ["", f"### {os.path.basename(r['path'])}"]
        out += [f"- **ERROR** {e}" for e in r["errors"]]
        out += [f"- {w}" for w in r["warnings"]]
    out += ["", "Hook scores are text heuristics (0-100): they catch weak openers and missing specifics, they do not predict views. "
            "Our own performance report (`reports/performance.md`) is the real judge."]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--summary", help="also write the Markdown report to this file (appends)")
    a = ap.parse_args()
    eps = a.episodes or (sorted(glob.glob("episodes/*/*.yaml")) if a.all else [])
    if not eps:
        ap.error("give episode files or --all")
    results = [check(p) for p in eps]
    md = report(results)
    print(md)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(md)
    bad = [r["path"] for r in results if r["errors"]]
    for p in bad:
        print(f"::error file={p}::episode has quality errors, see the report")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
