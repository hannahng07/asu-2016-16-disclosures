#!/usr/bin/env python3
r"""The firms that mention the standard and record nothing: a control group, stratified.

WHY THIS IS NOT ONE GROUP
-------------------------
"No effect" hides five different firms, and an investor study that pools them is comparing
its treated firms against a mixture it cannot interpret:

    adopted_immaterial    adopted and said so in terms -- "the adoption did not have a
                          material impact". The firm looked, and there was nothing to
                          report. The tightest control there is: same standard, same
                          calendar, same disclosure obligation, no economic effect
    adopted_unquantified  adopted, said nothing about size. Silent, not negative
    expected_only         forecast an effect that never appears as a record
    evaluating_only       "we are currently evaluating the impact" and never returns to it
    standard_only         the ASU appears in the accounting-policy boilerplate and nowhere
                          else. The weakest membership of all

THE CAVEAT THAT GOVERNS EVERY USE OF THIS FILE
----------------------------------------------
These firms are controls for DISCLOSURE, not for TRANSFER. Disclosure is required only
when material, so a control firm may well have moved IP and never written it down --
REGN, YELP and INSM say nothing across 28-29 filings each. Read as "did not disclose",
never as "did not transfer". `xbrl_tagged` is the one independent witness available: a
firm that tagged the ASU member in XBRL adopted it whatever its prose says, and a firm the
reader placed as `table_only` is NOT a control at all -- it is a treated firm the corpus
stripped. Both are marked so neither can be pooled in by accident.

A SIXTH GROUP, NOT IN THIS FILE
-------------------------------
Firms in the corpus that never mention the standard in any form. The count is printed; the
list is a by-product of the sweep manifest, not of the frame. They are the broadest
control and the least informative, because for them absence of language is all that is
known.

Writes: control_firms_Claude.csv    one row per non-effect firm, stratum + event link
        control_group_summary_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
FIRMS = HERE / "population_firms_Claude.csv"
FILINGS = HERE / "population_filings_Claude.csv"
LINKED = HERE / "population_filings_linked_Claude.csv"
FLAGS = HERE / "xbrl_firm_flags_Claude.csv"
READER = HERE / "reader_prod_tagged_no_prose_answers_Claude.csv"
MANIFEST = HERE / "sweep_manifest_Claude.csv"
OUT = HERE / "control_firms_Claude.csv"
SUM = HERE / "control_group_summary_Claude.csv"

# strongest claim first: a firm that ever said "not material" is placed by that, whatever
# else it also said in other years
ORDER = [("adoption_no_effect", "adopted_immaterial"),
         ("adoption", "adopted_unquantified"),
         ("expected_effect", "expected_only"),
         ("evaluating", "evaluating_only"),
         ("standard", "standard_only")]
EVENT = ["car_3day_market", "cum_event_return", "cum_event_turnover", "bidaskspread"]


def main():
    firms = list(csv.DictReader(FIRMS.open(encoding="utf-8")))
    ctrl = [f for f in firms if f["ever_effect"] != "1"]

    byfirm = collections.defaultdict(list)
    for r in csv.DictReader(FILINGS.open(encoding="utf-8")):
        byfirm[r["cik"].lstrip("0")].append(r)

    # the event link, per filing, from the linked file -- keyed the same way
    link = {}
    if LINKED.exists():
        for r in csv.DictReader(LINKED.open(encoding="utf-8")):
            link[(str(r["cik"]).lstrip("0"), r["accession"])] = r

    tagged, rlabel = {}, {}
    if FLAGS.exists():
        for r in csv.DictReader(FLAGS.open(encoding="utf-8")):
            tagged[r["cik"].lstrip("0")] = r
    if READER.exists():
        for r in csv.DictReader(READER.open(encoding="utf-8")):
            rlabel[r["cik"].lstrip("0")] = r["reader_label"]

    rows = []
    for f in ctrl:
        cik = f["cik"].lstrip("0")
        fs = byfirm.get(cik, [])
        classes = {r["disclosure_class"] for r in fs}
        stratum = next((name for k, name in ORDER if k in classes), "none")
        # the control's own event: the first filing that carries the mention placing it
        key = next((k for k, name in ORDER if name == stratum), None)
        first = min((r for r in fs if r["disclosure_class"] == key),
                    key=lambda r: r["filing_date"], default=None)
        lk = link.get((cik, first["accession"]), {}) if first else {}
        t = tagged.get(cik, {})
        rows.append({
            "cik": f["cik"], "company": f["company"], "stratum": stratum,
            "n_filings_with_mention": len(fs),
            "classes_seen": " ".join(sorted(classes)),
            "first_mention_date": f["first_any_mention_date"],
            "first_mention_class": f["first_any_mention_class"],
            "event_date": (first["filing_date"] if first else ""),
            "event_form": (first["form"] if first else ""),
            "event_accession": (first["accession"] if first else ""),
            "event_sentence": (" ".join(str(first["sentence"]).split())[:400]
                               if first else ""),
            "xbrl_tagged": 1 if t else 0,
            "xbrl_max_amount": t.get("max_xbrl_amount", ""),
            "reader_label": rlabel.get(cik, ""),
            # a reader-confirmed table_only firm is TREATED, not control
            "excluded_from_control": 1 if rlabel.get(cik) == "table_only" else 0,
            "gvkey": lk.get("gvkey", ""), "permno": lk.get("permno", ""),
            "tic": lk.get("tic", ""), "link_basis": lk.get("link_basis", ""),
            "atq": lk.get("atq", ""), "saleq": lk.get("saleq", ""),
            "mvecrsp": lk.get("mvecrsp", ""), "prccq": lk.get("prccq", ""),
            **{c: lk.get(c, "") for c in EVENT}})
    rows.sort(key=lambda r: (r["stratum"], r["company"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    print(f"wrote {OUT.name}: {n:,} non-effect firms "
          f"(of {len(firms):,} firms with any clean mention)")
    print(f"   the treated population is {len(firms)-n:,} firms\n")
    srows = []
    print(f"{'stratum':<24}{'firms':>7}{'w/ CAR':>8}{'XBRL':>7}{'excl':>6}   "
          f"{'usable':>7}")
    for k, name in ORDER + [(None, "none")]:
        g = [r for r in rows if r["stratum"] == name]
        if not g:
            continue
        car = sum(1 for r in g if r["car_3day_market"] not in ("", "nan", None))
        xb = sum(1 for r in g if r["xbrl_tagged"] == 1)
        ex = sum(r["excluded_from_control"] for r in g)
        print(f"{name:<24}{len(g):>7}{car:>8}{xb:>7}{ex:>6}   {len(g)-ex:>7}")
        srows.append({"stratum": name, "firms": len(g), "with_3day_car": car,
                      "xbrl_tagged": xb, "excluded_table_only": ex,
                      "usable_as_control": len(g) - ex})
    tot_ex = sum(r["excluded_from_control"] for r in rows)
    tot_car = sum(1 for r in rows if r["car_3day_market"] not in ("", "nan", None))
    print(f"{'TOTAL':<24}{n:>7}{tot_car:>8}"
          f"{sum(r['xbrl_tagged'] for r in rows):>7}{tot_ex:>6}   {n-tot_ex:>7}")
    with SUM.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(srows[0]))
        w.writeheader()
        w.writerows(srows)

    if MANIFEST.exists():
        allc = {r["cik"].lstrip("0") for r in csv.DictReader(MANIFEST.open(encoding="utf-8"))}
        mention = {f["cik"].lstrip("0") for f in firms}
        print(f"\nnever mention the standard at all: {len(allc - mention):,} firms "
              f"of {len(allc):,} in the corpus")
        print("   (not written here -- the broadest control and the least informative:")
        print("    for them, absence of language is the only thing known)")
    print("\nCONTROLS FOR DISCLOSURE, NOT FOR TRANSFER. A firm may have moved IP and never")
    print("written it down; the 10-K can confirm a transfer, never refute one.")


if __name__ == "__main__":
    main()
