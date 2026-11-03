#!/usr/bin/env python3
r"""Identification proof: firm x year, the sentence and the amount we stand behind.

WHAT THIS IS FOR
----------------
Brian, 17 September: *"goal is to get this deliverable as refined as possible. So we
can get solid identification proof, which we can then use as basis to identify firms
that similarly transferred IP."*

So this is not a coverage table. It is the set of firm-years where the filing says
something a person would defend in print, graded, with the reason recorded wherever it
does not. The graded set becomes the template for the Phase B sweep: whatever an A
looks like here is what to go looking for across every US multinational.

Two changes of unit from the earlier deliverable, both from Brian:

**Per YEAR, not per firm.** *"there could also be multiple transfers in different
years."* Gilead alone has 2018 (to the US) and 2019 (to Ireland AND the US). A
one-row-per-firm table has to throw one of those away.

**The verified year is an ESTIMATE.** *"We can also look in other years around that
year - that is an estimated 'verified' disclosure year."* So years are not filtered to
the verified one; the verified year is reported beside each row as context, and every
year with evidence gets a row.

GRADING, AND WHY IT IS TWO SCALES
----------------------------------
The sentence and the amount fail independently. REGN is the case: its destination
sentences are rate-reconciliation tables the corpus stripped of their digits, while
its amount sentence is as clean as any in the set -- *"(2) Income taxes for the year
ended December 31, 2018 includes a 162.1 million income tax benefit related to the
Company's sale of non-inventory related assets between foreign subsidiaries."* One
grade covering both would have to average them, and would be wrong about each.

    SENTENCE   A  the firm asserts a completed event in its own voice
               B  prose about a transfer, but descriptive or third-person
               C  table residue, or an announcement/forecast only

    AMOUNT     A  read from the transfer sentence itself, nearest the transfer
                  phrase, with effect language and no anticipatory wording
               B  read from an adjacent sentence in the same disclosure
               C  fell back to the largest figure, or a forecast, or a table
               -  none captured; `amount_missing_reason` says which kind of none

THE US VERDICT IS THREE-VALUED, NOT TWO
----------------------------------------
Brian: *"we'd also say 'US no' -- the sentence says 'between foreign subsidiaries'."*
Quite right, and it is a different answer from silence:

    yes        the US is named in the transfer sentence
    no         the sentence excludes it -- "between foreign subsidiaries",
               "among its foreign affiliates" -- or names another jurisdiction
    unnamed    a destination is stated but withheld: "to a higher taxed
               jurisdiction", "between tax jurisdictions"
    not_stated the disclosure says nothing about location

Collapsing `no` into `not_stated` discards a real answer to goal 2's question.

Writes: asu_v2_identification_proof_Claude.csv
"""
from __future__ import annotations

import collections
import csv
import re
import sys
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
CAND = HERE / "asu_v2_candidates_Claude.csv"
DELIV = HERE / "asu_v2_di_deliverable_Claude.csv"
OUT = HERE / "asu_v2_identification_proof_Claude.csv"

# The firm asserting that it did something, in its own voice and in the past.
ASSERTS = re.compile(
    r"\b(?:we|the\s+Company|the\s+Corporation)\s+(?:completed|transferred|sold|"
    r"entered\s+into|changed|consolidated|recorded|recognized|recognised|adopted)\b"
    r"|\b(?:we|the\s+Company)\s+\w+\s+(?:completed|transferred|recorded)\b"
    r"|\bincludes?\s+a\s+[\d.,]+\s*(?:million|billion)[^.]{0,80}?(?:related\s+to|"
    r"resulting\s+from)\b"
    r"|\bresulting\s+from\s+(?:an?\s+)?(?:intra|inter|transfer|sale)"
    r"|\bdue\s+to\s+(?:an?\s+|the\s+)?(?:intra|inter|transfer|sale)", re.I)
FORECAST = re.compile(
    r"anticipat\w+|estimat\w+|expects?\s+to|will\s+record|would\s+result"
    r"|is\s+evaluating|are\s+evaluating|will\s+be\s+effective|plans?\s+to\s+adopt", re.I)
# Describing what the standard does, rather than what the firm did.
BOILERPLATE = re.compile(
    r"the\s+FASB\s+issued|this\s+ASU\s+requires|requires\s+(?:an\s+)?entit\w+\s+to"
    r"|amended\s+guidance\s+was\s+issued|prior\s+to\s+the\s+adoption", re.I)


def grade_sentence(r):
    s = trim_furniture(r["anchor_sentence"])
    if r["table_residue"] == "yes":
        return "C", "table_residue"
    if AUDITOR.search(s):
        return "C", "auditors_voice_not_the_firm"
    if len(s) > 900:
        return "C", "sentence_never_terminated"
    if BACKWARD_ONLY.search(s):
        # "...the non-recurring benefit IN THE YEAR-AGO PERIOD resulting from
        # intra-entity transfers..." is Adobe describing its 2020 transfer inside a
        # 2021 filing. The transfer is real and already has its own row; counting it
        # again here would invent a second event.
        return "C", "backward_reference_to_a_prior_year"
    if FORECAST.search(s) and not ASSERTS.search(s):
        return "C", "forecast_or_announcement"
    if BOILERPLATE.search(s) and not ASSERTS.search(s):
        return "B", "describes_the_standard"
    if ASSERTS.search(s):
        return "A", "firm_asserts_completed_event"
    return "B", "transfer_prose_no_assertion"


# A figure sitting in a transfer sentence is not necessarily the transfer's figure.
# Two ways that goes wrong, both found by reading the proof set:
#
#   CRM  "...benefited by approximately 2.0 billion from the one-time discrete tax
#         benefit resulting from ... an INTRA-ENTITY TRANSFER of intangible property
#         and AN UNREALIZED GAIN OF 1.7 BILLION associated with the initial public
#         offerings..."   -- nearest-to-anchor took the IPO gain.
#   ADBE "Net income of 1.12 billion ... INCREASED BY 16 MILLION ... primarily due to
#         increases in revenue ... in part due to the non-recurring benefit IN THE
#         YEAR-AGO PERIOD resulting from intra-entity transfers..."  -- the figure is
#         a change in net income, and the transfer is a BACKWARD REFERENCE to a prior
#         year already captured in its own row.
#
# So a figure is disqualified by what sits beside it, and a sentence that only looks
# back is not evidence of a transfer in this year.
# CAREFUL: "net income TAX benefit" is the tax effect, and an early version of this
# list disqualified Microsoft's 3.3 billion -- the clearest US case in the set --
# because "net income" appears inside it. Every term here is negative-lookahead'd
# against the tax nouns that would make it the thing we want.
NOT_THE_TAX_EFFECT = re.compile(
    r"unrealized\s+gains?"
    r"|net\s+income(?!\s+tax)"
    r"|revenues?(?!\s+(?:tax|related))"
    r"|earnings\s+per\s+share|diluted\s+earnings"
    r"|cash\s+(?:provided|used|flows?)"
    r"|(?<!tax\s)increased\s+by|(?<!tax\s)decreased\s+by"
    r"|initial\s+public\s+offering|market\s+capitali"
    r"|operating\s+(?:expenses|income|margin)"
    r"|stock[-\s]based\s+compensation", re.I)
BACKWARD_ONLY = re.compile(
    r"year[-\s]ago\s+period|prior[-\s]year\s+period|in\s+the\s+prior\s+year"
    r"|compared\s+to\s+the\s+(?:prior|year[-\s]ago)", re.I)
MONEY_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand)\b", re.I)
_MULT = {"billion": 1e9, "million": 1e6, "thousand": 1e3}


def pick_amount(sentence, anchor_text, wider=""):
    """Re-pick the figure, disqualifying ones attached to something else.

    The extractor keeps every figure with its provenance; choosing among them is the
    deliverable's job, and this is where 'the amount we feel strongly about' is
    decided. Returns (value, why) or (None, reason).
    """
    if BACKWARD_ONLY.search(sentence):
        return None, "sentence_only_refers_back_to_a_prior_year"
    pos = sentence.lower().find((anchor_text or "").lower()[:20])
    best = None
    for m in MONEY_RE.finditer(sentence):
        lo, hi = max(0, m.start() - 55), min(len(sentence), m.end() + 55)
        if NOT_THE_TAX_EFFECT.search(sentence[lo:hi]):
            continue
        v = float(m.group(1).replace(",", "")) * _MULT[m.group(2).lower()]
        d = abs(m.start() - pos) if pos >= 0 else m.start()
        if best is None or d < best[1]:
            best = (v, d)
    if best is None and wider:
        # Adobe states the transfer in one sentence and the figure in the next --
        # "we completed an intra-entity transfer of certain IP rights ... As a result
        # of this transaction, we recorded ..." -- which is the project's own defect
        # 3. Looking only at the anchor sentence demoted a correct 224m to C.
        for m in MONEY_RE.finditer(wider):
            lo, hi = max(0, m.start() - 55), min(len(wider), m.end() + 55)
            if NOT_THE_TAX_EFFECT.search(wider[lo:hi]):
                continue
            v = float(m.group(1).replace(",", "")) * _MULT[m.group(2).lower()]
            return v, "qualifying_figure_in_the_adjacent_sentence"
    if best is None:
        return None, "every_figure_attached_to_something_else"
    return best[0], "nearest_qualifying_figure"


TRANSFERISH = re.compile(
    r"intra[-\s]?entity|intra[-\s]?group|intercompany|inter\s?company"
    r"|transferr?(?:ed|s)?|consolidation\s+of|non[-\s]?inventory", re.I)


def grade_amount(r):
    # The figure has to sit near the transfer language, in a sentence that is
    # actually about a transfer. Adobe's 2021 proof row was "Net income of 1.12
    # billion ... increased by 16 million ... primarily due to increases in
    # revenue" -- a real figure, correctly parsed, about nothing relevant.
    s = trim_furniture(r["anchor_sentence"])
    if r["amount_best"] and not TRANSFERISH.search(s):
        return "C", "figure_not_in_a_transfer_sentence"
    if r["amount_best"]:
        v, why = pick_amount(s, r["anchor_text"], r.get("candidate_text", ""))
        if v is None:
            return "C", why
    if r["amount_best"] and AUDITOR.search(s):
        return "C", "auditors_voice_not_the_firm"
    if not r["amount_best"]:
        if int(r["n_stripped_magnitudes"] or 0) > 0:
            return "-", "figure_removed_by_corpus"
        return "-", "no_figure_in_disclosure"
    basis = r["amount_basis"] or ""
    if r["table_residue"] == "yes":
        return "C", "read_from_table_residue"
    if FORECAST.search(r["anchor_sentence"]):
        return "C", "forecast_figure"
    if basis.startswith("anchor_sentence"):
        return "A", basis
    if basis == "anchored_to_effect_language":
        return "B", "adjacent_sentence_effect_language"
    return "C", basis or "unanchored"


NON_US = ("Ireland", "Irish", "Switzerland", "Singapore", "Netherlands", "Bermuda",
          "Cayman", "Luxembourg", "Puerto Rico", "Israel", "Hong Kong", "Malta",
          "United Kingdom", "Jersey", "Barbados", "Bahamas", "Isle of Man")


def us_verdict(r):
    if r["destination_is_us"] == "yes" and r["us_in_anchor_sentence"] == "yes":
        return "yes", r["destination"] or "United States"
    if r["destination_excludes_us"] == "yes":
        return "no", "stated: between foreign entities"
    if (r["destination_basis"] in ("prep_to", "cued")
            and r["destination_in_anchor_sentence"] == "yes"
            and r["destination"] in NON_US):
        return "no", r["destination"]
    if r["destination_unnamed_form"]:
        return "unnamed", r["destination_unnamed_form"]
    return "not_stated", ""


# Page furniture the corpus leaves inline, which the sentence splitter then welds
# onto the front of a real sentence: Monster's proof row opened "45 Table of Contents
# Our Business Overview We develop, market, sell and distribute energy drink
# beverages..." with the actual disclosure hundreds of characters later.
FURNITURE = re.compile(
    r"^\s*(?:\d{1,3}\s+)?(?:Table\s+of\s+Contents?|PART\s+[IV]+|Item\s+\d"
    r"|[A-Z][a-z]+\s+Inc\.?\s*\|)[^.]{0,120}?(?=[A-Z])", re.I)

# The AUDITOR's voice, not the firm's. A Critical Audit Matter describes the
# disclosure accurately but is not the company asserting the event, and an
# identification set built on it is quoting the wrong party.
AUDITOR = re.compile(
    r"Critical\s+Audit\s+Matter|Report\s+of\s+Independent\s+Registered"
    r"|As\s+described\s+in\s+Note|Refer\s+to\s+Note\s+\d+\s+to\s+the"
    r"|our\s+audit|the\s+financial\s+statement\s+audit", re.I)

# A sentence that is really page furniture plus prose: the transfer phrase and the
# figure have to sit in the SAME clause, not merely the same merged block.
def trim_furniture(s):
    m = FURNITURE.match(s)
    return s[m.end():].lstrip() if m else s


RANK = {"A": 0, "B": 1, "C": 2, "-": 3}


def main():
    rows = list(csv.DictReader(CAND.open(encoding="utf-8")))
    deliv = {r["ticker"]: r for r in csv.DictReader(DELIV.open(encoding="utf-8"))}

    # firm x calendar year of the disclosed period
    buckets = collections.defaultdict(list)
    for r in rows:
        if not r["ticker"] or not r["period_cal_year"]:
            continue
        try:
            y = int(r["period_cal_year"])
        except ValueError:
            continue
        buckets[(r["ticker"], y)].append(r)

    out = []
    for (tic, y), cands in sorted(buckets.items()):
        sg = [(grade_sentence(c), c) for c in cands]
        best_s = min(sg, key=lambda t: (RANK[t[0][0]], -float(t[1]["score"] or 0)))
        ag = [(grade_amount(c), c) for c in cands]
        best_a = min(ag, key=lambda t: (RANK[t[0][0]], -float(t[1]["score"] or 0)))

        # the US verdict takes the most informative answer available that year:
        # a named destination beats an exclusion beats an unnamed form beats silence
        order = {"yes": 0, "no": 1, "unnamed": 2, "not_stated": 3}
        uv = sorted(((us_verdict(c), c) for c in cands),
                    key=lambda t: order[t[0][0]])[0]

        verified = deliv.get(tic, {}).get("verified_transfer_year", "")
        out.append({
            "ticker": tic,
            "year": y,
            "verified_transfer_year": verified,
            "years_from_verified": (y - int(verified)) if verified.isdigit() else "",
            "sentence_grade": best_s[0][0],
            "sentence_basis": best_s[0][1],
            "amount_grade": best_a[0][0],
            "amount_basis_graded": best_a[0][1],
            "amount": (pick_amount(trim_furniture(best_a[1]["anchor_sentence"]),
                                    best_a[1]["anchor_text"],
                                    best_a[1].get("candidate_text", ""))[0]
                       if best_a[0][0] in ("A", "B") else best_a[1]["amount_best"]),
            "amount_as_extracted": best_a[1]["amount_best"],
            "amount_direction": best_a[1]["effect_direction"],
            "amount_dta_dtl": best_a[1]["dta_dtl"],
            "us_verdict": uv[0][0],
            "us_evidence": uv[0][1],
            "disclosure_type": best_s[1]["disclosure_type"],
            "date_usable_as_transfer_date": best_s[1]["date_usable_as_transfer_date"],
            "period_text": best_s[1]["period_text"],
            "candidates_this_year": len(cands),
            "sentence_form": best_s[1]["form"],
            "sentence_filed": best_s[1]["filing_date"],
            "sentence_file": best_s[1]["file"],
            "THE_SENTENCE": trim_furniture(best_s[1]["anchor_sentence"])[:600],
            "amount_form": best_a[1]["form"],
            "amount_filed": best_a[1]["filing_date"],
            "amount_file": best_a[1]["file"],
            "THE_AMOUNT_SENTENCE": (trim_furniture(best_a[1]["anchor_sentence"])[:600]
                                    if best_a[0][0] != "-" else ""),
        })

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print(f"wrote {OUT.name}  ({len(out)} firm-years, "
          f"{len({r['ticker'] for r in out})} firms)\n")
    win = [r for r in out if 2018 <= r["year"] <= 2021]
    print(f"--- 2018-2021: {len(win)} firm-years, "
          f"{len({r['ticker'] for r in win})} firms ---")
    print("sentence grade:", dict(collections.Counter(r["sentence_grade"] for r in win)))
    print("amount grade:  ", dict(collections.Counter(r["amount_grade"] for r in win)))
    print("US verdict:    ", dict(collections.Counter(r["us_verdict"] for r in win)))
    strong = [r for r in win if r["sentence_grade"] == "A"]
    print(f"\nA-grade sentences, 2018-2021: {len(strong)} firm-years, "
          f"{len({r['ticker'] for r in strong})} firms")
    both = [r for r in strong if r["amount_grade"] == "A"]
    print(f"  of which the amount is also A: {len(both)}")
    print("\nWHY the rest fall short (sentence basis, 2018-2021):")
    for k, n in collections.Counter(
            r["sentence_basis"] for r in win if r["sentence_grade"] != "A").most_common():
        print(f"  {k:<32} {n}")
    print("\nWHY no amount (2018-2021):")
    for k, n in collections.Counter(
            r["amount_basis_graded"] for r in win if r["amount_grade"] == "-").most_common():
        print(f"  {k:<32} {n}")


if __name__ == "__main__":
    main()
