#!/usr/bin/env python3
r"""Put the disclosing filings next to the market's reaction to them.

WHY
---
The identification work exists to answer an investor question, and until now the frame has
stopped at the filing. `ASUdata_CRSP_Compustat_May25.dta` carries the other half: gvkey,
permno, the quarterly Compustat items and the event-window variables already built
(`car_3day_market`, `cum_event_return`, `cum_event_turnover`, the bid-ask measures). This
joins the two so every disclosing filing carries its own market reaction.

HOW THE JOIN IS MADE, strongest first -- and the basis travels with the row
---------------------------------------------------------------------------
    filing_date   same CIK, same filing date. The filing is the event; this is exact
    period        same CIK, same period of report (our datadate = their datadate)
    nearest       same CIK, the panel row whose filing date is closest within 45 days --
                  for amended or re-filed documents where the dates move a little
    firm_only     the firm is in the panel but no filing row matches: gvkey and permno
                  are carried, the event variables are NOT

A row joined `firm_only` has no event window and must never be used as though it had one.
`link_days_apart` records the gap for every non-exact join.

WHAT THIS DOES NOT DO
---------------------
It does not build event windows. Those are already in the panel, computed on the filing
dates the panel itself carries -- so a `nearest` join means the returns belong to a
NEIGHBOURING filing, not to ours. Use `link_basis == "filing_date"` for anything that
turns on the event date.

The panel starts in 2016, so pre-adoption filings and the 2016 tail of the corpus have no
match by construction, not by failure.

Writes: population_filings_linked_Claude.csv / .dta
        link_event_coverage_Claude.csv   what matched, by year and form
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PANEL = HERE / "ASUdata_CRSP_Compustat_May25.dta"
FILINGS = HERE / "population_filings_Claude.csv"
OUT = HERE / "population_filings_linked_Claude"
COV = HERE / "link_event_coverage_Claude.csv"

PANEL_COLS = ["gvkey", "cik", "tic", "conm", "datadate", "fyearq", "fqtr", "formtype",
              "filingdate", "reportdate", "permno", "atq", "saleq", "niq", "txdbaq",
              "txdbq", "txdbclq", "prccq", "mvecrsp", "car_3day_market",
              "car_3day_decile", "cum_event_return", "cum_event_turnover",
              "return_std_dev", "bidaskspread", "median_bidask", "mean_bidask",
              "median_bidask_nonevent", "mean_bidask_nonevent",
              "median_nonevent_turnover", "asufirm", "asucount"]
EVENT_COLS = ["car_3day_market", "car_3day_decile", "cum_event_return",
              "cum_event_turnover", "return_std_dev", "bidaskspread", "median_bidask",
              "mean_bidask", "median_bidask_nonevent", "mean_bidask_nonevent",
              "median_nonevent_turnover"]
KEEP = ["cik", "accession", "form", "filing_date", "company", "datadate", "fyear",
        "double_irish", "disclosure_class", "is_effect", "evidence_kind",
        "transfer_timing", "transfer_year", "amount", "amount_source", "dta_dtl",
        "effect_direction", "us_verdict", "destination", "sentence"]


def d(x):
    return pd.to_datetime(x, errors="coerce")


def main():
    fil = pd.read_csv(FILINGS, dtype=str)
    # the frame's own gvkey/ticker are filled only for the Double Irish firms; the panel
    # has them for everyone, so drop ours before the merge and let the panel's stand
    fil = fil.drop(columns=[c for c in ("gvkey", "ticker") if c in fil.columns])
    fil["cikn"] = fil.cik.str.lstrip("0")
    fil["fdate"] = d(fil.filing_date)
    fil["pdate"] = d(fil.datadate)

    p = pd.read_stata(PANEL, columns=PANEL_COLS)
    p["cikn"] = p.cik.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.lstrip("0")
    p["fdate"] = d(p.filingdate)
    p["pdate"] = d(p.datadate)
    p = p.dropna(subset=["cikn"])
    print(f"panel: {len(p):,} firm-quarters, {p.cikn.nunique():,} CIKs, "
          f"{p.fdate.min():%Y-%m-%d} to {p.fdate.max():%Y-%m-%d}")

    # ---- 1. exact on cik + filing date
    a = p.drop_duplicates(["cikn", "fdate"])
    m = fil.merge(a, on=["cikn", "fdate"], how="left", suffixes=("", "_p"))
    m["link_basis"] = m.permno.notna().map({True: "filing_date", False: ""})
    m["link_days_apart"] = 0.0

    # ---- 2. period of report, for the rows still empty
    todo = m.link_basis == ""
    b = p.drop_duplicates(["cikn", "pdate"])[["cikn", "pdate"] +
                                             [c for c in p.columns
                                              if c not in ("cikn", "pdate", "fdate")]]
    fix = m.loc[todo, ["cikn", "pdate"]].merge(b, on=["cikn", "pdate"], how="left")
    for c in fix.columns:
        if c in ("cikn", "pdate"):
            continue
        m.loc[todo, c] = fix[c].values
    got = todo & m.permno.notna()
    m.loc[got, "link_basis"] = "period"
    m.loc[got, "link_days_apart"] = (m.loc[got, "fdate"] - d(m.loc[got, "filingdate"])).dt.days

    # ---- 3. nearest filing within 45 days
    todo = m.link_basis == ""
    if todo.any():
        left = m.loc[todo, ["cikn", "fdate"]].reset_index().sort_values("fdate")
        right = p.dropna(subset=["fdate"]).sort_values("fdate")
        near = pd.merge_asof(left, right, on="fdate", by="cikn",
                             direction="nearest", tolerance=pd.Timedelta("45D"))
        near = near.set_index("index")
        for c in near.columns:
            if c in ("cikn", "fdate"):
                continue
            m.loc[near.index, c] = near[c]
        got = todo & m.permno.notna()
        m.loc[got, "link_basis"] = "nearest"
        m.loc[got, "link_days_apart"] = (
            m.loc[got, "fdate"] - d(m.loc[got, "filingdate"])).dt.days

    # ---- 4. firm only: gvkey/permno from any row of that firm, no event variables
    todo = m.link_basis == ""
    firm = (p.sort_values("fdate").drop_duplicates("cikn")
            .set_index("cikn")[["gvkey", "permno", "tic", "conm"]])
    for c in ("gvkey", "permno", "tic", "conm"):
        m.loc[todo, c] = m.loc[todo, "cikn"].map(firm[c])
    got = todo & m.permno.notna()
    m.loc[got, "link_basis"] = "firm_only"
    m.loc[got, EVENT_COLS] = pd.NA          # no event window belongs to this row
    m.loc[m.link_basis == "", "link_basis"] = "no_match"

    out = m[[c for c in KEEP if c in m] +
            ["gvkey", "permno", "tic", "conm", "link_basis", "link_days_apart",
             "filingdate", "datadate_p" if "datadate_p" in m else "datadate",
             "fyearq", "fqtr", "atq", "saleq", "niq", "txdbaq", "txdbq", "txdbclq",
             "prccq", "mvecrsp"] + EVENT_COLS].copy()
    out.to_csv(f"{OUT}.csv", index=False)
    try:
        st = out.copy()
        for c in st.columns:
            if st[c].dtype == object:
                st[c] = st[c].fillna("").astype(str)
        longs = [c for c in st.columns if st[c].dtype == object
                 and st[c].str.len().max() > 2000]
        st.to_stata(f"{OUT}.dta", write_index=False, version=118, convert_strl=longs)
    except Exception as e:                                   # noqa: BLE001
        print(f"  (.dta not written: {e})")

    eff = out[out.is_effect == "1"]
    print(f"\nfilings in the frame: {len(out):,}; effect filings: {len(eff):,}")
    print("\nhow the EFFECT filings joined:")
    for k, v in eff.link_basis.value_counts().items():
        print(f"   {k:<14}{v:>6}   ({v/len(eff):.0%})")
    ev = eff[(eff.link_basis == "filing_date") & eff.car_3day_market.notna()]
    print(f"\n   effect filings with an EXACT filing-date link AND a 3-day CAR: "
          f"{len(ev):,} ({len(ev)/len(eff):.0%} of effect filings), "
          f"{ev.cik.nunique():,} firms")
    print(f"   permno present on {eff.permno.notna().sum():,} effect filings, "
          f"gvkey on {eff.gvkey.notna().sum():,}")

    # ---- firm level: the FIRST effect filing, which is the event most of the study wants
    fe = (eff.sort_values(["cik", "filing_date"]).drop_duplicates("cik")
          .rename(columns={"filing_date": "first_effect_date",
                           "accession": "first_effect_accession",
                           "form": "first_effect_form",
                           "link_basis": "first_effect_link_basis"}))
    keep = ["cik", "company", "gvkey", "permno", "tic", "conm", "first_effect_date",
            "first_effect_accession", "first_effect_form", "first_effect_link_basis",
            "double_irish", "evidence_kind", "transfer_timing", "transfer_year",
            "amount", "amount_source", "dta_dtl", "effect_direction", "us_verdict",
            "destination", "atq", "saleq", "mvecrsp", "prccq"] + EVENT_COLS
    fe[[c for c in keep if c in fe]].to_csv(HERE / "population_firms_event_Claude.csv",
                                            index=False)
    n_car = fe[(fe.first_effect_link_basis == "filing_date")
               & fe.car_3day_market.notna()]
    print(f"\nfirm level: {len(fe):,} firms, first effect filing carried through; "
          f"{len(n_car):,} have an exact link and a 3-day CAR on that filing")

    cov = (out.assign(year=d(out.filing_date).dt.year)
           .groupby(["year", "form", "link_basis"]).size()
           .rename("filings").reset_index())
    cov.to_csv(COV, index=False)
    y = (eff.assign(year=d(eff.filing_date).dt.year)
         .groupby("year")
         .agg(effect_filings=("cik", "size"),
              with_car=("car_3day_market", lambda s: s.notna().sum())))
    print("\nby filing year (effect filings, and how many carry a 3-day CAR):")
    print(y.to_string())
    print("\n   the panel starts in 2016, so 2016 and earlier have no match by "
          "construction -- that is the data's window, not a failure of the join")


if __name__ == "__main__":
    main()
