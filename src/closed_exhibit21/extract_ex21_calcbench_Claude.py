#!/usr/bin/env python3
r"""Irish subsidiaries from a Calcbench Exhibit 21 PDF export.

WHY THIS EXISTS ALONGSIDE extract_ex21_irish_subs_Claude.py
------------------------------------------------------------
Brian, 20 August: *"I added a PDF... 2016 Ex 21 Disclosures from Calcbench. I'm
thinking this is going to be the cleaner file in which to get the names of the
Irish subs."*

He is right, and the reason is structural rather than incidental.

The Loughran-McDonald corpus FLATTENS the exhibit's table into one run of text:

    AbbVie Aviation LLC Illinois AbbVie Biopharmaceuticals LLC Delaware ...

so a name is whatever sits between two recognised jurisdictions, and every
defect fixed in that reader on 20 August came from that one decision -- names
truncated at a bracket, two entities welded together by a jurisdiction the
vocabulary did not know, "Rep. of" left on the end of the previous company.

The Calcbench PDF keeps the COLUMNS:

    Abbott Ireland                                           Ireland
    Abbott Laboratories, Ireland, Limited                    Ireland

Name and jurisdiction are separated by whitespace on the same line, so the
split is positional rather than lexical. There is no vocabulary to be
incomplete, and a jurisdiction inside a name -- "AbbVie Ireland Holdings
Unlimited Company" -- cannot be mistaken for the column, because it is not in
the column.

WHAT IT COSTS
-------------
Coverage. The PDF holds one year at a time and the firms Calcbench happened to
export. The 10-X corpus holds every 10-K filed 2016-2024. So this is the
BETTER READER OF A NARROWER SOURCE, and the two are complementary: use this to
verify and correct names, use the corpus for reach.

THE STRUCTURE OF THE EXPORT
---------------------------
    <Company Name> 10-K:
    Period Ending: 12/31/2016 (from 10-K reported on: 2/17/2017)
    <the exhibit, verbatim, as laid out on the page>

Firms are delimited by that first line. Everything until the next one belongs
to the firm named in it.

Usage
-----
    cd "Grant and Nguyen"
    python extract_ex21_calcbench_Claude.py "..\Grant and Lin\DoubleIrishResearch\2016 Ex 21 Disclosures from Calchbench.pdf"

Writes: ex21_calcbench_<year>_Claude.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

FIRM = re.compile(r"^(?P<name>.+?)\s+10-K:\s*$")
PERIOD = re.compile(r"Period Ending:\s*(\d{1,2}/\d{1,2}/(\d{4}))")

# name, two-or-more spaces, jurisdiction. The gap IS the column boundary.
ROW = re.compile(r"^\s*(?P<name>\S.*?\S)\s{2,}(?P<jur>[A-Za-z][A-Za-z .,'’&()/-]{1,40})\s*$")

IRISH = re.compile(r"^\s*(?:the\s+)?(republic\s+of\s+ireland|ireland,?\s*republic\s+of|"
                   r"ireland|republic\s+of\s+ireland\s*\(.*\)|eire)\s*[.*†‡]?\s*$", re.I)

# Lines that match ROW's shape but are not subsidiaries.
NOT_A_ROW = re.compile(
    r"^\s*(name of subsidiar|subsidiar|domestic|foreign|international|jurisdiction|"
    r"state or |country|entity|exhibit|list of|the following|percentage|"
    r"where ownership|quicklinks|table of contents|page\b)", re.I)

# An asterisk or footnote marker on the name is an ownership note, not a name.
FOOTNOTE_TAIL = re.compile(r"\s*[*†‡]+\s*$")

# Exhibits number their rows, and the number is part of the LAYOUT, not the
# name: Aircastle's list gives "129   Constitution Aircraft Leasing (Ireland) 3".
# A bare leading integer is stripped only when a letter follows it, so
# "3M Company" and "1-800-FLOWERS" survive.
LEAD_NUMBER = re.compile(r"^\s*\(?\d{1,3}\)?[.)]?\s+(?=[A-Za-z])")

MIN_NAME, MAX_NAME = 3, 120


def pdf_to_text(pdf: Path) -> str:
    """pdftotext -layout. The layout flag is the whole point -- without it the
    columns collapse and this reader has no advantage over the other one."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
        out = Path(fh.name)
    try:
        subprocess.run(["pdftotext", "-layout", str(pdf), str(out)],
                       check=True, capture_output=True)
        return out.read_text(encoding="utf-8", errors="replace")
    finally:
        out.unlink(missing_ok=True)


def parse(text: str):
    firm = year = None
    rows, stats = [], {"firms": 0, "firms_with_irish": 0, "rows": 0}
    seen_firm_irish = False

    for line in text.splitlines():
        m = FIRM.match(line)
        if m and len(m.group("name")) < 90:
            firm, year = m.group("name").strip(), None
            stats["firms"] += 1
            seen_firm_irish = False
            continue
        if firm is None:
            continue
        p = PERIOD.search(line)
        if p and year is None:
            year = p.group(2)
            continue
        if NOT_A_ROW.match(line):
            continue
        r = ROW.match(line)
        if not r:
            continue
        jur = r.group("jur").strip()
        if not IRISH.match(jur):
            continue
        name = FOOTNOTE_TAIL.sub("", r.group("name").strip())
        # A leading glyph is a list bullet the PDF kept -- "Ù   Gartner Ireland
        # Limited". Digits survive, so 3M and 1-800-FLOWERS are safe.
        name = re.sub(r"^[^A-Za-z0-9(]+", "", name)
        name = LEAD_NUMBER.sub("", name).strip(" ,;.-–—|")
        if not (MIN_NAME <= len(name) <= MAX_NAME):
            continue
        if not re.search(r"[A-Za-z]{3}", name):
            continue
        rows.append({
            "parent_company": firm,
            "period_year": year or "",
            "subsidiary_name": name,
            "jurisdiction_as_written": jur,
        })
        stats["rows"] += 1
        if not seen_firm_irish:
            stats["firms_with_irish"] += 1
            seen_firm_irish = True
    return rows, stats


def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        k = (r["parent_company"].lower(), r["period_year"],
             r["subsidiary_name"].lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def write(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="+",
                    help="one or more Calcbench exports, or a folder of them")
    ap.add_argument("--year", help="label; inferred per file if omitted")
    ap.add_argument("--no-combined", action="store_true",
                    help="skip the merged all-years file")
    args = ap.parse_args()

    pdfs = []
    for p in args.pdf:
        path = Path(p)
        if path.is_dir():
            pdfs.extend(sorted(path.glob("*.pdf")))
        elif path.exists():
            pdfs.append(path)
        else:
            sys.exit(f"Not found: {path}")

    combined = []
    for pdf in pdfs:
        rows, stats = parse(pdf_to_text(pdf))
        if not rows:
            print(f"{pdf.name}: NO Irish rows -- is pdftotext -layout available?")
            continue
        year = args.year or max(
            (r["period_year"] for r in rows if r["period_year"]),
            key=lambda y: sum(1 for r in rows if r["period_year"] == y),
            default="unknown")
        for r in rows:
            r.setdefault("source_pdf", pdf.name)
            r["source_pdf"] = pdf.name
        rows = dedupe(rows)
        write(HERE / f"ex21_calcbench_{year}_Claude.csv", rows)
        combined.extend(rows)
        print(f"{pdf.name}")
        print(f"  firms in the export        {stats['firms']:,}")
        print(f"    with an Irish subsidiary {stats['firms_with_irish']:,}")
        print(f"  Irish rows, de-duplicated  {len(rows):,}")
        print(f"  distinct names             "
              f"{len({r['subsidiary_name'].lower() for r in rows}):,}")
        print(f"  wrote ex21_calcbench_{year}_Claude.csv")
        print()

    if combined and not args.no_combined and len(pdfs) > 1:
        combined = dedupe(combined)
        out = HERE / "ex21_calcbench_ALLYEARS_Claude.csv"
        write(out, combined)
        years = sorted({r["period_year"] for r in combined if r["period_year"]})
        print(f"COMBINED  {len(combined):,} rows across {len(years)} years "
              f"({', '.join(years)})")
        print(f"  distinct firms   {len({r['parent_company'] for r in combined}):,}")
        print(f"  distinct names   "
              f"{len({r['subsidiary_name'].lower() for r in combined}):,}")
        print(f"  wrote {out.name}")


if __name__ == "__main__":
    main()
