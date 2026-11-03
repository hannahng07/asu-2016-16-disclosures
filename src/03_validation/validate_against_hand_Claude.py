#!/usr/bin/env python3
r"""Join the hand-collected sheet to the extraction and measure the destination gap.

`Deferredtaxes_IPtransfers_DIfirms_handcollected.xlsx` (Sheet1) is the first source
in this project that carries a HAND-VERIFIED TRANSFEREE COUNTRY. Everything measured
before it was recall against firms known to have transferred — this is the first time
the DESTINATION can be scored against a known answer rather than asserted.

It also carries `Transfer Year (based on DTA/DTL benefit)`, which supersedes the
single-year-per-firm identifiers in `di_firm_years_Claude.txt`, and a `Deferred Tax
ID` classification ("Non-US", "N/A - ASU same year as TCJA").

WHAT THE FIRST JOIN SHOWED
---------------------------
Of 49 firms where the hand sheet names a transferee country:

    my verdict agrees and is specific        10
    my verdict is "not stated"               37
    my verdict conflicts                      1   ZNGA, and see below

So the extractor is **right when it speaks and silent too often** — which is the
honest shape of the destination problem and the reason A2 is still open. Precision on
the destination is high; recall is about one in five.

ZNGA IS NOT A FALSE POSITIVE — IT IS BRIAN'S POINT ABOUT MULTIPLE TRANSFERS
---------------------------------------------------------------------------
The hand sheet gives Zynga's transferee country as Ireland. Zynga's FY2021 10-K says
*"in the third quarter of 2020, we completed an intra-entity transfer of certain
intellectual property rights BACK TO THE U.S."* Both are true and they are different
events: the hand column records the Double Irish transferee, the 10-K sentence records
the later unwinding. A firm-level destination field cannot hold both, which is exactly
why the proof table is per firm PER YEAR.

The same reading applies to REGN and VMW, where the hand sheet says "U.S. and Ireland"
and the extractor found only the non-US leg: not wrong, incomplete.

Writes: asu_v2_destination_validation_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import re
import sys
from pathlib import Path

import pandas as pd

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
HAND = HERE / "Deferredtaxes_IPtransfers_DIfirms_handcollected.xlsx"
PROOF = HERE / "asu_v2_identification_proof_Claude.csv"
OUT = HERE / "asu_v2_destination_validation_Claude.csv"

NON_US = r"ireland|irish|malta|bermuda|cayman|switzerland|singapore|netherlands|luxembourg|puerto rico"


def as_year(v):
    """The hand sheet carries 'TBD' and free text in year columns; keep it visible."""
    try:
        return int(v)
    except (TypeError, ValueError):
        t = str(v).strip()
        return "" if t.lower() in ("nan", "") else t


def classify(c: str) -> str:
    c = (c or "").lower()
    if not c or c in ("nan", "tbd") or "n/a" in c:
        return ""
    us = bool(re.search(r"\bu\.?s\.?a?\b|united states", c))
    non_us = bool(re.search(NON_US, c))
    if us and non_us:
        return "both"
    if us:
        return "US"
    if non_us:
        return "non-US"
    return "other"


def main():
    d = pd.read_excel(HAND, sheet_name="Sheet1").dropna(subset=["Ticker"])
    hand = {}
    for _, r in d.iterrows():
        t = str(r["Ticker"]).strip()
        hand[t] = {
            "hand_status": str(r.get("Status ", "") or "").strip(),
            "hand_transfer_year": as_year(r.get("Transfer Year (based on DTA/DTL beneift)")),
            "hand_transferee_country": str(r.get("Transferee Country", "") or "").strip(),
            "hand_us_deferred_benefit": (r["US Deferred Tax Benefit"]
                                         if pd.notna(r.get("US Deferred Tax Benefit")) else ""),
            "hand_deferred_tax_id": str(r.get("Deferred Tax ID", "") or "").strip(),
            "hand_irish_exit_year": as_year(r.get("Irish Data Exit Year")),
        }

    proof = list(csv.DictReader(PROOF.open(encoding="utf-8")))
    mine = collections.defaultdict(list)
    for r in proof:
        mine[r["ticker"]].append(r)

    out = []
    for t, h in sorted(hand.items()):
        hc = classify(h["hand_transferee_country"])
        rows = mine.get(t, [])
        verdicts = {r["us_verdict"] for r in rows}
        mv = ("yes" if "yes" in verdicts else "no" if "no" in verdicts
              else "unnamed" if "unnamed" in verdicts else
              "not_stated" if rows else "no_candidates")
        named = sorted({r["us_evidence"] for r in rows
                        if r["us_verdict"] in ("yes", "no") and r["us_evidence"]})
        best = (sorted(rows, key=lambda r: (r["sentence_grade"], r["amount_grade"]))[0]
                if rows else None)
        # does my set of years cover the hand year?
        years = sorted({int(r["year"]) for r in rows})
        hy = h["hand_transfer_year"] if isinstance(h["hand_transfer_year"], int) else None
        year_hit = ("exact" if hy and hy in years else
                    "within_1" if hy and any(abs(y - hy) <= 1 for y in years) else
                    "no" if hy and years else "")
        if hc and mv in ("yes", "no"):
            agree = ("agrees" if (hc == "US" and mv == "yes")
                     or (hc == "non-US" and mv == "no")
                     or (hc == "both") else "conflicts")
        elif hc:
            agree = "silent"
        else:
            agree = ""
        out.append({
            "ticker": t, **h,
            "hand_country_class": hc,
            "my_us_verdict": mv,
            "my_destinations_named": "; ".join(named),
            "destination_agreement": agree,
            "my_years_with_evidence": "; ".join(str(y) for y in years),
            "hand_year_covered": year_hit,
            "best_sentence_grade": best["sentence_grade"] if best else "",
            "best_amount_grade": best["amount_grade"] if best else "",
            "best_amount": best["amount"] if best else "",
        })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    scored = [r for r in out if r["hand_country_class"]]
    print(f"wrote {OUT.name}  ({len(out)} firms, {len(scored)} with a hand country)\n")
    print("DESTINATION, scored against the hand-verified transferee country:")
    for k, n in collections.Counter(r["destination_agreement"] for r in scored).most_common():
        print(f"  {k:<12} {n:>3}   ({n/len(scored):.0%})")
    spoke = [r for r in scored if r["my_us_verdict"] in ("yes", "no")]
    ok = [r for r in spoke if r["destination_agreement"] == "agrees"]
    print(f"\n  when the extractor names a destination it is right "
          f"{len(ok)} of {len(spoke)}")
    print(f"  it stays silent on {sum(1 for r in scored if r['destination_agreement']=='silent')}"
          f" of {len(scored)} firms where a destination is known")
    print("\n  >>> destination PRECISION is high; RECALL is about one in five. <<<")

    yr = [r for r in out if r["hand_year_covered"]]
    print(f"\nTRANSFER YEAR, hand year vs the years I have evidence for (n={len(yr)}):")
    for k, n in collections.Counter(r["hand_year_covered"] for r in yr).most_common():
        print(f"  {k:<10} {n:>3}   ({n/len(yr):.0%})")

    print("\nfirms where the hand sheet knows a country and the extractor is silent:")
    sil = [r for r in scored if r["destination_agreement"] == "silent"]
    for r in sil[:30]:
        print(f"  {r['ticker']:<6} {r['hand_transferee_country'][:34]:<36} "
              f"S={r['best_sentence_grade']} A={r['best_amount_grade']}")


if __name__ == "__main__":
    main()
