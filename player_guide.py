# Player guide (EN/ES answers + scrim reminders) — data and pure logic, no Discord here.
#
# Source of truth: the coaching-brain repo's player-guide/ (copied into
# "coaching brain/player-guide/"). en/*.md are the English player pages, tagged
# ✅ coach said it · 🔶 maybe · ❓ unconfirmed. cheatsheet.json holds the 3–5
# reminder lines per map in EN and ES.
#
# Used by coach_cog.py (/ask, /reminder). Kept free of discord/openai imports so
# it is unit-testable.

import json
import os
import re

GUIDE_DIR = os.path.join("coaching brain", "player-guide")
LIMIT = 2000  # Discord message limit

# key → (guide page, mode page, keywords found in a question)
MAPS = {
    "takeoff": ("maps/takeoff", "modes/hardpoint", ["takeoff", "take off"]),
    "combine": ("maps/combine", "modes/hardpoint", ["combine"]),
    "hacienda": ("maps/hacienda", "modes/hardpoint", ["hacienda"]),
    "summit": ("maps/summit", "modes/hardpoint", ["summit"]),
    "arsenal": ("maps/arsenal", "modes/hardpoint", ["arsenal"]),
    "raid": ("maps/raid", "modes/control", ["raid"]),
    "standoff": ("maps/standoff", "modes/control", ["standoff"]),
    "crossroads-strike": ("maps/crossroads-strike", "modes/control", ["crossroads"]),
    "firing-range": ("maps/firing-range", "modes/snd", ["firing range", "firingrange"]),
    "coastal": ("maps/coastal", "modes/snd", ["coastal"]),
    "slums": ("maps/slums", "modes/snd", ["slums"]),
}
PLAYERS = ["maozyn", "mao", "exile", "kingz", "cartels", "jason", "polar", "swish"]

RULES = """You answer questions from players of a Call of Duty: Mobile team coached by Flower, usually right before a scrim.
Answer ONLY from the NOTES below — the coach's own notes, built from the coach's session transcripts.

Rules:
1. Never add tactics, meta or opinions that are not in the NOTES. If the NOTES don't cover the question, say so in one line and suggest asking Flower.
2. Keep the condition of every point (map, hill P1–P4, attack/defense, situation, timing). Never stretch a map-specific rule to another map. If two notes look different, give both with their conditions.
3. Put the session tag and confidence after each point exactly as in the NOTES (e.g. `S19 ✅`). Say "maybe" for 🔶. Never give ❓ items as instructions; mention them only as "unconfirmed".
4. Answer in the language of the question: English, or natural Latin-American gaming Spanish (tú). Keep callouts and game terms in English in both (P1–P4, hill, slay out, recycle, flank, lurk, retake, head glitch, top red, spawn, trade…). Names: Maozyn, Exile, Kingz, Cartels, Jason, Polar; the coach is Flower.
5. Callout positions are mostly not defined — never describe where a callout is.
6. Discord format: first the direct answer in one or two sentences, then at most 5 short bullets starting with **Do:** or **Don't:**, each with its tag. No tables, no headings. Under 150 words unless the player asks for more."""

_CACHE: dict[str, tuple[float, str]] = {}


def _read(rel: str) -> str:
    path = os.path.join(GUIDE_DIR, rel)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    _CACHE[path] = (mtime, text)
    return text


def page(key: str) -> str:
    return _read(os.path.join("en", key + ".md"))


def all_pages() -> list[str]:
    base = os.path.join(GUIDE_DIR, "en")
    keys = []
    for root, _, files in os.walk(base):
        for f in files:
            if f.endswith(".md"):
                keys.append(os.path.relpath(os.path.join(root, f), base)[:-3].replace(os.sep, "/"))
    return sorted(keys)


def detect_maps(text: str) -> list[str]:
    t = text.lower()
    return [k for k, (_, _, kw) in MAPS.items() if any(w in t for w in kw)]


def build_context(question: str, forced_map: str | None = None) -> tuple[str, list[str]]:
    """Pick the guide pages for this question. Returns (prompt text, maps used)."""
    maps = [forced_map] if forced_map else detect_maps(question)
    keys = ["glossary", "team-principles"]
    if maps:
        for m in maps[:3]:
            keys += [MAPS[m][0], MAPS[m][1]]
    else:
        keys += [k for k in all_pages() if k != "team-notes"]
    q = question.lower()
    if any(re.search(rf"\b{p}\b", q) for p in PLAYERS):
        keys.append("team-notes")
    seen, notes = set(), []
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        body = re.sub(r"<sub>.*?</sub>", "", page(k), flags=re.S).strip()
        if body:
            notes.append(f"=== {k} ===\n{body}")
    return RULES + "\n\nNOTES:\n\n" + "\n\n".join(notes), maps


def split_message(text: str, limit: int = LIMIT) -> list[str]:
    """Split on line boundaries so each chunk fits one Discord message."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # one absurdly long line
            out.append(cur) if cur else None
            cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) > limit:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return [c.rstrip() for c in out if c.strip()]


# ── /reminder ────────────────────────────────────────────────────────────
_T = {
    "en": {"title": "## 🎮 Scrim reminder — vs {opp}", "today": "**Today:** {maps}",
           "fix": "### 🔧 Fix from last time",
           "legend": "-# From Coach Flower's transcripts · ✅ coach said it · 🔶 maybe (not confirmed) · `S19` = session 19",
           "cont": "### (continued) vs {opp}"},
    "es": {"title": "## 🎮 Recordatorio de scrim — vs {opp}", "today": "**Hoy:** {maps}",
           "fix": "### 🔧 Lo que quedamos en arreglar",
           "legend": "-# De las transcripciones del coach Flower · ✅ lo dijo el coach · 🔶 tal vez (sin confirmar) · `S19` = sesión 19",
           "cont": "### (continuación) vs {opp}"},
}


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def cheatsheet() -> dict:
    return json.loads(_read("cheatsheet.json") or "{}")


def build_reminder(lang: str, opponent: str, map_keys: list[str], fixes: list[str] | None = None) -> list[str]:
    """Discord messages (each ≤ 2000) for a pre-scrim reminder. Raises KeyError on an unknown map."""
    data, t = cheatsheet(), _T[lang]
    maps = [data["maps"][k] for k in map_keys]
    header = t["title"].format(opp=opponent) + "\n" + t["today"].format(
        maps=" · ".join(f"{m['title']} ({m['mode']})" for m in maps))
    sections = []
    for m in maps:
        lines = [f"### 🗺️ {m['title']} · {m['mode']}"] + [f"- {x}" for x in m[lang] if "❓" not in x]
        if m.get("note_" + lang):
            lines += ["", "-# ⚠️ " + m["note_" + lang]]
        sections.append("\n".join(lines))
    if fixes is None:
        fixes = [data["default_fixes"][mode][lang] for mode in dict.fromkeys(m["mode"] for m in maps)]
        fixes.append(data["common_fix"][lang])
    if fixes:
        sections.append("\n".join([t["fix"]] + [f"- {x}" for x in fixes]))
    footer = t["legend"]
    msgs, cur = [], header
    for sec in sections:
        trial = cur + "\n\n" + sec
        if _u16(trial + "\n\n" + footer) <= LIMIT:
            cur = trial
        else:
            msgs.append(cur + "\n\n" + footer)
            cur = t["cont"].format(opp=opponent) + "\n\n" + sec
    msgs.append(cur + "\n\n" + footer)
    return msgs
