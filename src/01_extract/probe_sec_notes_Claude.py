#!/usr/bin/env python3
r"""Does the SEC's Notes data set carry the ASU 2016-16 amounts the corpus removed?

THE QUESTION THIS ANSWERS, AND WHY IT IS WORTH ONE DOWNLOAD
------------------------------------------------------------
The Loughran-McDonald cleaned 10-X strips tables by design, which is where the
figures live: no dollar signs anywhere, 12% of magnitude words with no number in
front, 46% of filings affected at least once. Everything the extractor does about
amounts is working around that.

The SEC's Financial Statement **and Notes** Data Sets are the same filings with the
numbers intact and machine-readable, because they come from the filers' own XBRL
rather than from parsed text. If the ASU 2016-16 disclosure is tagged, the amount
stops being extracted and starts being joined -- and the 23% -> 85% work on sentence
selection stops being the binding constraint on goal 2.

NOT the `data.sec.gov` API. Checked, 17 September 2026: `companyconcept` for Apple's
`IncomeTaxExpenseBenefit` returns 400+ facts and every one is an un-dimensioned
total. The API drops the dimensional qualifiers, and the dimensional qualifier is
precisely the handle -- so it has to be these zips.

THE HANDLE
----------
`NUM` carries every numeric fact including footnote detail tags, with `dimh` keying
into `DIM`, whose `segments` field concatenates `{axis}={member};` pairs. The
disclosure is then a lookup:

    AdjustmentsForNewAccountingPronouncementsAxis=AccountingStandardsUpdate201616Member

That member is real and appears in filed documents. But firms vary in what they tag,
and many will carry the amount on a CUSTOM EXTENSION element instead -- which is why
this probe does not only look for the member. It runs three widening passes and
reports what each one finds, so the answer is "here is what is actually tagged",
not "the member was absent, therefore nothing is there".

THE TEST CASE
-------------
Run it on `2019q1_notes.zip` first. Apple's 10-Q filed 30 January 2019 is in that
quarter and carries "Upon adoption, the Company recorded $2.7 billion of net
deferred tax assets" -- an answer already known by hand. If 2,700,000,000 comes back
against CIK 320193, the route works and is worth scaling across 2017-2022. If it
does not, one download settled it and Calcbench becomes the primary instead.

WHAT THIS CANNOT DO
-------------------
Destination. Where the IP went is narrative and is not tagged in XBRL at any point.
Goal 1a and goal 2 stay with the text extractor no matter how well this works.

Usage
-----
    python probe_sec_notes_Claude.py 2019q1_notes.zip
    python probe_sec_notes_Claude.py 2019q1_notes.zip --all-ciks

Writes: sec_notes_asu_facts_Claude.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
OUT = HERE / "sec_notes_asu_facts_Claude.csv"
DI = HERE / "di_firm_years_Claude.txt"
GOLD = HERE / "tenk_gold_set_Claude.json"
KEY = HERE / "tenk_answer_key_Claude.json"

# Pass 1 -- the standard member, the cleanest possible handle.
MEMBER = re.compile(r"AccountingStandardsUpdate2016-?16Member", re.I)
# Pass 2 -- any tag whose NAME describes an intra-entity transfer. This is where
# custom extension elements show up (they sit in TAG with custom=1).
TAG_NAME = re.compile(
    r"intra[-_]?entity|intraentity|intercompany[a-z]*transfer|"
    r"transferof(intellectual|intangible|ip)|"
    r"(intellectual|intangible)[a-z]*transfer|noninventory", re.I)
# Pass 3 -- the segment text naming the standard even on a different axis.
SEG_1616 = re.compile(r"2016-?16", re.I)


def read_tsv(z, base):
    """The sets have been shipped as .tsv and as .txt; take whichever is there."""
    for ext in (".tsv", ".txt"):
        for name in z.namelist():
            if name.lower().endswith(base + ext):
                with z.open(name) as fh:
                    data = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                    return list(csv.DictReader(data, delimiter="\t")), name
    return None, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", help="a *_notes.zip from the SEC Financial Statement "
                                "and Notes Data Sets")
    ap.add_argument("--all-ciks", action="store_true",
                    help="do not restrict to the DI firms and the gold set")
    args = ap.parse_args()

    z = zipfile.ZipFile(args.zip)
    print("members:", ", ".join(sorted(n for n in z.namelist())[:12]))

    sub, sub_n = read_tsv(z, "sub")
    num, num_n = read_tsv(z, "num")
    dim, dim_n = read_tsv(z, "dim")
    tag, tag_n = read_tsv(z, "tag")
    for label, rows, n in (("sub", sub, sub_n), ("num", num, num_n),
                           ("dim", dim, dim_n), ("tag", tag, tag_n)):
        print(f"  {label:<4} {n or '(absent)':<28} "
              f"{len(rows) if rows is not None else 0:>9,} rows"
              + (f"   fields: {', '.join(list(rows[0])[:18])}" if rows else ""))
    if not (sub and num):
        print("\nSUB or NUM missing -- is this a *_notes.zip rather than a "
              "financial-statement-only set?")
        return

    # ---- who we care about -------------------------------------------------
    want = {}
    if DI.exists():
        for r in csv.DictReader(DI.open(), delimiter="\t"):
            c = (r.get("cik") or "").strip().lstrip("0")
            if c:
                want[c] = (r.get("tic") or "").strip()
    if GOLD.exists():
        for g in json.loads(GOLD.read_text()):
            c = (g.get("cik") or "").lstrip("0")
            if c:
                want.setdefault(c, g.get("ticker", ""))
    key = json.loads(KEY.read_text()) if KEY.exists() else {}

    by_adsh = {}
    for s in sub:
        cik = (s.get("cik") or "").lstrip("0")
        if args.all_ciks or cik in want:
            by_adsh[s["adsh"]] = s
    print(f"\nsubmissions in this quarter: {len(sub):,}; "
          f"kept for this population: {len(by_adsh):,}")

    # ---- dimensional lookup ------------------------------------------------
    seg_by_hash = {}
    if dim:
        hkey = "dimhash" if "dimhash" in dim[0] else list(dim[0])[0]
        skey = "segments" if "segments" in dim[0] else None
        if skey:
            for d in dim:
                seg_by_hash[d[hkey]] = d[skey]
    print(f"dimensional combinations in DIM: {len(seg_by_hash):,}")

    custom = {t["tag"] for t in (tag or []) if (t.get("custom") or "") == "1"}

    rows, hits = [], {"member": 0, "tag_name": 0, "segment_1616": 0}
    for f in num:
        adsh = f.get("adsh")
        s = by_adsh.get(adsh)
        if s is None:
            continue
        seg = seg_by_hash.get(f.get("dimh", ""), "")
        t = f.get("tag", "")
        why = ""
        if MEMBER.search(seg):
            why, hits["member"] = "asu_2016_16_member", hits["member"] + 1
        elif TAG_NAME.search(t):
            why, hits["tag_name"] = "tag_name", hits["tag_name"] + 1
        elif seg and SEG_1616.search(seg):
            why, hits["segment_1616"] = "segment_mentions_2016_16", hits["segment_1616"] + 1
        if not why:
            continue
        cik = (s.get("cik") or "").lstrip("0")
        rows.append({
            "cik": cik, "ticker": want.get(cik, ""), "company": s.get("name", ""),
            "form": s.get("form", ""), "period": s.get("period", ""),
            "fy": s.get("fy", ""), "fp": s.get("fp", ""), "filed": s.get("filed", ""),
            "adsh": adsh, "matched_on": why,
            "tag": t, "custom_tag": "yes" if t in custom else "",
            "version": f.get("version", ""),
            "ddate": f.get("ddate", ""), "qtrs": f.get("qtrs", ""),
            "uom": f.get("uom", ""), "value": f.get("value", ""),
            "segments": seg,
        })

    if rows:
        with OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    print(f"\nfacts matched: {len(rows):,}")
    for k, v in hits.items():
        print(f"  {k:<22} {v:,}")
    print(f"wrote {OUT.name}")

    # ---- the test that matters --------------------------------------------
    print("\n--- against the hand-known answers ---")
    apple = [r for r in rows if r["cik"] == "320193"]
    if apple:
        print(f"AAPL: {len(apple)} facts")
        for r in sorted(apple, key=lambda r: -abs(float(r["value"] or 0)))[:6]:
            print(f"   {float(r['value']):>18,.0f}  {r['tag']}"
                  f"{' [custom]' if r['custom_tag'] else ''}  {r['form']} {r['filed']}")
        near = [r for r in apple
                if abs(abs(float(r["value"] or 0)) - 2.7e9) < 5e7]
        print("   2.7 BILLION FOUND" if near else
              "   2.7 billion NOT among these facts")
    else:
        print("AAPL: no facts in this quarter's file")

    for tic, wants in sorted(key.items()):
        got = [r for r in rows if r["ticker"] == tic]
        if not got:
            continue
        vals = {abs(float(r["value"] or 0)) for r in got}
        m = [w for w in wants if any(abs(v - w) <= max(1.0, w * 0.005) for v in vals)]
        print(f"{tic:<6} {len(got):>4} facts   "
              + (f"ANSWER KEY MATCHED: {', '.join(f'{x:,.0f}' for x in m)}"
                 if m else "no answer-key value in this quarter"))


if __name__ == "__main__":
    main()
