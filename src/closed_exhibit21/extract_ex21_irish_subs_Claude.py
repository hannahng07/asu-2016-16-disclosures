#!/usr/bin/env python3
r"""Irish subsidiaries disclosed in Exhibit 21, for every US MNE in the sample.

WHY
---
Brian, 19 August:

> "I initially identified DI firms based on their Exhibit 21 disclosures in 2013
>  and 2014. So the tracking list is based primarily on the 2014 data. I
>  handcollected most of the Irish filings for these firms that I identified
>  from between 2014 and 2022. But I am DEFINITELY missing non-Double-Irish
>  firms' affiliates for those years... what I want to do is start adding to the
>  subsidiary tracker - Irish subsidiaries disclosed after 2015 - so that we can
>  build a full database for all companies."

The tracking list is anchored on a 2013-14 snapshot. Every Irish subsidiary that
first appears in a later Exhibit 21 is invisible to it. `USMNEswithIrishsubsinEx21.dta`
gives the population: **1,160 US MNEs, 7,867 firm-years, 2006-2022, and 34,107
Irish-subsidiary mentions** -- but as COUNTS (`irelandcount`), not names.

This reads the names.

WHERE THE NAMES COME FROM
-------------------------
The Loughran-McDonald 10-X corpus keeps Exhibit 21 as a tagged `<EX-21>` block.
Measured 19 August over 300 sampled 2021 10-Ks: **53% carry the EX-21 body and
52% include a jurisdiction table.** So roughly half the filings have the names
inline, at no additional download cost.

THE PARSING PROBLEM, AND THE TRAP IN IT
---------------------------------------
The corpus flattens the exhibit's table into a single run of text:

    AbbVie Aviation LLC Illinois AbbVie Biopharmaceuticals LLC Delaware ...

so a subsidiary's name is whatever sits between one jurisdiction and the next.
That works until the jurisdiction word appears INSIDE a name, which for this
project is constant:

    "AbbVie Ireland Holdings Unlimited Company"

A naive split produces "AbbVie" [Ireland] "Holdings Unlimited Company" -- two
fragments and no real entity. The tell is what FOLLOWS the word: a jurisdiction
is followed by the next company's name, while an in-name "Ireland" is followed
by corporate-form words (Holdings, Unlimited, Limited, Company, Ltd, Inc...).
That guard is applied below and is the difference between a usable list and a
list of fragments.

WHAT IT WRITES
--------------
One row per (firm, filing year, subsidiary name), with the CIK, company name,
fiscal year, jurisdiction as written, and the filing it came from. Nothing is
de-duplicated across years on purpose -- WHEN a subsidiary first appears is the
question being asked.

Usage
-----
    cd "Grant and Nguyen"
    python extract_ex21_irish_subs_Claude.py --from-year 2018
    python extract_ex21_irish_subs_Claude.py --from-year 2018 --cik 1551152

Writes: ex21_irish_subsidiaries_Claude.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
import zipfile
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

HERE = Path(__file__).resolve().parent
OUT = HERE / "ex21_irish_subsidiaries_Claude.csv"
ZIPS = ["10-X_C_2016-2020.zip", "10-X_C_2021.zip", "10-X_C_2022.zip",
        "10-X_C_2023.zip", "10-X_C_2024.zip"]

_STATES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|"
           "Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|"
           "Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|"
           "New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|"
           "Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|"
           "Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|"
           "District of Columbia|Puerto Rico|United States")
_COUNTRIES = ("Republic of Ireland|Northern Ireland|Ireland|United Kingdom|England and Wales|"
              "England|Scotland|Wales|Bermuda|Cayman Islands|Luxembourg|Netherlands|Switzerland|"
              "Singapore|Germany|France|Spain|Italy|Belgium|Denmark|Sweden|Norway|Finland|Austria|"
              "Poland|Portugal|Greece|Hungary|Czech Republic|Israel|India|China|Japan|South Korea|"
              "Korea|Australia|New Zealand|Canada|Mexico|Brazil|Argentina|Chile|Colombia|Malta|"
              "Cyprus|Jersey|Guernsey|Isle of Man|Barbados|Bahamas|Panama|Hong Kong|Taiwan|"
              "Thailand|Malaysia|Indonesia|Philippines|Vietnam|Turkey|Russia|South Africa|"
              "United Arab Emirates|Saudi Arabia|Egypt|Nigeria|Kenya|Costa Rica|Uruguay|Peru|"
              "Venezuela|Ecuador|Slovakia|Slovenia|Croatia|Romania|Bulgaria|Ukraine|Lithuania|"
              "Latvia|Estonia|Iceland|Mauritius|Curacao|Aruba|Delaware")

# ADDED 20 August, each one measured in the extraction before it went in.
# A jurisdiction MISSING from this list does not lose a row -- it RUNS TWO
# ENTITIES TOGETHER, because the name is taken as everything up to the next
# recognised jurisdiction. "Becton Dickinson Zambia Limited Zambia Benex Ltd"
# was one string. Every entry below was found by looking at what follows a
# corporate form inside an extracted name, and each was read in context first.
#
# Canadian provinces are here because exhibits name the province, not Canada.
# CITIES ARE DELIBERATELY ABSENT. Dublin appears as a jurisdiction in about two
# filings and inside 74 distinct company names -- Bard Dublin ITC Limited, SPX
# Flow Technology Dublin Limited, The Dublin Business School Limited. Adding it
# would break far more than it fixed, and the corporate-form guard does not
# help when the next word is "ITC".
_ADDED = ("British Virgin Islands|Virgin Islands|Gibraltar|Nova Scotia|Ontario|Quebec|"
          "British Columbia|Alberta|Manitoba|Saskatchewan|New Brunswick|Newfoundland|"
          "Labuan|Myanmar|Gabon|Sri Lanka|Zambia|Armenia|Kazakhstan|Azerbaijan|Serbia|"
          "Macedonia|Moldova|Bangladesh|Ghana|Uganda|Morocco|Tunisia|Algeria|Bahrain|"
          "Oman|Iraq|Guatemala|Honduras|El Salvador|Dominican Republic|Trinidad|Belize|"
          "Liechtenstein")

JURISDICTION = re.compile(rf"\b({_STATES}|{_COUNTRIES}|{_ADDED})\b")
IRISH = re.compile(r"^(Republic of Ireland|Northern Ireland|Ireland)$", re.I)

# "Rep. of Ireland" and "Republic of Ireland" are written with the qualifier
# BEFORE the word the splitter matches on, so the qualifier lands at the end of
# the previous company's name: every Willis Lease entity came out as
# "WLFC (Ireland) Limited Rep. of". 64 rows across 11 names.
_TRAILING_QUALIFIER = re.compile(r"[\s,;.-]*\b(Rep\.?|Republic)\s+of\s*$", re.I)

# A JURISDICTION WORD INSIDE A NAME. "AbbVie Ireland Holdings Unlimited Company"
# is one entity, not "AbbVie" in Ireland followed by "Holdings Unlimited
# Company". A real jurisdiction is followed by the NEXT company's name; an
# in-name one is followed by a corporate-form or descriptive word.
# ONLY STRUCTURAL CORPORATE-FORM WORDS BELONG HERE, and this list was trimmed
# once already. A first version also included International, Investments,
# Finance, Services, Pharma*, Manufacturing, Global and similar. Those words
# open company names as often as they continue them, so
# "Fournier Laboratories Ireland Ltd. [Ireland] Pharmacyclics (Europe) Limited"
# was read as ONE entity -- the real jurisdiction was skipped because
# "Pharmacyclics" matched Pharma\w*. Two subsidiaries became one string.
#
# What is left is words that can only ever FOLLOW a name, never start one.
NAME_CONTINUES = re.compile(
    r"^\s*(Holdings?|Holding|Unlimited|Limited|Ltd\.?|Company|Companies|Inc\.?|"
    r"Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|LP|L\.P\.|PLC|P\.L\.C\.|"
    r"and\b|&|\()", re.I)

# A name with no corporate form is usually a fragment -- "AbbVie" on its own is
# the tail of a split, not a subsidiary. Flagged rather than dropped, because
# some genuine Irish entities are named without a suffix in the exhibit.
HAS_FORM = re.compile(
    r"\b(Unlimited|Limited|Ltd|Company|Inc|Incorporated|Corporation|Corp|LLC|"
    r"LP|PLC|DAC|UC|Holdings?|Group|Partnership|Trust|Fund|Designated)\b", re.I)

# Junk that is not a subsidiary name.
NOT_A_NAME = re.compile(
    r"^(and|or|the|of|in|a|an|as|is|are|was|were|its|d\s*b\s*a|inc|llc|ltd|"
    r"subsidiar\w*|jurisdiction\w*|state\w*|country|name|incorporation|"
    r"organi[sz]ation|entity|entities|list|exhibit|following|percent\w*|owned)$", re.I)

MIN_NAME, MAX_NAME = 4, 110


def irish_subsidiaries(segment: str):
    """(name, jurisdiction, looks_complete) for each Irish entity in EX-21.

    THE PARENTHESISED JURISDICTION, and why it cost 2,226 rows.
    ----------------------------------------------------------
    Exhibits use round brackets for BOTH things, and the first version of this
    function handled neither:

        "Facebook Ireland Limited (Ireland)"        parens hold the JURISDICTION
        "Aircastle Advisor (Ireland) Limited"       parens are part of the NAME

    Splitting on the bare word truncated the name at the opening bracket in
    both cases -- 2,226 of 16,388 rows (14%) ended in a stray "(", including
    "Facebook Ireland Limited (" and every one of Aircastle's leasing
    entities. The Aircastle rows were worse than truncated: they also emitted a
    phantom "Limited" as a second subsidiary.

    The discriminator is the same one used everywhere else here -- what FOLLOWS
    the closing bracket. A corporate form after ")" means the parens sat inside
    the name; anything else means they held the jurisdiction. So the bracket is
    absorbed into the match on both sides and the existing test is applied past
    it, which is why both cases above now come out whole.
    """
    text = re.sub(r"\s+", " ", segment)
    out, prev_end = [], 0
    for m in JURISDICTION.finditer(text):
        wrapped = (m.start() > 0 and text[m.start() - 1] == "("
                   and text[m.end():m.end() + 1] == ")")
        end = m.end() + (1 if wrapped else 0)
        start = m.start() - (1 if wrapped else 0)
        after = text[end:end + 40]
        if NAME_CONTINUES.match(after):
            continue                      # the word is part of a name; see above
        name = text[prev_end:start].strip(" ,;.-–—|")
        prev_end = end
        if not IRISH.match(m.group(1)):
            continue
        name = _TRAILING_QUALIFIER.sub("", name)
        name = re.sub(r"^[\d\.\)\s]+", "", name).strip()
        if not (MIN_NAME <= len(name) <= MAX_NAME) or NOT_A_NAME.match(name):
            continue
        if not re.search(r"[A-Za-z]{3}", name):
            continue
        out.append((name, m.group(1), "yes" if HAS_FORM.search(name) else ""))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2018,
                    help="only filings FILED in this year or later")
    ap.add_argument("--cik", help="restrict to one CIK, for checking")
    ap.add_argument("--panel", default="ex21_panel_Claude.csv",
                    help="CIK list; falls back to reading every 10-K")
    args = ap.parse_args()

    wanted = None
    panel = HERE / args.panel
    meta = {}
    di_ciks: set[str] = set()
    if panel.exists():
        wanted = set()
        with panel.open(newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("cik") or "").strip().lstrip("0")
                if c:
                    wanted.add(c)
                    meta.setdefault(c, r)
                    # DoubleIrish is per firm-YEAR in the panel; a firm that ran
                    # the structure in any year is a Double Irish firm here.
                    if (r.get("DoubleIrish") or "").strip() in ("1", "1.0"):
                        di_ciks.add(c)
    if args.cik:
        wanted = {args.cik.lstrip("0")}

    rows, stats = [], collections.Counter()
    for zp in ZIPS:
        p = HERE / zp
        if not p.exists():
            continue
        z = zipfile.ZipFile(p)
        for name in z.namelist():
            if not name.endswith(".txt") or "_10-K" not in name:
                continue
            m = re.search(r"^(\d{4})(\d{2})(\d{2})_", name.split("/")[-1])
            if not m or int(m.group(1)) < args.from_year:
                continue
            cm = re.search(r"edgar_data_(\d+)_", name)
            if not cm:
                continue
            cik = cm.group(1).lstrip("0")
            if wanted is not None and cik not in wanted:
                continue
            stats["10-Ks read"] += 1
            try:
                text = z.read(name).decode("utf-8", errors="replace")
            except Exception:
                continue
            i = text.find("<EX-21")
            if i < 0:
                stats["no EX-21 body"] += 1
                continue
            j = text.find("</EX-21", i)
            seg = text[i:j if j > 0 else i + 400_000]
            stats["with EX-21 body"] += 1
            subs = irish_subsidiaries(seg)
            if subs:
                stats["with >=1 Irish subsidiary"] += 1
            g = meta.get(cik, {})
            for nm, jur, complete in subs:
                rows.append({
                    "cik": cik, "gvkey": g.get("gvkey", ""),
                    "ticker": g.get("ticker", ""), "company": g.get("conm", ""),
                    "double_irish_firm": "1" if cik in di_ciks else "0",
                    "filing_date": m.group(0).rstrip("_"),
                    "filing_year": int(m.group(1)),
                    "subsidiary_name": nm, "jurisdiction_as_written": jur,
                    "looks_complete": complete,
                    "source_file": name.split("/")[-1],
                })
        z.close()

    if rows:
        seen = set()
        deduped = []
        for r in rows:
            k = (r["cik"], r["filing_year"], r["subsidiary_name"].lower())
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)
        rows = deduped
        with OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    print(f"10-Ks read (filed {args.from_year}+)   {stats['10-Ks read']:,}")
    print(f"  with an EX-21 body               {stats['with EX-21 body']:,}")
    print(f"  no EX-21 body                    {stats['no EX-21 body']:,}")
    print(f"  with at least one Irish sub      {stats['with >=1 Irish subsidiary']:,}")
    print(f"\nIrish subsidiary rows            {len(rows):,}")
    if rows:
        print(f"  distinct firms                 {len({r['cik'] for r in rows}):,}")
        print(f"  distinct subsidiary names      {len({r['subsidiary_name'].lower() for r in rows}):,}")
        print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
