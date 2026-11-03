#!/usr/bin/env python3
r"""Brian's federal-vs-foreign deferred tax test, as a firm-year panel.

THE DESIGN, IN HIS WORDS
------------------------
*"Prose that states a transfer occurs within a Q or K, then the subsequent K, we
look at US vs Foreign DTAs. Key is we don't focus on the TCJA years, but right
after."*

Implemented as: for every Double Irish firm, line up the calendar year the TEXT
extractor dates a transfer to against that firm's own annual
`DeferredFederalIncomeTaxExpenseBenefit` and `DeferredForeignIncomeTaxExpenseBenefit`
from the SEC Notes XBRL. Each 10-K restates three years of that footnote, so a firm's
own baseline comes free -- which is what makes "large" mean anything.

WHAT THE FIRST PASS SHOWED, AND WHY THE OUTPUT IS SHAPED THIS WAY
------------------------------------------------------------------
Outbound to Ireland the test is clean -- five for five, the foreign line jumping an
order of magnitude in the transfer year while the federal line stays ordinary:

    CRM  FY2021 foreign -2,084m (prior +60m)     ADBE FY2020 foreign -1,313m (prior -12m)
    DELL FY2020 foreign -5,327m (prior -96m)     VMW  FY2020 foreign -5,018m (prior -8m)
    IART FY2020 foreign   -57.3m (prior -7.5m)

Inbound to the US it is one for two. GILD FY2018 federal +324m against foreign -21m is
the right signature and the right sign (a charge, matching the prose). ZNGA shows no
federal movement at all despite saying "back to the U.S."

So the test EXCLUDES better than it CONFIRMS, and this script reports it that way. A
`foreign_jump` is evidence the IP did not come onshore. A `federal_jump` is a
candidate to read by hand, not a finding -- the federal line is noisy in years with no
transfer at all (DELL FY2019 federal -1,150m, nothing disclosed).

TCJA
----
Fiscal 2017 and 2018 are contaminated by rate remeasurement, and SAB 118
measurement-period adjustments trail into 2019. Those years are flagged
`tcja_window`, never silently dropped, so a reader can see what is being excluded.

Writes: asu_v2_fedfor_panel_Claude.csv    one row per firm-year
        asu_v2_fedfor_summary_Claude.csv  one row per firm with a dated transfer
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
GEO = [HERE / "sec_notes_v2_Claude_GEOTAX.csv",
       HERE / "sec_notes_asu_all_Claude_GEOTAX.csv"]
DELIV = HERE / "asu_v2_di_deliverable_Claude.csv"
CAND = HERE / "asu_v2_candidates_Claude.csv"
DI = HERE / "di_firm_years_Claude.txt"
OUT_PANEL = HERE / "asu_v2_fedfor_panel_Claude.csv"
OUT_SUM = HERE / "asu_v2_fedfor_summary_Claude.csv"

FED = "DeferredFederalIncomeTaxExpenseBenefit"
FOR = "DeferredForeignIncomeTaxExpenseBenefit"
TCJA = {2017, 2018}          # rate remeasurement; SAB 118 trails into 2019


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

    # --- the panel: firm x fiscal year x (federal, foreign)
    # A firm restates the same year in several filings; keep the LARGEST absolute
    # value seen for a year, because a restatement that splits a line across
    # dimensions would otherwise read as a smaller movement than the firm reported.
    cell = collections.defaultdict(dict)   # (tic, year) -> {"fed":v,"for":v,"src":...}
    for path in GEO:
        if not path.exists():
            continue
        for r in csv.DictReader(path.open(encoding="utf-8")):
            if r["tag"] not in (FED, FOR) or r["cik"] not in di:
                continue
            if r.get("segments"):          # dimensioned splits, not the total
                continue
            if (r.get("qtrs") or "") != "4":
                continue
            dd = r.get("ddate") or ""
            if len(dd) < 4:
                continue
            y = int(dd[:4])
            v = f(r.get("value"))
            if v is None:
                continue
            k = (di[r["cik"]], y)
            fld = "fed" if r["tag"] == FED else "for"
            if fld not in cell[k] or abs(v) > abs(cell[k][fld]):
                cell[k][fld] = v
                cell[k][fld + "_src"] = f"{r['form']} {r['filed']}"
            cell[k]["company"] = r["company"]
            cell[k]["cik"] = r["cik"]

    # --- the transfer DATES the text gives us, mapped into FISCAL years
    #
    # A calendar year is not a fiscal year, and for the firms this project cares
    # about most it is routinely a different one. Salesforce's transfer is "the
    # second quarter of fiscal 2021", which the extractor correctly converts to
    # July 2020 -- calendar 2020. The tax footnote that reports it belongs to the
    # fiscal year ENDING 31 January 2021, which the XBRL keys as 2021. Joining on
    # calendar year compared Salesforce's transfer against the wrong year's
    # footnote and reported "no movement" for the clearest case in the set.
    #
    # So the transfer date is placed in whichever fiscal period CONTAINS it, using
    # the firm's own year ends -- the same per-firm per-year calendar A4 built.
    deliv = {r["ticker"]: r for r in csv.DictReader(DELIV.open(encoding="utf-8"))}
    tdates = collections.defaultdict(set)
    for r in csv.DictReader(CAND.open(encoding="utf-8")):
        if (r["ticker"] and r["disclosure_type"] == "current_period_transfer"
                and r["period_cal_end"]):
            tdates[r["ticker"]].add(r["period_cal_end"])

    def fy_start(end_iso):
        y, m, d = (int(x) for x in end_iso.split("-"))
        return f"{y-1:04d}-{m:02d}-{d:02d}"

    tyears = collections.defaultdict(set)
    fyend = {}
    for path in GEO:
        if not path.exists():
            continue
        for r in csv.DictReader(path.open(encoding="utf-8")):
            if r["cik"] in di and (r.get("qtrs") or "") == "4":
                dd = r.get("ddate") or ""
                if len(dd) == 8:
                    iso = f"{dd[:4]}-{dd[4:6]}-{dd[6:]}"
                    fyend.setdefault((di[r["cik"]], int(dd[:4])), iso)
    for tic, dates in tdates.items():
        for (t, y), end_iso in fyend.items():
            if t != tic:
                continue
            start = fy_start(end_iso)
            if any(start < d <= end_iso for d in dates):
                tyears[tic].add(y)

    rows = []
    for (tic, y), d in sorted(cell.items()):
        if "fed" not in d and "for" not in d:
            continue
        rows.append({
            "ticker": tic, "cik": d.get("cik", ""), "company": d.get("company", ""),
            "fiscal_year": y,
            "deferred_federal": d.get("fed", ""), "deferred_foreign": d.get("for", ""),
            "federal_source": d.get("fed_src", ""), "foreign_source": d.get("for_src", ""),
            "tcja_window": "yes" if y in TCJA else "",
            "text_dates_a_transfer_here": "yes" if y in tyears.get(tic, set()) else "",
        })
    with OUT_PANEL.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # --- the test, per firm
    by_tic = collections.defaultdict(dict)
    for r in rows:
        by_tic[r["ticker"]][r["fiscal_year"]] = r

    out = []
    for tic, years in sorted(by_tic.items()):
        for y in sorted(years):
            if not years[y]["text_dates_a_transfer_here"]:
                continue
            cur, prior = years[y], years.get(y - 1)
            fed, forn = f(cur["deferred_federal"]), f(cur["deferred_foreign"])
            pf = f(prior["deferred_federal"]) if prior else None
            pfo = f(prior["deferred_foreign"]) if prior else None

            def jump(now, before):
                """A movement large against the firm's own prior year."""
                if now is None:
                    return ""
                if before is None:
                    return "no_baseline"
                if abs(before) < 1e6:
                    return "yes" if abs(now) > 5e7 else "no"
                return "yes" if abs(now) >= 5 * abs(before) else "no"

            fj, gj = jump(fed, pf), jump(forn, pfo)

            # WHICH LINE MOVED MORE, not whether each moved. Testing the two lines
            # separately against their own prior year made every Ireland case read
            # "both moved", because a small federal base makes an ordinary wiggle
            # look like a jump: Adobe's federal moved 146m against a foreign move of
            # 1,301m and both cleared a 5x bar.
            #
            # The ratio also gets Gilead right, which the separate tests could not.
            # Its FY2019 deltas are 1,167m federal against 1,203m foreign -- almost
            # exactly balanced -- and the prose says the transfer went "to Ireland
            # AND the United States". An honest ambiguous is the correct answer
            # there, not a forced pick.
            dfed = abs(fed - pf) if (fed is not None and pf is not None) else None
            dfor = abs(forn - pfo) if (forn is not None and pfo is not None) else None
            ratio = ""
            if dfed is not None and dfor is not None:
                if max(dfed, dfor) < 5e7:
                    verdict = "neither line moved materially"
                elif dfor >= 3 * max(dfed, 1.0):
                    ratio = f"foreign {dfor / max(dfed, 1.0):.1f}x"
                    verdict = "FOREIGN dominates -- not the US"
                elif dfed >= 3 * max(dfor, 1.0):
                    ratio = f"federal {dfed / max(dfor, 1.0):.1f}x"
                    verdict = "FEDERAL dominates -- candidate, read by hand"
                else:
                    ratio = f"balanced {dfor / max(dfed, 1.0):.1f}x"
                    verdict = "both lines moved comparably -- ambiguous"
            else:
                verdict = "no baseline"
            out.append({
                "ticker": tic, "fiscal_year": y,
                "tcja_window": cur["tcja_window"],
                "text_status": deliv.get(tic, {}).get("status", ""),
                "text_destination": (
                    deliv.get(tic, {}).get("destination", "")
                    if deliv.get(tic, {}).get("status", "") in
                    ("us_destination_confirmed", "other_destination_named") else ""),
                "deferred_federal": fed if fed is not None else "",
                "prior_federal": pf if pf is not None else "",
                "deferred_foreign": forn if forn is not None else "",
                "prior_foreign": pfo if pfo is not None else "",
                "delta_federal": dfed if dfed is not None else "",
                "delta_foreign": dfor if dfor is not None else "",
                "dominance": ratio,
                "federal_jump": fj, "foreign_jump": gj,
                "verdict": verdict,
            })
    if out:
        with OUT_SUM.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0]))
            w.writeheader()
            w.writerows(out)

    print(f"panel:   {len(rows):,} firm-years, {len(by_tic)} DI firms")
    print(f"tested:  {len(out)} firm-years where the text dates a transfer\n")
    for v, n in collections.Counter(r["verdict"] for r in out).most_common():
        print(f"  {v:<42} {n}")
    print("\n--- each tested firm-year ---")
    print(f"{'tic':<6}{'FY':<6}{'federal':>15}{'prior':>15}{'foreign':>15}{'prior':>15}"
          f"  {'dest':<14} verdict")
    for r in sorted(out, key=lambda r: (r["ticker"], r["fiscal_year"])):
        def m(x):
            return f"{x:,.0f}" if isinstance(x, float) else "-"
        print(f"{r['ticker']:<6}{r['fiscal_year']:<6}{m(r['deferred_federal']):>15}"
              f"{m(r['prior_federal']):>15}{m(r['deferred_foreign']):>15}"
              f"{m(r['prior_foreign']):>15}  {(r['text_destination'] or '-')[:13]:<14}"
              f"{r['verdict']}{'  [' + r['dominance'] + ']' if r['dominance'] else ''}"
              f"{'  [TCJA]' if r['tcja_window'] else ''}")
    print("\nA foreign jump is evidence the IP did NOT come onshore -- that direction")
    print("held five for five on the firms whose text names Ireland. A federal jump is")
    print("a candidate to read, not a finding: the federal line moves in years with no")
    print("transfer disclosed at all.")


if __name__ == "__main__":
    main()
