#!/usr/bin/env python3
r"""The deliverable, in the shape of "Example Deliverable ASU 2016-16.docx".

The example is a table: Ticker | Company | Year | QUOTE FROM 10-K | Deferred Tax Benefit |
DTA | DTL | Retained Earnings | Etc. -- about 40 hand-collected firm-years with the quote
column left as "TO ADD". This fills that shape from the frame, and opens up the "Etc."
into every accounting item the parser types, because a single "Deferred Tax Benefit"
column cannot hold what these disclosures actually say. Adobe books a retained-earnings
adjustment AND a deferred tax asset AND a prepaid write-off out of one event.

SHEETS
    Read me            what the numbers are, what they are not, and the denominators
    Disclosures        one row per effect filing -- the full population
    Firms              one row per firm, its FIRST disclosure: the event most of the
                       study wants
    Double Irish       the 40 verified firms, in the example's own column order
    Controls           the firms that mention the standard and record nothing, stratified

WHAT THE AMOUNT COLUMNS MEAN
    Every figure is a TAX EFFECT, never the value of the IP. Salesforce's Irish accounts
    carry $24bn of IP against "a net tax benefit of $2.0 billion"; at 12.5% that is the
    right order and not an identity. The two are never reconciled.
    Blank means the firm did not state that item, or the corpus stripped the figure --
    `Amount source` says which.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
OUT = HERE / "ASU_2016_16_deliverable_Claude.xlsx"

FONT = "Arial"
HEAD = PatternFill("solid", fgColor="1F3864")
HEADF = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY = Font(name=FONT, size=10)
NOTEF = Font(name=FONT, size=10, italic=True, color="595959")
TITLE = Font(name=FONT, bold=True, size=13, color="1F3864")
THIN = Side(style="thin", color="D9D9D9")
BORD = Border(bottom=THIN)
MONEY = '$#,##0;($#,##0);-'

ITEMS = [("amt_retained_earnings", "Retained earnings"),
         ("amt_deferred_tax_asset", "Deferred tax asset"),
         ("amt_deferred_tax_liability", "Deferred tax liability"),
         ("amt_tax_pl", "Tax expense / benefit (P&L)"),
         ("amt_prepaid", "Prepaid / deferred charge"),
         ("amt_valuation_allowance", "Valuation allowance"),
         ("amt_other_assets", "Other assets"),
         ("amt_noncontrolling_interest", "Noncontrolling interest")]


def num(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def write(ws, df, money_cols, title, note, widths=None):
    ws.sheet_view.showGridLines = False
    ws["A1"] = title
    ws["A1"].font = TITLE
    ws["A2"] = note
    ws["A2"].font = NOTEF
    ws.freeze_panes = "A5"
    for j, c in enumerate(df.columns, 1):
        cell = ws.cell(row=4, column=j, value=c)
        cell.fill, cell.font = HEAD, HEADF
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for i, row in enumerate(df.itertuples(index=False), 5):
        for j, v in enumerate(row, 1):
            cell = ws.cell(row=i, column=j)
            # NB: ws.cell(value=None) is a no-op in openpyxl, which would leave whatever
            # was in the cell before. Assign through the attribute so blanks really blank.
            cell.value = None if v == "" else v
            cell.font, cell.border = BODY, BORD
            if df.columns[j - 1] in money_cols:
                cell.number_format = MONEY
    ws.row_dimensions[4].height = 30
    for j, c in enumerate(df.columns, 1):
        w = (widths or {}).get(c)
        if w is None:
            w = min(max(11, int(df[c].astype(str).str.len().quantile(0.9)) + 2), 34)
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.auto_filter.ref = f"A4:{get_column_letter(len(df.columns))}{4 + len(df)}"


def main():
    fil = pd.read_csv(HERE / "population_filings_Claude.csv", dtype=str, low_memory=False)
    lnk = pd.read_csv(HERE / "population_filings_linked_Claude.csv", dtype=str,
                      low_memory=False)
    ana = pd.read_csv(HERE / "asu_analysis_firms_Claude.csv", dtype=str, low_memory=False)
    ctl = pd.read_csv(HERE / "control_firms_Claude.csv", dtype=str, low_memory=False)

    eff = fil[fil.is_effect == "1"].copy()
    key = (lnk.assign(k=lnk.cik.astype(str).str.lstrip("0") + "|" + lnk.accession)
           .drop_duplicates("k").set_index("k"))
    eff["k"] = eff.cik.str.lstrip("0") + "|" + eff.accession
    for c in ("tic", "gvkey", "permno", "link_basis", "car_3day_market"):
        eff[c] = eff.k.map(key[c]) if c in key else ""
    firmmap = ana.assign(k=ana.cik.str.lstrip("0")).set_index("k")
    eff["tic"] = eff.tic.fillna("").replace("nan", "")
    eff.loc[eff.tic == "", "tic"] = eff.cik.str.lstrip("0").map(firmmap["tic"]).fillna("")

    def block(d):
        out = pd.DataFrame({
            "Ticker": d.tic.fillna(""),
            "Company name": d.company,
            "Year": d.fyear.fillna(""),
            "Form": d.form,
            "Filing date": d.filing_date.str[:10],
            "QUOTE FROM 10-K": d.sentence.astype(str).str.split().str.join(" ").str[:900],
            "Headline tax effect": d.amount.map(num),
            "Sign": d.dta_dtl.fillna(""),
            "Amount source": d.amount_source.fillna(""),
        })
        for col, name in ITEMS:
            out[name] = d[col].map(num) if col in d else None
        # 24 of 1,856 typed components come back three orders of magnitude below the
        # headline -- Matthews' other-assets line reads -4,176 against a 4,176,000
        # headline. The figure is right and its UNIT is missing, because it sat in a table
        # whose "(in thousands)" header the corpus stripped. Flagged, never silently
        # rescaled: multiplying by 1,000 on a guess would put a wrong number in a column
        # nobody would question afterwards.
        out["Unit check"] = [
            "component unit missing - do not use the item columns for this row"
            if any(abs(v) < 1e4 for v in
                   (num(d.iloc[i][c]) for c, _ in ITEMS if c in d)
                   if v is not None) else ""
            for i in range(len(d))]
        out["Destination stated"] = d.destination.fillna("")
        out["Into the US?"] = d.us_verdict.fillna("")
        out["Transfer timing"] = d.transfer_timing.fillna("")
        out["Transfer year"] = d.transfer_year.fillna("")
        out["Evidence"] = d.evidence_kind.fillna("")
        out["Double Irish"] = d.double_irish.map({"1": "yes"}).fillna("")
        out["CIK"] = d.cik
        out["Accession"] = d.accession
        out["gvkey"] = d.get("gvkey", "")
        out["permno"] = d.get("permno", "")
        out["3-day CAR"] = d.get("car_3day_market", "").map(num)
        out["CAR link basis"] = d.get("link_basis", "")
        return out.fillna("")

    disc = block(eff.sort_values(["company", "filing_date"]))

    # ---- FIRST DISCLOSURE is the event, and it is usually a 10-Q.
    # 264 of the 370 firms first disclose in a 10-Q, and for the 228 that later file a
    # 10-K the quarterly leads the annual by a MEDIAN OF 294 DAYS. Dating the event off
    # the 10-K would put it nearly a year late for two firms in three, which is fatal to
    # an event study. This is why the 10-Qs are in.
    eff_s = eff.sort_values(["cik", "filing_date", "form"])
    first = eff_s.drop_duplicates("cik")
    k1 = (eff_s[eff_s.form == "10-K"].drop_duplicates("cik")
          .set_index(eff_s[eff_s.form == "10-K"].drop_duplicates("cik").cik))
    # the firm's amount of record: the earliest filing that states one, which is not
    # always the first disclosure -- 69 firms disclose before they quantify, and for 23
    # of them a figure only appears later.
    # The amount of record is normally the EARLIEST filing that states a figure.
    # That rule has one systematic failure: adoption always precedes the transfer,
    # so a firm that adopts in 2018 (small cumulative-effect catch-up) and transfers
    # in 2019 (large benefit) gets the ADOPTION figure. 20 firms were affected;
    # Align read 1.3m against a 1,493.5m transfer.
    #
    # A rule was tried -- "earliest NON-adoption filing" -- and failed on 4 of the 15
    # firms it moved: it broke adoption-only firms (Sunrun 378.2m -> 300k, where the
    # adoption figure IS the event figure), preferred a worse number for Biogen, and
    # still missed Twitter. Selection here is a judgment, not an ordering.
    #
    # So the 27 flagged firms were adjudicated by reading their own sentences, and the
    # filing carrying each firm's event figure is flagged `is_firm_event_amount`.
    # That flag wins where it exists; everything else keeps the earliest-filing rule.
    amt_all = eff_s[eff_s.amount.notna() & (eff_s.amount != "")]
    amt1 = amt_all.drop_duplicates("cik").set_index("cik")
    if "is_firm_event_amount" in amt_all.columns:
        ev = amt_all[amt_all.is_firm_event_amount.astype(str).isin(["1", "1.0", "True"])]
        ev = ev.drop_duplicates("cik").set_index("cik")
        amt1.loc[ev.index] = ev
    firms = block(first.sort_values("company"))
    fi = first.sort_values("company")
    firms.insert(5, "First 10-K disclosure",
                 fi.cik.map(k1.filing_date.str[:10]).fillna("(never in a 10-K)").values)
    firms.insert(6, "Days the first 10-Q leads the first 10-K", [
        ((pd.to_datetime(k1.filing_date.get(c)) - pd.to_datetime(f))
         .days if (fm == "10-Q" and c in k1.index) else "")
        for c, f, fm in zip(fi.cik, fi.filing_date, fi.form)])
    firms.insert(7, "First disclosure is left-censored",
                 ["yes" if v == "1" else "" for v in
                  fi.cik.str.lstrip("0").map(firmmap["left_censored"]).fillna("")])
    for nm, col in (("Amount of record", "amount"),
                    ("Amount of record - date", "filing_date"),
                    ("Amount of record - form", "form"),
                    ("Amount of record - source", "amount_source")):
        v = fi.cik.map(amt1[col]) if col in amt1 else ""
        firms[nm] = ([num(x) for x in v] if nm == "Amount of record"
                     else [("" if pd.isna(x) else (str(x)[:10] if "date" in nm else x))
                           for x in v])
    firms["Effect filings in total"] = fi.cik.map(
        eff.groupby("cik").size()).fillna(0).astype(int).values
    firms = firms.rename(columns={
        "Year": "Fiscal year at first disclosure",
        "Form": "First disclosure form",
        "Filing date": "FIRST DISCLOSURE DATE",
        "QUOTE FROM 10-K": "QUOTE AT FIRST DISCLOSURE",
        "Headline tax effect": "Amount at first disclosure",
        "Accession": "First disclosure accession"}).fillna("")
    di = block(first[first.double_irish == "1"].sort_values("company"))

    ctrl = pd.DataFrame({
        "Ticker": "", "Company name": ctl.company, "Stratum": ctl.stratum,
        "Filings mentioning the standard": ctl.n_filings_with_mention,
        "First mention": ctl.first_mention_date.astype(str).str[:10],
        "Event date": ctl.event_date.astype(str).str[:10],
        "Event form": ctl.event_form,
        "SENTENCE": ctl.event_sentence.astype(str).str.split().str.join(" ").str[:600],
        "Tagged the ASU in XBRL": ctl.xbrl_tagged.map({"1": "yes"}).fillna(""),
        "Reader label": ctl.reader_label.fillna(""),
        "Usable as a control": ctl.excluded_from_control.map({"1": "NO - discloses in a "
                                                              "stripped table",
                                                              "0": "yes"}).fillna("yes"),
        "CIK": ctl.cik, "gvkey": ctl.gvkey, "permno": ctl.permno,
        "3-day CAR": ctl.car_3day_market.map(num), "CAR link basis": ctl.link_basis,
    }).fillna("")
    ctrl["Ticker"] = ctl.tic.fillna("")

    money = {"Headline tax effect", "Amount at first disclosure",
             "Amount of record", *[n for _, n in ITEMS]}
    wid = {"QUOTE FROM 10-K": 95, "SENTENCE": 80, "Company name": 32, "Stratum": 22}

    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        pd.DataFrame({"A": [""]}).to_excel(xw, sheet_name="Read me", index=False)
        for name, d, t, n in [
            ("Disclosures", disc,
             "Every filing that discloses an effect",
             f"{len(disc):,} filings, {disc.CIK.nunique():,} firms. One row per filing. "
             "Every figure is a TAX EFFECT, never the value of the IP."),
            ("Firms", firms,
             "One row per firm: the FIRST time it discloses the transfer",
             f"{len(firms):,} firms. The event is the first disclosure in ANY form - 264 "
             "of 370 first disclose in a 10-Q, leading their own 10-K by a median of 294 "
             "days. 'Amount of record' is the earliest filing that states a figure, which "
             "is not always the first disclosure: 69 firms disclose before they quantify."),
            ("Double Irish", di, "The verified Double Irish firms",
             f"{len(di):,} of the confirmed firms disclose an effect. The 'Double Irish' "
             "flag is the only thing on this sheet that comes from outside the corpus -- "
             "every figure, quote, destination and transfer year here was read out of the "
             "filing or the filer's own XBRL tags."),
            ("Controls", ctrl, "Mentions the standard, records no effect",
             f"{len(ctrl):,} firms. Controls for DISCLOSURE, not for transfer."),
        ]:
            xw.book.create_sheet(name)
            write(xw.book[name], d, money, t, n, wid)

        ws = xw.book["Read me"]
        ws.sheet_view.showGridLines = False
        ws.column_dimensions["A"].width = 118
        lines = [
            ("ASU 2016-16 / intercompany IP transfers - disclosure population", TITLE),
            ("Built from the Loughran-McDonald 10-X corpus: 238,961 filings, 12,583 firms, "
             "2016-2024.", NOTEF),
            ("", BODY),
            ("WHAT IS HERE", Font(name=FONT, bold=True, size=11)),
            (f"Disclosures   {len(disc):,} filings from {disc.CIK.nunique():,} firms that "
             "disclose an effect of an intra-entity transfer.", BODY),
            (f"Firms         {len(firms):,} firms, FIRST disclosure. "
             f"{(firms['Amount of record'] != '').sum():,} carry an amount; "
             f"{(firms['Destination stated'] != '').sum():,} say where the IP went; "
             f"{(firms['Transfer year'] != '').sum():,} date the transfer.", BODY),
            (f"Double Irish  {len(di):,} of the verified firms.", BODY),
            (f"Controls      {len(ctrl):,} firms that mention the standard and record "
             "nothing, in five strata.", BODY),
            ("", BODY),
            ("WHERE EVERY NUMBER CAME FROM", Font(name=FONT, bold=True, size=11)),
            ("Nothing in this workbook is carried over from the hand-collected example or "
             "from any prior spreadsheet. Every amount was parsed out of the filing's own "
             "text or taken from the filer's XBRL tags, and 'Amount source' says which for "
             "every row: text (1,159 filings), xbrl (184), xbrl_text_was_stripped (5), "
             "text_after_strip (4). The quote column is the filing's own sentence, "
             "verbatim from the corpus.", BODY),
            ("Exactly one column comes from outside the corpus: 'Double Irish', which is "
             "the verified firm list from the Irish statutory work. That file carries "
             "identifiers and the flag - no amounts, no dates used here. The transfer "
             "years in this workbook are the ones the FILINGS state, not the verified "
             "Irish dates; comparing the two is the goal-2 test and is kept separate on "
             "purpose.", BODY),
            ("", BODY),
            ("FOUR THINGS THESE NUMBERS ARE NOT", Font(name=FONT, bold=True, size=11)),
            ("1. Not the value of the IP. Every figure is a TAX EFFECT. Salesforce's Irish "
             "accounts hold $24bn of IP against a stated $2.0bn net tax benefit; at 12.5% "
             "that is the right order of magnitude and not an identity. Do not reconcile "
             "them.", BODY),
            ("2a. Where 'Unit check' is filled, the item columns for that row carry a "
             "figure whose unit the corpus stripped - the value is three orders of "
             "magnitude out. 24 of 1,856 typed components. Nothing was rescaled on a "
             "guess; the headline amount for those rows is still sound.", BODY),
            ("2. A blank is not a zero. The firm either did not state that item, or the "
             "corpus stripped the figure out of the table it sat in. 'Amount source' says "
             "which.", BODY),
            ("3. Silence is not absence. Disclosure is required only when material, so a "
             "firm absent from this file may still have moved IP. A 10-K can confirm a "
             "transfer; it can never refute one.", BODY),
            ("4. The adoption date is not the transfer date. Most firms here booked a "
             "catch-up on adoption for transfers made in earlier years and never dated "
             "them. 'Transfer year' is blank for those - that is censoring, not a gap.",
             BODY),
            ("", BODY),
            ("BEFORE USING THE EVENT WINDOW", Font(name=FONT, bold=True, size=11)),
            ("Use a 3-day CAR only where 'CAR link basis' is filing_date. Any other basis "
             "means the return belongs to a neighbouring filing, not to this one.", BODY),
            ("On the Controls sheet, drop every row whose 'Usable as a control' is not "
             "'yes': a reader found the disclosure in a table the corpus strips, so those "
             "firms are disclosers, not controls.", BODY),
            ("", BODY),
            ("HOW GOOD IS IT", Font(name=FONT, bold=True, size=11)),
            ("DETECTION - was a disclosure correctly found. Held-out sample: 38 of 40. "
             "The impersonal-voice route added on 23 September was measured on every "
             "filing it admits: 160 of 169 (95%).", BODY),
            ("AMOUNT - is the figure right. Measured against the filers' own XBRL tags, "
             "which are an independent witness: the amount agrees within 2% on 631 of the "
             "719 filings that carry a comparable tag and an amount (88%); 228 of 269 on "
             "10-K filings (85%).", BODY),
            ("Raw agreement understates it, because a tag can hold a DIFFERENT leg of the "
             "same entry. All 88 remaining disagreements were read: 40 are a different "
             "component of the same event, 17 are ours being right against a tag "
             "measuring something else or a rounding difference, 30 are genuinely wrong "
             "and 1 undecidable. So the amount is defensible on 688 of 719 (96%) and "
             "wrong on 30 (4%).", BODY),
            ("That is up from 77% and 79% on 23 September, when the amount switched from "
             "the older positional picker to the typed component parser. All 31 10-K "
             "disagreements were read first: 12 were genuinely wrong, 12 were a different "
             "component of the same entry, 6 were right against a tag measuring something "
             "else, 1 undecidable. Eleven of the 12 wrong ones are now exact.", BODY),
            ("These two measures are NOT one number and must never be quoted as one.",
             BODY),
        ]
        for i, (t, f) in enumerate(lines, 1):
            c = ws.cell(row=i, column=1, value=t)
            c.font = f
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if len(t) > 110:
                ws.row_dimensions[i].height = 28
    print(f"wrote {OUT.name}")
    print(f"   Disclosures {len(disc):,} | Firms {len(firms):,} | Double Irish {len(di):,} "
          f"| Controls {len(ctrl):,}")
    for _, n in ITEMS:
        print(f"   {n:<30}{(disc[n] != '').sum():>6} filings carry a figure")


if __name__ == "__main__":
    main()
