#!/usr/bin/env python3
r"""The firm panel the Exhibit 21 extraction joins against.

WHY IT WAS REBUILT, 20 August
-----------------------------
Brian, 20 August: *"Could we also add the tickers for all of these companies?
They should also be in the stata file that I sent."*

They were. `USMNEswithIrishsubsinEx21.dta` carries TWO ticker fields and the
first version of this panel took the wrong one:

    tic      Compustat's ticker.  Populated on all 7,867 rows / 1,160 firms.
    ticker   Brian's own merge field. Populated on 1,152 rows / 103 firms.

`ticker` is the one that had been picked, so 765 of the 863 firms in the
extraction carried no ticker at all -- 82% of rows.

THE TWO FIELDS AGREE EXACTLY where both are present: 103 firms, zero
disagreements. So `tic` is not a substitute for Brian's field, it is the same
field with the gaps filled, which is why it is taken without qualification.

ONE THING TO KNOW ABOUT `tic`
-----------------------------
12 of the 1,160 carry a Compustat inactive-security code rather than a trading
symbol -- ARAMARK as 0083A, Toys R Us as 1231B, Avaya as 5933B. These are firms
that were acquired or taken private, and the code is what Compustat holds. They
are left as they are: the value is correct, it is simply not a symbol anyone
would recognise. `conm` is the readable identifier in those rows.

Usage
-----
    cd "Grant and Nguyen"
    python build_ex21_panel_Claude.py

Writes: ex21_panel_Claude.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DTA = (HERE.parent / "Grant and Lin" / "DoubleIrishResearch"
       / "USMNEswithIrishsubsinEx21.dta")
OUT = HERE / "ex21_panel_Claude.csv"

COLS = ["gvkey", "cik", "tic", "ticker", "conm", "fyear",
        "irelandcount", "dothaven", "preftaxcount", "DoubleIrish"]


def main() -> None:
    if not DTA.exists():
        sys.exit(f"Not found: {DTA}")
    df = pd.read_stata(DTA, columns=COLS)

    brian = df["ticker"].astype(str).str.strip()
    both = df[brian != ""]
    disagree = int((both["tic"].astype(str).str.strip()
                    != both["ticker"].astype(str).str.strip()).sum())

    df["ticker"] = df["tic"].astype(str).str.strip()
    df = df.drop(columns=["tic"])
    df["cik"] = df["cik"].astype(str).str.strip()
    df.to_csv(OUT, index=False)

    n_firms = df["cik"].nunique()
    with_ticker = df.loc[df["ticker"] != "", "cik"].nunique()
    print(f"panel rows              {len(df):,}")
    print(f"distinct firms          {n_firms:,}")
    print(f"  with a ticker         {with_ticker:,}")
    print(f"Double Irish firms      {df.loc[df['DoubleIrish'].astype(str).str.strip().isin(['1', '1.0']), 'cik'].nunique():,}")
    print(f"tic vs Brian's ticker, disagreements where both present: {disagree}")
    print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
