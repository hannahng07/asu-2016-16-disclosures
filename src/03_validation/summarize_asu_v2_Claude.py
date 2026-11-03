#!/usr/bin/env python3
r"""One row per Double Irish firm: what the 10-Ks were found to say.

This is job A1's reading of the candidate file -- "catch every confirmed case",
turned into a table where a miss is visible per firm rather than buried in a
rate. It selects nothing and discards nothing: every column that says "best"
names which candidate it came from, and the candidate file holds the rest.

Columns
-------
filings_with_candidates   how many of this firm's filings carried any candidate
candidates                how many candidate sentences in total
hand_transfer_year        Brian's hand-recorded year, where there is one
years_found               every calendar year any candidate resolved to
year_match                exact / within_1 / no / no_year / no_hand_year
best_amount               the rank-1 candidate's amount, with its filing
effect_direction          benefit / cost / mixed, counted across candidates
dta_dtl                   DTA / DTL / both, counted across candidates
destination_pointed_at    jurisdictions a candidate points at ("to X" / cue)
us_destination            yes when a candidate names the US in the SAME
                          SENTENCE as the transfer phrase -- the strict test
stripped_amount_rows      candidates whose figure the corpus removed; these are
                          disclosures with a missing number, never firms that
                          disclosed none

Writes: asu_v2_di_firm_summary_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
CAND = HERE / "asu_v2_candidates_Claude.csv"
GOLD = HERE / "tenk_gold_set_Claude.json"
DI = HERE / "di_firm_years_Claude.txt"
OUT = HERE / "asu_v2_di_firm_summary_Claude.csv"


def main():
    rows = list(csv.DictReader(CAND.open(encoding="utf-8")))
    gold = {g["ticker"]: g for g in json.loads(GOLD.read_text())}
    di = {}
    for r in csv.DictReader(DI.open(), delimiter="\t"):
        di[(r["tic"] or "").strip()] = r

    by = collections.defaultdict(list)
    for r in rows:
        if r["ticker"]:
            by[r["ticker"]].append(r)

    out = []
    for tic in sorted(set(di) | set(by)):
        cands = by.get(tic, [])
        g = gold.get(tic, {})
        hand = g.get("hand_transfer_year") or ""
        years = sorted({int(r["period_cal_year"]) for r in cands
                        if r["period_cal_year"]})
        if not hand:
            ym = "no_hand_year"
        elif not cands:
            ym = "not_detected"
        elif not years:
            ym = "no_year"
        elif int(hand) in years:
            ym = "exact"
        elif any(abs(y - int(hand)) <= 1 for y in years):
            ym = "within_1"
        else:
            ym = "no"
        r1 = [r for r in cands if r["candidate_rank"] == "1" and r["amount_best"]]
        r1.sort(key=lambda r: -float(r["amount_best"]))
        best = r1[0] if r1 else None
        dirs = collections.Counter(r["effect_direction"] for r in cands)
        dts = collections.Counter(r["dta_dtl"] for r in cands)
        pointed = sorted({r["destination"] for r in cands
                          if r["destination_basis"] in ("prep_to", "cued")})
        us = [r for r in cands if r["destination_is_us"] == "yes"
              and r["us_in_anchor_sentence"] == "yes"]
        out.append({
            "ticker": tic,
            "cik": (di.get(tic, {}).get("cik") or g.get("cik") or "").lstrip("0"),
            "in_di_list": "yes" if tic in di else "",
            "filings_with_candidates": len({r["file"] for r in cands}),
            "candidates": len(cands),
            "hand_transfer_year": hand,
            "years_found": "; ".join(str(y) for y in years),
            "year_match": ym,
            "best_amount": best["amount_best"] if best else "",
            "best_amount_form": best["form"] if best else "",
            "best_amount_filing_date": best["filing_date"] if best else "",
            "best_amount_basis": best["amount_basis"] if best else "",
            "effect_direction": "; ".join(f"{k}:{v}" for k, v in dirs.most_common()
                                          if k != "none"),
            "dta_dtl": "; ".join(f"{k}:{v}" for k, v in dts.most_common()
                                 if k != "none"),
            "destination_pointed_at": "; ".join(pointed),
            "us_destination": "yes" if us else "",
            "us_sentence": (us[0]["anchor_sentence"][:400] if us else ""),
            "stripped_amount_rows": sum(
                1 for r in cands if not r["amount_best"]
                and int(r["n_stripped_magnitudes"] or 0) > 0),
        })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    n_det = sum(1 for r in out if r["candidates"])
    print(f"wrote {OUT.name}  ({len(out)} firms)")
    print(f"  firms with at least one candidate   {n_det} of {len(out)}")
    for k in ("exact", "within_1", "no", "no_year", "not_detected", "no_hand_year"):
        n = sum(1 for r in out if r["year_match"] == k)
        print(f"  year_match {k:<14} {n}")
    us = [r for r in out if r["us_destination"]]
    print(f"\n  firms naming the UNITED STATES as the destination, in the same")
    print(f"  sentence as the transfer: {len(us)}")
    for r in us:
        print(f"    {r['ticker']:<6} {r['us_sentence'][:150]}")


if __name__ == "__main__":
    main()
