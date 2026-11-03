#!/usr/bin/env python3
r"""One row per firm, treated and control in the same table: the export.

WHAT THIS IS FOR
----------------
Everything up to here has been identification. This is the file the investor study
actually runs on: every firm that mentions ASU 2016-16 anywhere in the corpus, marked as
disclosing an effect or not, carrying its event date, its amount, its sign, where the IP
went, and its CRSP/Compustat keys -- so it can be merged with anything else by gvkey or
permno without re-deriving any of it.

    group = treated    the firm discloses an effect. `event_date` is its FIRST such
                       filing: the disclosure event
    group = control    the firm mentions the standard and never records an effect.
                       `event_date` is the first filing carrying the mention that places
                       its stratum -- the nearest thing it has to the same event

THE CONTROL GROUP HERE IS A SUBSAMPLE OF THE UNTREATED, NOT THE UNTREATED
-------------------------------------------------------------------------
Every row in this file is a firm that mentions ASU 2016-16 somewhere in the corpus. The
untreated universe is larger and this file does not contain it:

    1,724   mention the standard, record no effect        <- the `control` rows here
   10,507   never mention the standard in any form        -> never_mention_firms_Claude.csv
        ?   in Compustat/CRSP but never read by the sweep (not a 10-K/10-Q filer in the
            corpus window, or filing under a different CIK)

`untreated_frame` names which of these a row belongs to, so the file can be stacked with
the others without the strata being mistaken for the whole comparison group. Which
untreated firms the analysis uses is a design decision, not a property of this file.

THE FOUR THINGS A USER OF THIS FILE MUST NOT DO
-----------------------------------------------
1. Do not read `group = control` as "did not transfer". Disclosure is required only when
   material. These are controls for DISCLOSURE. The 10-K can confirm a transfer; it can
   never refute one.
2. Do not pool `usable_control = 0` rows into the comparison group. The reader found the
   disclosure in a table the corpus strips -- they are treated firms wearing a control's
   clothes, and including them biases an event study toward finding nothing.
3. Do not use an event window unless `link_basis == "filing_date"`. Any other basis means
   the returns belong to a NEIGHBOURING filing, not to this one.
4. Do not treat `amount` as the value of the IP. It is a tax effect. Never reconcile the
   two.

THE PRE-ADOPTION CATCH-UPS ARE A CATEGORY, NOT A GAP
----------------------------------------------------
247 of the 352 treated firms never date their transfer. Their disclosure is an adoption
catch-up: it books the tax effect of transfers made in earlier years and does not say
which. Carrying them as `transfer_year = missing` invites two mistakes -- dropping them,
which throws away 70% of the treated firms, or imputing a year, which invents data.

They are not missing. They are LEFT-CENSORED: the transfer happened at an unknown date
BEFORE a date we know. `transfer_era` names the category and `transfer_year_hi` carries
the bound, so the firms can be modelled as censored observations rather than dropped:

    dated             105   the text states the year. transfer_year_lo == _hi
    catchup_undated   247   pre-adoption, year unknown, bounded above by the adoption
                            year. 236 of the 247 carry that bound; 11 do not
    current_period          the transfer is in the filing's own period
    unknown                 neither dated nor placeable as a catch-up

`transfer_censoring` says which: `point`, `upper_bound_only`, or `none`. Nothing here
narrows the interval -- only a pre-2016 balance-sheet series can do that, and every source
on this machine opens at or after adoption.

WHAT IS DELIBERATELY EMPTY
--------------------------
`transfer_year` is blank for the adoption-catch-up firms, because the text does not
contain the date -- it is not a parsing failure, and filling it would be an invention.
`destination` is blank wherever the firm did not say. `amount` is blank where the corpus
stripped the figure and XBRL carried none.

Writes: asu_analysis_firms_Claude.csv / .dta
        asu_analysis_coverage_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

import pandas as pd

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
FIRMS = HERE / "population_firms_Claude.csv"
EVENT = HERE / "population_firms_event_Claude.csv"
CTRL = HERE / "control_firms_Claude.csv"
# written by coregistrant_map_Claude.py, which reads THIS file for names, so on a
# first build it is absent and the columns come through blank. Run it, then re-run.
COREG = HERE / "coregistrant_map_Claude.csv"
OUT = HERE / "asu_analysis_firms_Claude"
COV = HERE / "asu_analysis_coverage_Claude.csv"

EV = ["car_3day_market", "car_3day_decile", "cum_event_return", "cum_event_turnover",
      "return_std_dev", "bidaskspread", "median_bidask", "mean_bidask",
      "median_bidask_nonevent", "mean_bidask_nonevent", "median_nonevent_turnover"]
FIN = ["atq", "saleq", "mvecrsp", "prccq"]
ORDER = ["cik", "company", "group", "untreated_frame", "stratum", "double_irish",
         "gvkey", "permno", "tic", "link_basis",
         "firm_group_id", "is_coregistrant", "parent_cik", "parent_company",
         "parent_permno", "parent_gvkey", "parent_ambiguous",
         "event_date", "event_form", "event_accession", "event_class",
         "first_any_mention_date", "first_any_mention_class",
         "n_effect_filings", "n_filings_with_mention", "left_censored",
         "amount", "max_amount", "amount_source", "dta_dtl", "effect_direction",
         "ever_cost",
         "evidence_kind", "destination", "us_verdict", "ever_us_destination",
         "transfer_timing", "transfer_era", "transfer_year", "transfer_year_lo",
         "transfer_year_hi", "transfer_censoring", "transfer_year_basis",
         "transfer_year_never_stated", "years_disclosure_after_transfer",
         "ever_evaluating", "first_evaluating_date", "days_evaluating_to_effect",
         "xbrl_tagged", "reader_label", "usable_control"] + FIN + EV


def _era(b):
    """The transfer's date as a CATEGORY plus an interval, never as a silent blank."""
    yr = (b.get("first_transfer_year") or "").strip()
    ub = (b.get("transfer_year_upper_bound") or "").strip()
    tim = (b.get("first_transfer_timing") or "").strip()
    if b.get("ever_effect") != "1":
        return {"transfer_era": "", "transfer_year_lo": "", "transfer_year_hi": "",
                "transfer_censoring": ""}
    if yr:
        return {"transfer_era": "dated", "transfer_year_lo": yr,
                "transfer_year_hi": yr, "transfer_censoring": "point"}
    if tim in ("current_period", "current_period_inferred"):
        return {"transfer_era": "current_period", "transfer_year_lo": "",
                "transfer_year_hi": ub, "transfer_censoring":
                ("upper_bound_only" if ub else "none")}
    if tim == "pre_adoption" or b.get("transfer_date_never_stated") == "1":
        # left-censored: it happened before the bound, at an unknown date. The bound is
        # the adoption year, which is the ONE thing the catch-up disclosure does fix.
        return {"transfer_era": "catchup_undated", "transfer_year_lo": "",
                "transfer_year_hi": ub,
                "transfer_censoring": ("upper_bound_only" if ub else "none")}
    return {"transfer_era": "unknown", "transfer_year_lo": "", "transfer_year_hi": ub,
            "transfer_censoring": ("upper_bound_only" if ub else "none")}


def main():
    f = {r["cik"].lstrip("0"): r for r in csv.DictReader(FIRMS.open(encoding="utf-8"))}
    ev = {r["cik"].lstrip("0"): r for r in csv.DictReader(EVENT.open(encoding="utf-8"))}
    ct = {r["cik"].lstrip("0"): r for r in csv.DictReader(CTRL.open(encoding="utf-8"))}
    cg = ({r["cik"]: r for r in csv.DictReader(COREG.open(encoding="utf-8"))}
          if COREG.exists() else {})

    rows = []
    for cik, b in f.items():
        treated = b["ever_effect"] == "1"
        e = ev.get(cik, {}) if treated else {}
        c = ct.get(cik, {}) if not treated else {}
        src = e or c
        rows.append({
            "cik": b["cik"], "company": b["company"],
            "group": "treated" if treated else "control",
            "stratum": ("disclosed_effect" if treated else c.get("stratum", "")),
            # which slice of the untreated universe this row is, if any.
            "untreated_frame": ("" if treated else "mentions_no_effect"),
            "double_irish": b["double_irish"],
            "gvkey": src.get("gvkey", ""), "permno": src.get("permno", ""),
            "tic": src.get("tic", "") or b.get("ticker", ""),
            "link_basis": (e.get("first_effect_link_basis", "") if treated
                           else c.get("link_basis", "")),
            # joint filings: one accession, several CIKs. `firm_group_id` is the CIK the
            # market knows, so counting firms by it counts FILINGS-as-firms rather than
            # registrants. Nothing is collapsed here -- giving six Entergy subsidiaries
            # the parent's CAR would put one event in an event study six times.
            "firm_group_id": (g.get("parent_cik") or cik if (g := cg.get(cik, {})) or True
                              else cik),
            "is_coregistrant": cg.get(cik, {}).get("is_coregistrant_of_parent", "0"),
            "parent_cik": cg.get(cik, {}).get("parent_cik", ""),
            "parent_company": cg.get(cik, {}).get("parent_company", ""),
            "parent_permno": cg.get(cik, {}).get("parent_permno", ""),
            "parent_gvkey": cg.get(cik, {}).get("parent_gvkey", ""),
            "parent_ambiguous": cg.get(cik, {}).get("parent_ambiguous", ""),
            "event_date": (b["first_effect_date"] if treated else c.get("event_date", "")),
            "event_form": (b["first_effect_form"] if treated else c.get("event_form", "")),
            "event_accession": (b["first_effect_accession"] if treated
                                else c.get("event_accession", "")),
            "event_class": ("effect" if treated else c.get("stratum", "")),
            "first_any_mention_date": b["first_any_mention_date"],
            "first_any_mention_class": b["first_any_mention_class"],
            "n_effect_filings": b["n_effect_filings"],
            "n_filings_with_mention": c.get("n_filings_with_mention", ""),
            "left_censored": b["first_effect_left_censored"],
            "amount": b["first_amount"], "max_amount": b["max_amount"],
            "amount_source": e.get("amount_source", ""),
            "dta_dtl": b["first_amount_dta_dtl"],
            "effect_direction": b["first_amount_direction"],
            # first_amount_dta_dtl is the sign of the FIRST amount; ever_cost is whether the
            # firm EVER records a cost in any filing. They are different counts and have
            # been quoted as one before -- 21 vs 86 on the same 352 firms.
            "ever_cost": b.get("ever_cost", ""),
            "evidence_kind": e.get("evidence_kind", ""),
            "destination": e.get("destination", ""),
            "us_verdict": e.get("us_verdict", ""),
            "ever_us_destination": b.get("ever_us_destination", ""),
            "transfer_timing": b["first_transfer_timing"],
            **_era(b),
            "transfer_year": b["first_transfer_year"],
            "transfer_year_basis": b["first_transfer_year_basis"],
            "transfer_year_never_stated": b["transfer_date_never_stated"],
            "years_disclosure_after_transfer": b["years_disclosure_after_transfer"],
            "ever_evaluating": b["ever_evaluating"],
            "first_evaluating_date": b["first_evaluating_date"],
            "days_evaluating_to_effect": b["days_evaluating_to_effect"],
            "xbrl_tagged": (b.get("ever_xbrl_tagged", "") if treated
                            else c.get("xbrl_tagged", "")),
            "reader_label": c.get("reader_label", ""),
            # 1 = safe to use as a control. 0 = the reader found the disclosure in a
            # stripped table, so this firm is treated and must be left out.
            "usable_control": ("" if treated
                               else (0 if c.get("excluded_from_control") == "1" else 1)),
            **{k: src.get(k, "") for k in FIN + EV}})

    df = pd.DataFrame(rows)[ORDER]
    df.to_csv(f"{OUT}.csv", index=False)
    try:
        st = df.copy()
        for c2 in st.columns:
            if st[c2].dtype == object:
                st[c2] = st[c2].fillna("").astype(str)
        longs = [c2 for c2 in st.columns if st[c2].dtype == object
                 and st[c2].str.len().max() > 2000]
        st.to_stata(f"{OUT}.dta", write_index=False, version=118, convert_strl=longs)
    except Exception as e2:                                      # noqa: BLE001
        print(f"  (.dta not written: {e2})")

    t = df[df.group == "treated"]
    c = df[df.group == "control"]
    print(f"wrote {OUT.name}.csv / .dta: {len(df):,} firms "
          f"({len(t):,} treated, {len(c):,} control)")
    for gname, g in (("treated", t), ("control", c)):
        ncor = (g.is_coregistrant == "1").sum()
        ngrp = g.firm_group_id.nunique()
        print(f"   {gname}: {len(g):,} registrants -> {ngrp:,} distinct filing groups "
              f"({ncor} are co-registrants of a parent in the same file)")
    print(f"\n   control rows SAFE to use as controls: {(c.usable_control == 1).sum():,}"
          f" of {len(c):,}  ({(c.usable_control == 0).sum()} are stripped-table "
          f"disclosers, flagged out)")
    exact = (t.link_basis == "filing_date") & t.car_3day_market.notna() & (t.car_3day_market != "")
    cexact = ((c.link_basis == "filing_date") & c.car_3day_market.notna()
              & (c.car_3day_market != "") & (c.usable_control == 1))
    print(f"\n   USABLE FOR AN EVENT STUDY (exact filing-date link AND a 3-day CAR):")
    print(f"      treated {exact.sum():,} of {len(t):,}      control {cexact.sum():,} of "
          f"{(c.usable_control == 1).sum():,} usable controls")
    print(f"\n   treated, with an amount:        {(t.amount != '').sum():,} of {len(t):,}")
    print(f"   treated, sign known (DTA/DTL):  {(t.dta_dtl != '').sum():,} of {len(t):,}"
          f"   of which the FIRST amount is a DTL: {(t.dta_dtl == 'DTL').sum():,}")
    print(f"   treated, EVER records a cost:   {(t.ever_cost == '1').sum():,} of {len(t):,}"
          f"   (a different count from the line above -- do not quote them as one)")
    print(f"   treated, destination stated:    {(t.destination != '').sum():,} of {len(t):,}")
    print("\n   TRANSFER DATE, as a category rather than a blank:")
    for k, g in t.groupby("transfer_era"):
        hib = (g.transfer_year_hi != "").sum()
        print(f"      {k:<20}{len(g):>5} firms   {hib:>4} carry an upper bound")
    print(f"   treated, Double Irish:          {(t.double_irish == '1').sum():,}")
    print("\nby stratum:")
    srows = []
    for k, g in df.groupby("stratum"):
        u = ((g.link_basis == "filing_date") & g.car_3day_market.notna()
             & (g.car_3day_market != "")).sum()
        print(f"   {k:<24}{len(g):>6} firms   {u:>5} with an exact event window")
        srows.append({"stratum": k, "firms": len(g), "with_event_window": int(u)})
    pd.DataFrame(srows).to_csv(COV, index=False)


if __name__ == "__main__":
    main()
