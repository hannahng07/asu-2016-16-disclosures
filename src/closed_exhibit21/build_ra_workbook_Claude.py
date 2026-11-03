#!/usr/bin/env python3
r"""The RA's workbook: new subsidiaries to research, checked against the tracker
by Irish CRO number as he types it.

WHY
---
Brian, 20 August:

> "It might be difficult to detect name changes... however, I'm asking this new
>  RA to pull Irish CRO numbers when he downloads the financial statements.
>  Maybe we can combine the old and new tracker files in the same Excel doc -
>  different sheets. Then the 'new' file will have a blank CRO line - when he
>  inputs the CRO - could we have a column next to it that cross-references the
>  old file and identifies whether that # is already in the sample?"

That is the right shape, and it is better than what it replaces. Everything the
name matching does -- the Companies Act form conversions, the possible_rename_of
column, the normalisation arguments -- is an attempt to guess at an identity
that the CRO number simply states. A name can be renamed, abbreviated, run
together with its neighbour or spelt three ways in three exhibits. A company
number cannot.

So the check happens at the moment of data entry, in the workbook, against the
one key both files can share.

HOW THE CHECK WORKS
-------------------
Sheet "New subs (research)" column A is blank for the RA. Column B holds:

    =IF(TRIM(A2)="","",IF(COUNTIF(...)>0,"ALREADY IN SAMPLE","NEW - proceed"))

and column C names the tracked subsidiary when there is a hit, which is what
turns the check into a rename detector: if the RA enters 411234 against
"Foo Ireland DAC" and column C says "Foo Ireland Limited", the rename is
demonstrated rather than inferred.

THE ONE TRAP IN THE LOOKUP, AND IT IS IN THE SOURCE DATA
---------------------------------------------------------
The tracker's own Irish ID column mixes text and numbers, and some values carry
a leading TAB -- "\t420222". A COUNTIF against that column matches 414156 and
misses 420222, silently, and the RA would be told a tracked company is new.

Both sides are therefore coerced: the tracker sheet is written with a cleaned
text key in column A, and the formula wraps the RA's entry in TRIM(...)&"".
Anything he types -- with spaces, as a number, as text -- lands on the same key.

Usage
-----
    cd "Grant and Nguyen"
    python build_ra_workbook_Claude.py

Writes: Irish_Subsidiary_Tracker_RA_Worklist_Claude.xlsx
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import openpyxl
import re
import zipfile
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule

HERE = Path(__file__).resolve().parent
LIN = HERE.parent / "Grant and Lin" / "DoubleIrishResearch"
TRACKER = LIN / "Irish_Subsidiary_Tracker__Asof081126_updated.xlsx"
NEW = HERE / "ex21_NEW_irish_subs_for_review_Claude.csv"
OUT = LIN / "Irish_Subsidiary_Tracker_RA_Worklist_Walsh.xlsx"

S_NEW = "New subs (research)"
S_OLD = "Existing tracker"
S_README = "Read me first"

FONT = "Arial"
HDR_FILL = PatternFill("solid", fgColor="1F3864")
INPUT_FILL = PatternFill("solid", fgColor="FFFF00")
HIT_FILL = PatternFill("solid", fgColor="FFC7CE")
OK_FILL = PatternFill("solid", fgColor="C6EFCE")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def clean_id(v) -> str:
    """The tracker's Irish ID, as a comparable string.

    Values arrive as ints, as floats, and as strings with a leading tab.
    """
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip().replace("\t", "").replace(" ", "")
    s = re.sub(r"\.0$", "", s)
    return s


def clean_cell(v):
    """Tidy a value copied out of the tracker.

    Two things travel with it. Cached Excel errors arrive as the literal string
    '#N/A' -- the tracker's ticker column holds four, on the XL Group rows --
    and re-writing those would ship a workbook that recalculates with errors in
    it, for a defect that is not ours and not visible to the RA anyway. And many
    subsidiary names carry leading tabs and newlines from an earlier paste.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        s = v.replace("\t", " ").replace("\n", " ").strip()
        return "" if s.startswith("#") and s.endswith(("A", "F", "0", "!", "?")) else s
    return v


def read_tracker():
    wb = openpyxl.load_workbook(TRACKER, read_only=True, data_only=True)
    ws = next((wb[n] for n in wb.sheetnames if "sub-level" in n.lower()), None)
    if ws is None:
        sys.exit(f"No 'Sub-Level tracker' sheet in {TRACKER.name}")
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    wb.close()
    header = rows[0]
    # column B is Irish ID, C ticker, E parent, F subsidiary, G.. the years
    out = []
    for r in rows[1:]:
        rid = clean_id(r[1])
        sub = clean_cell(r[5])
        if not rid and not str(sub).strip():
            continue
        out.append({
            "irish_id": rid,
            "ticker": clean_cell(r[2]),
            "parent_company": clean_cell(r[4]),
            "irish_subsidiary": clean_cell(sub),
            "years": [clean_cell(c) for c in r[6:18]],
        })
    year_headers = [str(c) for c in header[6:18]]
    return out, year_headers


def style_header(ws, row=1):
    for c in ws[row]:
        if c.value is None:
            continue
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HDR_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.border = BORDER


def strip_workbook_protection(path: Path) -> bool:
    """Remove the empty <workbookProtection/> element openpyxl writes.

    openpyxl emits it by default and it carries no attributes, so it protects
    nothing -- but some Excel builds read its mere PRESENCE as "the workbook
    structure is protected" and refuse edits. Brian hit exactly that: the
    reviewer's workbook opened but would not accept a keystroke.

    The fix is a straight rewrite of the zip with that one element dropped;
    every other part is copied through byte for byte, so formulas, formatting
    and conditional rules are untouched.
    """
    # The scratch copy goes to the system temp dir, NOT beside the target.
    # OneDrive refuses deletes from this process, so a temp file written into
    # the shared folder cannot be cleaned up and becomes litter next to the
    # deliverable -- which is how the wrong file gets opened.
    tmp = Path(tempfile.gettempdir()) / (path.stem + ".protfix.tmp")
    try:
        zin = zipfile.ZipFile(path)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "xl/workbook.xml":
                    x = data.decode("utf-8")
                    x = re.sub(r"<workbookProtection\s*/>", "", x)
                    x = re.sub(r"<workbookProtection.*?</workbookProtection>", "",
                               x, flags=re.S)
                    data = x.encode("utf-8")
                zout.writestr(item, data)
        zin.close()
        shutil.copy2(tmp, path)
        return True
    except Exception:
        return False
    finally:
        if tmp.exists():
            tmp.unlink()


def entries_already_made(path: Path) -> int:
    """How many CRO numbers the reviewer has already typed into column A.

    THIS SCRIPT REBUILDS THE WORKBOOK FROM SCRATCH, so running it over a file
    the RA has been working in would destroy every number he had entered --
    silently, and with no way to tell afterwards which rows were lost. The
    project's own rule applies: a step that writes a file must refuse to write a
    damaging one, and say so.
    """
    if not path.exists():
        return 0
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb[S_NEW] if S_NEW in wb.sheetnames else None
        if ws is None:
            wb.close()
            return 0
        n = sum(1 for r in ws.iter_rows(min_row=2, min_col=1, max_col=1,
                                        values_only=True)
                if r[0] not in (None, ""))
        wb.close()
        return n
    except Exception:
        # Unreadable is not the same as empty. Treat it as occupied.
        return -1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite even if the workbook already has CRO numbers in it")
    args = ap.parse_args()

    n = entries_already_made(OUT)
    if n != 0 and not args.force:
        stamp = datetime.now().strftime("%Y_%m_%d_%H%M")
        keep = OUT.with_name(f"{OUT.stem}_RA_WORK_{stamp}.xlsx")
        shutil.copy2(OUT, keep)
        sys.exit(
            f"REFUSING TO OVERWRITE {OUT.name}.\n"
            f"It already holds {n if n > 0 else 'an unknown number of'} CRO "
            f"numbers entered by the reviewer.\n"
            f"A copy has been saved as {keep.name}.\n"
            f"Re-run with --force only if you have merged that work somewhere safe.")

    tracker, year_headers = read_tracker()
    with NEW.open(newline="", encoding="utf-8", errors="replace") as fh:
        new = list(csv.DictReader(fh))

    wb = openpyxl.Workbook()

    # ------------------------------------------------ Existing tracker
    ws_old = wb.active
    ws_old.title = S_OLD
    old_cols = ["irish_id", "ticker", "parent_company", "irish_subsidiary"] + year_headers
    ws_old.append(old_cols)
    for t in tracker:
        ws_old.append([t["irish_id"], t["ticker"], t["parent_company"],
                       t["irish_subsidiary"]] + t["years"])
    for row in ws_old.iter_rows(min_row=2, max_col=len(old_cols)):
        for c in row:
            c.font = Font(name=FONT, size=10)
        row[0].alignment = Alignment(horizontal="left")
    style_header(ws_old)
    ws_old.freeze_panes = "B2"
    ws_old.auto_filter.ref = f"A1:{get_column_letter(len(old_cols))}{ws_old.max_row}"
    for col, w in zip("ABCD", (12, 10, 34, 44)):
        ws_old.column_dimensions[col].width = w
    for i in range(len(year_headers)):
        ws_old.column_dimensions[get_column_letter(5 + i)].width = 7

    n_old = ws_old.max_row
    # The lookup range. Absolute, and bounded rather than whole-column so the
    # formula stays cheap over ~2,900 rows.
    KEY = f"'{S_OLD}'!$A$2:$A${n_old}"
    SUB = f"'{S_OLD}'!$D$2:$D${n_old}"
    PAR = f"'{S_OLD}'!$C$2:$C${n_old}"

    # ------------------------------------------------ New subs
    ws = wb.create_sheet(S_NEW)
    # COLUMN ORDER FOLLOWS THE TASK, left to right.
    #
    # The first version put the twelve year columns last, at AC to AN, behind 28
    # columns of reference material. That is a horizontal scroll on every one of
    # 1,450 rows, for the second thing the reviewer has to type. They now sit
    # immediately after the name and the lookup answer, so one screen holds
    # everything he touches: read the name, type the number, read the answer,
    # tick the years. Diagnostics move right, where they are consulted rather
    # than used.
    lead = ["ticker", "company", "subsidiary_name"]
    year_cols = [str(y) for y in range(2014, 2026)]
    tail = ["search_difficulty", "name_flags", "name_ok", "sources", "name_source",
            "name_variants", "n_name_variants", "first_year", "last_year",
            "years", "n_filings", "possible_rename_of", "rename_score",
            "fic", "sic", "sic_group", "is_financial", "double_irish_firm",
            "cik", "gvkey"]
    src_cols = lead + tail
    head = (["irish_cro_num", "already_in_sample?", "matched_tracker_subsidiary",
             "matched_tracker_parent", "same_number_used_on_other_rows"]
            + lead + year_cols + tail)
    ws.append(head)

    for r in new:
        ws.append(["", "", "", "", ""]
                  + [r.get(c, "") for c in lead]
                  + ["" for _ in year_cols]
                  + [r.get(c, "") for c in tail])

    last = ws.max_row
    for i in range(2, last + 1):
        # COUNTIF coerces its criteria, so TRIM(A)&"" lands on the text keys in
        # the tracker sheet whether the RA types a number or a string.
        ws.cell(i, 2).value = (
            f'=IF(TRIM(A{i})="","",'
            f'IF(COUNTIF({KEY},TRIM(A{i})&"")>0,"ALREADY IN SAMPLE","NEW - proceed"))')
        ws.cell(i, 3).value = (
            f'=IF(TRIM(A{i})="","",'
            f'IFERROR(INDEX({SUB},MATCH(TRIM(A{i})&"",{KEY},0)),""))')
        ws.cell(i, 4).value = (
            f'=IF(TRIM(A{i})="","",'
            f'IFERROR(INDEX({PAR},MATCH(TRIM(A{i})&"",{KEY},0)),""))')
        # ONE COMPANY, TWO NAMES, TWO ROWS.
        #
        # The worked case is Aon. CRO 604607 was incorporated in May 2017 as
        # LINZICON LIMITED, became AON LIMITED, and is now AON PUBLIC LIMITED
        # COMPANY -- and the Exhibit 21 rows follow it, so the same company can
        # legitimately appear in this sheet more than once under different
        # spellings. When it does, the RA enters the same number twice and this
        # column says so, which is how a rename gets caught INSIDE the new list
        # rather than only against the old tracker.
        ws.cell(i, 5).value = (
            f'=IF(TRIM(A{i})="","",'
            f'IF(COUNTIF($A$2:$A${last},TRIM(A{i})&"")>1,'
            f'"SAME COMPANY - also entered elsewhere, likely a rename",""))')

    # The year columns are the reviewer's OTHER input, so they are shaded like
    # column A. Everything he types is yellow; everything the sheet computes is
    # not. That is the whole legend.
    y0 = 5 + len(lead) + 1                 # 1-based index of the 2014 column
    y1 = y0 + len(year_cols) - 1
    for row in ws.iter_rows(min_row=2, max_col=len(head)):
        for c in row:
            c.font = Font(name=FONT, size=10)
        for c in row[0:1] + row[y0 - 1:y1]:
            c.fill = INPUT_FILL
            c.font = Font(name=FONT, size=10, color="0000FF")
            c.border = BORDER
        row[0].alignment = Alignment(horizontal="left")
        for c in row[y0 - 1:y1]:
            c.alignment = Alignment(horizontal="center")
    style_header(ws)
    ws.freeze_panes = "F2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(head))}{last}"
    for col, w in zip(["A", "B", "C", "D", "E", "F", "G", "H"],
                      (14, 18, 30, 24, 26, 9, 26, 46)):
        ws.column_dimensions[col].width = w
    for i in range(y0, y1 + 1):
        ws.column_dimensions[get_column_letter(i)].width = 6

    # HIDE THE ROWS THAT ARE NOT THE PRIORITY GROUP.
    #
    # Brian, 20 August: "The sheet should be sorted so that the irrelevant ones
    # are hidden." Nothing is deleted -- clearing the filter brings all 3,161
    # back -- but the reviewer opens on the 1,450 that matter.
    #
    # Both the filter criteria AND the hidden flags are written. openpyxl cannot
    # make Excel evaluate a filter on open, so the criteria alone would leave
    # every row visible; the hidden flags alone would leave him unable to
    # restore them from the filter menu. Together they behave as a filter he
    # applied himself.
    def col_of(name):
        return head.index(name)            # zero-based, as add_filter_column wants

    ws.auto_filter.add_filter_column(col_of("name_ok"), ["yes"], blank=False)
    ws.auto_filter.add_filter_column(col_of("fic"), ["USA"], blank=False)
    ws.auto_filter.add_filter_column(col_of("is_financial"), [], blank=True)

    i_ok, i_fic, i_fin = (col_of("name_ok"), col_of("fic"), col_of("is_financial"))
    shown = 0
    for i, r in enumerate(new, start=2):
        keep = (r.get("name_ok") == "yes" and r.get("fic") == "USA"
                and not r.get("is_financial"))
        if keep:
            shown += 1
        else:
            ws.row_dimensions[i].hidden = True

    rng = f"B2:B{last}"
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'$B2="ALREADY IN SAMPLE"'], fill=HIT_FILL, stopIfTrue=False))
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'$B2="NEW - proceed"'], fill=OK_FILL, stopIfTrue=False))

    # ------------------------------------------------ Read me
    ws_r = wb.create_sheet(S_README, 0)
    lines = [
        ("Irish subsidiary tracker — research worklist", True),
        ("", False),
        (f"Built {Path(__file__).name}, from ex21_NEW_irish_subs_for_review_Claude.csv "
         f"and {TRACKER.name}.", False),
        ("", False),
        ("WHAT TO DO", True),
        (f"1.  Work on the '{S_NEW}' sheet. Every row is an Irish subsidiary disclosed in a "
         "US parent's Exhibit 21 that is NOT in the existing tracker by name.", False),
        ("2.  Find the company on the CRO register (core.cro.ie) and type its company "
         "number into column A. That is the ONLY column to type in — it is shaded yellow.", False),
        ("     If the name is not found, check the CRO's PREVIOUS NAMES field on similar "
         "companies. Aon is the worked example: company 604607 was incorporated in May 2017 "
         "as LINZICON LIMITED, became AON LIMITED, and is now AON PUBLIC LIMITED COMPANY. "
         "All three are the same company, and only the number says so.", False),
        ("3.  Column B answers immediately, and columns C and D show which tracked "
         "subsidiary the number belongs to when there is a hit.", False),
        ("", False),
        ("WHAT COLUMN B MEANS", True),
        ("ALREADY IN SAMPLE   the company number is in the existing tracker. Do NOT create "
         "a new row. Column C is the name it is tracked under — if that name differs from "
         "the one in this sheet, you have found a rename, which is worth noting.", False),
        ("NEW - proceed       the number is not in the tracker. Download the financial "
         "statements and fill the year columns.", False),
        ("", False),
        ("Column E watches for the same number entered on more than one row. That is not a "
         "mistake — it means one company appears in this sheet under two names, which is a "
         "rename. Note it and carry on.", False),
        ("", False),
        ("EXAMPLE (delete this line once you start)", True),
        ("Type 414156 into column A of any row and column B will read ALREADY IN SAMPLE, "
         "because that number is the first row of the existing tracker.", False),
        ("", False),
        ("WHICH ROWS TO DO FIRST", True),
        ("Filter to name_ok = yes, fic = USA, and is_financial blank. That is about 1,450 "
         "rows and is the population the project needs first. The sheet is already sorted "
         "so the most consistently disclosed entities are at the top.", False),
        ("", False),
        ("A WARNING ABOUT THE NAMES", True),
        ("These names were read out of Exhibit 21 tables automatically and about a quarter "
         "carry a defect — name_flags says which. 'two_entities_run_together' means the "
         "row holds two companies; 'no_corporate_form' usually means the name is cut "
         "short. Use judgement; the flags are a guide, not a verdict.", False),
        ("", False),
        ("possible_rename_of / rename_score are a GUESS made from the names alone, before "
         "any CRO number existed. Column B is the real answer. Where the two disagree, "
         "believe column B.", False),
        ("", False),
        (f"The '{S_OLD}' sheet is a copy of the Sub-Level tracker, for reference and for "
         "the lookup. Do not edit it — column B of the research sheet reads from it.", False),
    ]
    for i, (text, bold) in enumerate(lines, start=1):
        c = ws_r.cell(i, 1, text)
        c.font = Font(name=FONT, size=13 if i == 1 else 10, bold=bold or i == 1)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws_r.column_dimensions["A"].width = 116

    out = OUT
    try:
        wb.save(out)
    except PermissionError:
        out = OUT.with_name(OUT.stem + "_new.xlsx")
        wb.save(out)
        print("(the original was open in Excel; wrote a new file instead)")
    if strip_workbook_protection(out):
        print("removed the empty workbookProtection element "
              "(Excel treats it as a locked workbook)")
    print(f"existing tracker rows   {n_old - 1:,}")
    print(f"new subs to research    {last - 1:,}")
    print(f"  visible on open       {shown:,}  (the rest are filtered out, not deleted)")
    print(f"  CRO number goes in    column A")
    print(f"  year ticks go in      columns {get_column_letter(y0)} to {get_column_letter(y1)}"
          f"  (2014-2025)")
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
