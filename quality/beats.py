"""Timed beat sheet for an episode, before it is rendered.

Adapted from beats.py in https://github.com/Jakeschincariol/instagram-agent-skill
(MIT License, Copyright (c) 2026 Jake Schincariol, see quality/LICENSE-instagram-agent-skill).

Instead of a generic words-per-minute guess it uses our own narration: Kokoro speaks about
185 words a minute at speed 1.0 (measured on the v4 renders), scaled by the channel's speed,
plus the same lead, pauses and tail that studio/core.build_voice adds.
"""
import re

WPM_AT_1X = 185
LEAD, GAP, TAIL = 0.15, 0.3, 0.4
HOOK_WINDOW = 3.0     # seconds: the spoken hook should land before this
MAX_STATIC = 6.0      # seconds on one line with no scene change or update on screen
ABSTRACT_RUN = 3      # lines in a row with no number or name
TARGET = (30, 45)     # seconds, from the audience research

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")
CONCRETE_RE = re.compile(r"\$\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-Z][a-z]{2,}\b|\b(?:two|three|four|five|six|seven|eight|nine|ten|"
                         r"twelve|fifteen|twenty|thirty|forty|fifty|hundred|thousand|million|billion|half)\b", re.I)
STOP = set("the a an and or but if of to in on for with that this it is are was were be been you your i my me we our "
           "they them he she so just not no do did does have has had will can at as by from out up off one all what".split())


def words(text):
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def analyse(ep, speed=1.0):
    wps = WPM_AT_1X * speed / 60
    t, rows = LEAD, []
    for i, ln in enumerate(ep["lines"]):
        n = len(words(ln["text"]))
        dur = n / wps
        rows.append({"n": i + 1, "start": t, "dur": dur, "words": n, "text": ln["text"],
                     "changes": i == 0 or "scene" in ln or "update" in ln,
                     "concrete": bool(CONCRETE_RE.search(ln["text"]) or CONCRETE_RE.search(ln.get("caption", "")))})
        t += dur + ln.get("pause", GAP)
    total = t + ep.get("tail", TAIL)
    warn = []
    first = rows[0]
    if first["start"] + first["dur"] > HOOK_WINDOW:
        warn.append(f"The first spoken line ends at ~{first['start'] + first['dur']:.1f}s ({first['words']} words). Hooks that land "
                    f"inside {HOOK_WINDOW:.0f}s hold more viewers; aim for {int((HOOK_WINDOW - LEAD) * wps)} words or fewer.")
    static = [r["n"] for r in rows if not r["changes"] and r["dur"] > MAX_STATIC]
    if static:
        warn.append(f"Line(s) {', '.join(map(str, static))} run over {MAX_STATIC:.0f}s with nothing new on screen. "
                    "Add an `update` or split the line.")
    run = 0
    for r in rows:
        run = 0 if r["concrete"] else run + 1
        if run == ABSTRACT_RUN:
            warn.append(f"Lines {r['n'] - ABSTRACT_RUN + 1}-{r['n']} have no number or name. Put something checkable in one.")
    a = {w.lower() for w in words(rows[0]["text"]) if len(w) > 2} - STOP
    b = {w.lower() for w in words(rows[-1]["text"]) if len(w) > 2} - STOP
    loop = sorted(a & b)
    if not loop:
        warn.append("No loop: the last line shares no word with the first, so the end does not invite a replay.")
    lo, hi = TARGET
    if not lo <= total <= hi:
        warn.append(f"Estimated length {total:.0f}s is outside the {lo}-{hi}s target.")
    return {"total": total, "rows": rows, "loop": loop, "warnings": warn}
