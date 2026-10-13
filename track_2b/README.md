# Nearby Stars, Plain Words

**Hack Apertus, Track 2B (Own Project). Team rC (solo): Ram Charan Polisetti.**

A small web app that answers beginner astronomy questions from a real
dataset: the 1,113 stars nearest to the Sun, measured by the Gaia space
telescope (Gaia DR3). You ask things like "What is the closest star?",
"How far is Tau Ceti?" or "How many stars are within 10 light years?",
and the app looks the facts up in the data first. Only then, if an
Apertus endpoint is configured, does the language model phrase the
answer in plain words. The model never invents numbers: it receives the
retrieved facts and a strict instruction to use only those facts.

If no endpoint is configured, or the endpoint call fails, the app still
answers. A deterministic fallback builds the answer directly from the
same facts. That makes the app fully usable offline and in an
air-gapped deployment, which is the point of the design: the language
model improves the wording, never the truth.

The honest edges of the data are part of the app. Gaia cannot measure
the very brightest stars accurately, so seven famous names (Vega, Alpha
Centauri, Procyon, Altair, Pollux, Arcturus, Capella) are not in this
Gaia extract. The app says so plainly and gives their textbook
(Hipparcos) distances from a clearly labelled reference table. Gaia's
brightness value for Sirius is also wrong in this extract (detector
saturation), and the "brightest stars" answer carries a warning about
that.

## Run it

Judges: from a clean checkout of this repository, at the repository
root (or inside `track_2b/`), run:

```bash
make run
```

This builds a Docker image (`python:3.12-slim`, no packages installed;
the app is Python 3 standard library only) and starts the app on port
8000. Then open http://localhost:8000 or use the API:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "How far is Tau Ceti?"}'
```

To have answers phrased by Apertus, set the three environment variables
before `make run` (the Makefile forwards them into the container):

```bash
export LLM_NAME=swiss-ai/Apertus-v1.5-8B
export LLM_BASE_URL=https://your-apertus-endpoint/v1
export LLM_API_KEY=your-key
make run
```

`LLM_BASE_URL` must be an OpenAI-compatible endpoint (the app POSTs to
`<LLM_BASE_URL>/chat/completions`). Leave all three unset to run the
data-only fallback. Every `/ask` response says which path answered, in
its `source` field: `apertus` or `data-fallback`, and includes the
retrieved `facts`.

Without Docker, the app also runs directly:
`python3 track_2b/src/app.py` (port 8000).

## The data

Source: ESA Gaia DR3, retrieved from the public Gaia TAP service
(https://gea.esac.esa.int/tap-server/tap/sync) with this ADQL query:

```sql
SELECT TOP 2000 source_id, ra, dec, parallax, parallax_over_error,
phot_g_mean_mag, bp_rp, teff_gspphot FROM gaiadr3.gaia_source
WHERE parallax >= 66 AND parallax_over_error > 10
ORDER BY parallax DESC
```

The quality cut (parallax_over_error > 10) leaves 1,113 stars, all
within about 15 parsecs (49.4 light years). `track_2b/src/prepare_data.py`
computes distances from parallax (distance = 1000 / parallax_mas
parsecs, times 3.26156 for light years) and attaches common names to 14
well-known stars. Each name had to pass two checks: a Gaia source
within 0.15 degrees of the star's published position, and a
Gaia-derived distance within 15 percent of the published distance.
Eleven candidates failed and were dropped, mostly the very brightest
stars, which is a known Gaia limitation. The raw TAP result is kept in
`track_2b/data/nearby_stars_raw.csv`; the app uses
`track_2b/data/nearby_stars.csv`. Total data size: about 208 KB.

Dataset citation: ESA Gaia mission, Data Release 3. Gaia Collaboration
et al., "Gaia Data Release 3: Summary of the content and survey
properties", Astronomy & Astrophysics 674, A1 (2023). This work has
made use of data from the European Space Agency (ESA) mission Gaia
(https://www.cosmos.esa.int/gaia), processed by the Gaia Data
Processing and Analysis Consortium (DPAC,
https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the
DPAC has been provided by national institutions, in particular the
institutions participating in the Gaia Multilateral Agreement.

## Layout

| Path | What it is |
| --- | --- |
| `track_2b/src/app.py` | The whole app: retrieval, fallback, LLM phrasing, HTTP server |
| `track_2b/src/prepare_data.py` | Builds `nearby_stars.csv` from the raw TAP result |
| `track_2b/src/static/index.html` | The single-page web UI |
| `track_2b/data/` | Raw and prepared Gaia DR3 extracts (about 208 KB) |
| `track_2b/Dockerfile`, `track_2b/Makefile` | Container build and `make run` |
| `track_2b/technical_report.md` | The technical report (PDF: `rC_Report.pdf`) |

## Sovereign deployment

The project targets the on-premise and air-gapped architectures (see
the technical report for the full section). In short: the container
needs no network access at runtime. Point `LLM_BASE_URL` at an Apertus
endpoint served on your own infrastructure (for example a local
vLLM or SGLang deployment of the open Apertus weights), or unset it and
run data-only. No question ever has to leave the building.

## Licence

Code: Apache License 2.0 (see `LICENSE`). Documentation: CC BY 4.0.
The derived dataset in `track_2b/data/` is released under
CDLA-Permissive-2.0; the underlying measurements are ESA Gaia DR3 data,
used with the acknowledgement above.
