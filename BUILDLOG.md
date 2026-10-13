# BUILDLOG: Hack Apertus, Track 2B "Own Project"

Project: **Nearby Stars, Plain Words**, a Dockerized web app that answers
beginner astronomy questions from a real Gaia DR3 nearby-stars dataset, with
the Apertus LLM (via an OpenAI-compatible endpoint set by env vars) phrasing
plain-language answers, and a deterministic data-only fallback when no LLM is
configured.

Team name for the report file: `rC` (solo, Ram Charan Polisetti).
Deadline: Fri Oct 16, 2026, 06:00 AM EDT. Build started Tue Oct 13, 2026 (EDT).

## Step 0: Requirements and template (done)

- Read `~/workspace/your_files/hackathon-requirements-oct-2026.md` section 1 and
  the template's own README files. Key constraints captured:
  - Keep `track_2b/` under its exact template name; delete the other track
    folders; repo must be PUBLIC.
  - `make run` must work from a clean checkout and run the project in Docker.
  - LLM config only via env vars `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`.
  - `data/` max 100 MB.
  - `technical_report.md` in the track folder; PDF export named
    `TeamName_Report.pdf` (here: `rC_Report.pdf`), max 6 pages.
  - Track 2B report must document a sovereign deployability option
    (on-premise / air-gapped / sovereign Swiss cloud).
  - Licensing: code Apache-2.0 (template LICENSE is Apache-2.0), docs CC-BY-4.0.
- Template cloned from https://github.com/HackApertus/project-template into
  `~/workspace/apertus-build/`. Template layout: root README + LICENSE, one
  folder per track, each with Makefile stub, README, technical_report.md stub,
  src/, data/, docs/.
- Decision: the template demonstrates no code stack for 2B (src/ is empty), so
  the app is written in **Python 3 standard library only** (http.server, csv,
  json, urllib). Rationale: zero third-party dependencies means the Docker
  build cannot fail on package downloads, the image is small, and the runtime
  story for the air-gapped architecture is clean. The LLM call is a plain
  HTTPS POST to an OpenAI-compatible `/chat/completions` endpoint.
- Decision: implement `make run` inside `track_2b/Makefile` (the template's own
  location) AND add a thin root `Makefile` that delegates into `track_2b/`, so
  `make run` works from both the repo root and the track folder. Nothing in the
  template is renamed or moved.
- Docker is NOT available on this build VM (`docker: command not found`).
  Docker verification will be done on rC's iMac over SSH (see TOOLS.md).

## Step 1: Template pruning (done)

- Deleted `track_1a/`, `track_1b/`, `track_2a/`. Kept `track_2b/` as-is.
- Root README replaced later with the project README; the template LICENSE
  (Apache-2.0) is kept.

## Step 2: Data: Gaia DR3 query (in progress)

See data section in the technical report for the exact ADQL and citation.

## Step 2: Data (done)

- ADQL sent to the public Gaia TAP sync service
  (https://gea.esac.esa.int/tap-server/tap/sync), first try succeeded:
  `SELECT TOP 2000 source_id, ra, dec, parallax, parallax_over_error,
  phot_g_mean_mag, bp_rp, teff_gspphot FROM gaiadr3.gaia_source
  WHERE parallax >= 66 AND parallax_over_error > 10 ORDER BY parallax DESC`
- Result: 1,113 rows (the parallax_over_error > 10 quality cut is what keeps
  it under the 2,000 cap). Raw result kept as `data/nearby_stars_raw.csv`.
- `src/prepare_data.py` computes distance_ly = (1000 / parallax_mas) * 3.26156
  and writes `data/nearby_stars.csv` sorted by distance (nearest: Proxima
  Centauri, 4.25 ly; farthest 49.4 ly). Total data size ~208 KB, far under
  the 100 MB cap.
- Common names: 25 candidate famous stars were matched by sky position
  (tolerance 0.15 deg) and cross-checked against their published distances
  (15 percent). 14 verified and kept (Proxima Centauri, Barnard's Star,
  Wolf 359, Lalande 21185, Sirius, Tau Ceti, Epsilon Eridani, 61 Cygni A/B,
  Epsilon Indi, Ross 128, TRAPPIST-1, Lacaille 9352, Luyten 726-8 A).
  11 dropped, mostly the very brightest stars (Alpha Centauri A/B, Procyon,
  Vega, Altair, Pollux, Arcturus, Capella, Denebola, Fomalhaut, Ross 154):
  they have no usable astrometric entry at their position in this extract, a
  known Gaia bright-star limitation. The app answers questions about seven of
  them from a clearly labelled reference table (Hipparcos textbook distances)
  and says plainly that they are not in the Gaia data.
- Known data wart, handled in the app: Gaia's G magnitude for Sirius in this
  extract is 8.5 (true value about -1.5); bright-star photometry saturates.
  The "brightest" answer carries a warning sentence about this.

## Step 3: App (done)

- `track_2b/src/app.py`: Python 3 standard library only (http.server).
  Endpoints: `GET /` (single-page UI in `src/static/index.html`),
  `POST /ask` with JSON {"question": ...}, `GET /health`.
- Retrieval intents: closest stars, brightest stars, hottest stars,
  count within N light years or parsecs, named-star lookup, plus a help
  answer. Facts are composed from the CSV; nothing is invented.
- LLM: if `LLM_BASE_URL` is set, POSTs to `<base>/chat/completions` with
  `LLM_NAME` (default swiss-ai/Apertus-v1.5-8B), bearer `LLM_API_KEY`, a
  beginner-friendly system prompt (facts only, plain words, no em dashes),
  temperature 0.3. Any error or missing config returns the deterministic
  answer instead. The JSON response carries `source`: "apertus" or
  "data-fallback", and the retrieved `facts`.
- `track_2b/Dockerfile`: python:3.12-slim, copies src/ and data/, runs the
  app on port 8000. No pip installs at build time.
- Makefiles: `track_2b/Makefile` builds and runs the container, forwarding
  the three LLM env vars; root `Makefile` delegates into track_2b.

## Step 4: Native tests (done, this VM)

Fallback mode (no env vars), server on port 8000:
- GET /health -> {"status": "ok", "stars": 1113, "max_distance_ly": 49.4,
  "llm_configured": false}
- "What is the closest star to us?" -> Proxima Centauri 4.2 ly, Barnard's
  Star 6.0 ly, Wolf 359 7.9 ly. Correct.
- "Which nearby stars are brightest?" -> top-5 by Gaia G magnitude plus the
  Sirius saturation warning.
- "How far is Vega?" -> explains Vega is too bright for Gaia in this
  extract; textbook distance about 25 light years.
LLM mode, against a local mock OpenAI-compatible endpoint on :9999:
- "How far is Tau Ceti?" -> mock verified it received the model name and the
  retrieved facts; app returned source "apertus".
- Same question with LLM_BASE_URL pointing at a dead port -> app returned
  the data answer with source "data-fallback". Fallback on failure verified.
- One process-management mishap during testing: a `pkill -f` pattern matched
  the test shell itself and killed the first mock-test run. Re-ran with
  PID-based cleanup; no project files affected.

## Step 5: Docker test (in progress, on the iMac)

## Step 5: Docker test (done, on the iMac)

- No Docker on this VM, so the project was copied to /tmp/apertus-test on
  rC's iMac and tested there.
- First attempt as the regular user failed: permission denied on the Docker
  socket (an iMac user-permissions quirk, not a project fault). Re-ran with
  sudo.
- Result: `make run` from track_2b built the image
  (nearby-stars-plain-words:latest, python:3.12-slim) and started the
  container on port 8000. Verified live: GET /health and POST /ask both
  answered from inside the container. The root Makefile delegation was also
  exercised; its first failure was the same Docker-socket permission issue.
- The test container was left running on the iMac at the moment work was
  paused (see pivot note). It is a throwaway test copy in /tmp, not the
  submission.

## PIVOT: 2026-10-13 ~14:20 EDT: building paused by rC

- rC asked for a brainstorm BEFORE the project is chosen. All building,
  publishing and submitting stopped. Nothing was pushed to GitHub; no
  technical report or PDF was written; no video script yet.
- State of the partial build, left untouched in ~/workspace/apertus-build/:
  template pruned to track_2b; app complete and tested natively (fallback,
  mock-LLM and dead-endpoint modes all verified); data complete
  (1,113 Gaia DR3 stars); Dockerfile + Makefiles written and Docker-verified
  on the iMac. Remaining if this concept is chosen: technical_report.md,
  rC_Report.pdf, GitHub publish, video script, submission form.
- Brainstorm deliverable: ~/workspace/your_files/apertus-brainstorm.md

## Brainstorm phase (2026-10-13, after the pivot)

- Read the four official track READMEs from the template's git history
  (working tree untouched): 1A is a findings submission (up to 5 issues;
  favoured topics include bias and factual incorrectness), 1B is a Swiss
  localisation evaluation (dialects, domain factuality, alignment), 2A has
  five named academia challenges (FHGR, OpenParlData, OST, UZH, ZHAW;
  ZHAW needs robot hardware, out of scope), 2B is the open own-project
  track with the three sovereign architectures.
- Wrote ~/workspace/your_files/apertus-brainstorm.md: 8 candidates, at
  least one per track, each with data source, Apertus's role, honest hour
  estimate, fit against the five judging criteria, and risks. Nearby Stars
  included as Candidate 7 with no favouritism; ranked honestly against a
  1A bias red-team (Candidate 2) that plays to rC's evaluation background.
- No building, publishing, or pushing was done in this phase.

## RESUMED: 2026-10-13 ~17:26 EDT: rC picked Candidate 7

- rC chose "Nearby Stars, Plain Words" (Track 2B). Remaining work: repo
  hygiene, technical report + rC_Report.pdf, clean-checkout Docker
  re-verification, GitHub publish, video script, submission-fields prep.
  The hackathon form itself is NOT submitted (demo video URL still needed).

## Step 6: Repo hygiene (done)

- Confirmed layout: only `track_2b/` remains, under its exact template name;
  other track folders already deleted (Step 1). Root `Makefile` delegates
  into `track_2b/`; `track_2b/Makefile` does the Docker build and run.
- LICENSE at repo root verified: Apache License, Version 2.0.
- `data/` total: 208 KB (raw + prepared CSV), far under the 100 MB cap.
- Dataset facts re-verified from `data/nearby_stars.csv`: 1,113 rows,
  14 with verified common names, 518 with a GSP-Phot temperature, 8 stars
  within 10 ly, nearest Proxima Centauri at 4.25 ly, farthest 49.37 ly.
- Em-dash sweep: `src/app.py`, `src/prepare_data.py` and
  `src/static/index.html` contain no em dashes. The remaining hits were in
  template files (root README, track_2b/README.md, technical_report.md
  stub), all replaced in Steps 6-7 with new text written without em dashes.
- Root README.md replaced with the project README (what it is, `make run`,
  env vars, data citation + exact ADQL, licences). `track_2b/README.md`
  carries the same project README so the project root folder is
  self-describing.

## Step 7: Technical report and PDF (done)

- `track_2b/technical_report.md` rewritten in full, following the template
  stub's section structure: Summary, Architecture (with the mandatory
  Target architecture subsection naming on-premise (a) and air-gapped
  (b), with build-time vs runtime separated), Use of Apertus (model
  swiss-ai/Apertus-v1.5-8B, env-var config, strict facts-only system
  prompt, fallback behaviour), Data (exact ADQL, quality cuts, verified
  name matching, bright-star gaps), Evaluation (five sample Q&As captured
  fresh natively on 2026-10-13 plus the three-mode test table),
  Limitations (narrow intents, Sirius saturation, mock-endpoint caveat,
  518/1,113 temperature coverage, 1/parallax approximation),
  Reproducibility, Next steps, References (Gaia DR3 A&A 674, A1 + the
  full ESA/DPAC acknowledgement).
- Sample Q&A evidence captured natively before writing: closest stars,
  Tau Ceti (11.9 ly), Vega (honest reference-table answer), brightest
  (with Sirius warning), count within 10 ly (8). All match the CSV.
- PDF export: Markdown -> HTML -> WeasyPrint (in ~/workspace/.venv;
  `markdown` package confirmed present, no LaTeX/pandoc on this VM).
  Output `rC_Report.pdf`: **4 pages** (limit 6), page numbers in the
  footer. A copy sits at the repository root (per the finish-task
  instructions) and in `track_2b/` (per the track README instruction to
  upload the PDF into the track directory).

## Step 8: Clean-checkout Docker re-verification (done, on the iMac)

- Method: `git archive HEAD` of the final committed tree, copied to the
  iMac, extracted fresh at /tmp/apertus-clean. Nothing from the working
  tree or the old Step 5 test copy leaked into the test.
- Access note: this build VM runs exec as root, whose passwd home is
  /root, so plain `ssh imac` never read /home/hatch/.ssh/config (the
  alias + tailnet ProxyCommand live there) and direct connections were
  reset by the egress proxy. Working form, for future runs:
  `ssh -F /home/hatch/.ssh/config -i /home/hatch/.ssh/id_ed25519
  -o UserKnownHostsFile=<file> imac` (iMac host key fingerprint
  SHA256:p1DF1zvB7ZwO9FNXzVIvRXrMPJ++9OhOmMm23uB/IV8, accepted once via
  accept-new on this documented path).
- First `make run` attempt failed at `docker run` (Error 125): the
  leftover Step 5 test container (8e7d7763544a, up 3 hours) still held
  port 8000. It was stopped and removed; this was test litter, not a
  project fault.
- Second attempt, `make run` from the repository root of the clean
  checkout: image built (nearby-stars-plain-words:latest), container
  started, and from the iMac itself:
  - GET /health -> {"status": "ok", "stars": 1113,
    "max_distance_ly": 49.4, "llm_configured": false}
  - POST /ask "How far is Tau Ceti?" -> "Tau Ceti is 11.9 light years
    away; apparent magnitude 3.3 in the Gaia G band.",
    source "data-fallback"
- Test container stopped and removed afterwards; the /tmp test copy was
  deleted. The iMac's own stacks (Immich, Nextcloud AIO) were untouched
  and healthy throughout.

## Step 9: Publish and submission prep (done)

- GitHub repo created with `gh` and pushed:
  https://github.com/ram-polisetti/apertus-nearby-stars
  Public, default branch `main`. GitHub detects the licence as
  Apache-2.0 (verified via the API and on the repo page, which also
  renders the project README). Root contents: README.md, LICENSE,
  Makefile, BUILDLOG.md, rC_Report.pdf, track_2b/ (with
  technical_report.md, rC_Report.pdf, Dockerfile, src/, data/).
- Video script written to ~/workspace/your_files/apertus-video-script.md
  (timed sections, second ranges, on-screen action plus spoken lines,
  about 1:55 at a natural pace, one-take friendly).
- Submission fields pre-filled in
  ~/workspace/your_files/apertus-submission-fields.md: track 2B, repo
  URL, report filename rC_Report.pdf (4 pages), project descriptions,
  contact, architecture. Only the demo video URL is open; the form
  itself was NOT submitted.
- Em-dash sweep repeated over all repo text after these edits,
  including this log: zero em dashes remain in the repository.
