#!/usr/bin/env python3
r"""The footnote as the filer wrote it -- tables and all -- from the SEC Notes data sets.

WHY THIS EXISTS
---------------
Loughran-McDonald strips tables, which is the single severe property of this corpus: no
dollar signs, and 12% of magnitude words lose their figure. Every amount problem in this
project traces back to it.

The fix was already on the machine. The SEC Financial Statement AND NOTES data sets --
the `20XXqY_notes.zip` files -- carry `txt.tsv`, the full text of every tagged text block
as filed, tables intact. Axalta's 2020q4 income-tax note comes back with its effective-tax
-rate table AND the sentence "On January 1, 2020, we completed an intra-entity transfer of
certain intellectual property rights (the IP) to our Swiss subsidiary" -- amount, date and
destination, none of which survives the stripping.

Scanning one quarter takes about 11 seconds, so this is cheap.

WHAT IT DOES NOT COVER
----------------------
The Notes data sets begin at 2018q1. A firm whose only disclosure is 2016 or 2017 cannot
be reached this way at all -- that is the data's window, not a failure. Quarters absent
from the folder are reported so they can be downloaded.

    --mode plan     which accessions are wanted, and which quarters hold them
    --mode pull     scan the quarters and write the matched blocks (resumable)
    --mode report   what was recovered
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import html
import os
import re
import sys
import time
import zipfile
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
FILINGS = HERE / "population_filings_Claude.csv"
PLAN = HERE / "notes_text_plan_Claude.csv"
SCOPE_DEFAULT = "all"
PARTS = HERE / "notes_text_parts_dest"
OUT = HERE / "notes_text_blocks_Claude.csv"

# the block has to be ABOUT this, not merely in a filing that is
# The first anchor match in a long block is usually policy boilerplate -- "after
# elimination of intercompany transactions" sits at the top of every significant-
# accounting-policies note and tells us nothing. Anchor on the phrases that mean THIS
# disclosure, score the block, and centre the excerpt on the match that has a dollar
# figure beside it.
ANCHOR = re.compile(r"intra-?\s?entity\s+(?:transfer|sale|asset)|2016\s*-?\s*16|"
                    r"inter-?\s?company\s+(?:transfer|sale)s?\s+of|"
                    r"internal\s+(?:transfer|sale)s?\s+of|"
                    r"transfers?\s+of\s+(?:certain\s+)?(?:intellectual\s+propert|intangible)",
                    re.I)
MONEY = re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s*(?:million|billion|thousand)?|"
                   r"\b[\d,]+(?:\.\d+)?\s*(?:million|billion)\b", re.I)
WINDOW = 1400


# ---------------------------------------------------------------- goal 1a: WHERE
# The amount excerpt is centred on the money. The destination is often somewhere else in
# the same note -- "the IP was transferred to our Swiss subsidiary" three paragraphs from
# the figure -- so it gets a window of its own. A country name is only taken as a
# destination cue when transfer language sits beside it; "our Irish subsidiary holds cash"
# is not a transfer.
COUNTRY = re.compile(
    r"\b(Ireland|Irish|Switzerland|Swiss|Singapore|Netherlands|Dutch|Luxembourg|Bermuda|"
    r"Cayman|United Kingdom|U\.K\.|Israel|Israeli|Canada|Canadian|United States|U\.S\.|"
    r"Puerto Rico|Hungary|Belgium|Germany|France|Japan|China|India|Malta|Cyprus|Barbados|"
    r"Jersey|Guernsey|Hong Kong|Australia|Brazil|Mexico|Poland|Czech|Denmark|Sweden|"
    r"Norway|Finland|Spain|Italy|Austria|Korea|Taiwan|Thailand|Vietnam|Philippines|"
    r"Indonesia|Costa Rica|Panama|Uruguay|Chile|Argentina)\b")
MOVE = re.compile(r"transferr?|sale|sold|moved|migrat|reorganiz|restructur|licens|"
                  r"contribut|domicil", re.I)


def _dest_excerpt(txt):
    """A window around the first country named within reach of transfer language."""
    for m in COUNTRY.finditer(txt):
        a, b = max(0, m.start() - 200), m.start() + 120
        if MOVE.search(txt[a:b]):
            return txt[max(0, m.start() - 420):m.start() + 620]
    return ""


def _score(tag, txt):
    """How likely this block is the disclosure rather than a note that brushes past it."""
    s = 0
    if re.search(r"IncomeTax.*TextBlock", tag, re.I):
        s += 3
    if re.search(r"AccountingPolic|NewAccountingPronounc|AccountingChange", tag, re.I):
        s += 1
    if re.search(r"2016\s*-?\s*16", txt):
        s += 3
    if re.search(r"intra-?\s?entity\s+(?:transfer|sale)", txt, re.I):
        s += 2
    return s


# A SECOND, LOOSER PASS. The strict anchor above was tightened to keep policy
# boilerplate out ("after elimination of intercompany transactions"), and that tightening
# lost 20 firms whose footnote says the same thing in other words -- "intercompany sale of
# assets", "transfers between subsidiaries". Rather than loosen the strict pattern and let
# the boilerplate back in, a filing with NO strict hit is retried on a loose one and the
# block SCORE decides whether what comes back is the disclosure. Provenance is recorded:
# every row says which pass found it.
LOOSE = re.compile(r"intra-?\s?entity|2016\s*-?\s*16|intercompany|inter-?company", re.I)


def _excerpt(txt, pat=None):
    """The window around the anchor match that has money nearest to it."""
    best, bestd = None, 10 ** 9
    for m in (pat or ANCHOR).finditer(txt):
        mm = MONEY.search(txt, m.end(), m.end() + 900)
        d = (mm.start() - m.end()) if mm else 10 ** 8
        if d < bestd:
            best, bestd = m, d
    if best is None:
        return None, False
    a, b = max(0, best.start() - 320), min(len(txt), best.start() + WINDOW)
    return txt[a:b], bestd < 10 ** 8


def quarter(d):
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}q{(m - 1) // 3 + 1}"


def available():
    return {os.path.basename(p).split("_")[0] for p in glob.glob(str(HERE / "*_notes.zip"))}


def targets(scope="all"):
    """Every effect filing worth pulling the real footnote for.

    scope "nochk"  only firms whose amount of record has no XBRL tag to check it -- the
                   stratum this started on
    scope "all"    every firm in the population. The footnote as filed is the answer to
                   the stripped-table problem for amounts, signs AND destinations, and
                   scanning a quarter costs the same whether one firm is wanted or four
                   hundred, so there is no reason to keep it to one stratum.
    """
    rows = [r for r in csv.DictReader(FILINGS.open(encoding="utf-8"))
            if r["is_effect"] == "1"]
    byf = collections.defaultdict(list)
    for r in rows:
        byf[r["cik"].lstrip("0")].append(r)
    out = []
    for c, v in byf.items():
        v.sort(key=lambda r: r["filing_date"])
        a = next((r for r in v if r["amount"]), None)
        if scope == "all" or (a and not a["xbrl_amount"]):
            for r in v:
                out.append({"cik": r["cik"], "accession": r["accession"],
                            "company": r["company"], "form": r["form"],
                            "filing_date": r["filing_date"][:10],
                            "fyear": r["fyear"],
                            "is_amount_of_record": int(r is a),
                            "has_xbrl_check": int(bool(a and a["xbrl_amount"])),
                            "quarter": quarter(r["filing_date"])})
    return out


def do_plan(scope):
    t = targets(scope)
    have = available()
    with PLAN.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(t[0]) + ["quarter_downloaded"])
        w.writeheader()
        for r in t:
            w.writerow({**r, "quarter_downloaded": int(r["quarter"] in have)})
    by = collections.Counter(r["quarter"] for r in t)
    print(f"wrote {PLAN.name}: {len(t):,} filings, "
          f"{len({r['cik'] for r in t}):,} firms")
    print(f"   in a downloaded quarter: {sum(1 for r in t if r['quarter'] in have):,}")
    miss = sorted({r["quarter"] for r in t} - have)
    pre = [q for q in miss if q < "2018q1"]
    post = [q for q in miss if q >= "2018q1"]
    print(f"   quarters before 2018q1 (the sets do not exist): {len(pre)} "
          f"-> {sum(by[q] for q in pre)} filings")
    print(f"   quarters NOT downloaded but available from the SEC: {post} "
          f"-> {sum(by[q] for q in post)} filings")


def do_pull(budget):
    PARTS.mkdir(exist_ok=True)
    plan = [r for r in csv.DictReader(PLAN.open(encoding="utf-8"))
            if r["quarter_downloaded"] == "1"]
    byq = collections.defaultdict(dict)
    for r in plan:
        byq[r["quarter"]][r["accession"]] = r
    for q in sorted(byq):
        if (PARTS / f"{q}.done").exists():
            continue
        want = byq[q]
        t0, rows = time.time(), []
        with zipfile.ZipFile(HERE / f"{q}_notes.zip") as z, z.open("txt.tsv") as fh:
            head = fh.readline().decode("utf-8", "replace").rstrip("\n").split("\t")
            ia, it, iv = head.index("adsh"), head.index("tag"), head.index("value")
            for line in fh:
                p = line.decode("utf-8", "replace").rstrip("\n").split("\t")
                if len(p) <= iv or p[ia] not in want:
                    continue
                raw = html.unescape(p[iv])
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
                ex, has_money = _excerpt(txt)
                pass_used = "strict"
                if ex is None:
                    ex, has_money = _excerpt(txt, LOOSE)
                    pass_used = "loose"
                if ex is None:
                    continue
                r = want[p[ia]]
                rows.append({**{k: r[k] for k in
                                ("cik", "accession", "company", "form", "filing_date",
                                 "fyear", "is_amount_of_record")},
                             "tag": p[it], "block_chars": len(txt),
                             "score": _score(p[it], txt) + (1 if has_money else 0),
                             "has_money": int(has_money), "pass": pass_used,
                             "dest_excerpt": _dest_excerpt(txt), "excerpt": ex})
        tmp = PARTS / f"{q}.tmp"
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["cik", "accession", "company", "form",
                                               "filing_date", "fyear",
                                               "is_amount_of_record", "tag",
                                               "block_chars", "score", "has_money",
                                               "pass", "dest_excerpt", "excerpt"])
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, PARTS / f"{q}.csv")
        (PARTS / f"{q}.done").write_text(f"{len(rows)}\n")
        print(f"{q}: {len(want)} accessions wanted, {len(rows)} matching blocks "
              f"({time.time()-t0:.0f}s)")
        if time.time() - t0 > budget:
            print("   budget reached -- rerun to continue")
            return
    print("all downloaded quarters scanned")


def do_report():
    rows = []
    for p in sorted(glob.glob(str(PARTS / "*.csv"))):
        rows.extend(csv.DictReader(open(p, encoding="utf-8")))
    # the best block per filing: the longest excerpt from the most specific tag
    best = {}
    for r in rows:
        k = (r["cik"], r["accession"])
        key = (r["pass"] == "strict", int(r["score"]), int(r["has_money"]),
               -len(r["excerpt"]))
        if k not in best or key > (best[k]["pass"] == "strict", int(best[k]["score"]),
                                   int(best[k]["has_money"]), -len(best[k]["excerpt"])):
            best[k] = r
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(best.values(), key=lambda r: (r["company"], r["filing_date"])))
    firms = {r["cik"] for r in best.values()}
    rec = [r for r in best.values() if r["is_amount_of_record"] == "1"]
    print(f"wrote {OUT.name}: {len(best):,} filings with a real footnote excerpt, "
          f"{len(firms):,} firms")
    print(f"   of which the AMOUNT-OF-RECORD filing itself: {len(rec):,}")
    print(f"   firms where at least one filing was recovered: {len(firms):,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("plan", "pull", "report"))
    ap.add_argument("--budget", type=float, default=140)
    ap.add_argument("--scope", default="all", choices=("all", "nochk"))
    a = ap.parse_args()
    {"plan": lambda: do_plan(a.scope), "pull": lambda: do_pull(a.budget),
     "report": do_report}[a.mode]()


if __name__ == "__main__":
    main()
