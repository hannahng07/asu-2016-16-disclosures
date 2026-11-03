#!/usr/bin/env python3
r"""Modified-retrospective adopters: when the transfer happened vs when the tax hit.

WHY THIS IS ITS OWN TABLE
-------------------------
Settled point 3 of the project: *the adoption date is not the transfer date.* Under
the modified retrospective method a firm recognises, in one go, the tax consequences
of transfers that ALREADY HAPPENED — and the note almost never says when. Apple is
the specimen:

> "In the first quarter of 2019, the Company adopted FASB ASU No. 2016-16 ... utilizing
>  the modified retrospective transition method. Upon adoption, the Company recorded
>  $2.7 billion of net deferred tax assets, reduced other non-current assets by $128
>  million, and increased retained earnings by $2.6 billion."

Three amounts, one recognition date, and **no transfer date at all**. Brian dates the
underlying transfer to 2015. So a row like this carries a date that is real, precise,
and four years wrong for any event study that treats it as the transfer.

This table separates the two explicitly so nothing downstream can conflate them:

    recognition_period      when the catch-up was booked — stated, reliable
    transfer_date_stated    whether the note says when the transfer occurred
    lag_years               recognition year minus the verified transfer year

and it splits out the COMPONENTS, because the adoption note reports the effect in
pieces that mean different things. Apple's $2.7bn (the deferred tax asset created),
$2.6bn (the retained earnings credit) and $128m (the other-asset writedown) are one
event described three ways, and picking whichever the extractor reached first would
report a different number per firm for the same thing.

PROSPECTIVE ADOPTERS ARE THE OPPOSITE CASE
-------------------------------------------
A firm that adopted prospectively has no catch-up — Boston Scientific: *"We adopted
Update No. 2016-16 prospectively in the first quarter of 2018."* For those, a
disclosed transfer IS a current-period event and the date can be used. The method is
therefore recorded, not assumed.

Writes: asu_v2_retrospective_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
CAND = HERE / "asu_v2_candidates_Claude.csv"
DELIV = HERE / "asu_v2_di_deliverable_Claude.csv"
OUT = HERE / "asu_v2_retrospective_Claude.csv"

_M = r"(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand)"
_MULT = {"billion": 1e9, "million": 1e6, "thousand": 1e3}

# The firm actually adopting, in the past — not "will adopt" or "is evaluating".
ADOPTED = re.compile(
    r"upon\s+adoption|we\s+adopted|the\s+Company\s+adopted|the\s+Corporation\s+adopted"
    r"|adopted\s+(?:this\s+|the\s+|FASB\s+)?(?:amended\s+guidance|ASU|Update|standard)"
    r"|as\s+a\s+result\s+of\s+the\s+adoption", re.I)
FUTURE = re.compile(
    r"will\s+adopt|plans?\s+to\s+adopt|expects?\s+to\s+adopt|is\s+evaluating"
    r"|are\s+(?:currently\s+)?evaluating|anticipat\w+\s+record|must\s+adopt", re.I)
METHOD_MR = re.compile(r"modified[-\s]retrospective", re.I)
METHOD_PRO = re.compile(r"adopted[^.]{0,60}prospectiv|prospectiv\w+\s+(?:in|as\s+of)", re.I)

COMPONENTS = [
    ("deferred_tax_asset", re.compile(
        rf"(?:record|recogni)\w*\s+(?:approximately\s+)?(?:a\s+)?{_M}\s+"
        rf"(?:of\s+)?(?:net\s+)?deferred\s+tax\s+asset", re.I)),
    ("deferred_tax_asset", re.compile(
        rf"(?:net\s+)?deferred\s+tax\s+assets?\s+of\s+(?:approximately\s+)?{_M}", re.I)),
    ("retained_earnings", re.compile(
        rf"(?:increas|decreas|reduc)\w*\s+(?:to\s+)?(?:the\s+)?(?:opening\s+|beginning\s+)?"
        rf"(?:balance\s+of\s+)?retained\s+earnings\s+(?:by|of)\s+(?:approximately\s+)?{_M}",
        re.I)),
    ("retained_earnings", re.compile(
        rf"(?:cumulative[-\s]effect\s+adjustment|net\s+reduction)[^.]{{0,60}}?"
        rf"retained\s+earnings\s+of\s+(?:approximately\s+)?{_M}", re.I)),
    ("retained_earnings", re.compile(
        rf"{_M}\s+cumulative\s+effect\s+adjustment", re.I)),
    ("other_assets", re.compile(
        rf"reduc\w*\s+other\s+non-?current\s+assets\s+by\s+(?:approximately\s+)?{_M}",
        re.I)),
    ("prepaid_taxes", re.compile(
        rf"(?:decrease|reduction)\s+in\s+prepaid\s+(?:income\s+)?taxes?[^.]{{0,40}}?{_M}",
        re.I)),
]

# Does the note say when the underlying transfer happened? Anything naming a period
# that is NOT the adoption period — a past year, a past quarter.
TRANSFER_DATE = re.compile(
    r"transfers?\s+(?:that\s+)?(?:occurred|completed|made|entered\s+into)\s+"
    r"(?:in|during|on)\s+([^.,;]{3,40})"
    r"|(?:in|during)\s+((?:fiscal\s+)?(?:19|20)\d{2})[^.]{0,40}?"
    r"(?:we|the\s+Company)\s+(?:completed|transferred)", re.I)


def money(m):
    return float(m.group(1).replace(",", "")) * _MULT[m.group(2).lower()]


def main():
    rows = list(csv.DictReader(CAND.open(encoding="utf-8")))
    deliv = {r["ticker"]: r for r in csv.DictReader(DELIV.open(encoding="utf-8"))}

    by = collections.defaultdict(list)
    for r in rows:
        if r["ticker"]:
            by[r["ticker"]].append(r)

    out = []
    for tic, cands in sorted(by.items()):
        # the adoption EVENT: past-tense adoption with an effect, not an announcement
        events = []
        for c in cands:
            txt = c["candidate_text"]
            if not ADOPTED.search(txt):
                continue
            if FUTURE.search(txt) and not re.search(
                    r"upon\s+adoption[^.]{0,80}record|we\s+adopted[^.]{0,80}record", txt, re.I):
                continue
            comp = {}
            for name, pat in COMPONENTS:
                m = pat.search(txt)
                if m and name not in comp:
                    comp[name] = money(m)
            if not comp and not c["amount_best"]:
                continue
            events.append((c, comp))
        if not events:
            continue
        # prefer the one reporting the most components, then the earliest filing
        c, comp = max(events, key=lambda t: (len(t[1]), -int(t[0]["filing_date"] or 0)))

        txt = c["candidate_text"]
        method = ("modified_retrospective" if METHOD_MR.search(txt)
                  else "prospective" if METHOD_PRO.search(txt) else "not_stated")
        td = TRANSFER_DATE.search(txt)
        verified = deliv.get(tic, {}).get("verified_transfer_year", "")
        rec_year = c["period_cal_year"] or ""
        lag = ""
        if rec_year and verified.isdigit():
            lag = int(rec_year) - int(verified)

        out.append({
            "ticker": tic,
            "adoption_method": method,
            "recognition_period_text": c["period_text"],
            "recognition_cal_year": rec_year,
            "recognition_form": c["form"],
            "recognition_filed": c["filing_date"],
            "transfer_date_stated_in_note": "yes" if td else "no",
            "transfer_date_as_stated": (td.group(1) or td.group(2)).strip() if td else "",
            "verified_transfer_year": verified,
            "lag_years_recognition_minus_transfer": lag,
            "component_deferred_tax_asset": comp.get("deferred_tax_asset", ""),
            "component_retained_earnings": comp.get("retained_earnings", ""),
            "component_other_assets": comp.get("other_assets", ""),
            "component_prepaid_taxes": comp.get("prepaid_taxes", ""),
            "components_found": len(comp),
            "extractor_amount_best": c["amount_best"],
            "date_usable_as_transfer_date": ("yes" if method == "prospective" else "NO"),
            "file": c["file"],
            "THE_ADOPTION_TEXT": txt[:900],
        })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print(f"wrote {OUT.name}  ({len(out)} firms with an adoption entry)\n")
    print("method:", dict(collections.Counter(r["adoption_method"] for r in out)))
    print("transfer date stated in the note:",
          dict(collections.Counter(r["transfer_date_stated_in_note"] for r in out)))
    print("components recovered:",
          dict(collections.Counter(r["components_found"] for r in out)))
    lags = [r["lag_years_recognition_minus_transfer"] for r in out
            if isinstance(r["lag_years_recognition_minus_transfer"], int)]
    if lags:
        lags.sort()
        print(f"\nlag, recognition year minus verified transfer year (n={len(lags)}):")
        print(f"  min {lags[0]}  median {lags[len(lags)//2]}  max {lags[-1]}")
        print("  distribution:", dict(collections.Counter(lags)))
    print("\n--- firms reporting more than one component ---")
    for r in sorted(out, key=lambda r: -r["components_found"])[:10]:
        if r["components_found"] < 2:
            break
        def m(v):
            return f"{v/1e9:.2f}bn" if isinstance(v, float) and abs(v) >= 1e9 else (
                f"{v/1e6:.1f}m" if isinstance(v, float) else "-")
        print(f"  {r['ticker']:<6} {r['adoption_method']:<24} recognised "
              f"{r['recognition_period_text'][:22]:<24} "
              f"DTA {m(r['component_deferred_tax_asset']):>8}  "
              f"RE {m(r['component_retained_earnings']):>8}  "
              f"other {m(r['component_other_assets']):>8}  "
              f"lag {r['lag_years_recognition_minus_transfer']}")


if __name__ == "__main__":
    main()
