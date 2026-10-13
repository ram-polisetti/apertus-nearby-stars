#!/usr/bin/env python3
"""Prepare the nearby-stars dataset for the app.

Reads data/nearby_stars_raw.csv (the Gaia DR3 TAP result), computes distances,
attaches common names to well-known stars by coordinate matching (each
candidate is verified: a Gaia source must sit within TOL_DEG of the reference
position and its parallax must imply a distance within 15 percent of the
reference distance), and writes data/nearby_stars.csv.

Reference positions/distances are the widely published J2000 values for these
stars (e.g. from the Research Consortium on Nearby Stars list and SIMBAD).
Any candidate that fails verification is dropped and reported on stdout.
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
RAW = os.path.join(DATA, "nearby_stars_raw.csv")
OUT = os.path.join(DATA, "nearby_stars.csv")
LY_PER_PC = 3.26156
TOL_DEG = 0.15

# name, ra_deg (J2000), dec_deg (J2000), reference distance in light years
FAMOUS = [
    ("Proxima Centauri", 217.3935, -62.6761, 4.25),
    ("Alpha Centauri A", 219.9009, -60.8344, 4.37),
    ("Alpha Centauri B", 219.9134, -60.8374, 4.37),
    ("Barnard's Star", 269.4521, 4.6933, 5.96),
    ("Wolf 359", 164.1203, 7.0025, 7.86),
    ("Lalande 21185", 165.8327, 35.9699, 8.31),
    ("Sirius", 101.2872, -16.7161, 8.60),
    ("Procyon", 114.8255, 5.2250, 11.46),
    ("Tau Ceti", 26.0170, -15.9396, 11.91),
    ("Epsilon Eridani", 53.2327, -9.4583, 10.48),
    ("61 Cygni A", 316.7176, 38.7415, 11.41),
    ("61 Cygni B", 316.7303, 38.7233, 11.41),
    ("Epsilon Indi", 330.8376, -56.7857, 11.87),
    ("Ross 128", 176.9351, 0.8044, 11.03),
    ("Altair", 297.6958, 8.8683, 16.73),
    ("Vega", 279.2347, 38.7837, 25.04),
    ("Fomalhaut", 344.4127, -29.6222, 25.13),
    ("Pollux", 116.3289, 28.0262, 33.78),
    ("Arcturus", 213.9153, 19.1824, 36.71),
    ("Capella", 79.1723, 45.9980, 42.92),
    ("TRAPPIST-1", 346.6224, -5.0414, 39.46),
    ("Denebola", 177.2650, 14.5721, 36.20),
    ("Lacaille 9352", 346.4730, -35.8530, 10.74),
    ("Ross 154", 277.4619, -23.8367, 9.69),
    ("Luyten 726-8 A", 24.7544, -17.9860, 8.73),
]


def main():
    with open(RAW, newline="") as f:
        rows = list(csv.DictReader(f))
    stars = []
    for r in rows:
        try:
            plx = float(r["parallax"])
            ra = float(r["ra"])
            dec = float(r["dec"])
        except (TypeError, ValueError):
            continue
        if plx <= 0:
            continue
        dist_pc = 1000.0 / plx
        stars.append(
            {
                "source_id": r["source_id"],
                "ra": f"{ra:.6f}",
                "dec": f"{dec:.6f}",
                "parallax_mas": f"{plx:.3f}",
                "distance_ly": f"{dist_pc * LY_PER_PC:.2f}",
                "g_mag": r["phot_g_mean_mag"] or "",
                "bp_rp": r["bp_rp"] or "",
                "teff_k": r["teff_gspphot"] or "",
                "name": "",
                "_ra": ra,
                "_dec": dec,
                "_dly": dist_pc * LY_PER_PC,
            }
        )
    matched, dropped = [], []
    used = set()
    for name, cra, cdec, cref in FAMOUS:
        best, best_sep = None, 1e9
        for s in stars:
            if s["source_id"] in used:
                continue
            sep = math.hypot(
                (s["_ra"] - cra) * math.cos(math.radians(cdec)), s["_dec"] - cdec
            )
            if sep < best_sep:
                best, best_sep = s, sep
        if best is not None and best_sep <= TOL_DEG and abs(best["_dly"] - cref) / cref <= 0.15:
            best["name"] = name
            used.add(best["source_id"])
            matched.append(f"{name}: sep {best_sep:.3f} deg, {best['_dly']:.2f} ly")
        else:
            dropped.append(
                f"{name}: nearest sep {best_sep:.3f} deg"
                + (f", dist {best['_dly']:.2f} ly vs ref {cref}" if best else "")
            )
    stars.sort(key=lambda s: s["_dly"])
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["source_id", "ra", "dec", "parallax_mas", "distance_ly", "g_mag", "bp_rp", "teff_k", "name"]
        )
        for s in stars:
            w.writerow(
                [s["source_id"], s["ra"], s["dec"], s["parallax_mas"], s["distance_ly"],
                 s["g_mag"], s["bp_rp"], s["teff_k"], s["name"]]
            )
    print(f"wrote {len(stars)} stars to {OUT}")
    print(f"named matches: {len(matched)}")
    for m in matched:
        print("  OK  ", m)
    for d in dropped:
        print("  DROP", d)


if __name__ == "__main__":
    sys.exit(main())
