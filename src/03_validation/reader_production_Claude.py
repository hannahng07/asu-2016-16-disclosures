#!/usr/bin/env python3
r"""Production reading: the questions the code cannot answer, put to a calibrated reader.

The reader was calibrated on 23 September against the hand-read sets (38 of 40 on
detection given the same evidence the frame uses, 27 of 33 on amounts against the filers'
own tags). This runs it on the places the code cannot reach.

TASK 1 -- tagged_no_prose
--------------------------
144 firms tagged ASU 2016-16 in XBRL and have NO effect filing in the text frame. Each is
one of three things, and only reading tells them apart:

    table_only      the disclosure exists but lives in a table, which Loughran-McDonald
                    strips. The firm belongs in the population and the text route can
                    never see it
    adoption_only   the firm adopted and recorded nothing worth stating: correctly
                    outside the population
    not_relevant    the tag is on something else entirely

This is the definitional question the frame has been carrying since the recall test, and
it decides whether 144 firms join a 351-firm population.

WHAT THE READER IS GIVEN
------------------------
The same evidence the frame has, and nothing more: the best sentences the extractor found
in that firm's filings, the class the frame assigned, and the XBRL facts the filer tagged
(element name and value). No labels, no hints about what answer is wanted.

    --mode batch --task tagged_no_prose     write reader_prod_<task>_<n>.txt
    --mode ingest --task tagged_no_prose --answers f1.txt f2.txt ...
                                            merge the answers, report the split, and
                                            write reader_prod_<task>_answers_Claude.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
FILINGS = HERE / "population_filings_Claude.csv"
FLAGS = HERE / "xbrl_firm_flags_Claude.csv"
AMOUNTS = HERE / "xbrl_amounts_Claude.csv"
PER_BATCH = 36


def rows_tagged_no_prose():
    flags = [r for r in csv.DictReader(FLAGS.open(encoding="utf-8"))
             if r["xbrl_tagged_no_text_effect"] == "1"]
    fil = collections.defaultdict(list)
    for r in csv.DictReader(FILINGS.open(encoding="utf-8")):
        fil[r["cik"].lstrip("0")].append(r)
    amt = collections.defaultdict(list)
    for r in csv.DictReader(AMOUNTS.open(encoding="utf-8")):
        amt[r["cik"].lstrip("0")].append(r)

    out = []
    for f in flags:
        cik = f["cik"].lstrip("0")
        cands = sorted(fil.get(cik, []),
                       key=lambda r: -float(r["max_score"] or 0))[:2]
        facts = sorted(amt.get(cik, []), key=lambda r: int(r["xbrl_tag_rank"]))[:3]
        out.append({
            "cik": f["cik"], "company": f["company"],
            "classes": ", ".join(sorted({c["disclosure_class"] for c in cands})) or "none",
            "sentences": " || ".join(" ".join(str(c["sentence"]).split())[:320]
                                     for c in cands) or "(no candidate sentence)",
            "tags": "; ".join(f"{a['xbrl_tag']}={float(a['xbrl_amount']):,.0f}"
                              f" [{a['form']} {a['filed'][:4]}]" for a in facts),
        })
    return out



# ---------------------------------------------------------------- TASK 2: firm_past
def rows_firm_past():
    """The 94 filings that pass EFFECT + INTRA + FIGURE and fail only FIRM_PAST.

    FIRM_PAST exists to stop the standard's own transition text reading as the firm
    recording something: "adjustment RECORDED in retained earnings" is the rule talking.
    It is a precision guard, and it is now the binding constraint on recall -- these 94
    say a tax effect of a transfer, with a figure, in a voice the guard rejects:

        "the effective tax rate for the quarter benefited from a deferred tax benefit of
         38 million resulting from intercompany transfers of intellectual property"

    Impersonal, but the firm reporting its own result. Whether that is an effect
    disclosure is a reading question, so it is read before the pattern moves.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("dc", HERE / "disclosure_class_Claude.py")
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    out = []
    for r in csv.DictReader(FILINGS.open(encoding="utf-8")):
        if r["is_effect"] == "1":
            continue
        s = " ".join(dc.PAGEBREAK.sub(" ", str(r["sentence"])).split())
        if dc.TABLEISH.search(s) or len(s) > 900:
            continue
        if (dc.EFFECT.search(s) and dc.INTRA.search(s) and not dc.FIRM_PAST.search(s)
                and not dc.FUTURE.search(s) and dc.FIGURE.search(s)):
            out.append({"cik": r["cik"], "company": r["company"],
                        "classes": r["disclosure_class"],
                        "sentences": s[:420],
                        "tags": f"{r['form']} {r['filing_date'][:10]}"})
    return out


TASKS = {"tagged_no_prose": rows_tagged_no_prose, "firm_past": rows_firm_past}


def do_batch(task):
    rows = TASKS[task]()
    for i in range(0, len(rows), PER_BATCH):
        chunk = rows[i:i + PER_BATCH]
        p = HERE / f"reader_prod_{task}_{i // PER_BATCH + 1}.txt"
        lines = []
        for j, r in enumerate(chunk, i + 1):
            lines.append(
                f"{j}|{r['company'][:34]}|FRAME CLASS: {r['classes']}"
                f" || TEXT FOUND: {r['sentences']}"
                f" || XBRL TAGGED: {r['tags']}")
        p.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {p.name}: {len(chunk)} firms")
    print(f"{len(rows)} firms in total")


def do_ingest(task, answers):
    rows = {str(i + 1): r for i, r in enumerate(TASKS[task]())}
    got = {}
    for path in answers:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            p = [x.strip() for x in line.split("|")]
            if len(p) >= 2 and p[0].isdigit():
                got[p[0]] = p[1:]
    out = []
    for k, r in rows.items():
        a = got.get(k, [])
        out.append({**r, "reader_label": (a[0] if a else ""),
                    "reader_confidence": (a[1] if len(a) > 1 else ""),
                    "reader_reason": (a[2] if len(a) > 2 else "")})
    p = HERE / f"reader_prod_{task}_answers_Claude.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    c = collections.Counter(r["reader_label"] or "(no answer)" for r in out)
    n = len(out)
    print(f"wrote {p.name}: {n} firms")
    for k, v in c.most_common():
        print(f"   {k:<18}{v:>4}   ({v/n:.0%} of {n})")
    if task != "tagged_no_prose":
        return
    tb = [r for r in out if r["reader_label"] == "table_only"]
    print(f"\n   firms the reader says DISCLOSE in a table the corpus strips: {len(tb)}")
    print("   (adding them would take the population from 351 to "
          f"{351 + len(tb)} firms -- Brian's call, not the reader's)")
    for r in tb[:12]:
        print(f"     {r['company'][:34]:<36}{r['tags'][:70]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("batch", "ingest"))
    ap.add_argument("--task", default="tagged_no_prose")
    ap.add_argument("--answers", nargs="*", default=[])
    a = ap.parse_args()
    if a.mode == "batch":
        do_batch(a.task)
    else:
        do_ingest(a.task, a.answers)


if __name__ == "__main__":
    main()
