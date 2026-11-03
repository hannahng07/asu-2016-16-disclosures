#!/usr/bin/env python3
r"""Option C: price the anchor widening before paying for a 238,961-filing re-sweep.

WHY
---
Bristol-Myers Squibb writes "an 853 million deferred tax charge resulting from an INTERNAL
TRANSFER of certain intangible assets to the U.S." -- an intra-entity transfer of IP,
stated without either of the words the anchor is built on. BMS was caught anyway, by the
"transfer of <adj> intangible assets TO" alternative. A firm that writes the same thing
without a following preposition would not be.

The question is what a widened anchor would ADD, and how much of the addition is junk.
Answering it by re-sweeping everything costs hours and produces a number nobody has a
denominator for. This measures the addition on a sample first.

THE TWO POPULATIONS PROBED, kept apart on purpose
-------------------------------------------------
    random    a fixed-seed sample of the corpus. Gives the UNBIASED added-yield rate and,
              more importantly, the junk rate -- the thing that decides whether the
              widening is safe to run over everything
    targeted  every filing of a firm that tagged ASU 2016-16 in XBRL, plus the Double
              Irish list. High prior, so it finds real misses fast -- but its yield rate
              means nothing for the corpus and must never be quoted as one

WHAT IS COUNTED
---------------
A filing is a GAIN when the widened anchor matches and the current anchor does not. The
matching sentence is written out so the junk rate can be read rather than assumed.

    --mode plan     build the target list
    --mode next     do the next chunk (resumable, atomic; repeat until done)
    --mode report   the two rates, with denominators, and the sentences to read
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys
import time
import zipfile
from pathlib import Path

import extract_asu_v2_Claude as E

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "sweep_manifest_Claude.csv"
FLAGS = HERE / "xbrl_firm_flags_Claude.csv"
DI = HERE / "di_firm_years_Claude.txt"
PLAN = HERE / "anchor_probe_plan_Claude.csv"
PARTS = HERE / "anchor_probe_parts"
OUT = HERE / "anchor_probe_gains_Claude.csv"
N_RANDOM = 12000
SEED = 20260922
SIZE = 1500

# ---------------------------------------------------------------- the widening
# Every alternative names the asset. "internal" alone is far too common a word -- it is
# internal controls, internal use software, internal investigations -- so it is never a
# literal the probe opens a window on by itself.
_NP = r"(?:[^.]|\\.(?=\\d))"
WIDE_EXTRA = re.compile(
    rf"internal\s+(?:transfers?|sales?)\s+of\s+{E._CERTAIN}{E._IPISH}|"
    rf"internal\s+(?:transfers?|sales?)\s+of\s+{E._CERTAIN}assets?|"
    rf"internally\s+transferr?ed\s+{E._CERTAIN}{E._IPISH}|"
    rf"transferr?ed\s+{E._CERTAIN}{E._IPISH}\s+internally|"
    rf"internal\s+(?:restructurings?|reorganizations?)\s+{_NP}{{0,80}}?{E._IPISH}",
    re.I)
NEED = ("internal",)


def wide_hits(flat: str):
    low = flat.lower()
    if "internal" not in low:
        return []
    out, pos = [], []
    i = low.find("internal")
    while i != -1:
        pos.append(i)
        i = low.find("internal", i + 1)
    spans, W = [], 400
    for p in pos:
        a, b = max(0, p - W), min(len(flat), p + W)
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    for a, b in spans:
        out.extend(WIDE_EXTRA.finditer(flat, a, b))
    return out


# ------------------------------------------------------------------- the plan
def do_plan():
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    targ = set()
    if FLAGS.exists():
        for r in csv.DictReader(FLAGS.open(encoding="utf-8")):
            targ.add(r["cik"].lstrip("0"))
    if DI.exists():
        for r in csv.DictReader(DI.open(encoding="utf-8"), delimiter="\t"):
            c = (r.get("cik") or "").lstrip("0")
            if c:
                targ.add(c)
    tr = [r for r in rows if r["cik"].lstrip("0") in targ]
    rest = [r for r in rows if r["cik"].lstrip("0") not in targ]
    random.Random(SEED).shuffle(rest)
    sample = rest[:N_RANDOM]
    plan = ([{**r, "arm": "targeted"} for r in tr] +
            [{**r, "arm": "random"} for r in sample])
    plan.sort(key=lambda r: (r["zip"], r["name"]))
    with PLAN.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(plan[0]))
        w.writeheader()
        w.writerows(plan)
    print(f"wrote {PLAN.name}: {len(plan):,} filings "
          f"({len(tr):,} targeted from {len(targ):,} firms, {len(sample):,} random)")
    print(f"   corpus is {len(rows):,} filings, so the random arm is "
          f"{len(sample)/len(rows):.1%} of it")
    print(f"   {(len(plan)+SIZE-1)//SIZE} chunks of {SIZE}")


_ZC = {}


def _zip(name):
    if name not in _ZC:
        _ZC[name] = zipfile.ZipFile(HERE / name)
    return _ZC[name]


def do_next(budget):
    PARTS.mkdir(exist_ok=True)
    plan = list(csv.DictReader(PLAN.open(encoding="utf-8")))
    todo = None
    for s in range(0, len(plan), SIZE):
        if not (PARTS / f"chunk_{s}.done").exists():
            todo = s
            break
    if todo is None:
        print("all chunks done")
        return
    chunk = plan[todo:todo + SIZE]
    t0, rows, n = time.time(), [], 0
    for r in chunk:
        if time.time() - t0 > budget:
            break
        n += 1
        try:
            raw = _zip(r["zip"]).read(r["name"]).decode("utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            continue
        flat = re.sub(r"\s+", " ", E.strip_header(raw))
        w = wide_hits(flat)
        if not w:
            continue
        cur = E.anchor_hits(flat)
        if cur:
            continue                      # already reachable: not a gain
        m = w[0]
        a, b = max(0, m.start() - 160), min(len(flat), m.end() + 320)
        rows.append({"arm": r["arm"], "cik": r["cik"], "form": r["form"],
                     "filing_date": r["filing_date"], "accession": r["accession"],
                     "match": m.group(0)[:120], "window": flat[a:b]})
    if n < len(chunk):
        print(f"  budget reached after {n} of {len(chunk)} -- rerun to finish this chunk")
        return
    tmp = PARTS / f"chunk_{todo}.tmp"
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w2 = csv.DictWriter(fh, fieldnames=["arm", "cik", "form", "filing_date",
                                            "accession", "match", "window"])
        w2.writeheader()
        w2.writerows(rows)
    os.replace(tmp, PARTS / f"chunk_{todo}.csv")
    (PARTS / f"chunk_{todo}.done").write_text(f"{len(chunk)}\n")
    done = sum(1 for s in range(0, len(plan), SIZE)
               if (PARTS / f"chunk_{s}.done").exists())
    total = (len(plan) + SIZE - 1) // SIZE
    print(f"chunk {todo}: {len(chunk)} filings, {len(rows)} gains "
          f"({time.time()-t0:.0f}s) -- {done}/{total} chunks")


def do_report():
    plan = list(csv.DictReader(PLAN.open(encoding="utf-8")))
    seen = {}
    for s in range(0, len(plan), SIZE):
        p = PARTS / f"chunk_{s}.csv"
        if not p.exists():
            continue
        for r in csv.DictReader(p.open(encoding="utf-8")):
            seen[(r["cik"], r["accession"])] = r
    done = sum(int((PARTS / f"chunk_{s}.done").read_text())
               for s in range(0, len(plan), SIZE)
               if (PARTS / f"chunk_{s}.done").exists())
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        rows = sorted(seen.values(), key=lambda r: (r["arm"], r["cik"], r["filing_date"]))
        w = csv.DictWriter(fh, fieldnames=["arm", "cik", "form", "filing_date",
                                           "accession", "match", "window"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.name}: {len(rows)} gained filings")
    for arm in ("random", "targeted"):
        den = sum(1 for r in plan[:done] if r["arm"] == arm)
        num = sum(1 for r in rows if r["arm"] == arm)
        firms = len({r["cik"] for r in rows if r["arm"] == arm})
        if den:
            print(f"   {arm:<10}{num:>5} gained of {den:,} read "
                  f"({num/den:.3%}), {firms} firms")
    print(f"\n   filings read so far: {done:,} of {len(plan):,} planned")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("plan", "next", "report"))
    ap.add_argument("--budget", type=float, default=140)
    a = ap.parse_args()
    {"plan": lambda: do_plan(), "next": lambda: do_next(a.budget),
     "report": lambda: do_report()}[a.mode]()


if __name__ == "__main__":
    main()
