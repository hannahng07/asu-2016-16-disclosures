#!/usr/bin/env python3
r"""Which Exhibit 21 Irish subsidiaries are NOT already in the tracker.

WHY THIS EXISTS SEPARATELY
--------------------------
`extract_ex21_irish_subs_Claude.py` reads names out of the filings, one row per
(firm, filing year, name). That file answers "who disclosed what, when". It does
NOT answer the question Brian actually asked on 19 August:

> "What I want to do is start adding to the subsidiary tracker -- Irish
>  subsidiaries disclosed after 2015 -- so that we can build a full database for
>  all companies."

and again on 20 August:

> "I really want to give him a list of all of the filings that we find from
>  Ex 21 that do not appear in our current tracker."

That needs the extraction COLLAPSED to one row per firm + subsidiary, and then
differenced against the tracker. This does that, and it exists as a file because
the first version of it did not -- the lists were built ad hoc and could not be
regenerated when the extractor changed.

THE MATCH IS ON A NORMALISED NAME, AND THAT IS THE WEAK JOINT
-------------------------------------------------------------
The tracker keys on Irish company number; these rows have names only. So the
comparison strips what varies between an Exhibit 21 and a CRO register --
corporate form (Limited / Unlimited / Ltd / DAC / plc), punctuation, case, and
"The" -- and compares what is left.

That is good enough to say "this is new" and NOT good enough to say "this is the
same entity as tracker row 4127". Treat a match as a reason to skip and a
non-match as a reason to look, which is exactly what the list is for.

    tracker names            1,546  (Irish_Subsidiary_Tracker__Asof081126_updated.xlsx)

TWO THINGS TO KNOW BEFORE QUOTING first_year
--------------------------------------------
1. THE SCAN BOUNDARY IS 2016, so `first_year == 2016` means "2016 or earlier",
   not "new in 2016". 892 of the 3,259 sit there for that reason. Scanning from
   2018 originally put 1,112 rows in 2018 and made it look like a wave of Irish
   incorporation; it was the boundary. Away from the edge the rate is a steady
   200-350 a year.
2. THE CORPUS STARTS IN 2016. 10-Ks FILED in 2015 (mostly fiscal 2014) are not
   in `10-X_C_*.zip` at all -- the earliest is 20160104. Reaching them needs
   `10-X_C_2011-2015.zip` from the same source. Nothing here can see a
   subsidiary that was disclosed in 2015 and dropped before the 2016 filing.

Usage
-----
    cd "Grant and Nguyen"
    python build_ex21_new_lists_Claude.py
    python build_ex21_new_lists_Claude.py --freshman-from 2018

Writes:
    ex21_NEW_irish_subs_for_review_Claude.csv   everything not in the tracker
    ex21_NEW_since2017_freshman_list_Claude.csv the same, first disclosed >= 2018
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

HERE = Path(__file__).resolve().parent
# The merged file if merge_calcbench_Claude.py has run, otherwise the 10-X
# extraction alone. Calcbench adds 2013-2015, which the 10-X corpus cannot see
# at all, and supplies the better spelling wherever both sources have a name.
MERGED = HERE / "ex21_merged_subsidiaries_Claude.csv"
LM_ONLY = HERE / "ex21_irish_subsidiaries_Claude.csv"
SRC = MERGED if MERGED.exists() else LM_ONLY
FIRMS = HERE / "ex21_firm_ticker_list_Claude.csv"
TRACKER_NAMES = (HERE.parent / "Grant and Lin" / "DoubleIrishResearch" / "sample"
                 / "review_queue" / "tracker_known_subsidiary_names_Claude.json")
OUT_ALL = HERE / "ex21_NEW_irish_subs_for_review_Claude.csv"
OUT_FRESHMAN = HERE / "ex21_NEW_since2017_freshman_list_Claude.csv"

# The year columns in the existing tracker's "Sub-Level tracker" sheet.
YEARS = range(2014, 2026)

# Stripped before comparing. Deliberately does NOT include words that carry
# meaning -- Holdings, Group, International and the like distinguish real
# entities from each other and must survive.
#
# Teoranta, ULC, CLG, CPT and ICAV were added 20 August. The Companies Act 2014
# forced a legal-form change on most Irish companies during the 2015-16
# transition -- an existing private company became an LTD or a DAC, an unlimited
# company had to spell "Unlimited Company" out in full -- so the SAME entity
# appears under two names either side of that window. Stripping the form is what
# makes "Abbott Ireland Limited" and "Abbott Ireland Designated Activity
# Company" one row rather than two. That already worked for the English forms;
# Teoranta is the Irish for Limited and was being missed.
_FORMS = (r"unlimited company|designated activity company|public limited company|"
          r"company limited by guarantee|unlimited|limited|teoranta|ltd|llc|inc|"
          r"incorporated|corporation|corp|plc|dac|ulc|clg|cpt|icav|"
          r"u\.?c|company|co")
_FORM_TAIL = re.compile(rf"\b({_FORMS})\b", re.I)

# TRAILING NOISE, REMOVED FROM THE MATCH KEY ONLY.
#
# Earlier today this was left alone, on the grounds that a rule stripping a
# trailing number turns "Phillips 66" into "Phillips". That was right about the
# DISPLAYED name and wrong about the match key, and it was costing real matches:
# "Northern Trust Fund Managers (Ireland) Limited 100" failed against the
# tracker's own "Northern Trust Fund Managers (Ireland)" over an ownership
# percentage that is part of neither name.
#
# The discriminator was available all along -- strip a trailing figure ONLY when
# a corporate form precedes it. "Phillips 66" has no form and survives, and so
# do Aircastle's "Constitution Aircraft Leasing (Ireland) 3, 4, 5", where the
# number distinguishes real entities from one another.
#
# The name written to the CSV is untouched. This changes the key, not the data.
_OWNERSHIP_TAIL = re.compile(
    rf"\b({_FORMS})\b[\s,.]*(?:\d[\d.,]*\s*%?|N\s*/?\s*A)\s*$", re.I)

# A status clause is a fact about the entity, not part of its name, and the
# tracker and the exhibits disagree about whether to carry it.
_STATUS = re.compile(
    r"[,\s]+(?:in\s+(?:members\s+)?(?:voluntary\s+)?liquidation|in\s+receivership|"
    r"dissolved|struck\s+off|formerly\s+known\s+as\b.*|f\s*/?\s*k\s*/?\s*a\b.*|"
    r"d\s*/?\s*b\s*/?\s*a\b.*)\s*$", re.I)

_DOUBLED_JURISDICTION = re.compile(r"\b(ireland|eire)(?:\s+\1)+\b")


# NAME QUALITY, flagged not filtered.
#
# Brian, 20 August: *"Many of the names look like they aren't going to match to
# anything - they appear to be cut off or on partial lists."* He is right for
# 28% of rows, and wrong about the cause for most of them: the dominant defect
# is not truncation but the OPPOSITE -- two entities run together because the
# jurisdiction between them was not in the vocabulary.
#
# Nothing is dropped. A flagged name is still a real subsidiary in a real
# exhibit, and some flags are false (Carlyle's CLO vehicles are legitimately
# eleven words long). The column exists so the RA can sort the clean 72% to the
# top and read the rest with his eyes open.
_FORM = re.compile(
    r"\b(Unlimited Company|Designated Activity Company|Limited|Ltd|Inc|"
    r"Incorporated|Corporation|Corp|LLC|PLC|DAC|Partnership|Trust)\b", re.I)
_TRAIL = re.compile(r"(\d[\d.,]*\s*%?|N\s*/?\s*A)\s*$")
_ADDR = re.compile(r"\b(Dublin|Street|Road|House|Floor|Square|Park|Cork|Galway)\b", re.I)


def name_flags(name: str, looks_complete: str) -> str:
    n = (name or "").strip()
    f = []
    if looks_complete != "yes":
        f.append("no_corporate_form")     # probably a fragment
    if len(_FORM.findall(n)) >= 2:
        f.append("two_entities_run_together")
    if len(n.split()) > 9:
        f.append("very_long")
    if _TRAIL.search(n):
        f.append("trailing_number_or_NA")  # an ownership % or an address
    if re.match(r"^[^A-Za-z]", n):
        f.append("leading_junk")
    if _ADDR.search(n):
        f.append("address_words")
    return "|".join(f)


# CAN THE RA ACTUALLY SEARCH THIS NAME?
#
# Brian, 20 August, looking at the top of the list: *"Right off the bat 'Aon
# Limited' - I won't be able to find that one by name in the Irish database."*
#
# He is right, and the name is not a defect: "Aon Limited" is verbatim in Aon
# plc's 2020 and 2021 Exhibit 21, filed under Ireland, and the same exhibit
# lists "Aon UK Limited" under the United Kingdom separately, so it is not the
# UK broker misplaced. It is simply a real company with an unsearchable name.
#
# WORD COUNT IS NOT THE TEST, which is the thing to get right here. "Seagate
# Technology Unlimited Company" and "Boston Scientific Limited" reduce to two
# words and are perfectly searchable; "Services Limited" reduces to one and is
# not a name at all. What matters is whether what remains DISTINGUISHES the
# company, so the test is against a vocabulary of non-distinctive words and
# against the parent's own name.
_GENERIC = {
    "a", "an", "the", "services", "service", "private", "gp", "lp", "holdings",
    "holding", "group", "international", "finance", "financial", "investments",
    "investment", "management", "operations", "indirect", "direct", "global",
    "europe", "european", "ireland", "irish", "trading", "trustees", "trustee",
    "nominees", "nominee", "partners", "partnership", "capital", "ventures",
    "enterprises", "technologies", "technology", "solutions", "systems",
}
_STOPWORDS = re.compile(r"\b(the|of|and|for|in|a|an)\b", re.I)


def search_core(name: str) -> str:
    """What is left to search the CRO on, once form and filler are gone."""
    return re.sub(r"\s+", " ", _STOPWORDS.sub(" ", normalise(name))).strip()


def search_difficulty(name: str, parent: str) -> str:
    core = search_core(name)
    if not core:
        return "UNUSABLE - no name left"
    toks = core.split()
    if all(t in _GENERIC for t in toks):
        # "Services Limited", "GP Limited", "Private Limited". Almost always a
        # fragment of a longer name rather than a company.
        return "UNUSABLE - generic words only"
    pcore = set(search_core(parent).split())
    if pcore and set(toks) <= pcore:
        # "Aon Limited" for Aon plc, "Abbott" for Abbott Laboratories. Real, but
        # a CRO search will return several and the year range is what separates
        # them.
        return "GENERIC - same as parent, expect several CRO hits"
    return ""


# LIKELY RENAMES, flagged for the reviewer.
#
# Brian, 20 August: *"I believe the Irish Companies Act required certain types
# of companies to change legal form - so the 'not in tracker' subs could end up
# just being name changes."*
#
# The pure legal-form conversion is already handled: normalise() strips the form
# entirely, so "Abbott Ireland Limited" and "Abbott Ireland Designated Activity
# Company" collapse to one key and never reach this list. The Companies Act
# transition is therefore NOT inflating the count, which is worth stating
# because it is the obvious thing to suspect.
#
# What survives is the rename that changed WORDS as well as form -- "Shire
# Pharmaceutical Investment Trading" against a tracked "Shire Pharmaceutical
# Investment Trading Ireland", or "H.B. Fuller Finance" against "H.B. Fuller
# Finance Ireland". Those are candidates, not conclusions: two genuinely
# different subsidiaries of one parent often differ by a single word too. The
# reviewer decides; this only puts the candidate in front of him.
RENAME_MIN = 0.55


def rename_candidate(norm: str, index: dict[str, list[str]]) -> tuple[str, float]:
    """Closest tracker name sharing a first word. Jaccard over tokens."""
    parts = norm.split()
    if not parts:
        return "", 0.0
    t = set(parts)
    best, score = "", 0.0
    for cand in index.get(parts[0], ()):
        c = set(cand.split())
        j = len(t & c) / len(t | c)
        if j > score:
            best, score = cand, j
    return (best, round(score, 2)) if score >= RENAME_MIN else ("", 0.0)


def normalise(name: str) -> str:
    s = (name or "").strip()
    s = _STATUS.sub(" ", s)
    m = _OWNERSHIP_TAIL.search(s)
    if m:
        s = s[:m.start()] + " " + m.group(1)
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"^\s*the\b", " ", s)
    s = _FORM_TAIL.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # "yelp ireland ireland", "facebook ireland holdings ireland". The tracker's
    # stored names carry the jurisdiction column appended to the name, so an
    # entity called "... Ireland Limited" ends up with the word twice and never
    # matches the exhibit's single copy. Collapse a REPEATED JURISDICTION only.
    # Not any repeated token: "johnson johnson ireland" is Johnson & Johnson
    # with the ampersand stripped, and collapsing that would invent an entity.
    s = _DOUBLED_JURISDICTION.sub(r"\1", s)
    # The same defect non-adjacently: "facebook ireland holdings ireland", where
    # the appended jurisdiction column sits after a word that belongs to the
    # name. Drop a TRAILING "ireland" only when the word already appears earlier,
    # so "Yelp Ireland Limited" keeps its one copy and only the duplicate goes.
    parts = s.split()
    if len(parts) > 1 and parts[-1] in ("ireland", "eire") and parts[-1] in parts[:-1]:
        s = " ".join(parts[:-1])
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freshman-from", type=int, default=2018,
                    help="freshman list keeps rows first disclosed in this year or later")
    args = ap.parse_args()

    known = {normalise(n) for n in json.loads(TRACKER_NAMES.read_text(encoding="utf-8"))}
    known.discard("")
    tracker_index: dict[str, list[str]] = collections.defaultdict(list)
    for k in known:
        tracker_index[k.split()[0]].append(k)

    # fic and sic, for prioritising. Brian, 20 August: "We're focused on firms
    # in the US right now" and "we are excluding financial firms for now and
    # they can be a big part of the sample." Both are carried, neither is
    # applied -- the exclusions are his to make and the rows stay in the file.
    firm = {}
    if FIRMS.exists():
        with FIRMS.open(newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                firm[r["cik"]] = r

    with SRC.open(newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.DictReader(fh))

    pairs: dict[tuple[str, str], dict] = {}
    year_field = "year" if rows and "year" in rows[0] else "filing_year"
    for r in rows:
        nm = r["subsidiary_name"].strip()
        key = (r["cik"], normalise(nm))
        if not key[1]:
            continue
        p = pairs.setdefault(key, {
            "ticker": r.get("ticker", ""), "company": r.get("company", ""),
            "double_irish_firm": r.get("double_irish_firm", ""),
            "cik": r["cik"], "gvkey": r.get("gvkey", ""),
            "subsidiary_name": nm, "years": set(), "n_filings": 0,
            "variants": set(), "sources": set(), "cb_name": "",
            "looks_complete": r.get("looks_complete", ""),
            "normalised": key[1],
        })
        try:
            p["years"].add(int(float(r.get(year_field) or 0)))
        except ValueError:
            pass
        p["n_filings"] += 1
        p["variants"].add(nm)
        src = r.get("source", "10-X")
        p["sources"].add(src)
        # CALCBENCH DECIDES THE SPELLING. It reads the exhibit's columns rather
        # than inferring boundaries from a jurisdiction vocabulary, so where the
        # two sources disagree about a name it is the one to believe. Keep its
        # longest spelling; fall back to the 10-X name only when it has none.
        if src == "calcbench" and len(nm) > len(p["cb_name"]):
            p["cb_name"] = nm
        # Prefer the longest spelling seen -- exhibits abbreviate inconsistently.
        if len(nm) > len(p["subsidiary_name"]):
            p["subsidiary_name"] = nm
        if r.get("looks_complete") == "yes":
            p["looks_complete"] = "yes"

    new = []
    in_tracker = 0
    for (cik, norm), p in pairs.items():
        if norm in known:
            in_tracker += 1
            continue
        if p["cb_name"]:
            p["subsidiary_name"] = p["cb_name"]
        p["name_source"] = ("calcbench" if p["cb_name"]
                            else ("10-X" if p["sources"] else ""))
        p["sources"] = "+".join(sorted(p["sources"]))
        ys = sorted(y for y in p["years"] if y)
        p["first_year"], p["last_year"] = ys[0], ys[-1]
        p["years"] = ",".join(str(y) for y in ys)
        f = firm.get(cik, {})
        p["fic"] = f.get("fic", "")
        p["sic"] = f.get("sic", "")
        p["sic_group"] = f.get("sic_group", "")
        p["is_financial"] = f.get("is_financial", "")
        # The RA fills this from the CRO website; it is the join that turns a
        # name into a tracker row.
        p["irish_cro_num"] = ""
        cand, score = rename_candidate(norm, tracker_index)
        p["possible_rename_of"] = cand
        p["rename_score"] = score or ""
        p["search_difficulty"] = search_difficulty(p["subsidiary_name"], p["company"])
        # EVERY RAW SPELLING THAT COLLAPSED INTO THIS ROW.
        #
        # 488 of 4,018 pairs hold more than one, and almost always they are the
        # same company spelled differently -- "Moody's Analytics Ireland
        # Limited" and "Moody s Analytics Ireland Ltd". But where a name reduces
        # to a single generic token the collapse can merge things that are NOT
        # the same: Aon's row holds "Aon Limited" (real), "Aon plc" (the parent
        # listing itself) and "The Aon" (a truncation of "The Aon Ireland
        # MasterTrustee Limited"). So for those rows the years column spans
        # entities rather than describing one, and this column is the warning.
        others = sorted(v for v in p["variants"] if v != p["subsidiary_name"])
        p["name_variants"] = " | ".join(others)
        p["n_name_variants"] = len(p["variants"])
        p["name_flags"] = name_flags(p["subsidiary_name"], p["looks_complete"])
        p["name_ok"] = "" if p["name_flags"] else "yes"
        # Mirrors the year columns in Irish_Subsidiary_Tracker__Asof081126.
        # Brian, 20 August: "they are all blank as they'll all be no." Nothing
        # here has an Irish filing collected yet, and writing "no" into a column
        # that means "we hold accounts for this year" would assert a fact
        # nobody has checked -- so they are left empty for the reviewer to fill.
        for y in YEARS:
            p[str(y)] = ""
        new.append(p)

    # Clean names first, then most consistently disclosed: established entities
    # whose name is reliable enough to search the CRO with, at the top.
    new.sort(key=lambda p: (p["name_flags"] != "", -p["n_filings"],
                            -len(p["years"]), p["company"]))
    cols = (["irish_cro_num", "ticker", "company", "subsidiary_name"]
            + [str(y) for y in YEARS]
            + ["sources", "name_source", "search_difficulty",
               "name_variants", "n_name_variants",
               "possible_rename_of", "rename_score", "name_ok", "name_flags",
               "fic", "sic", "sic_group",
               "is_financial", "double_irish_firm", "cik", "gvkey",
               "first_year", "last_year", "years", "n_filings",
               "looks_complete", "normalised"])

    def write(path: Path, data):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    fresh = [p for p in new if p["first_year"] >= args.freshman_from]
    write(OUT_ALL, new)
    write(OUT_FRESHMAN, fresh)

    print(f"extraction rows              {len(rows):,}")
    print(f"firm + subsidiary pairs      {len(pairs):,}")
    print(f"  already in the tracker     {in_tracker:,}")
    print(f"  NOT in the tracker         {len(new):,}")
    print(f"    distinct firms           {len({p['cik'] for p in new}):,}")
    print(f"    complete-looking names   {sum(1 for p in new if p['looks_complete'] == 'yes'):,}")
    print(f"    at Double Irish firms    {sum(1 for p in new if p['double_irish_firm'] == '1'):,}")
    print()
    us = [p for p in new if p["fic"] == "USA"]
    usnf = [p for p in us if p["is_financial"] != "yes"]
    print(f"  parent incorporated in USA {len(us):,}   ({len({p['cik'] for p in us}):,} firms)")
    print(f"    and NOT a financial firm {len(usnf):,}   ({len({p['cik'] for p in usnf}):,} firms)  <- the priority list")
    print(f"  financial firms (SIC 6xxx) {sum(1 for p in new if p['is_financial'] == 'yes'):,}")
    print()
    ok = [p for p in new if p["name_ok"]]
    print(f"  name usable as written     {len(ok):,}  ({100*len(ok)//max(len(new),1)}%)")
    flg = collections.Counter(f for p in new for f in p["name_flags"].split("|") if f)
    for k, v in flg.most_common():
        print(f"    {k:28} {v:5}")
    best = [p for p in ok if p["fic"] == "USA" and p["is_financial"] != "yes"]
    print(f"  usable name + US + non-financial  {len(best):,}  <- start here")
    print()
    ss = collections.Counter(p["sources"] for p in new)
    print(f"  by source                {dict(ss)}")
    print(f"  name taken from Calcbench {sum(1 for p in new if p['name_source'] == 'calcbench'):,}")
    print()
    mv = sum(1 for p in new if p["n_name_variants"] > 1)
    print(f"  rows holding >1 raw spelling            {mv:,}   (see name_variants)")
    print()
    sd = collections.Counter(p["search_difficulty"] for p in new if p["search_difficulty"])
    print(f"  hard or impossible to search by name  {sum(sd.values()):,}")
    for k, v in sd.most_common():
        print(f"    {k:46} {v:5}")
    print()
    ren = [p for p in new if p["possible_rename_of"]]
    print(f"  possibly a RENAME of a tracked entity  {len(ren):,}")
    print(f"    (Companies Act form changes are already collapsed and are NOT in this count)")
    print()
    fy = collections.Counter(p["first_year"] for p in new)
    print("first disclosed  " + "  ".join(f"{y}:{fy[y]}" for y in sorted(fy)))
    print("  (years are FISCAL years. 2013 is the earliest export, so first_year")
    print("   2013 means '2013 or earlier'. 2015 carries the 10-X corpus boundary,")
    print("   and 2024 is short because those filings mostly arrive in 2025.)")
    print()
    print(f"wrote {OUT_ALL.name}       {len(new):,}")
    print(f"wrote {OUT_FRESHMAN.name}  {len(fresh):,}")


if __name__ == "__main__":
    main()
