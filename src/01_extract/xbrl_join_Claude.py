#!/usr/bin/env python3
r"""XBRL as a second evidence channel: the amount the corpus stripped, and the sign.

WHY
---
Loughran-McDonald removes tables. 46% of filings lose at least one figure that way, and in
this population it shows as sentences like BioMarin's "recognized a deferred tax asset of
million", Disney's "recorded a billion deferred tax asset" and Qualcomm's "approximately
billion". The number is not missing from the world -- it is missing from the corpus. The
filer tagged it in XBRL, where nothing was stripped.

`xbrl_asu_probe_Claude.py` collected those facts (9,449 of them, 20 quarters). This module
turns them into three things the frame can use:

    the AMOUNT      for filings where the text carried none, joined on cik + accession
    the SIGN        from the ELEMENT NAME, which says asset or liability outright --
                    a far better instrument than the words around the figure
    a SECOND WITNESS  firms that tagged the standard but whose text reads as boilerplate,
                    flagged rather than silently absent

WHICH FACT IS "THE AMOUNT"
---------------------------
A filing can carry a dozen member-tagged facts: the cumulative-effect adjustment, the
balance-sheet lines it moved, and the equity totals it sits inside. They are not
interchangeable. Tags are ranked, and the rank is recorded in `xbrl_tag` so any row can be
argued with:

    1 the cumulative-effect adjustment itself
    2 the quantified effect of adoption
    3 the deferred tax asset or liability recognised
    4 the account that moved (prepaid, other assets, retained earnings)
    9 an equity total that merely carries the member on an axis -- NEVER the amount

Only the `asu_member` pass is used. The `tag_name` pass is a lead, not evidence: OPKO's
`RevenueFromTransferOfIntellectualProperty` facts are licensing revenue on an 8-K.

WHAT THIS DOES NOT DO
---------------------
It does not add filings to the population. A firm that tagged the standard and wrote
nothing readable is flagged (`xbrl_tagged_no_text_effect`) so the decision is visible and
reversible, not folded into the count.

Writes: xbrl_amounts_Claude.csv   one row per (cik, accession) with the chosen amount
        xbrl_firm_flags_Claude.csv one row per firm that tagged the member
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
FACTS = HERE / "xbrl_asu_facts_Claude.csv"
FILINGS = HERE / "population_filings_Claude.csv"
FIRMS = HERE / "population_firms_Claude.csv"
OUT = HERE / "xbrl_amounts_Claude.csv"
FLAGS = HERE / "xbrl_firm_flags_Claude.csv"

RANKS = [
    (1, re.compile(r"CumulativeEffect", re.I)),
    (2, re.compile(r"EffectOfAdoptionQuantification|CumulativeEffectOfChangeOnEquity", re.I)),
    (3, re.compile(r"DeferredTax|DeferredIncomeTax", re.I)),
    (4, re.compile(r"PrepaidExpense|OtherAssets|OtherLiabilities|RetainedEarnings"
                   r"|IncomeTaxExpenseBenefit|InventoryNet", re.I)),
    (9, re.compile(r"StockholdersEquity|MembersEquity|AssetsTotal|^Assets$", re.I)),
]
DTL = re.compile(r"DeferredTaxLiabilit|DeferredIncomeTaxLiabilit", re.I)
DTA = re.compile(r"DeferredTaxAsset|DeferredIncomeTaxAsset|DeferredTaxAssetsLiabilitiesNet", re.I)
FIELDS = ["cik", "accession", "adsh", "quarter", "name", "form", "filed", "period",
          "xbrl_amount", "xbrl_tag", "xbrl_tag_rank", "xbrl_dta_dtl", "xbrl_ddate",
          "xbrl_period", "xbrl_days_from_period", "xbrl_n_facts", "xbrl_components",
          "xbrl_segments"]


def _d(x):
    try:
        return dt.date(int(x[:4]), int(x[4:6]), int(x[6:8]))
    except Exception:
        return None


def rank_of(tag):
    for r, pat in RANKS:
        if pat.search(tag):
            return r
    return 5


def main():
    facts = [r for r in csv.DictReader(FACTS.open(encoding="utf-8"))
             if r["why"] in ("asu_member", "both") and r["uom"] == "USD"]
    by = collections.defaultdict(list)
    for r in facts:
        by[(r["cik"].lstrip("0"), r["adsh"])].append(r)

    rows = []
    for (cik, adsh), rs in by.items():
        best = None
        for r in rs:
            try:
                v = float(r["value"])
            except (TypeError, ValueError):
                continue
            if v == 0:
                continue
            # a fact whose date sits outside the filing's own period belongs to another
            # context: Analog Devices repeats its FY2019 331m cumulative-effect tag in
            # every 10-Q of that year, while the text of each quarter reports 13m, 22m.
            # Distance from the period the filing reports on breaks the tie.
            a, b = _d(r["ddate"]), _d(r["period"])
            far = abs((a - b).days) if (a and b) else 999
            k = (rank_of(r["tag"]), 0 if far <= 100 else 1, far, -abs(v))
            if best is None or k < best[0]:
                best = (k, r, v)
        if best is None:
            continue
        _, r, v = best
        rows.append({
            "cik": f"{int(cik):010d}", "accession": adsh,
            "adsh": adsh.replace("-", ""), "quarter": r["quarter"], "name": r["name"],
            "form": r["form"], "filed": r["filed"], "period": r["period"],
            "xbrl_amount": abs(v), "xbrl_tag": r["tag"],
            "xbrl_tag_rank": rank_of(r["tag"]),
            "xbrl_dta_dtl": ("DTL" if DTL.search(r["tag"]) else
                             ("DTA" if DTA.search(r["tag"]) else "")),
            "xbrl_ddate": r["ddate"], "xbrl_period": r["period"],
            "xbrl_days_from_period": (abs((_d(r["ddate"]) - _d(r["period"])).days)
                                      if (_d(r["ddate"]) and _d(r["period"])) else ""),
            "xbrl_n_facts": len(rs),
            # every tagged component of the same adoption entry, strongest tag first.
            # A single "the amount" cannot serve every question: the retained-earnings
            # adjustment, the deferred tax asset recognised and the prepaid balance
            # written off are three different numbers from one event, and filings state
            # two or three of them in the same sentence.
            "xbrl_components": "; ".join(
                f"{x['tag']}={float(x['value']):.0f}"
                for x in sorted(rs, key=lambda y: (rank_of(y["tag"]), y["tag"]))
                if x["value"] not in ("", None) and x["uom"] == "USD")[:600],
            "xbrl_segments": r["segments"][:160]})
    rows.sort(key=lambda r: (r["cik"], r["filed"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # ------------------------------------------------------------------ the join
    fil = list(csv.DictReader(FILINGS.open(encoding="utf-8")))
    have_acc = {(r["cik"].lstrip("0"), r["accession"].replace("-", "")) for r in fil}
    eff_acc = {(r["cik"].lstrip("0"), r["accession"].replace("-", ""))
               for r in fil if r["is_effect"] == "1"}
    eff_ciks = {r["cik"].lstrip("0") for r in fil if r["is_effect"] == "1"}
    # NB: measure against the TEXT amount. Once the builder has run, `amount` already
    # carries XBRL fills, and counting those would report zero work left to do.
    no_amt = {(r["cik"].lstrip("0"), r["accession"].replace("-", ""))
              for r in fil if r["is_effect"] == "1"
              and (r.get("amount_source") or ("text" if r["amount"] else "")) != "text"}

    hit_any = [r for r in rows if (r["cik"].lstrip("0"), r["adsh"]) in have_acc]
    hit_eff = [r for r in rows if (r["cik"].lstrip("0"), r["adsh"]) in eff_acc]
    fills = [r for r in rows if (r["cik"].lstrip("0"), r["adsh"]) in no_amt
             and r["xbrl_tag_rank"] <= 3]
    print(f"XBRL member facts: {len(facts):,} -> {len(rows):,} filings with a chosen amount")
    print(f"  joined to a filing we read (cik+accession): {len(hit_any):,}")
    print(f"  of which the filing is an EFFECT filing:    {len(hit_eff):,}")
    print(f"  EFFECT filings with NO text amount that XBRL can fill: {len(fills):,}")
    print(f"     (rank 1-3 only: the adjustment, the quantified effect, or the DTA/DTL)")
    sign = collections.Counter(r["xbrl_dta_dtl"] for r in hit_eff if r["xbrl_dta_dtl"])
    print(f"  sign available from the element name on {sum(sign.values()):,} effect "
          f"filings: {dict(sign)}")

    # ------------------------------------------------------------- the firm flags
    firms = {r["cik"].lstrip("0"): r for r in
             csv.DictReader(FIRMS.open(encoding="utf-8"))}
    byfirm = collections.defaultdict(list)
    for r in rows:
        byfirm[r["cik"].lstrip("0")].append(r)
    frows = []
    for cik, rs in sorted(byfirm.items()):
        f = firms.get(cik)
        frows.append({
            "cik": f"{int(cik):010d}",
            "company": rs[0]["name"],
            "n_filings_tagged": len(rs),
            "quarters": " ".join(sorted({r["quarter"] for r in rs})),
            "max_xbrl_amount": max(r["xbrl_amount"] for r in rs),
            "best_tag_rank": min(r["xbrl_tag_rank"] for r in rs),
            "in_frame": "yes" if f else "no",
            "ever_effect": (f["ever_effect"] if f else ""),
            "first_any_mention_class": (f["first_any_mention_class"] if f else ""),
            "xbrl_tagged_no_text_effect": 1 if (cik not in eff_ciks) else 0})
    with FLAGS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(frows[0]))
        w.writeheader()
        w.writerows(frows)
    n_only = sum(r["xbrl_tagged_no_text_effect"] for r in frows)
    print(f"\nfirms that tagged the member: {len(frows):,}; of them {n_only:,} have no "
          f"effect filing in the text frame (flagged, NOT added to the population)")


if __name__ == "__main__":
    main()
