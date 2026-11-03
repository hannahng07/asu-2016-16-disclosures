#!/usr/bin/env python3
r"""Measure the v2 candidate output. Every rate is printed with its denominator.

WHY THIS IS A SEPARATE FILE FROM THE EXTRACTOR
-----------------------------------------------
The project's standing rule: "Never state a rate without saying what its
denominator is -- the 36% that became 23% is why. Read the disagreements before
believing any rate, and treat a number that flatters the method with the same
suspicion as one that does not."

The 36% was a validator that asked "does ANY amount this script extracted equal
ANY number in the hand note?" against notes that are long excerpts carrying
revenue and prior-year figures. Gartner scored correct holding 6.8m, 8m and
13.7m against a true answer of 38.1m.

So this script reports the SAME quantity several ways rather than picking the
flattering one, and names each one by what it actually asked:

    key amount == amount_best of the rank-1 candidate   <- what v1 could do
    key amount == amount_best of ANY candidate          <- v2's pick, unranked
    key amount present anywhere in ANY candidate        <- recall with provenance

The third is the number A3 is trying to move and it is NOT an accuracy figure --
it says the right answer is in the output with its sentence attached, not that
the script chose it. Quoting it as the match rate would be the 36% mistake
committed a second time. The first is the one comparable to the 23%.

DETECTION AND AMOUNT ARE NOT ONE NUMBER
----------------------------------------
Detection -- was this filing correctly identified as carrying a transfer
disclosure -- is what goal 1 lives on and ran at 81%. Amount extraction is what
the 23% measures, binds goal 2, and is close to irrelevant to goal 1. They are
printed in separate blocks here and must stay separate when quoted.

Usage
-----
    python validate_asu_v2_Claude.py
    python validate_asu_v2_Claude.py --disagreements       # print them to read
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

HERE = Path(__file__).resolve().parent
CAND = HERE / "asu_v2_candidates_Claude.csv"
V1 = HERE / "asu_2016_16_extracted_Claude.csv"
KEY = HERE / "tenk_answer_key_Claude.json"
GOLD = HERE / "tenk_gold_set_Claude.json"


def close(a, b, tol=0.005):
    return abs(a - b) <= max(1.0, abs(b) * tol)


def rate(n, d, label, note=""):
    pct = f"{n / d:.0%}" if d else "n/a"
    print(f"  {label:<52} {n:>4} of {d:<4} ({pct}){('  ' + note) if note else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disagreements", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(CAND.open(encoding="utf-8")))
    key = json.loads(KEY.read_text())
    gold = {g["ticker"]: g for g in json.loads(GOLD.read_text())}

    by_tic = collections.defaultdict(list)
    for r in rows:
        if r["ticker"]:
            by_tic[r["ticker"]].append(r)

    print("=" * 74)
    print("v2 CANDIDATE OUTPUT".center(74))
    print("=" * 74)
    files = {r["file"] for r in rows}
    print(f"  candidate rows                   {len(rows):,}")
    print(f"  filings with >=1 candidate       {len(files):,}")
    print(f"  tickers with >=1 candidate       {len(by_tic):,}")
    per = collections.Counter(int(r['n_candidates']) for r in rows if r['candidate_rank'] == '1')
    tot = sum(per.values()) or 1
    print(f"  candidates per matched filing    mean "
          f"{sum(k * v for k, v in per.items()) / tot:.1f}, "
          f"median {sorted(k for k, v in per.items() for _ in range(v))[tot // 2]}, "
          f"max {max(per) if per else 0}")
    print("     (this is the cost of not choosing: every extra candidate is a row")
    print("      a person or the answer key has to pass over)")

    # ------------------------------------------------------------ DETECTION
    print("\n" + "=" * 74)
    print("DETECTION -- goal 1's number. NOT the amount rate.")
    print("=" * 74)
    testable = [t for t, g in gold.items() if g.get("cik") and g.get("hand_transfer_year")]
    found = [t for t in testable if t in by_tic]
    rate(len(found), len(testable),
         "gold tickers with a CIK and a hand year: detected",
         "(81% in v1)")
    print("  NOTE: a ticker not detected is not a firm that did not transfer IP.")
    print("  ASU 2016-16 disclosure is required only when MATERIAL, so absence in")
    print("  a 10-K is never evidence of absence. REGN, YELP and INSM say nothing")
    print("  across 28-29 filings each. The 10-K can confirm; it cannot refute.")

    # --------------------------------------------------------------- AMOUNT
    print("\n" + "=" * 74)
    print("AMOUNT -- against the strict 13-ticker answer key. Four questions,")
    print("four different numbers. The first is the one comparable to the 23%.")
    print("=" * 74)
    v1_hits = set()
    if V1.exists():
        v1rows = list(csv.DictReader(V1.open(encoding="utf-8")))
        for r in v1rows:
            t = r["ticker"]
            if t in key and r["asu_amount"]:
                try:
                    if any(close(float(r["asu_amount"]), w) for w in key[t]):
                        v1_hits.add(t)
                except ValueError:
                    pass

    q = collections.defaultdict(set)
    detail = {}
    for t, wants in key.items():
        cands = by_tic.get(t, [])
        d = {"rank1_best": False, "any_best": False, "anywhere": False,
             "present_but_unpicked": False, "no_candidates": not cands}
        for r in cands:
            best = r["amount_best"]
            vals = [float(v) for v in r["amounts_all"].split("; ") if v]
            hit_any_val = any(close(v, w) for v in vals for w in wants)
            hit_best = False
            if best:
                try:
                    hit_best = any(close(float(best), w) for w in wants)
                except ValueError:
                    pass
            if hit_best:
                d["any_best"] = True
                if r["candidate_rank"] == "1":
                    d["rank1_best"] = True
            if hit_any_val:
                d["anywhere"] = True
                if not hit_best:
                    d["present_but_unpicked"] = True
        detail[t] = d
        for k, v in d.items():
            if v:
                q[k].add(t)

    n = len(key)
    rate(len(q["rank1_best"]), n,
         "key amount = amount_best of the RANK-1 candidate", "(v1: %d)" % len(v1_hits))
    rate(len(q["any_best"]), n, "key amount = amount_best of ANY candidate")
    rate(len(q["anywhere"]), n, "key amount PRESENT in some candidate (recall)")
    print("\n  The third line is what A3 set out to move, and it is a RECALL")
    print("  figure with provenance, not an accuracy one: it says the right")
    print("  number is in the file with the sentence it came from. Quoting it")
    print("  as 'the match rate' would repeat the 36% error exactly.")
    print(f"\n  v1 as last run, same key: {len(v1_hits)} of {n} "
          f"({len(v1_hits)/n:.0%})  {sorted(v1_hits)}")

    # ----------------------------------------------------------------- YEAR
    print("\n" + "=" * 74)
    print("YEAR -- calendar, after fiscal conversion, vs the hand transfer year")
    print("=" * 74)
    for label, restrict in (("all candidates", None),
                            ("current_period_transfer only", "current_period_transfer")):
        exact = within1 = parsed = 0
        tested = 0
        for t in testable:
            cands = [r for r in by_tic.get(t, [])
                     if not restrict or r["disclosure_type"] == restrict]
            if not cands:
                continue
            tested += 1
            hand = int(gold[t]["hand_transfer_year"])
            years = {int(r["period_cal_year"]) for r in cands if r["period_cal_year"]}
            if not years:
                continue
            parsed += 1
            if hand in years:
                exact += 1
            elif any(abs(y - hand) <= 1 for y in years):
                within1 += 1
        print(f"\n  {label}  (denominator: {tested} detected tickers with a hand year)")
        rate(parsed, tested, "a calendar year was parsed for at least one candidate")
        rate(exact, tested, "EXACT hand year among the candidate years")
        rate(exact + within1, tested, "within one year")
        print("     NOTE: 'among the candidate years' is a recall test over every")
        print("     candidate, not a single dated answer. It is the right test for")
        print("     A3's output and it is NOT comparable to a one-row-per-filing rate.")

    src = collections.Counter(r["fye_source"] for r in rows if r["period_cal_year"])
    print("\n  where each converted date's fiscal calendar came from:")
    for k, v in src.most_common():
        print(f"    {(k or '(none)'):<42} {v:>5}")

    # ------------------------------------------------- SIGN, DTA/DTL, DEST
    print("\n" + "=" * 74)
    print("SIGN AND DTA/DTL -- settled point 5, the sample-selection check")
    print("=" * 74)
    dirs = collections.Counter(r["effect_direction"] for r in rows)
    dts = collections.Counter(r["dta_dtl"] for r in rows)
    print("  effect_direction:", dict(dirs))
    print("  dta_dtl:         ", dict(dts))
    cost_only = [r for r in rows if r["effect_direction"] == "cost"]
    print(f"\n  candidates reading as a COST rather than a benefit: {len(cost_only)}")
    print("  The DI firms are expected to be DTA cases, so these are worth reading")
    print("  individually -- they are the only place a cost case can show up before")
    print("  Phase B opens, and calibrating on DI firms alone cannot surface one.")
    for r in cost_only[:6]:
        print(f"    {r['ticker']:<6} {r['form']:<5} {r['filing_date']}  "
              f"{(r['amount_best'] or '-'):>14}  {r['anchor_sentence'][:110]}")

    print("\n" + "=" * 74)
    print("DESTINATION -- goal 1a, and goal 2's actual question")
    print("=" * 74)
    with_dest = [r for r in rows if r["destination"]]
    pointed = [r for r in with_dest if r["destination_basis"] in ("prep_to", "cued")]
    us = [r for r in rows if r["destination_is_us"] == "yes"]
    rate(len(with_dest), len(rows),
         "candidates naming a jurisdiction in the disclosure")
    rate(len(pointed), len(rows),
         "POINTED AT: 'to X' / 'into X' / a destination cue")
    def near(r, col, limit=200):
        try:
            return int(r[col] or 10 ** 9) <= limit
        except ValueError:
            return False

    us_same = [r for r in us if r["us_in_anchor_sentence"] == "yes"]
    us_clean = [r for r in us_same if near(r, "us_chars_from_transfer_phrase")]
    rate(len(us), len(rows), "points at the UNITED STATES")
    rate(len(us_same), len(rows), "  ...named in the SAME SENTENCE as the transfer")
    rate(len(us_clean), len(rows), "  ...and within 200 chars of the transfer phrase")
    print(f"  tickers surviving all three: "
          f"{sorted({r['ticker'] for r in us_clean if r['ticker']})}")
    print("  Each of those three lines is a stricter claim than the one above it.")
    print("  The loosest is not wrong, it is just not evidence on its own: the two")
    print("  it drops are deferred-tax and rate-reconciliation TABLES that the")
    print("  corpus stripped of their figures, which is why they do not look like")
    print("  tables any more.")
    dd = collections.Counter(r["destination"] for r in pointed)
    print("  destinations pointed at:", dict(dd.most_common(10)))
    tics = sorted({r["ticker"] for r in us if r["ticker"]})
    print(f"  tickers with a US destination: {len(tics)}  {tics}")
    print("\n  Per FILING rather than per candidate -- the unit a person reads:")
    f_dest = {r["file"] for r in pointed}
    f_us = {r["file"] for r in us}
    rate(len(f_dest), len(files), "filings where some candidate points at a jurisdiction")
    rate(len(f_us), len(files), "filings where some candidate points at the US")
    print("\n  destinations_wide_window holds what the SURROUNDING prose names.")
    print("  It is a lead to follow by hand, not evidence: read over the whole")
    print("  candidate it turned risk factors and the stripped tax footnote into")
    print("  United States 'destinations' on filings that name none.")

    print("\n" + "=" * 74)
    print("STRIPPED AMOUNTS -- a missing figure is the corpus, not the firm")
    print("=" * 74)
    stripped = [r for r in rows if int(r["n_stripped_magnitudes"] or 0) > 0]
    no_amt_but_stripped = [r for r in stripped if not r["amount_best"]]
    rate(len(stripped), len(rows), "candidates with a magnitude word missing its figure")
    rate(len(no_amt_but_stripped), len(rows),
         "NO amount captured, but a stripped magnitude present")
    print("  Those last are disclosures whose number the corpus removed. They are")
    print("  the rows to take to the 10-Q or to raw EDGAR, and they must never be")
    print("  counted as firms that disclosed no amount.")
    tbl = [r for r in rows if r["table_residue"] == "yes"]
    rate(len(tbl), len(rows), "candidates flagged as stripped-table residue")

    # -------------------------------------------------------- disagreements
    if args.disagreements:
        print("\n" + "=" * 74)
        print("THE DISAGREEMENTS -- read these before believing any rate above")
        print("=" * 74)
        for t, wants in sorted(key.items()):
            d = detail[t]
            if d["rank1_best"]:
                continue
            print(f"\n--- {t}  want {', '.join(f'{w:,.0f}' for w in wants)}  "
                  f"({len(by_tic.get(t, []))} candidates)")
            if d["no_candidates"]:
                print("    NO CANDIDATES AT ALL -- detection failure, or the firm is")
                print("    absent from the corpus for the relevant years.")
                continue
            if d["anywhere"] and not d["any_best"]:
                print("    the right number IS in a candidate and amount_best passed")
                print("    over it -- selection, not detection, and recoverable from")
                print("    amounts_all by anyone reading the file.")
            best = sorted(by_tic[t], key=lambda r: (r["candidate_rank"] != "1",))[:3]
            for r in best:
                print(f"    rank{r['candidate_rank']}/{r['n_candidates']} {r['form']} "
                      f"{r['filing_date']} best={r['amount_best'] or '-'} "
                      f"all=[{r['amounts_all'][:70]}]")
                print(f"      {r['anchor_sentence'][:200]}")


if __name__ == "__main__":
    main()
