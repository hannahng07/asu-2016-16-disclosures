#!/usr/bin/env python3
r"""Phase B gate: the first precision measurement this project has ever had.

WHY THIS IS THE GATE
--------------------
Detection has two clauses -- *was this filing correctly identified as carrying a
transfer disclosure, and was one not there wrongly claimed?* Only the first has ever
been tested. Every rate in Phase A is RECALL, measured on firms already known to have
transferred IP: 81% detection, 84% on the gold tickers, 72% on the Irish B1s. A pattern
running 84% recall and 40% precision would be identical in all of them.

Phase B sweeps roughly 200,000 filings of firms that mostly did not transfer anything.
At that scale precision is what decides whether the output is a population or a pile.

WHAT IS MEASURED, AND WHAT IS NOT
----------------------------------
This measures PRECISION ONLY: of the filings the anchor flags, how many really carry a
transfer disclosure. It says nothing about recall on the full population, because that
would mean reading the filings the anchor did NOT flag -- thousands of them, almost all
empty. Precision is the cheap half and the half that gates the sweep.

THE SAMPLE
----------
Drawn at random from every 10-K and 10-Q in the Loughran-McDonald corpus whose CIK is
NOT in the Double Irish population and NOT already in the Phase A candidate set. Those
firms are where the pattern was built; including them would measure the fit, not the
method.

Stratified by filing year and the year is carried on every row, so the result can be
re-cut to 2018-2021 -- where the disclosures cluster -- without drawing a new sample.
Seed is fixed at 20260920 so the same sample comes back on a re-run.

WHAT COMES OUT
--------------
One row per CANDIDATE, not per filing, because a filing can be flagged for more than
one reason and each reason is separately right or wrong. Every row carries the sentence
the anchor matched, its score, its amount, whether it looks like table residue, and
enough provenance to open the filing. Nothing is adjudicated here: the verdict column
is left empty for reading.

    --mode sample   enumerate the corpus, draw the sample, write it
    --mode run      read the sampled filings, emit every candidate

Writes: phaseB_sample_Claude.csv    the drawn sample, one row per filing
        phaseB_hits_Claude.csv      one row per candidate, for adjudication
        phaseB_readlog_Claude.csv   one row per filing read, hit or not
"""
from __future__ import annotations

import argparse
import collections
import csv
import random
import re
import sys
import zipfile
from pathlib import Path

import extract_asu_v2_Claude as E

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
ZIPS = ["10-X_C_2016-2020.zip", "10-X_C_2021.zip", "10-X_C_2022.zip",
        "10-X_C_2023.zip", "10-X_C_2024.zip"]
SAMPLE = HERE / "phaseB_sample_Claude.csv"
HITS = HERE / "phaseB_hits_Claude.csv"
READLOG = HERE / "phaseB_readlog_Claude.csv"


def tagged(p, tag):
    return p.with_name(p.stem + (f"_{tag}" if tag else "") + p.suffix)
SEED = 20260920

NAME = re.compile(r"(\d{8})_(10-[KQ])_edgar_data_(\d+)_")


def excluded_ciks():
    """Every CIK the pattern was built on -- the DI list and the Phase A candidates."""
    out = set()
    p = HERE / "di_firm_years_Claude.txt"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8"), delimiter="\t"):
            c = (r.get("cik") or "").strip().lstrip("0")
            if c:
                out.add(c)
    p = HERE / "asu_v2_candidates_Claude.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            c = (r.get("cik") or "").strip().lstrip("0")
            if c:
                out.add(c)
    return out


def enumerate_corpus(excl):
    rows = []
    for zp in ZIPS:
        p = HERE / zp
        if not p.exists():
            print(f"  (missing {zp})")
            continue
        z = zipfile.ZipFile(p)
        n = 0
        for name in z.namelist():
            if not name.endswith(".txt"):
                continue
            m = NAME.search(name)
            if not m:
                continue
            date, form, cik = m.group(1), m.group(2), m.group(3).lstrip("0")
            if cik in excl:
                continue
            rows.append({"zip": zp, "name": name, "filing_date": date,
                         "form": form, "cik": cik, "year": date[:4]})
            n += 1
        z.close()
        print(f"  {zp}: {n:,} eligible filings")
    return rows


def do_sample(n_target):
    excl = excluded_ciks()
    print(f"CIKs excluded (the pattern was built on them): {len(excl):,}\n")
    univ = enumerate_corpus(excl)
    byyear = collections.defaultdict(list)
    for r in univ:
        byyear[r["year"]].append(r)
    total = len(univ)
    firms = len({r["cik"] for r in univ})
    print(f"\nuniverse: {total:,} filings, {firms:,} firms")
    rng = random.Random(SEED)
    out = []
    for y in sorted(byyear):
        share = len(byyear[y]) / total
        k = max(1, round(n_target * share))
        out.extend(rng.sample(byyear[y], min(k, len(byyear[y]))))
    rng.shuffle(out)
    with SAMPLE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"\nwrote {SAMPLE.name}  ({len(out):,} filings, "
          f"{len({r['cik'] for r in out}):,} firms)")
    print("by year:", dict(sorted(collections.Counter(r["year"] for r in out).items())))
    print("by form:", dict(collections.Counter(r["form"] for r in out).most_common()))


def do_run(start, count, append, tag=""):
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    sl = rows[start:start + count] if count else rows[start:]
    byzip = collections.defaultdict(list)
    for r in sl:
        byzip[r["zip"]].append(r)

    hits, log = [], []
    stats = collections.Counter()
    for zp, rs in byzip.items():
        p = HERE / zp
        if not p.exists():
            continue
        z = zipfile.ZipFile(p)
        for r in rs:
            stats["filings read"] += 1
            try:
                raw = z.read(r["name"]).decode("utf-8", errors="replace")
            except Exception:
                stats["unreadable"] += 1
                continue
            body = E.strip_header(raw)
            flat = re.sub(r"\s+", " ", body)
            low = flat.lower()
            passed_gate = E.gate(low)
            cands = E.candidates_for(flat) if passed_gate else []
            stats["passed the cheap gate"] += bool(passed_gate)
            stats["matched the anchor"] += bool(cands)
            stats["candidates"] += len(cands)
            hdr = E.header_fields(raw)
            log.append({**{k: r[k] for k in ("zip", "name", "cik", "form",
                                             "filing_date", "year")},
                        "company": hdr.get("company", "")[:60],
                        "passed_gate": "yes" if passed_gate else "",
                        "n_candidates": len(cands)})
            for k, c in enumerate(cands, 1):
                amts = E.amounts_in(c["effect_text"], len(c["anchor_sentence"]),
                                    c["anchor_in_eff"])
                best = amts[0] if amts else None
                hits.append({
                    "cik": r["cik"], "company": hdr.get("company", "")[:60],
                    "form": r["form"], "filing_date": r["filing_date"],
                    "year": r["year"], "candidate": k, "n_in_filing": len(cands),
                    "score": E.score_candidate(c["effect_text"]),
                    "disclosure_type": E.disclosure_type(c["effect_text"]),
                    "anchor_text": c["anchor_text"],
                    "fp_family": c.get("fp_family", ""),
                    "table_residue": "yes" if E.looks_like_table(
                        c["anchor_sentence"]) else "",
                    "amount": (best[0] if best else ""),
                    "amount_basis": (best[2] if best and len(best) > 2 else ""),
                    "names_the_standard": "yes" if E.ASU_1616.search(
                        c["effect_text"]) else "",
                    "THE_SENTENCE": c["anchor_sentence"][:700],
                    "PREV_SENTENCE": c["prev_sentence"][:300],
                    "NEXT_CONTEXT": c["effect_text"][len(c["anchor_sentence"]):][:400],
                    "verdict": "", "why": "",
                    "file": r["name"],
                })
        z.close()

    for path, data in ((tagged(HITS, tag), hits), (tagged(READLOG, tag), log)):
        if not data:
            continue
        mode = "a" if (append and path.exists()) else "w"
        with path.open(mode, newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            if mode == "w":
                w.writeheader()
            w.writerows(data)

    n = stats["filings read"]
    print(f"filings read {n:,}")
    for k in ("unreadable", "passed the cheap gate", "matched the anchor",
              "candidates"):
        v = stats[k]
        print(f"  {k:<26}{v:>7}" + (f"   ({v/n:.1%} of filings read)"
                                    if n and k != "candidates" else ""))
    if hits:
        print("\nflagged filings by year:",
              dict(sorted(collections.Counter(h["year"] for h in hits).items())))
        print("by disclosure_type:",
              dict(collections.Counter(h["disclosure_type"] for h in hits).most_common()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="run", choices=("sample", "run"))
    ap.add_argument("--n", type=int, default=3000, help="sample size, --mode sample")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--tag", default="", help="suffix for output files, e.g. v2")
    a = ap.parse_args()
    if a.mode == "sample":
        do_sample(a.n)
    else:
        do_run(a.start, a.count, a.append, a.tag)


if __name__ == "__main__":
    main()
