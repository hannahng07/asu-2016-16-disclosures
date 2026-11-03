#!/usr/bin/env python3
r"""The firms whose transfer year has to come from the balance sheet, and the window.

WHY
---
248 of the 352 population firms never state when the transfer happened: their disclosure
is an adoption catch-up, which books the tax effect of transfers made in earlier years and
does not date them. The corpus cannot fix this -- the text does not contain the date.

Under the OLD rule an intra-entity transfer created a PREPAID TAX ASSET / deferred charge
that was amortised until the asset left the group, and on adoption that balance was written
off against retained earnings while deferred tax assets appeared. So the transfer shows as a
jump in the deferred-charge balance, in the year it happened -- years before the disclosure.

Everything on the machine starts too late to see it: the 10-X corpus begins in 2016, the
SEC notes data sets at 2018q1, the Calcbench export at Q1 2018 (and for the undated firms
it covers, only 278 rows carry a non-current tax asset). All three windows open at or after
adoption. Hence a Compustat pull.

This script regenerates the list from the CURRENT frame, so the window and the flags match
whatever the last build produced.

Writes: compustat_pull_list_Claude.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FIRMS = HERE / "population_firms_Claude.csv"
OUT = HERE / "compustat_pull_list_Claude.csv"
COLS = ["cik", "company", "ticker", "gvkey", "group", "double_irish", "ever_effect",
        "ever_assertion_only", "first_effect_date", "first_effect_fyear",
        "first_transfer_year", "first_transfer_year_basis", "transfer_year_upper_bound",
        "transfer_date_never_stated", "n_effect_pre_adoption", "max_amount",
        "pull_year_start", "pull_year_end", "why_in_list"]


def main():
    f = pd.read_csv(FIRMS, dtype=str)
    pop = f[f.ever_effect == "1"].copy()
    cmp_ = f[(f.ever_effect != "1") & (f.ever_adoption == "1")].copy()
    pop["group"], cmp_["group"] = "population_effect", "comparison_adoption_only"
    out = pd.concat([pop, cmp_], ignore_index=True)

    ub = pd.to_numeric(out.transfer_year_upper_bound, errors="coerce")
    fy = pd.to_numeric(out.first_effect_fyear, errors="coerce")
    end = ub.fillna(fy).fillna(2018)
    # eight years before the bound is enough to contain the transfer for every dated case
    # seen so far (the largest gap between transfer and disclosure is 7 years)
    out["pull_year_start"] = (end - 8).clip(lower=2008).astype(int)
    out["pull_year_end"] = (end + 2).clip(upper=2024).astype(int)
    out["why_in_list"] = [
        "no stated transfer date -- date it from the balance sheet"
        if (g == "population_effect" and n == "1")
        else ("has a stated transfer year -- VALIDATION case for the jump method"
              if g == "population_effect" else "comparison group")
        for g, n in zip(out.group, out.transfer_date_never_stated)]

    out[COLS].to_csv(OUT, index=False, quoting=csv.QUOTE_MINIMAL)
    n_und = ((out.group == "population_effect") &
             (out.transfer_date_never_stated == "1")).sum()
    n_val = ((out.group == "population_effect") &
             (out.transfer_date_never_stated != "1")).sum()
    print(f"wrote {OUT.name}: {len(out):,} firms")
    print(f"   population, no stated date (the ones to date): {n_und}")
    print(f"   population, stated date (validation set):      {n_val}")
    print(f"   comparison group, adoption only:               {(out.group=='comparison_adoption_only').sum()}")
    print(f"   window spans {out.pull_year_start.min()}-{out.pull_year_end.max()}; "
          f"a single 2008-2024 pull is simpler")
    print("\nitems: funda txdba txndb txdb txdc aco ao txp txt txfed txfo txdfed txdfo "
          "at sale ni xrd intan gdwl fic loc; fundq txdbq txdbaq atq saleq niq; "
          "crsp.ccmxpf_lnkhist gvkey lpermno linktype linkprim linkdt linkenddt")


if __name__ == "__main__":
    main()
