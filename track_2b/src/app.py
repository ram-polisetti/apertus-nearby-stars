#!/usr/bin/env python3
"""Nearby Stars, Plain Words.

A tiny web app that answers beginner astronomy questions from a real
Gaia DR3 nearby-stars dataset. Retrieval over the bundled CSV produces the
facts; when an Apertus endpoint is configured through the LLM_NAME,
LLM_BASE_URL and LLM_API_KEY environment variables, the model phrases the
answer in plain language. With no endpoint configured (or if the call
fails), a deterministic fallback answers from the same facts, so the app is
fully useful offline and in an air-gapped deployment.

Python 3 standard library only. Run: python3 src/app.py (port 8000).
"""
import csv
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "..", "data", "nearby_stars.csv")
STATIC = os.path.join(HERE, "static")
PORT = int(os.environ.get("PORT", "8000"))

LLM_NAME = os.environ.get("LLM_NAME", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")

# Famous stars that have no usable astrometric entry in this Gaia DR3 extract
# (Gaia struggles with the very brightest stars). Values are the standard
# textbook distances (Hipparcos based), and answers say so plainly.
REFERENCE_ONLY = {
    "vega": ("Vega", 25.0),
    "alpha centauri": ("Alpha Centauri", 4.37),
    "procyon": ("Procyon", 11.5),
    "altair": ("Altair", 16.7),
    "pollux": ("Pollux", 33.8),
    "arcturus": ("Arcturus", 36.7),
    "capella": ("Capella", 42.9),
}

# Big-picture reference answers: the beginner questions everyone asks
# first, which no 49 light year dataset can answer from its own rows.
# Same spirit as REFERENCE_ONLY: standard textbook values and estimates,
# worded plainly, honest about being estimates rather than Gaia
# measurements, and pointing back to the local data where natural.
BIG_PICTURE_MILKY_WAY_COUNT = (
    "Astronomers estimate that the Milky Way holds somewhere between "
    "100 and 400 billion stars, and about 200 billion is the number most "
    "often quoted. Nobody counted them one by one: the estimate comes "
    "from weighing the galaxy and working out how much of its mass is in "
    "stars. This app maps the 1,113 stars within 49 light years of home, "
    "a tiny local sample of that huge number."
)
BIG_PICTURE_MILKY_WAY_SIZE = (
    "The Milky Way is a spiral galaxy about 100,000 light years across, "
    "with a disk roughly 1,000 light years thick. That size is an "
    "estimate built from mapping its spiral arms and rotation, not "
    "something anyone measured directly. The whole 49 light year "
    "neighbourhood mapped in this app would be a tiny speck inside it."
)
BIG_PICTURE_ANDROMEDA = (
    "The nearest large galaxy to ours is Andromeda, about 2.5 million "
    "light years away. Its light has been travelling for 2.5 million "
    "years, yet on a dark night you can just see it with the naked eye "
    "as a faint smudge. The stars in this app, all within 49 light "
    "years, are far closer to home."
)
BIG_PICTURE_NAKED_EYE = (
    "On a really dark night, far from city lights, you can see roughly "
    "2,500 stars with the naked eye at one time. Counting the whole sky "
    "over both hemispheres, there are perhaps 5,000 to 9,000 visible in "
    "total, depending on your eyes and the sky. It feels like millions, "
    "but it is a few thousand of the galaxy's billions."
)
BIG_PICTURE_LIGHT_YEAR = (
    "A light year is a distance, not a time: it is how far light "
    "travels in one year, about 9.46 trillion kilometres. Light moves at "
    "300,000 kilometres every second, but space is so big that starlight "
    "still takes years to reach us. So when this app says a star is "
    "11.9 light years away, it also means the light you see left it "
    "11.9 years ago."
)
BIG_PICTURE_UNIVERSE_AGE = (
    "The universe is about 13.8 billion years old, counting from the "
    "Big Bang. That figure comes mainly from the cosmic microwave "
    "background, the faint leftover glow of the hot early universe, "
    "measured very precisely by satellites such as Planck. The stars in "
    "this app all formed much later, in a universe already billions of "
    "years old."
)
BIG_PICTURE_MOON = (
    "The Moon is about 384,000 kilometres from Earth, so its light "
    "reaches us in about 1.3 seconds. It is by far the closest thing in "
    "the sky, roughly 400 times closer than the Sun. Compared with even "
    "the nearest star in this app, 4.3 light years away, it is "
    "practically next door."
)
BIG_PICTURE_SUN = (
    "The Sun is about 150 million kilometres from Earth, a distance "
    "astronomers call one astronomical unit, or 1 AU. Its light takes "
    "about 8 minutes 20 seconds to reach us, so we always see the Sun "
    "as it was 8 minutes ago. The nearest star beyond it, Proxima "
    "Centauri, is about 270,000 times farther away."
)


def big_picture(q):
    """Reference answer for a big-picture question, or None.

    Checked before the local intents on purpose: "how many stars are in
    the Milky Way" must not be mistaken for a count inside the dataset.
    """
    if "andromeda" in q or "nearest galaxy" in q or "closest galaxy" in q:
        return BIG_PICTURE_ANDROMEDA
    if "milky way" in q:
        if any(w in q for w in ("big", "wide", "across", "diameter", "size", "large")):
            return BIG_PICTURE_MILKY_WAY_SIZE
        return BIG_PICTURE_MILKY_WAY_COUNT
    if "naked eye" in q or "can i see" in q or "can you see" in q or "see at night" in q:
        return BIG_PICTURE_NAKED_EYE
    if "light year" in q and any(
        w in q for w in ("what", "mean", "is a light", "how long", "how far is a")
    ):
        return BIG_PICTURE_LIGHT_YEAR
    if "universe" in q and any(w in q for w in ("old", "age", "begin", "born")):
        return BIG_PICTURE_UNIVERSE_AGE
    if "moon" in q and any(w in q for w in ("far", "distance", "away", "close")):
        return BIG_PICTURE_MOON
    if "sun" in q and "how far" in q:
        return BIG_PICTURE_SUN
    return None


def load_stars():
    stars = []
    with open(DATA_PATH, newline="") as f:
        for row in csv.DictReader(f):
            try:
                row["distance_ly"] = float(row["distance_ly"])
                row["parallax_mas"] = float(row["parallax_mas"])
                row["g_mag"] = float(row["g_mag"]) if row["g_mag"] else None
                row["teff_k"] = float(row["teff_k"]) if row["teff_k"] else None
                row["bp_rp"] = float(row["bp_rp"]) if row["bp_rp"] else None
                ra = math.radians(float(row["ra"]))
                dec = math.radians(float(row["dec"]))
            except ValueError:
                continue
            # Equatorial coordinates to a 3D position in light years, Sun at
            # the origin: x toward RA 0h on the equator, y toward the north
            # celestial pole, z toward RA 6h. Used by the 3D star map.
            d = row["distance_ly"]
            row["x"] = round(d * math.cos(dec) * math.cos(ra), 3)
            row["y"] = round(d * math.sin(dec), 3)
            row["z"] = round(-d * math.cos(dec) * math.sin(ra), 3)
            stars.append(row)
    stars.sort(key=lambda s: s["distance_ly"])
    return stars


STARS = load_stars()
NAMED = {s["name"].lower(): s for s in STARS if s["name"]}
MAX_LY = STARS[-1]["distance_ly"] if STARS else 0.0


def fmt_star(s):
    base = s["name"] if s["name"] else f"Gaia DR3 {s['source_id']}"
    return base


def describe(s):
    bits = [f"{fmt_star(s)} is {s['distance_ly']:.1f} light years away"]
    if s["g_mag"] is not None:
        bits.append(f"apparent magnitude {s['g_mag']:.1f} in the Gaia G band")
    if s["teff_k"]:
        bits.append(f"surface temperature about {s['teff_k']:.0f} K")
    return "; ".join(bits) + "."


def focus_payload(s):
    """The star an answer is about, for the 3D map and info panel."""
    if s is None:
        return None
    return {
        "source_id": s["source_id"],
        "name": fmt_star(s),
        "distance_ly": round(s["distance_ly"], 2),
        "distance_pc": round(s["distance_ly"] / 3.26156, 2),
        "g_mag": s["g_mag"],
        "teff_k": s["teff_k"],
        "bp_rp": s["bp_rp"],
        "x": s["x"],
        "y": s["y"],
        "z": s["z"],
    }


def retrieve(question):
    """Return (facts_text, direct_answer, focus_star_or_None).

    Pure data work, no LLM involved. focus_star is the dataset row the
    answer centres on, so the UI can fly the 3D camera to it.
    """
    q = " ".join(question.lower().strip().split())

    # Big-picture reference questions first: they sound like dataset
    # questions ("how many stars...") but are not about the local data.
    bp = big_picture(q)
    if bp:
        return bp, bp, None

    # Named-star lookup: "how far is sirius", "tell me about tau ceti".
    for name, s in NAMED.items():
        if name in q:
            return describe(s), describe(s), s
    for key, (label, ly) in REFERENCE_ONLY.items():
        if key in q:
            text = (
                f"{label} is one of the very brightest stars in the sky, and Gaia "
                f"cannot measure stars that bright accurately, so it is not in this "
                f"Gaia dataset. Its textbook distance (from the Hipparcos mission) "
                f"is about {ly:.0f} light years."
            )
            return text, text, None

    m = re.search(r"within (\d+(?:\.\d+)?)\s*(light ?years|ly|parsecs?|pc)", q)
    if m or "how many" in q:
        limit = float(m.group(1)) if m else 10.0
        if m and m.group(2).startswith("p"):
            limit *= 3.26156
        n = sum(1 for s in STARS if s["distance_ly"] <= limit)
        text = (
            f"There are {n} stars in this Gaia DR3 dataset within "
            f"{limit:.0f} light years of the Sun. The dataset holds "
            f"{len(STARS)} stars out to {MAX_LY:.0f} light years."
        )
        return text, text, None

    if "closest" in q or "nearest" in q:
        top = STARS[:3]
        text = "The closest stars to the Sun in this dataset are: " + " ".join(
            f"{i + 1}. {describe(s)}" for i, s in enumerate(top)
        )
        text += (
            " The Sun itself is not in the list, since Gaia measures other stars "
            "as seen from our solar system."
        )
        return text, text, top[0]

    if "brightest" in q or "bright" in q:
        bright = sorted(
            (s for s in STARS if s["g_mag"] is not None), key=lambda s: s["g_mag"]
        )[:5]
        text = (
            "The brightest nearby stars, by apparent magnitude as seen from Earth "
            "(smaller number means brighter), are: "
            + " ".join(f"{i + 1}. {describe(s)}" for i, s in enumerate(bright))
        )
        text += (
            " One warning: Gaia's brightness readings for the very brightest "
            "stars are unreliable, because they overload its detectors. Sirius "
            "is the brightest star in our night sky, but Gaia's value for it "
            "in this table (magnitude 8.5) is far too faint, so it does not "
            "appear in the list above."
        )
        return text, text, bright[0]

    if "hottest" in q or "temperature" in q:
        hot = sorted(
            (s for s in STARS if s["teff_k"]), key=lambda s: s["teff_k"], reverse=True
        )[:3]
        text = "The hottest stars in this nearby dataset are: " + " ".join(
            f"{i + 1}. {describe(s)}" for i, s in enumerate(hot)
        )
        return text, text, hot[0]

    if "how far" in q or "distance" in q:
        text = (
            "Ask me about a specific star by name, for example Sirius, Vega, "
            "Tau Ceti or TRAPPIST-1, and I will look it up. The closest star in "
            f"the data is {describe(STARS[0])}"
        )
        return text, text, None

    text = (
        f"This dataset holds {len(STARS)} real stars measured by the Gaia "
        f"space telescope, out to {MAX_LY:.0f} light years. You can ask: what "
        "is the closest star, which nearby stars are brightest, how far is a "
        "named star such as Sirius or Tau Ceti, or how many stars lie within "
        "10 light years. You can also ask big-picture questions, like how "
        "many stars are in the Milky Way or what a light year is."
    )
    return text, text, None


SYSTEM_PROMPT = (
    "You are a friendly astronomy explainer for complete beginners. Answer "
    "using ONLY the facts provided. Use plain words, short sentences, and no "
    "jargon. Never use em dashes. If the facts do not cover the question, "
    "say what the facts do cover instead of guessing."
)


def llm_answer(question, facts):
    if not LLM_BASE_URL:
        return None
    payload = {
        "model": LLM_NAME or "swiss-ai/Apertus-v1.5-8B",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Facts from the Gaia DR3 nearby stars dataset:\n{facts}\n\nQuestion: {question}",
            },
        ],
        "temperature": 0.3,
        "max_tokens": 220,
    }
    req = urllib.request.Request(
        LLM_BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        return body["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


def answer(question):
    facts, direct, focus = retrieve(question)
    polished = llm_answer(question, facts)
    if polished:
        return {
            "answer": polished,
            "source": "apertus",
            "facts": facts,
            "focus": focus_payload(focus),
        }
    return {
        "answer": direct,
        "source": "data-fallback",
        "facts": facts,
        "focus": focus_payload(focus),
    }


def stars_payload():
    """All stars with 3D positions, for the star map. Compact keys."""
    return [
        {
            "id": s["source_id"],
            "n": s["name"] or "",
            "x": s["x"],
            "y": s["y"],
            "z": s["z"],
            "d": round(s["distance_ly"], 2),
            "m": s["g_mag"],
            "c": s["bp_rp"],
            "t": s["teff_k"],
        }
        for s in STARS
    ]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._send(
                200,
                json.dumps(
                    {
                        "status": "ok",
                        "stars": len(STARS),
                        "max_distance_ly": round(MAX_LY, 1),
                        "llm_configured": bool(LLM_BASE_URL),
                        "llm_name": LLM_NAME or None,
                    }
                ),
            )
        elif path == "/stars.json":
            self._send(200, json.dumps(stars_payload()))
        elif path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/three.min.js":
            # Vendored Three.js (MIT licence), served locally so the app
            # works with no network at all.
            with open(os.path.join(STATIC, "three.min.js"), "rb") as f:
                self._send(200, f.read(), "application/javascript; charset=utf-8")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            question = str(body.get("question", "")).strip()
        except (ValueError, TypeError):
            question = ""
        if not question:
            self._send(400, json.dumps({"error": "send JSON with a 'question' field"}))
            return
        self._send(200, json.dumps(answer(question)))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"nearby-stars: {len(STARS)} stars loaded, llm={'yes' if LLM_BASE_URL else 'no'}, port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
