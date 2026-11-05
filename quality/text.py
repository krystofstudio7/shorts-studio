"""Text hygiene for scripts, titles and captions.

Adapted from humanize.py / slop.json in https://github.com/Jakeschincariol/instagram-agent-skill
(MIT License, Copyright (c) 2026 Jake Schincariol, see quality/LICENSE-instagram-agent-skill).

Two jobs, kept apart on purpose:

* clean(text): safe mechanical fixes applied automatically to every caption we publish:
  invisible characters (zero-width, BOM, Unicode tag smuggling, odd spaces) and typography
  (em/en dashes, curly quotes, ellipsis). A zero-width joiner *inside an emoji* is kept, so
  compound emoji survive.
* scan(text): reports AI-sounding words, phrases and sentence shapes. It never rewrites,
  because a word like "vital" or "journey" can be the right word in a science or history script.
"""
import json
import os
import re
import unicodedata

LEX = json.load(open(os.path.join(os.path.dirname(__file__), "slop.json"), encoding="utf-8"))
URL_RE = re.compile(r"https?://\S+|www\.\S+")
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️]")
ZWJ = "‍"


def _codepoints(spec):
    if "-" in spec:
        a, b = spec.split("-")
        return range(int(a[2:], 16), int(b[2:], 16) + 1)
    return [int(spec[2:], 16)]


INVISIBLE = {}
for _e in LEX["invisible"]:
    for _cp in _codepoints(_e["cp"]):
        INVISIBLE[chr(_cp)] = (_e["name"], "" if _e["action"] == "delete" else " ")


def _emoji_zwj(text, i):
    return text[i] == ZWJ and 0 < i < len(text) - 1 and EMOJI.match(text[i - 1]) and EMOJI.match(text[i + 1])


def invisible(text):
    """[(name, count)] of invisible characters a keyboard never types (emoji joiners excluded)."""
    found = {}
    for i, c in enumerate(text):
        if (c in INVISIBLE or unicodedata.category(c) == "Cf") and not _emoji_zwj(text, i):
            name = INVISIBLE.get(c, ("invisible format character",))[0]
            found[name] = found.get(name, 0) + 1
    return sorted(found.items())


def clean(text):
    """Strip invisible characters and fix typography. URLs are left untouched."""
    urls = []

    def stash(m):
        urls.append(m.group(0))
        return f"\x00{len(urls) - 1}\x00"

    text = URL_RE.sub(stash, text)
    out = []
    for i, c in enumerate(text):
        if (c in INVISIBLE or (unicodedata.category(c) == "Cf" and c != "\x00")) and not _emoji_zwj(text, i):
            out.append(INVISIBLE.get(c, ("", ""))[1])
        else:
            out.append(c)
    text = "".join(out)
    text = re.sub(r"\s*—\s*", ", ", text)              # em dash -> comma
    text = re.sub(r"(?<=\d)\s*–\s*(?=\d)", "-", text)  # 5–10 -> 5-10
    text = re.sub(r"\s+–\s+", ", ", text)              # en dash used as a dash
    text = text.replace("–", "-")
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'), ("…", "...")):
        text = text.replace(a, b)
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)
    text = re.sub(r",[ \t]*\n", "\n", text)
    for i, u in enumerate(urls):
        text = text.replace(f"\x00{i}\x00", u)
    return text


_TERMS = sorted(LEX["phrases"] + LEX["words"], key=lambda e: -len(e["find"]))
_TERM_RE = [(e, re.compile(r"\b" + re.escape(e["find"]).replace(r"\ ", r"\s+") + r"\b", re.I)) for e in _TERMS]
_STRUCT = []
for _s in LEX["structures"]:
    try:
        _STRUCT.append((_s, re.compile(_s["regex"], re.M)))
    except re.error:
        pass
# shapes that only make sense in a caption (hashtag walls, emoji bullets) are checked by caption.py
CAPTION_ONLY = {"Hashtag wall (5+)", "Emoji bullet list", "Rocket / fire / bulb / sparkle / dart emoji"}


def scan(text, spoken=False):
    """[(kind, what, suggestion)] for AI-sounding vocabulary and sentence shapes."""
    hits, low = [], text
    for e, rx in _TERM_RE:
        n = len(rx.findall(low))
        if n:
            hits.append(("word", e["find"], f"try \"{e['replace']}\"" if e["replace"] else "cut it"))
            low = rx.sub(" ", low)  # "delve into" must not also count as "delve"
    for s, rx in _STRUCT:
        if spoken and s["name"] in CAPTION_ONLY:
            continue
        if rx.search(text):
            hits.append(("shape", s["name"], s["fix"]))
    return hits
