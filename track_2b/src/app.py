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
import os
import re
import urllib.error
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
            except ValueError:
                continue
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


def retrieve(question):
    """Return (facts_text, direct_answer). Pure data work, no LLM involved."""
    q = " ".join(question.lower().strip().split())

    # Named-star lookup first: "how far is sirius", "tell me about tau ceti".
    for name, s in NAMED.items():
        if name in q:
            return describe(s), describe(s)
    for key, (label, ly) in REFERENCE_ONLY.items():
        if key in q:
            text = (
                f"{label} is one of the very brightest stars in the sky, and Gaia "
                f"cannot measure stars that bright accurately, so it is not in this "
                f"Gaia dataset. Its textbook distance (from the Hipparcos mission) "
                f"is about {ly:.0f} light years."
            )
            return text, text

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
        return text, text

    if "closest" in q or "nearest" in q:
        top = STARS[:3]
        text = "The closest stars to the Sun in this dataset are: " + " ".join(
            f"{i + 1}. {describe(s)}" for i, s in enumerate(top)
        )
        text += (
            " The Sun itself is not in the list, since Gaia measures other stars "
            "as seen from our solar system."
        )
        return text, text

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
        return text, text

    if "hottest" in q or "temperature" in q:
        hot = sorted(
            (s for s in STARS if s["teff_k"]), key=lambda s: s["teff_k"], reverse=True
        )[:3]
        text = "The hottest stars in this nearby dataset are: " + " ".join(
            f"{i + 1}. {describe(s)}" for i, s in enumerate(hot)
        )
        return text, text

    if "how far" in q or "distance" in q:
        text = (
            "Ask me about a specific star by name, for example Sirius, Vega, "
            "Tau Ceti or TRAPPIST-1, and I will look it up. The closest star in "
            f"the data is {describe(STARS[0])}"
        )
        return text, text

    text = (
        f"This dataset holds {len(STARS)} real stars measured by the Gaia "
        f"space telescope, out to {MAX_LY:.0f} light years. You can ask: what "
        "is the closest star, which nearby stars are brightest, how far is a "
        "named star such as Sirius or Tau Ceti, or how many stars lie within "
        "10 light years."
    )
    return text, text


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
    facts, direct = retrieve(question)
    polished = llm_answer(question, facts)
    if polished:
        return {"answer": polished, "source": "apertus", "facts": facts}
    return {"answer": direct, "source": "data-fallback", "facts": facts}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
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
        elif self.path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
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
