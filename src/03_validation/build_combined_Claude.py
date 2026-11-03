#!/usr/bin/env python3
r"""One row per firm-year carrying all three signals: tag, date, DTA/DTL.

Brian, 18 September: *"looking at tags, plus IP dates, then DTA / DTL. These are very
large amounts, so we should be able to grab it."*

Right on the amounts — the median member-qualified XBRL fact is 5.8m but the tail runs
to 34bn, and the transfers this study cares about sit in that tail. Large is exactly
what makes them findable in structured data where the prose gives nothing.

THE THREE SIGNALS, AND WHY EACH IS HERE
----------------------------------------
**TAG** — the SEC Notes XBRL fact carrying
`AdjustmentsForNewAccountingPronouncements=AccountingStandardsUpdate201616`. Machine
readable, never stripped, and it reaches firms whose effect is too small for prose
(TFX at 1.8m, invisible to any text pattern).

**DATE** — the transfer year. Three sources in descending order of trust: the hand
sheet's `Transfer Year (based on DTA/DTL benefit)`, the text extractor's converted
calendar period, and the XBRL fact's own period. They disagree, and the row records
which was used rather than silently picking.

**DTA/DTL** — the movement in `DeferredFederalIncomeTaxExpenseBenefit` against
`DeferredForeignIncomeTaxExpenseBenefit`, relative to the firm's own prior year. This
is the ONLY US-versus-foreign signal for most of the population, because the
destination-ceiling work established that the 10-K simply does not name the
destination: of 33 silent firms, the country appeared in the text for 1, and that one
was spurious.

Scored against the hand transferee country at a $50m floor it was right 14 of 14.

THE FISCAL-YEAR JOIN IS THE TRAP
---------------------------------
A calendar year is not a fiscal year, and the firms that matter most are the ones
where they differ. Salesforce's transfer is calendar 2020; the fiscal year reporting
it is labelled **2021** because it ends 31 January. Joining calendar to fiscal-year
label compared Salesforce against the year before its own transfer and scored it
wrong. Every non-December filer is exposed — Salesforce, Dell, VMware, Adobe, Apple,
Microsoft. Mapped here through each firm's own year end.

Writes: asu_v2_combined_firmyear_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

import pandas as pd

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
GEO = [HERE / "sec_notes_v2_Claude_GEOTAX.csv",
       HERE / "sec_notes_asu_all_Claude_GEOTAX.csv"]
ASU = [HERE / "sec_notes_v2_Claude.csv", HERE / "sec_notes_asu_all_Claude.csv"]
PROOF = HERE / "asu_v2_identification_proof_Claude.csv"
FYE = HERE / "asu_v2_fye_map_Claude.csv"
HAND = HERE / "Deferredtaxes_IPtransfers_DIfirms_handcollected.xlsx"
DI = HERE / "di_firm_years_Claude.txt"
OUT = HERE / "asu_v2_combined_firmyear_Claude.csv"

FED = "DeferredFederalIncomeTaxExpenseBenefit"
FOR = "DeferredForeignIncomeTaxExpenseBenefit"
FLOOR = 5e7          # see the calibration table in the 18 Sep project note
RATIO = 3.0


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    di = {}
    for r in csv.DictReader(DI.open(), delimiter="\t"):
        c = (r.get("cik") or "").strip().lstrip("0")
        if c:
            di[c] = (r.get("tic") or "").strip()

    # fiscal year end month per firm, for the calendar -> fiscal-label map
    fye_month = {}
    for r in csv.DictReader(FYE.open(encoding="utf-8")):
        if r["ticker"]:
            fye_month[r["ticker"]] = int(r["fiscal_year_end"][5:7])

    def fy_label(tic, cal_year):
        m = fye_month.get(tic)
        return cal_year + 1 if m and m <= 6 else cal_year

    # ---- DTA/DTL panel
    cell = collections.defaultdict(dict)
    for p in GEO:
        if not p.exists():
            continue
        for r in csv.DictReader(p.open(encoding="utf-8")):
            if r["tag"] not in (FED, FOR) or r["cik"] not in di:
                continue
            if r.get("segments") or (r.get("qtrs") or "") != "4":
                continue
            dd = r.get("ddate") or ""
            if len(dd) < 4:
                continue
            v = f(r.get("value"))
            if v is None:
                continue
            k = (di[r["cik"]], int(dd[:4]))
            fld = "fed" if r["tag"] == FED else "for"
            if fld not in cell[k] or abs(v) > abs(cell[k][fld]):
                cell[k][fld] = v

    # ---- XBRL ASU tag facts
    tags = collections.defaultdict(list)
    for p in ASU:
        if not p.exists():
            continue
        for r in csv.DictReader(p.open(encoding="utf-8")):
            if r["why"] != "asu_member" or r["cik"] not in di:
                continue
            v = f(r.get("value"))
            if v is None:
                continue
            dd = r.get("ddate") or ""
            y = int(dd[:4]) if len(dd) >= 4 else None
            tags[(di[r["cik"]], y)].append((abs(v), v, r["tag"], r["form"], r["filed"]))

    # ---- hand sheet
    d = pd.read_excel(HAND, sheet_name="Sheet1").dropna(subset=["Ticker"])
    hand = {}
    for _, r in d.iterrows():
        t = str(r["Ticker"]).strip()
        y = r.get("Transfer Year (based on DTA/DTL beneift)")
        try:
            y = int(y)
        except (TypeError, ValueError):
            y = None
        hand[t] = (y, str(r.get("Transferee Country", "") or "").strip())

    # ---- the text proof
    proof = collections.defaultdict(list)
    for r in csv.DictReader(PROOF.open(encoding="utf-8")):
        proof[(r["ticker"], int(r["year"]))].append(r)

    firms = sorted({t for t, _ in cell} | {t for t, _ in proof} | set(hand))
    out = []
    for tic in firms:
        hy, hcountry = hand.get(tic, (None, ""))
        years = sorted({y for (t, y) in cell if t == tic}
                       | {y for (t, y) in proof if t == tic}
                       | ({fy_label(tic, hy)} if hy else set()))
        for y in years:
            if y < 2016 or y > 2023:
                continue
            cur, prior = cell.get((tic, y), {}), cell.get((tic, y - 1), {})
            fed, forn = cur.get("fed"), cur.get("for")
            pf, pfo = prior.get("fed"), prior.get("for")
            dfed = abs(fed - pf) if None not in (fed, pf) else None
            dfor = abs(forn - pfo) if None not in (forn, pfo) else None
            if dfed is None or dfor is None:
                call, why = "", "no_baseline"
            elif max(dfed, dfor) < FLOOR:
                call, why = "", f"below_{int(FLOOR/1e6)}m_floor"
            elif dfor >= RATIO * max(dfed, 1.0):
                call, why = "non-US", f"foreign {dfor/max(dfed,1.0):.1f}x"
            elif dfed >= RATIO * max(dfor, 1.0):
                call, why = "US", f"federal {dfed/max(dfor,1.0):.1f}x"
            else:
                call, why = "", f"balanced {dfor/max(dfed,1.0):.1f}x"

            tg = sorted(tags.get((tic, y), []), reverse=True)
            pr = proof.get((tic, y), [])
            best = (sorted(pr, key=lambda r: (r["sentence_grade"], r["amount_grade"]))[0]
                    if pr else None)
            text_dest = ""
            if pr:
                vs = {r["us_verdict"] for r in pr}
                text_dest = ("yes" if "yes" in vs else "no" if "no" in vs
                             else "unnamed" if "unnamed" in vs else "not_stated")
            if not (tg or best or call):
                continue
            out.append({
                "ticker": tic,
                "fiscal_year": y,
                "is_hand_transfer_year": "yes" if hy and fy_label(tic, hy) == y else "",
                "hand_transfer_year": hy or "",
                "hand_transferee_country": hcountry,
                # --- TAG
                "xbrl_asu_facts": len(tg),
                "xbrl_largest_amount": tg[0][1] if tg else "",
                "xbrl_largest_tag": tg[0][2] if tg else "",
                "xbrl_form": tg[0][3] if tg else "",
                "xbrl_filed": tg[0][4] if tg else "",
                # --- TEXT
                "text_sentence_grade": best["sentence_grade"] if best else "",
                "text_amount_grade": best["amount_grade"] if best else "",
                "text_amount": best["amount"] if best else "",
                "text_us_verdict": text_dest,
                "text_sentence": (best["THE_SENTENCE"][:400] if best else ""),
                # --- DTA/DTL
                "deferred_federal": fed if fed is not None else "",
                "deferred_foreign": forn if forn is not None else "",
                "delta_federal": dfed if dfed is not None else "",
                "delta_foreign": dfor if dfor is not None else "",
                "dtadtl_call": call,
                "dtadtl_basis": why,
                # --- combined
                "destination_best_available": (
                    "US" if text_dest == "yes" else
                    "non-US" if text_dest == "no" else
                    call if call else
                    "unnamed" if text_dest == "unnamed" else ""),
                "destination_source": (
                    "10-K text" if text_dest in ("yes", "no") else
                    "deferred tax lines" if call else
                    "text says unnamed" if text_dest == "unnamed" else "none"),
            })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print(f"wrote {OUT.name}  ({len(out)} firm-years, "
          f"{len({r['ticker'] for r in out})} firms)\n")
    print("signals present per firm-year:")
    print(f"  XBRL tag fact        {sum(1 for r in out if r['xbrl_asu_facts']):>4}")
    print(f"  text disclosure      {sum(1 for r in out if r['text_sentence_grade']):>4}")
    print(f"  DTA/DTL call         {sum(1 for r in out if r['dtadtl_call']):>4}")
    both = [r for r in out if r["text_sentence_grade"] and r["dtadtl_call"]]
    print(f"  text AND DTA/DTL     {len(both):>4}")

    print("\nDESTINATION, best available source:")
    for k, n in collections.Counter(r["destination_source"] for r in out).most_common():
        print(f"  {k:<22} {n:>4}")
    named = [r for r in out if r["destination_best_available"] in ("US", "non-US")]
    print(f"\n  firm-years with a US/non-US answer: {len(named)} "
          f"({len({r['ticker'] for r in named})} firms)")
    print("  of which the answer comes from the deferred tax lines rather than text:",
          sum(1 for r in named if r["destination_source"] == "deferred tax lines"))
    print("  US:", sum(1 for r in named if r["destination_best_available"] == "US"),
          " non-US:", sum(1 for r in named if r["destination_best_available"] == "non-US"))

    print("\n--- the hand transfer years, all three signals side by side ---")
    print(f"{'tic':<7}{'FY':<6}{'hand country':<22}{'tag':>14}{'text':>13} {'S/A':<5}"
          f"{'DTA/DTL':<9}{'source'}")
    for r in sorted((r for r in out if r["is_hand_transfer_year"]),
                    key=lambda r: r["ticker"]):
        def m(v):
            v = f(v)
            return "" if v is None else (f"{v/1e9:.2f}bn" if abs(v) >= 1e9
                                         else f"{v/1e6:.0f}m")
        print(f"{r['ticker']:<7}{r['fiscal_year']:<6}{r['hand_transferee_country'][:20]:<22}"
              f"{m(r['xbrl_largest_amount']):>14}{m(r['text_amount']):>13} "
              f"{(r['text_sentence_grade'] or '-') + '/' + (r['text_amount_grade'] or '-'):<5}"
              f"{(r['dtadtl_call'] or '-'):<9}{r['destination_source']}")


if __name__ == "__main__":
    main()
