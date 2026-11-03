#!/usr/bin/env python3
r"""Phase B: run the Phase A extractor over the ENTIRE corpus, resumably.

WHY THIS SHAPE
--------------
The corpus is ~240,000 10-K and 10-Q filings in 15 GB of zips that live on Brian's
machine and cannot be staged anywhere else (the transfer limit is 400 MB a file). That
machine gives each command about three minutes and kills every process when the command
returns, so nothing can run in the background. The sweep therefore has to be a series of
short, independent calls, any of which can be cut off without losing work:

  * the corpus is enumerated ONCE into a fixed manifest, so every call agrees on what
    "filing 104,000" means
  * work is done in chunks, and each finished chunk is written to its own file through a
    temp-file-and-rename, so a call killed mid-chunk leaves nothing half-written
  * `--mode next` simply finds the first chunk with no file and does it, then the next,
    until its time budget is spent -- re-running it is always safe

THE SAME CODE AS PHASE A
------------------------
Every candidate row is produced by `extract_asu_v2_Claude.candidate_rows()`, the function
the Phase A run itself calls (refactored out of its main() on 21 September and shown to
produce byte-identical output). Nothing about the method is re-implemented here.

Two cores, so two worker processes.

STEPS, IN ORDER
---------------
    --mode manifest   list every 10-K and 10-Q in the corpus (seconds; run once)
    --mode fye        read every 10-K header for the firm's fiscal year end, which
                      the period conversion needs (header only, fast; resumable)
    --mode next       extract the next chunks until --budget seconds are used
    --mode status     how far along it is

Writes: sweep_manifest_Claude.csv, sweep_fye_Claude.csv
        sweep_parts/cand_NNNNNNN.csv   candidate rows, one file per chunk
        sweep_parts/log_NNNNNNN.csv    one row per filing read -- the denominators
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import multiprocessing as mp
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import extract_asu_v2_Claude as E

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
ZIPS = ["10-X_C_2016-2020.zip", "10-X_C_2021.zip", "10-X_C_2022.zip",
        "10-X_C_2023.zip", "10-X_C_2024.zip"]
MANIFEST = HERE / "sweep_manifest_Claude.csv"
FYE = HERE / "sweep_fye_Claude.csv"
PARTS = HERE / "sweep_parts"
NAME = re.compile(r"(\d{8})_(10-[KQ])_edgar_data_(\d+)_(.+)\.txt$")
LOGF = ["accession", "cik", "form", "filing_date", "company", "period_of_report",
        "n_candidates", "n_clean", "max_score", "max_clean_score"]


# ------------------------------------------------------------------ manifest
def do_manifest():
    rows = []
    for zp in ZIPS:
        p = HERE / zp
        if not p.exists():
            print(f"  (missing {zp})")
            continue
        with zipfile.ZipFile(p) as z:
            n = 0
            for name in z.namelist():
                m = NAME.search(name)
                if not m:
                    continue
                rows.append({"zip": zp, "name": name, "filing_date": m.group(1),
                             "form": m.group(2), "cik": m.group(3).lstrip("0"),
                             "accession": m.group(4)})
                n += 1
        print(f"  {zp}: {n:,} filings")
    rows.sort(key=lambda r: (r["zip"], r["name"]))
    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {MANIFEST.name}: {len(rows):,} filings, "
          f"{len({r['cik'] for r in rows}):,} firms")
    print("  by form:", dict(collections.Counter(r["form"] for r in rows)))
    print("  amendments (10-K/A, 10-Q/A) are not in the corpus naming and are excluded")


def manifest():
    return list(csv.DictReader(MANIFEST.open(encoding="utf-8")))


# ----------------------------------------------------------------------- fye
def do_fye(budget):
    """Fiscal year end per firm per year, from 10-K headers only -- no full read."""
    done = {}
    if FYE.exists():
        for r in csv.DictReader(FYE.open(encoding="utf-8")):
            done[(r["cik"], r["accession"])] = r
    todo = [r for r in manifest() if r["form"] == "10-K"
            and (r["cik"], r["accession"]) not in done]
    t0, out = time.time(), []
    byzip = collections.defaultdict(list)
    for r in todo:
        byzip[r["zip"]].append(r)
    for zp, rs in byzip.items():
        with zipfile.ZipFile(HERE / zp) as z:
            for r in rs:
                if time.time() - t0 > budget:
                    break
                try:
                    with z.open(r["name"]) as fh:
                        head = fh.read(6000).decode("utf-8", errors="replace")
                except Exception:
                    continue
                por = E.header_fields(head).get("period_of_report", "")
                out.append({"cik": r["cik"], "accession": r["accession"],
                            "period_of_report": por})
        if time.time() - t0 > budget:
            break
    new = not FYE.exists()
    with FYE.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["cik", "accession", "period_of_report"])
        if new:
            w.writeheader()
        w.writerows(out)
    left = len(todo) - len(out)
    print(f"fye: read {len(out):,} 10-K headers in {time.time()-t0:.0f}s; "
          f"{left:,} still to do" + ("" if left else "  -- COMPLETE"))


def load_fye():
    fye = collections.defaultdict(dict)
    if not FYE.exists():
        return fye
    for r in csv.DictReader(FYE.open(encoding="utf-8")):
        por = r["period_of_report"]
        if len(por) == 8 and por.isdigit():
            try:
                d = dt.date(int(por[:4]), int(por[4:6]), int(por[6:]))
            except ValueError:
                continue
            fye[r["cik"]][d.year] = d
    return fye


# -------------------------------------------------------------------- worker
_Z, _FYE_FOR, _POP = {}, None, {}


def _init():
    global _FYE_FOR, _POP
    _POP = E.load_population("di")
    _FYE_FOR = E.make_fye_for(load_fye(), _POP)


def _zip(zp):
    z = _Z.get(zp)
    if z is None:
        z = _Z[zp] = zipfile.ZipFile(HERE / zp)
    return z


def work(r):
    try:
        raw = _zip(r["zip"]).read(r["name"]).decode("utf-8", errors="replace")
    except Exception:
        return None, []
    hdr = E.header_fields(raw)
    flat = re.sub(r"\s+", " ", E.strip_header(raw))
    cands = E.candidates_for(flat)
    rows = []
    if cands:
        f = dict(cik=r["cik"], name=r["name"], hdr=hdr, cands=cands, form=r["form"])
        for x in E.candidate_rows(f, _FYE_FOR, _POP.get(r["cik"], {})):
            x["accession"] = r["accession"]
            rows.append(x)
    clean = [x for x in rows if not x.get("fp_family")]
    log = {"accession": r["accession"], "cik": r["cik"], "form": r["form"],
           "filing_date": r["filing_date"], "company": hdr.get("company", "")[:80],
           "period_of_report": hdr.get("period_of_report", ""),
           "n_candidates": len(rows), "n_clean": len(clean),
           "max_score": max((int(x["score"]) for x in rows), default=""),
           "max_clean_score": max((int(x["score"]) for x in clean), default="")}
    return log, rows


# ---------------------------------------------------------------------- next
def part(kind, start):
    return PARTS / f"{kind}_{start:07d}.csv"


def write_atomic(path, fields, rows):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def do_next(budget, size, workers):
    PARTS.mkdir(exist_ok=True)
    rows = manifest()
    starts = [s for s in range(0, len(rows), size) if not part("log", s).exists()]
    if not starts:
        print("all chunks done -- the sweep is COMPLETE")
        return
    t0, per_chunk, n_done = time.time(), None, 0
    with mp.Pool(workers, initializer=_init) as pool:
        for s in starts:
            left = budget - (time.time() - t0)
            if per_chunk and left < per_chunk * 1.15:
                break
            c0 = time.time()
            res = pool.map(work, rows[s:s + size], chunksize=20)
            logs = [l for l, _ in res if l]
            cands = [x for _, rs in res for x in rs]
            write_atomic(part("cand", s), E.FIELDS + ["accession"], cands)
            write_atomic(part("log", s), LOGF, logs)   # log last = chunk is done
            per_chunk = time.time() - c0
            n_done += 1
            print(f"  chunk {s:>7,}-{s+size-1:<7,} {len(logs):>5} filings, "
                  f"{sum(1 for l in logs if l['n_candidates']):>4} flagged, "
                  f"{len(cands):>5} candidates  {per_chunk:5.0f}s "
                  f"({len(logs)/per_chunk:.0f}/s)")
    do_status(size)


def do_status(size):
    rows = manifest()
    total = (len(rows) + size - 1) // size
    done = sum(1 for s in range(0, len(rows), size) if part("log", s).exists())
    print(f"\nprogress: {done} of {total} chunks ({done/total:.0%}), "
          f"{min(done*size, len(rows)):,} of {len(rows):,} filings")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=("manifest", "fye", "next", "status"))
    ap.add_argument("--budget", type=float, default=150)
    ap.add_argument("--size", type=int, default=2000,
                    help="filings per chunk; fixed once the sweep has started")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.mode == "manifest":
        do_manifest()
    elif a.mode == "fye":
        do_fye(a.budget)
    elif a.mode == "next":
        do_next(a.budget, a.size, a.workers)
    else:
        do_status(a.size)


if __name__ == "__main__":
    main()
