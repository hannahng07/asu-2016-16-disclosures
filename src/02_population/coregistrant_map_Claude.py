#!/usr/bin/env python3
r"""Joint filings: which CIKs are the same filing, and which one Compustat knows.

THE PROBLEM
-----------
Entergy's 10-K is filed by seven CIKs at once -- the parent and six operating
subsidiaries. The corpus stores it seven times, once per CIK, so the frame counts seven
firms where the market sees one. Six of them are absent from CRSP/Compustat because they
have no separately traded equity, and they look like a coverage failure. They are not.

Broadcom, CCO Holdings, Noble, Dow, CBL and Apartment Income REIT are the same shape.

HOW THE GROUPS ARE FOUND -- from the filings, not from a name match
-------------------------------------------------------------------
A joint filing has ONE accession number and several CIKs. Grouping CIKs that share an
accession is therefore an observation about the documents, not a guess about corporate
structure. Names are never used: "ENTERGY CORP /DE/" appears as the company name on all
seven CIKs, which is exactly why a name match would silently merge unrelated firms
elsewhere.

Groups are connected components over shared accessions, which is the honest closure --
if A files with B and B files with C, all three signed documents together.

WHICH CIK IS THE PARENT
-----------------------
The one Compustat/CRSP knows. If several in a group are in the panel the group is a
GENUINE multi-firm group, not a parent-and-subsidiaries one -- Dow/DuPont, Apartment
Income REIT -- and `parent_ambiguous` is set rather than a winner picked.

WHAT THIS DOES NOT DO
---------------------
It does not collapse anything. Giving six Entergy subsidiaries the parent's 3-day CAR
would put the same event in an event study six times, which is worse than leaving them
out. The map is written, the counts are reported, and the collapse is a decision.

Writes: coregistrant_map_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

import pandas as pd

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "sweep_manifest_Claude.csv"
PANEL = HERE / "ASUdata_CRSP_Compustat_May25.dta"
ANALYSIS = HERE / "asu_analysis_firms_Claude.csv"
OUT = HERE / "coregistrant_map_Claude.csv"


def main():
    acc = collections.defaultdict(set)
    nfil = collections.Counter()
    name = {}
    for r in csv.DictReader(MANIFEST.open(encoding="utf-8")):
        c = r["cik"].lstrip("0")
        acc[r["accession"]].add(c)
        nfil[c] += 1
    multi = [cs for cs in acc.values() if len(cs) > 1]

    # ---- connected components over shared accessions
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for cs in multi:
        cs = sorted(cs)
        for c in cs[1:]:
            union(cs[0], c)
    groups = collections.defaultdict(set)
    for c in list(parent):
        groups[find(c)].add(c)

    p = pd.read_stata(PANEL, columns=["gvkey", "cik", "tic", "conm", "permno"])
    p["cikn"] = (p.cik.astype(str).str.strip()
                 .str.replace(r"\.0$", "", regex=True).str.lstrip("0"))
    key = (p.dropna(subset=["cikn"]).drop_duplicates("cikn")
           .set_index("cikn")[["gvkey", "permno", "tic", "conm"]])
    inpan = set(key.index)

    for r in csv.DictReader(ANALYSIS.open(encoding="utf-8")):
        name[r["cik"].lstrip("0")] = r["company"]

    rows = []
    for _, members in groups.items():
        pan = sorted(members & inpan, key=lambda c: (-nfil[c], c))
        amb = len(pan) > 1
        par = pan[0] if pan else ""
        for c in sorted(members):
            k = key.loc[par] if par else None
            rows.append({
                "cik": c, "company": name.get(c, ""),
                "n_filings": nfil[c],
                "in_panel": 1 if c in inpan else 0,
                "group_size": len(members),
                "group_members": " ".join(sorted(members))[:300],
                "parent_cik": par,
                "parent_company": (k["conm"] if k is not None else ""),
                "parent_ambiguous": 1 if amb else 0,
                "parent_gvkey": (k["gvkey"] if k is not None else ""),
                "parent_permno": (k["permno"] if k is not None else ""),
                "parent_tic": (k["tic"] if k is not None else ""),
                "is_coregistrant_of_parent": 1 if (par and c != par) else 0,
                "basis": "shared_accession"})
    rows.sort(key=lambda r: (-r["group_size"], r["parent_cik"], r["cik"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"accessions with >1 CIK: {len(multi):,} of {len(acc):,}")
    print(f"groups: {len(groups):,} covering {len(rows):,} CIKs")
    print(f"   groups with NO member in the panel: "
          f"{sum(1 for g in groups.values() if not (g & inpan)):,}")
    print(f"   groups with MORE THAN ONE member in the panel (ambiguous): "
          f"{sum(1 for g in groups.values() if len(g & inpan) > 1):,}")

    ana = list(csv.DictReader(ANALYSIS.open(encoding="utf-8")))
    m = {r["cik"]: r for r in rows}
    for grp in ("treated", "control"):
        g = [r for r in ana if r["group"] == grp]
        ing = [r for r in g if r["cik"].lstrip("0") in m]
        nokey = [r for r in g if not r["permno"]]
        rec = [r for r in nokey if m.get(r["cik"].lstrip("0"), {}).get("parent_permno")
               not in ("", None) and str(m.get(r["cik"].lstrip("0"), {})
                                         .get("parent_permno")) != "nan"]
        col = [r for r in ing if m[r["cik"].lstrip("0")]["is_coregistrant_of_parent"] == 1]
        print(f"\n{grp}: {len(g):,} firms")
        print(f"   in a joint-filing group          {len(ing):,}")
        print(f"   without a permno of their own    {len(nokey):,}")
        print(f"   of those, a parent permno exists {len(rec):,}")
        print(f"   are a co-registrant of a parent  {len(col):,}  "
              f"<- would COLLAPSE, not gain a row")
    print("\nNothing has been collapsed or filled. The map is the deliverable.")


if __name__ == "__main__":
    main()
