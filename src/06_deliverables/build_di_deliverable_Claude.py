#!/usr/bin/env python3
r"""The Double Irish deliverable: did the 10-K/10-Q confirm the transfer, and
did it say the IP went into the United States?

WHAT THIS IS
------------
Goal 2, as the project instructions state it: "The Double Irish subset -- did
these firms transfer IP INTO the United States? Here the transfer dates are
already verified, so the search narrows to specific years and a wrong answer is
detectable."

So this narrows. For each DI firm it takes the verified transfer year from the
gold set and looks at what the filings say IN THAT WINDOW, rather than pooling
every candidate the firm ever produced. Pooling is what made the first cut of
this table useless: taking the largest rank-1 amount per firm reported Coca-Cola
at 75 billion and Boston Scientific at 108 billion, which are table figures from
a filing that happens to mention a transfer, not disclosures of anything.

TWO PIECES OF EVIDENCE PER FIRM, NOT ONE ROW OF FIELDS
-------------------------------------------------------
A firm gets two selected candidates, each carrying the sentence it came from and
the filing it came from:

  best_destination_evidence  the candidate that points at a jurisdiction
  best_amount_evidence       the candidate that states a tax effect

They are frequently NOT the same sentence, and collapsing them into one row of
columns invents a disclosure that no filing made. Everything behind them is in
`asu_v2_candidates_Claude.csv`; `..._evidence_file` and `..._filing_date` say
exactly where to look.

THE WINDOW, AND THE ONE EXCEPTION TO IT
----------------------------------------
In-window means the candidate's CALENDAR year (after fiscal conversion) is
within one year of the verified transfer year. The exception is settled point 3:
"the adoption date is not the transfer date", and an adoption catch-up under the
modified retrospective method can land years after the event -- Apple recorded
2.7bn in Q1 2019 for a 2015 transfer. So adoption candidates are kept whatever
their year and are labelled `adoption_cumulative_effect`, never silently dated.

STATUS -- and what it does NOT mean
------------------------------------
    us_destination_confirmed   a candidate names the US in the SAME SENTENCE as
                               the transfer phrase
    other_destination_named    a jurisdiction is pointed at ("to X" / a cue)
    disclosed_no_destination   a transfer disclosure, no destination stated
    adoption_only              only the adoption catch-up, no current transfer
    outside_verified_window    candidates exist, none within a year
    not_detected               no candidate in any filing
    no_verified_year           no hand transfer year to narrow to

`not_detected` and `disclosed_no_destination` DO NOT mean the firm did not
transfer IP, and must never be read that way. ASU 2016-16 disclosure is required
only when the effect is MATERIAL. A firm can transfer IP and say nothing at all.
The 10-K can confirm a transfer; it can never refute one. That is the ceiling on
this workstream and it belongs beside this table wherever it is quoted.

Writes:
    asu_v2_di_deliverable_Claude.csv    one row per DI firm
    asu_v2_di_evidence_Claude.csv       every in-window candidate, the backing
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
CAND = HERE / "asu_v2_candidates_Claude.csv"
GOLD = HERE / "tenk_gold_set_Claude.json"
DI = HERE / "di_firm_years_Claude.txt"
OUT = HERE / "asu_v2_di_deliverable_Claude.csv"
OUT_EV = HERE / "asu_v2_di_evidence_Claude.csv"


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# Apple states "anticipates recording approximately 9 billion", then 4 billion,
# then 3 billion, in successive filings, before recording 2.7 billion in a 10-Q.
# Every one of those is a correct reading of what the filing says and only the
# last is the number. A forecast selected as a firm's amount is worse than no
# amount, because it looks like an answer.
FORECAST_LANG = re.compile(
    r"(anticipat\w+|estimat\w+|expect\w+|projec\w+)\s+(to\s+)?"
    r"(record|recogni\w+|result)|will\s+record|would\s+result"
    r"|approximately\s+[\d,.]*\s*(billion|million)\s+(of\s+)?(net\s+)?deferred"
    r"\s+tax\s+assets?\s+(will|would)", re.I)


def quote(r, width=300):
    """The clause around the transfer phrase, not the first N characters.

    Where the corpus left a table standing, the anchor "sentence" begins in the
    middle of it and the disclosure is hundreds of characters in. Zynga's reads
    "89 Net operating loss carryforwards Deferred revenue Acquired intangible
    assets ..." for 550 characters before reaching "we completed an intra-entity
    transfer of certain intellectual property rights back to the U.S." Showing
    the first 600 characters shows the table and hides the finding.
    """
    s = r["anchor_sentence"]
    a = r["anchor_text"]
    i = s.lower().find(a.lower()[:20]) if a else -1
    if i < 0:
        return s[:width * 2]
    lo, hi = max(0, i - width // 2), min(len(s), i + width)
    return ("..." if lo else "") + s[lo:hi].strip() + ("..." if hi < len(s) else "")



# The extractor reaches six sentences forward for a destination, because Salesforce
# names Ireland that far from the transfer phrase. That reach also picks up country
# names belonging to other sentences, and the deliverable is where that has to be
# disciplined -- the candidate file keeps everything with its distance, this table
# states a finding.
#
# What the loose reading produced, read by hand: ALXN ("to an Irish subsidiary"),
# CRM ("consolidation of certain intangible property in Ireland") and MCHP are real.
# ABBV, BF.B, KO, META, PEP, PRGS and SYK are not -- Stryker's sentence says the
# transfer was "between tax jurisdictions" and names neither, while "United States"
# sits somewhere else in the paragraph. Seven of ten would have been wrong.
#
# So a destination counts here only when it is in the SAME SENTENCE as the transfer
# phrase, or within 200 characters of it -- the same rule already applied to the US
# claim, which is why the US count did not move when the window widened.
def near_anchor(r, limit=200):
    if r.get("destination_in_anchor_sentence") == "yes":
        return True
    try:
        return int(r.get("dest_chars_from_transfer_phrase") or 10 ** 9) <= limit
    except (TypeError, ValueError):
        return False


def main():
    rows = list(csv.DictReader(CAND.open(encoding="utf-8")))
    gold = {g["ticker"]: g for g in json.loads(GOLD.read_text())}
    di = {}
    for r in csv.DictReader(DI.open(), delimiter="\t"):
        t = (r.get("tic") or "").strip()
        if t:
            di[t] = r

    by = {}
    for r in rows:
        if r["ticker"]:
            by.setdefault(r["ticker"], []).append(r)

    out, evidence = [], []
    for tic in sorted(set(di) | set(by)):
        cands = by.get(tic, [])
        hand = as_int((gold.get(tic) or {}).get("hand_transfer_year"))

        def in_window(r):
            y = as_int(r["period_cal_year"])
            if hand is None or y is None:
                return False
            return abs(y - hand) <= 1

        adoption = [r for r in cands
                    if r["disclosure_type"] == "adoption_cumulative_effect"]
        window = [r for r in cands if in_window(r)]
        pool = window or adoption
        for r in pool:
            evidence.append({
                "ticker": tic, "hand_transfer_year": hand or "",
                "in_window": "yes" if in_window(r) else "",
                **{k: r[k] for k in (
                    "form", "filing_date", "file", "candidate_rank", "score",
                    "disclosure_type", "period_text", "period_cal_year",
                    "amount_best", "amount_basis", "amounts_all",
                    "effect_direction", "dta_dtl", "destination",
                    "destination_basis", "destination_is_us",
                    "us_in_anchor_sentence", "n_stripped_magnitudes",
                    "table_residue", "anchor_sentence")}})

        # --- destination evidence: strongest claim first
        def dest_key(r):
            return (
                r["us_in_anchor_sentence"] != "yes",
                r["destination_basis"] not in ("prep_to", "cued"),
                r["destination_in_anchor_sentence"] != "yes",
                not in_window(r),
                r["disclosure_type"] != "current_period_transfer",
                -as_float(r["score"]) if as_float(r["score"]) is not None else 0,
            )
        # The destination pool is NOT restricted to the verified window, and
        # Gilead is why. Its verified Double Irish year is 2020; the sentence
        # saying IP went to the United States is about 2018 and appears in the
        # FY2019 and FY2020 10-Ks. Narrowing the pool to 2020 +/- 1 threw the
        # single clearest answer to goal 2's question out of the table.
        #
        # A firm can move IP more than once and to more than one place -- Gilead
        # names Ireland AND the United States in one sentence -- so the window
        # ranks the candidates (see dest_key) but does not filter them, and
        # `destination_in_verified_window` says which case a row is.
        dest_pool = [r for r in cands if r["destination"]]
        d = sorted(dest_pool, key=dest_key)[0] if dest_pool else None

        # --- amount evidence: a stated effect, in window, transfer over adoption
        def amt_key(r):
            return (
                not in_window(r),
                r["disclosure_type"] != "current_period_transfer",
                not r["amount_basis"].startswith("anchor_sentence"),
                r["table_residue"] == "yes",
                -as_float(r["score"]) if as_float(r["score"]) is not None else 0,
            )
        amt_pool = [r for r in pool if r["amount_best"]] or \
                   [r for r in cands if r["amount_best"]]
        a = sorted(amt_pool, key=amt_key)[0] if amt_pool else None

        if not cands:
            status = "not_detected"
        elif hand is None:
            status = "no_verified_year"
        elif d is not None and d["us_in_anchor_sentence"] == "yes":
            status = "us_destination_confirmed"
        elif (d is not None and d["destination_basis"] in ("prep_to", "cued")
              and near_anchor(d)):
            status = "other_destination_named"
        elif not window and adoption:
            status = "adoption_only"
        elif not window:
            status = "outside_verified_window"
        else:
            status = "disclosed_no_destination"

        stripped = sum(1 for r in pool
                       if not r["amount_best"]
                       and as_int(r["n_stripped_magnitudes"] or 0))

        out.append({
            "ticker": tic,
            "cik": (di.get(tic, {}).get("cik") or (gold.get(tic) or {}).get("cik")
                    or "").lstrip("0"),
            "in_di_list": "yes" if tic in di else "",
            "verified_transfer_year": hand or "",
            "status": status,
            "filings_with_candidates": len({r["file"] for r in cands}),
            "candidates_total": len(cands),
            "candidates_in_window": len(window),
            "destination": d["destination"] if d else "",
            "destination_basis": d["destination_basis"] if d else "",
            # The STRICT test only: the US named in the same sentence as
            # the transfer phrase. MTSI has a US mention in its window and
            # its destination is "a higher taxed jurisdiction" -- naming it
            # a US case because the two words appear in the same candidate
            # would be the loosest reading of the most consequential column
            # in this table.
            "destination_is_us": (
                "yes" if d is not None and d["us_in_anchor_sentence"] == "yes"
                else ""),
            "us_chars_from_transfer_phrase": (
                d["us_chars_from_transfer_phrase"] if d else ""),
            "destination_near_transfer_phrase": (
                "yes" if d is not None and near_anchor(d) else "no" if d else ""),
            "dest_chars_from_transfer_phrase": (
                d["dest_chars_from_transfer_phrase"] if d else ""),
            "destination_in_verified_window": (
                "yes" if d is not None and in_window(d) else "no" if d else ""),
            "destination_evidence_form": d["form"] if d else "",
            "destination_evidence_date": d["filing_date"] if d else "",
            "destination_evidence_file": d["file"] if d else "",
            "destination_sentence": (quote(d) if d else ""),
            "amount": a["amount_best"] if a else "",
            "amount_direction": a["effect_direction"] if a else "",
            "amount_dta_dtl": a["dta_dtl"] if a else "",
            "amount_disclosure_type": a["disclosure_type"] if a else "",
            "amount_period": a["period_text"] if a else "",
            "amount_cal_year": a["period_cal_year"] if a else "",
            "amount_basis": a["amount_basis"] if a else "",
            "amount_looks_like_forecast": (
                "yes" if a is not None
                and FORECAST_LANG.search(a.get("candidate_text", "")
                                         or a["anchor_sentence"]) else ""),
            "amount_in_verified_window": (
                "yes" if a is not None and in_window(a) else "no" if a else ""),
            "amount_evidence_form": a["form"] if a else "",
            "amount_evidence_date": a["filing_date"] if a else "",
            "amount_evidence_file": a["file"] if a else "",
            "amount_sentence": (quote(a) if a else ""),
            "rows_with_amount_stripped_by_corpus": stripped,
        })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    with OUT_EV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(evidence[0]))
        w.writeheader()
        w.writerows(evidence)

    print(f"wrote {OUT.name}  ({len(out)} firms)")
    print(f"wrote {OUT_EV.name}  ({len(evidence)} in-window candidates)\n")
    order = ["us_destination_confirmed", "other_destination_named",
             "disclosed_no_destination", "adoption_only",
             "outside_verified_window", "not_detected", "no_verified_year"]
    for s in order:
        n = sum(1 for r in out if r["status"] == s)
        tics = [r["ticker"] for r in out if r["status"] == s]
        print(f"  {s:<26} {n:>3}   {' '.join(tics[:14])}"
              f"{' ...' if len(tics) > 14 else ''}")
    print("\n  not_detected and disclosed_no_destination are NOT evidence that a")
    print("  firm did not transfer IP. Disclosure is required only when material.")


if __name__ == "__main__":
    main()
