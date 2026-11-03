#!/usr/bin/env python3
r"""RECALL: who tagged ASU 2016-16 in XBRL that the text route never flagged.

WHY THIS IS THE MISSING MEASUREMENT
------------------------------------
Every rate this project has is PRECISION -- of the filings the anchor flagged, how many
really carry a transfer disclosure. Recall on the full population has never been measured,
because measuring it the obvious way means reading filings the anchor did NOT flag:
226,000 of them, almost all empty.

XBRL gives a second, independent witness. When a firm reports the effect of adopting
ASU 2016-16, it tags the fact with the standard as a dimension member
(`AdjustmentsForNewAccountingPronouncements = AccountingStandardsUpdate201616`). That
member is machine-readable, it is in the SEC's Financial Statement AND NOTES data sets,
and it does not care what words the firm used. Proven on 2019q1 (17 September): Apple's
three hand-collected figures came back exactly, and 297 filers used the member in that one
quarter.

So: every filer that tagged the member is a filing that SHOULD have been detected. The
ones the text route missed are countable recall misses, with the XBRL filer set as the
denominator. That is a real recall number on the real population, not a sample.

WHAT IT DOES NOT MEASURE
------------------------
Firms that disclosed in prose and tagged nothing are invisible here, so this is a LOWER
bound on the text route's recall against all disclosers, and an exact recall against
"firms that tagged". The two are not the same thing and are reported separately.
Destination is narrative and is never tagged -- goal 1a and goal 2 stay with the text.

THE THREE PASSES, AND ONLY THE FIRST IS EVIDENCE
-------------------------------------------------
    asu_member   the dimension names ASU 2016-16                -> evidence
    tag_name     the TAG name describes an intra-entity transfer -> a lead to read
    both         both                                            -> evidence
The 17 September probe found OPKO's 28 `RevenueFromTransferOfIntellectualProperty` facts
on an 8-K in the tag-name pass: licensing revenue, not an intra-entity transfer. The
passes are kept apart in the `why` column and never pooled.

SHAPE
-----
One quarter per call, because the machine gives each command about three minutes and
num.tsv is 1.2 GB uncompressed. Each finished quarter is written through a temp file and
renamed, so an interrupted call loses nothing and re-running is always safe.

    --mode next     do the next unfinished quarter (repeat until it says COMPLETE)
    --mode status   what is done
    --mode report   join the finished quarters against the population frame

Writes: xbrl_parts/facts_<quarter>.csv, xbrl_parts/filers_<quarter>.csv
        xbrl_asu_facts_Claude.csv, xbrl_recall_Claude.csv (report mode)
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import os
import re
import sys
import time
import zipfile
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
PARTS = HERE / "xbrl_parts"
FACTS = HERE / "xbrl_asu_facts_Claude.csv"
RECALL = HERE / "xbrl_recall_Claude.csv"

# the standard, however the filer spelled the member
ASU_MEMBER = re.compile(r"2016-?16|AccountingStandardsUpdate201616|ASU201616", re.I)
# a tag whose NAME is about an intra-entity transfer. A lead, not evidence.
TAG_NAME = re.compile(
    r"IntraEntity|IntercompanyTransfer|IntraGroupTransfer|"
    r"TransferOfIntellectualProperty|IntercompanySaleOfIntellectualProperty", re.I)
FIELDS = ["quarter", "adsh", "cik", "name", "form", "period", "fy", "fp", "filed",
          "tag", "version", "ddate", "qtrs", "uom", "value", "why", "segments"]
FILER_FIELDS = ["quarter", "cik", "name", "adsh", "form", "filed", "n_facts",
                "why_best", "max_abs_value"]
IN_CORPUS_NOTE = ("yes = this exact filing is in the 10-X corpus; firm_read_other_filing = "
                  "the firm is in the corpus but this filing is not; no = never shown")


def quarters():
    return sorted(p.name.split("_")[0] for p in HERE.glob("20*_notes.zip"))


def part(kind, q):
    return PARTS / f"{kind}_{q}.csv"


def write_atomic(path, fields, rows):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def do_quarter(q, budget):
    t0 = time.time()
    zp = HERE / f"{q}_notes.zip"
    z = zipfile.ZipFile(zp)

    # 1. the dimensional combinations that name the standard
    dims = {}
    with z.open("dim.tsv") as fh:
        next(fh)
        for line in fh:
            p = line.decode("utf-8", "replace").rstrip("\n").split("\t")
            if len(p) >= 2 and p[1] and ASU_MEMBER.search(p[1]):
                dims[p[0]] = p[1][:300]
    print(f"  {q}: {len(dims):,} dimension combinations name ASU 2016-16")

    # 2. the filings
    subs = {}
    with z.open("sub.tsv") as fh:
        head = next(fh).decode("utf-8", "replace").rstrip("\n").split("\t")
        ix = {k: head.index(k) for k in ("adsh", "cik", "name", "form", "period",
                                         "fy", "fp", "filed")}
        for line in fh:
            p = line.decode("utf-8", "replace").rstrip("\n").split("\t")
            if len(p) > max(ix.values()):
                subs[p[ix["adsh"]]] = {k: p[v] for k, v in ix.items()}

    # 3. stream the facts
    rows, n = [], 0
    with z.open("num.tsv") as fh:
        head = next(fh).decode("utf-8", "replace").rstrip("\n").split("\t")
        ix = {k: head.index(k) for k in ("adsh", "tag", "version", "ddate", "qtrs",
                                         "uom", "dimh", "value")}
        mx = max(ix.values())
        for line in fh:
            n += 1
            if n % 2_000_000 == 0 and time.time() - t0 > budget:
                print(f"  ran out of time after {n:,} facts -- quarter NOT written")
                return False
            p = line.decode("utf-8", "replace").rstrip("\n").split("\t")
            if len(p) <= mx:
                continue
            dim = dims.get(p[ix["dimh"]])
            tagged = TAG_NAME.search(p[ix["tag"]])
            if not dim and not tagged:
                continue
            why = ("both" if (dim and tagged) else ("asu_member" if dim else "tag_name"))
            s = subs.get(p[ix["adsh"]], {})
            rows.append({"quarter": q, "adsh": p[ix["adsh"]], "cik": s.get("cik", ""),
                         "name": s.get("name", ""), "form": s.get("form", ""),
                         "period": s.get("period", ""), "fy": s.get("fy", ""),
                         "fp": s.get("fp", ""), "filed": s.get("filed", ""),
                         "tag": p[ix["tag"]], "version": p[ix["version"]],
                         "ddate": p[ix["ddate"]], "qtrs": p[ix["qtrs"]],
                         "uom": p[ix["uom"]], "value": p[ix["value"]],
                         "why": why, "segments": dim or ""})

    # 4. one row per filer-filing
    byf = collections.defaultdict(list)
    for r in rows:
        byf[(r["cik"], r["adsh"])].append(r)
    filers = []
    for (cik, adsh), rs in byf.items():
        vals = []
        for r in rs:
            try:
                vals.append(abs(float(r["value"])))
            except (TypeError, ValueError):
                pass
        why = ("asu_member" if any(r["why"] in ("asu_member", "both") for r in rs)
               else "tag_name")
        filers.append({"quarter": q, "cik": cik, "name": rs[0]["name"], "adsh": adsh,
                       "form": rs[0]["form"], "filed": rs[0]["filed"],
                       "n_facts": len(rs), "why_best": why,
                       "max_abs_value": (max(vals) if vals else "")})
    PARTS.mkdir(exist_ok=True)
    write_atomic(part("facts", q), FIELDS, rows)
    write_atomic(part("filers", q), FILER_FIELDS, filers)   # filers last = quarter done
    print(f"  {q}: {n:,} facts scanned in {time.time()-t0:.0f}s -> {len(rows):,} matched, "
          f"{len({f['cik'] for f in filers}):,} filers, "
          f"{sum(1 for f in filers if f['why_best']=='asu_member'):,} of them on the member")
    return True


def do_next(budget):
    todo = [q for q in quarters() if not part("filers", q).exists()]
    if not todo:
        print("every quarter on disk is done -- COMPLETE")
        return
    t0, per = time.time(), None
    for q in todo:
        left = budget - (time.time() - t0)
        if per and left < per * 1.3:      # not enough time for another quarter
            break
        c0 = time.time()
        if not do_quarter(q, left):
            break
        per = time.time() - c0
    do_status()


def do_status():
    qs = quarters()
    done = [q for q in qs if part("filers", q).exists()]
    print(f"\nquarters: {len(done)} of {len(qs)} done" +
          ("" if len(done) < len(qs) else "  -- COMPLETE"))
    if len(done) < len(qs):
        print("  still to do:", " ".join(q for q in qs if q not in done))


def load(kind):
    rows = []
    for p in sorted(glob.glob(str(PARTS / f"{kind}_*.csv"))):
        rows.extend(csv.DictReader(open(p, encoding="utf-8")))
    return rows


def do_report():
    filers = load("filers")
    facts = load("facts")
    if not filers:
        print("nothing scanned yet")
        return
    # every fact, in one file, for the amount work
    write_atomic(FACTS, FIELDS, facts)

    pop = {r["cik"].lstrip("0"): r for r in
           csv.DictReader(open(HERE / "population_firms_Claude.csv", encoding="utf-8"))}
    seen = {r["cik"].lstrip("0") for r in
            csv.DictReader(open(HERE / "population_filings_Claude.csv", encoding="utf-8"))}
    # accession -> was that exact filing in the text route's output?
    acc_seen = {(r["cik"].lstrip("0"), r["accession"].replace("-", "")) for r in
                csv.DictReader(open(HERE / "population_filings_Claude.csv", encoding="utf-8"))}

    # ---- the denominator has to be filings WE READ. Sony, ORIX, ABB, ASML, Credit
    # Suisse and the rest of the foreign private issuers tag the member on 20-F and 6-K,
    # which the Loughran-McDonald 10-X corpus does not contain at all. Counting them as
    # recall misses would blame the extractor for a filing it was never shown.
    man = {(r["cik"].lstrip("0"), r["accession"].replace("-", "")) for r in
           csv.DictReader(open(HERE / "sweep_manifest_Claude.csv", encoding="utf-8"))}
    man_ciks = {c for c, _ in man}
    for f in filers:
        f["in_corpus"] = ("yes" if (f["cik"].lstrip("0"), f["adsh"].replace("-", "")) in man
                          else ("firm_read_other_filing"
                                if f["cik"].lstrip("0") in man_ciks else "no"))

    member = [f for f in filers if f["why_best"] == "asu_member"
              and f["in_corpus"] != "no"]
    outside = {f["cik"].lstrip("0") for f in filers if f["why_best"] == "asu_member"
               and f["in_corpus"] == "no"}
    print(f"filers on the member whose filing is NOT in the 10-X corpus "
          f"(20-F, 6-K, 40-F and the like): {len(outside)} firms -- excluded from the "
          f"recall denominator, since the extractor never saw those filings")
    ciks = {f["cik"].lstrip("0") for f in member}
    out, tally = [], collections.Counter()
    for cik in sorted(ciks):
        r = pop.get(cik)
        rows_here = [f for f in member if f["cik"].lstrip("0") == cik]
        if r and r["ever_effect"] == "1":
            v = "in the population"
        elif r and r["ever_effect"] != "1":
            v = f"mentioned, classed {r['first_any_mention_class']}"
        elif cik in seen:
            v = "read, no clean candidate"
        else:
            v = "MISSED by the text route"
        tally[v] += 1
        vals = [float(f["max_abs_value"]) for f in rows_here if f["max_abs_value"]]
        out.append({"cik": cik, "name": rows_here[0]["name"],
                    "quarters": " ".join(sorted({f["quarter"] for f in rows_here})),
                    "n_filings_tagged": len({f["adsh"] for f in rows_here}),
                    "max_abs_value": (max(vals) if vals else ""),
                    "verdict": v,
                    "in_frame_class": (r["first_any_mention_class"] if r else ""),
                    "in_corpus": rows_here[0]["in_corpus"],
                    "forms": " ".join(sorted({f["form"] for f in rows_here})),
                    "first_effect_date": (r["first_effect_date"] if r else "")})
    write_atomic(RECALL, list(out[0]), out)

    n = len(out)
    print(f"XBRL, {len({f['quarter'] for f in filers})} quarters scanned: "
          f"{len(filers):,} filer-filings matched, {len(facts):,} facts")
    print(f"filers that used the ASU 2016-16 MEMBER (the evidence pass): {n:,} firms\n")
    print("what the text route did with them:")
    for k, v in tally.most_common():
        print(f"   {k:<34}{v:>5}   ({v/n:.0%} of {n})")
    inpop = tally["in the population"]
    print(f"\n   RECALL against firms that tagged the member: {inpop} of {n} ({inpop/n:.0%})")
    print("   (a firm that tagged but is only classed 'adoption' is not necessarily a miss: "
          "adoption without an effect is not in the population by design)")
    miss = [o for o in out if o["verdict"] == "MISSED by the text route"]
    miss.sort(key=lambda o: -(o["max_abs_value"] or 0))
    print(f"\n   the {len(miss)} the text route never flagged, largest first:")
    for o in miss[:25]:
        v = o["max_abs_value"]
        print(f"     {o['name'][:38]:<40}{o['quarters'][:19]:<20}"
              f"{(f'{v:,.0f}' if v else ''):>16}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="next", choices=("next", "status", "report"))
    ap.add_argument("--budget", type=float, default=150)
    a = ap.parse_args()
    if a.mode == "next":
        do_next(a.budget)
    elif a.mode == "status":
        do_status()
    else:
        do_report()


if __name__ == "__main__":
    main()
