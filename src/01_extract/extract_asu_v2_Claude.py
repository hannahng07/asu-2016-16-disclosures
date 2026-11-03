#!/usr/bin/env python3
r"""ASU 2016-16 / intercompany IP transfers -- EVERY candidate, with provenance.

WHAT THIS IS AND WHY IT IS A SECOND FILE
----------------------------------------
This is Phase A jobs **A3** and **A4** from `PROJECT_INSTRUCTIONS.md`, built
alongside `extract_asu_2016_16_Claude.py` rather than inside it. The v1 script,
its output `asu_2016_16_extracted_Claude.csv`, the gold set, the answer key and
everything in `Hannah/` are untouched by this file. Nothing here overwrites a
dataset.

    A3  "Stop choosing one sentence per filing. Emit EVERY candidate with its
         amount, date, jurisdiction and provenance; let the answer key or a
         person select. Recall with provenance beats precision that silently
         discards the right answer."

    A4  "Convert fiscal periods to calendar dates using datadate... per firm
         AND per year, because US fiscal year ends move."

THE DEFECT A3 FIXES, IN THE PROJECT'S OWN NUMBERS
--------------------------------------------------
v1 keeps ONE window per filing -- the highest scoring -- and the right sentence
is frequently in a lower-scoring one:

    IT    want  38,100,000   got 6,800,000 / 8,000,000 / 13,700,000
    SNPS  want 130,500,000   got 22,800,000 / 24,000,000 / 27,000,000
    MNST  want 165,100,000   got 6,600,000 / 12,300,000 / 4,200,000,000

Detection was never the constraint (81%). Selection is. So this script does not
select. The unit of output is the CANDIDATE, not the filing: one row per anchor
sentence, ranked within its filing, every one of them written out with the
offset it came from and the sentence it was read out of. `candidate_rank` lets
any consumer reproduce v1's behaviour exactly (`candidate_rank == 1`) and lets
the validator measure what v1 could not: was the right answer PRESENT and
discarded, or never found at all. Those are different failures and they need
different fixes.

HOW A4 IS DONE WITHOUT COMPUSTAT
---------------------------------
"The second quarter of fiscal 2021" is meaningless without the filer's calendar,
and US fiscal year ends MOVE (HRB 30apr->30jun in 2022; VMW 31dec->31jan in
2017), so the conversion has to be per firm AND per year.

`di_firm_years_Claude.txt` holds one row per firm -- the first year only -- so it
cannot do this on its own. It is used here as a fallback and as the identifier
list, and the per-year calendar comes instead from the corpus itself: every
Loughran-McDonald filing carries its SEC header, and

    CONFORMED PERIOD OF REPORT:  20210131
    FISCAL YEAR END:             0131

give the fiscal period end of that filing directly. Pass 1 reads those headers
across every filing of every firm in the population and builds

    fye[cik][calendar_year_of_period_end] = period end date

which moves with the firm because it is read from the filings themselves. Pass 2
converts. `fye_source` records which route was used for every row, so a date
resting on a fallback is visible as such and never silently equal to one read
from a header.

Firms label a fiscal year by the calendar year it ENDS in -- Salesforce's fiscal
2021 ends 31 January 2021, Adobe's fiscal 2020 ends in November 2020, Apple's in
September. So "fiscal 2021" resolves to the period ending in calendar 2021, and
"the second quarter of fiscal 2021" to that period's end minus two quarters:
Salesforce Q2 FY2021 = the quarter ending 31 July 2020. That is the August 2020
the workstream note puts it at, and it is a year off the naive reading.

`period_cal_year` is the calendar year and is what should be compared with a
hand transfer year. `period_fiscal_year` is kept beside it, unconverted, so the
two can never be confused.

WHAT ELSE IS CAPTURED, AND WHY
-------------------------------
**Sign, and DTA versus DTL** -- settled point 5 of the project instructions:

    "Every Double Irish case seen so far records a deferred tax ASSET... The
     broader population will not all look like that. Treat this as a
     sample-selection risk, not a missing field."

`effect_direction` (benefit / cost / mixed / none) and `dta_dtl` (DTA / DTL /
both / none) are fields in their own right, and the cost vocabulary is matched
as well as the benefit vocabulary. Calibrating on the DI firms CANNOT surface a
cost case, because they are all DTA -- which is the reason to capture the field
now rather than when Phase B opens and the bias is already baked into the
population.

**Stripped amounts.** The corpus has no dollar signs and 12% of magnitude words
have lost their figure ("related tax benefits of million and billion"), which
affects 46% of filings. `n_stripped_magnitudes` counts magnitude words in the
candidate with no number in front. A candidate with an effect cue, a stripped
magnitude and no amount is a DISCLOSURE WITH ITS NUMBER REMOVED, not a firm that
disclosed nothing -- and it is exactly the row to go to the 10-Q or to raw EDGAR
for. Absence of an amount here is never evidence of absence.

**Every amount in the candidate**, not one. `amounts_all` is the full list;
`amount_best` applies v1's effect-language anchoring on top, and
`amount_basis` says which of the two it came from.

WHAT IS UNCHANGED FROM v1, DELIBERATELY
----------------------------------------
The anchor is Hannah's, with the three extensions read out of the mismatches
(CRM "certain" intervening, ANET "transaction", IT "sale") and the REGN rate-
reconciliation form. The money pattern still requires a magnitude word, because
the corpus has no currency symbol left to tell a figure from a page number. The
window still stops at the next OTHER standard (defect 2) and still carries the
following sentence (defect 3). None of that was the constraint and none of it is
re-litigated here.

Usage
-----
Build the fiscal calendar once, then extract one zip at a time (the shell this
runs in is capped at a few minutes per invocation, and a detached process does
not survive the call):

    python extract_asu_v2_Claude.py --mode fye --population di
    python extract_asu_v2_Claude.py --population di --zips 10-X_C_2016-2020.zip
    python extract_asu_v2_Claude.py --population di --zips 10-X_C_2021.zip --append
    ...
    python extract_asu_v2_Claude.py --population di --only CRM,ADBE,REGN   # spot test

Writes (new files, nothing overwritten):
    asu_v2_candidates_Claude.csv   one row per candidate, ranked, with provenance
    asu_v2_fye_map_Claude.csv      the per-firm per-year fiscal calendar it built
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import collections
import csv
import datetime as dt
import json
import re
import sys
import zipfile
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

HERE = Path(__file__).resolve().parent
GOLD_JSON = HERE / "tenk_gold_set_Claude.json"
DI_FIRMS = HERE / "di_firm_years_Claude.txt"
OUT_CAND = HERE / "asu_v2_candidates_Claude.csv"
OUT_FYE = HERE / "asu_v2_fye_map_Claude.csv"

ZIPS = ["10-X_C_2016-2020.zip", "10-X_C_2021.zip", "10-X_C_2022.zip",
        "10-X_C_2023.zip", "10-X_C_2024.zip"]

# ---------------------------------------------------------------- patterns --

ASU_1616 = re.compile(r"ASU\s*(?:No\.?\s*)?2016\s*-\s*16", re.I)

# `IP` is matched as an UPPER-CASE WHOLE WORD only. Until 21 September it sat inside a
# case-insensitive pattern with no word boundary, so it matched the "ip" in "owners-hip",
# "relationsHIP", "equIPment" and "IPP". The Phase B precision sample found the damage:
# Hain Celestial ("ownership transfers to these distributors"), Starwood ("ownership
# transfers to the lessee") and Hawaiian Electric three times ("consolidation of any
# significant IPP" -- an independent power producer). It was also most of the run time:
# the regex attempted a match at every "ip" in a 200-page filing.
_IPISH = r"(?:intellectual\s+propert(?:y|ies)|intangible(?:\s+asset)?s?|(?-i:\bIP\b))"
# WIDENED, 17 September, by a case the old list walked past -- and the case it
# walked past is the worst one it could have.
#
# Gilead states, in three consecutive 10-Ks:
#
#   "In 2018, we recorded a deferred tax CHARGE of 588 million related to a
#    transfer of ACQUIRED intangible assets from a foreign subsidiary to THE
#    UNITED STATES."
#   "...of 1.2 billion related to intangible ASSET TRANSFERS from a foreign
#    subsidiary to Ireland and the United States."
#
# `_CERTAIN` admitted only certain/the/its/our between "of" and the IP noun, so
# "of ACQUIRED intangible assets" did not match, and neither did the noun-
# compound "intangible asset transfers from". Gilead's 588 million is in the
# answer key and was absent from every candidate this script produced.
#
# What makes this more than one missed ticker: it is a COST case (a deferred tax
# CHARGE, not a benefit) whose destination is the UNITED STATES. That is
# simultaneously settled point 5 -- "the tax effect can be a COST... a pattern
# anchored on benefit language builds a population biased toward low-tax
# destinations" -- and goal 2's actual question. The anchor's blind spot was
# correlated with exactly the disclosures the study most needs, which is the
# form of bias that does not show up in an output file.
#
# So the modifier slot is now a bounded run of any words, not a closed list. The
# IP noun still has to be there, which is what keeps it from matching "transfer
# of the business to".
_ADJ = r"(?:[A-Za-z][A-Za-z-]*\s+){0,3}"
_CERTAIN = r"(?:certain\s+|the\s+|its\s+|our\s+)*"

# Hannah's anchor, with the four extensions each proved by a named filing.
# Unchanged from v1 -- detection is not what this script is trying to move.
TRANSFER_ANCHOR = re.compile(
    r"ASU\s*(?:No\.\s*)?2016\s*-?\s*16|"
    r"Accounting\s+Standards\s+Update(\s+No\.)?\s+2016\s*-?\s*16|"
    r"intra[-\s]?entity\s+(transfers?|assets?)|"
    r"intra[-\s]?entity\s+asset\s+transfers?|"
    r"intra[-\s]?group\s+transfers?|"
    r"intercompany\s+transfers?\s+of\s+assets|"
    # -- added 22 September, from the XBRL recall probe. Amazon and Starbucks both
    #    disclose an adoption effect in prose and both produced ZERO candidates,
    #    because the words sit in a different order than the anchor expected:
    #      Amazon:    "the income tax consequences of an INTERCOMPANY ASSET TRANSFER"
    #      Starbucks: "an INTRA-ENTITY SALE OR TRANSFER OF AN ASSET other than inventory"
    #    The third line is the standard's own phrase, which several firms use without
    #    ever writing "intra-entity" or "intercompany" next to it.
    r"intercompany\s+(?:asset|intangible|intellectual\s+propert\w+|IP)\s+transfers?|"
    r"intra[-\s]?entity\s+(?:sales?|transfers?)(?:\s+or\s+(?:sales?|transfers?))?"
    r"\s+of\s+(?:an?\s+|the\s+|certain\s+)*assets?|"
    r"intercompany\s+(?:sales?|transactions?|transfers?)(?:\s+or\s+(?:sales?|transfers?))?"
    r"\s+of\s+(?:an?\s+|the\s+|certain\s+)*assets?\s+other\s+than\s+inventor|"
    r"(?:sales?|transfers?)\s+of\s+(?:an?\s+|the\s+|certain\s+)*assets?\s+"
    r"other\s+than\s+inventor|"
    r"intercompany\s+transfers?\s+of\s+intellectual|"
    r"intercompany\s+transfers?\s+of\s+intangible|"
    r"intercompany\s+transfers?\s+of\s+certain\s+intellectual|"
    r"intercompany\s+transfers?\s+of\s+certain\s+intangible|"
    r"sold\s+intellectual\s+property\s+(between|to)|"
    r"transfer\s+of\s+intangible\s+(propert(?:y|ies)|assets?)|"
    rf"intra[-\s]?entity\s+transactions?|"
    rf"intra[-\s]?entity\s+(?:asset\s+)?transfers?\s+of\s+{_CERTAIN}{_IPISH}|"
    rf"inter\s?company\s+sales?\s+of\s+{_CERTAIN}{_IPISH}|"
    rf"transfers?\s+of\s+{_ADJ}{_IPISH}\s+(?:between|to|from|into)|"
    rf"transferr?ed\s+{_ADJ}{_IPISH}\s+(?:between|to|from|into)|"
    rf"sales?\s+of\s+{_ADJ}{_IPISH}\s+(?:between|to|from|into)|"
    # -- added 17 September, from Gilead: the NOUN-COMPOUND form, where the
    #    IP word modifies "transfer" instead of following "transfer of".
    #    "intangible asset transfers from a foreign subsidiary to Ireland and
    #    the United States"
    rf"{_IPISH}\s+(?:asset\s+|propert\w+\s+|rights?\s+)?transfers?\s+"
    r"(?:from|to|between|into)|"
    # -- added 17 September, from Salesforce. The firm never writes "transfer"
    #    in the sentence that names the destination:
    #
    #      "The Company changed its international corporate structure, which
    #       included the CONSOLIDATION OF CERTAIN INTANGIBLE PROPERTY IN IRELAND
    #       resulting in a net tax benefit related to foreign deferred tax assets."
    #
    #    A destination cue for exactly this phrasing was already in DEST_CUE, but
    #    the sentence was never reachable because nothing anchored it. Salesforce
    #    is the project's own worked example of a good disclosure and it was being
    #    filed under "no destination" -- on the strength of the one word the firm
    #    happened not to use.
    rf"consolidat\w+\s+of\s+{_ADJ}{_IPISH}|"
    rf"centrali[sz]\w+\s+(?:of\s+)?{_ADJ}{_IPISH}|"
    r"non[-\s]?inventory(?:[-\s]related)?\s+assets?|"
    r"(?:sales?|transfers?)\s+of\s+[^.]{0,60}?assets?\s+between\s+"
    r"(?:foreign\s+|its\s+|our\s+)*(?:subsidiar|affiliat|entit|member)",
    re.I)

# Defect 2: the capture window stops at the next OTHER pronouncement.
OTHER_STD = re.compile(
    r"AS[UC]\s*(?:No\.?\s*)?(?!2016\s*-\s*16)\d{4}\s*-\s*\d{2}", re.I)

# The corpus has ZERO dollar signs, so the magnitude word carries the match.
MONEY = re.compile(r"\$?\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)\b", re.I)
MAGNITUDE = re.compile(r"\b(billion|million|thousand)\b", re.I)
_MULT = {"billion": 1e9, "million": 1e6, "thousand": 1e3}

_MON = ("january|february|march|april|may|june|july|august|september|october"
        "|november|december")
_MONTHNUM = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october "
    "november december".split())}

# Ordered most-specific first. A calendar period stated outright beats a fiscal
# one that has to be converted -- REGN's "the year ended December 31, 2018" is
# the case, and reading it as a fiscal label is how v1 landed on the Tax Cuts
# and Jobs Act's December 2017 in the neighbouring sentence instead.
PERIOD_PATS = [
    (re.compile(rf"\b(?:year|quarter|period|months)\s+ended\s+({_MON})\s+"
                r"(\d{1,2}),?\s+(\d{4})", re.I), "period_ended"),
    (re.compile(rf"\b(first|second|third|fourth)\s+quarter\s+of\s+"
                r"(?:fiscal\s+)?(?:year\s+)?(\d{4})", re.I), "quarter"),
    (re.compile(rf"\b(Q[1-4])\s+(?:of\s+)?(?:fiscal\s+)?(?:year\s+)?(\d{{4}})", re.I),
     "quarter_q"),
    (re.compile(rf"\b(?:in|during)\s+({_MON})\s+(\d{{4}})", re.I), "month"),
    (re.compile(r"\bduring\s+(?:the\s+)?fiscal\s+(?:year\s+)?(\d{4})", re.I),
     "fiscal_year"),
    (re.compile(rf"\b({_MON})\s+(\d{{4}})", re.I), "month"),
    (re.compile(r"\bfiscal\s+(?:year\s+)?(\d{4})", re.I), "fiscal_year"),
]

JURISDICTIONS = ("Ireland", "Irish", "Bermuda", "Cayman", "Luxembourg",
                 "Netherlands", "Switzerland", "Singapore", "United Kingdom",
                 "Puerto Rico", "Israel", "Hong Kong", "Malta", "Jersey",
                 "Isle of Man", "Barbados", "Bahamas", "United States")
# "U.S." is everywhere in a 10-K, so it counts only when a destination cue is
# attached. Goal 2 is whether the IP came INTO the United States, so it has to
# be reachable -- but not at the price of matching every risk factor.
US_CUED_ONLY = re.compile(r"\bU\.?\s?S\.?\b|\bUnited\s+States\b")
DEST_CUE = re.compile(
    r"(realized\s+in|realizable\s+in|realised\s+in|transferr?ed\s+to|located\s+in"
    r"|domiciled\s+in|jurisdiction\s+of|subsidiar\w+\s+in|affiliate\s+in"
    r"|entity\s+in|consolidation\s+of\s+certain\s+intangible\s+property\s+in"
    r"|tax\s+rate\s+in|enacted\s+\w+\s+tax\s+rate|into\s+the|back\s+to"
    r"|onshore|repatriat\w+)", re.I)

# A destination can be STATED without being NAMED, and the distinction matters for
# goal 2 in opposite directions:
#
#   "between foreign subsidiaries"           REGN -- no place named, but it EXCLUDES
#   "between foreign affiliates"             CRM     the United States outright
#   "to a higher taxed jurisdiction"         MTSI -- direction given, place withheld
#   "between tax jurisdictions"              SYK  -- nothing given at all
#
# Filing all three under "no destination stated" throws away the first, which is a
# real answer to "did the IP come into the US?" -- it says no.
EXCLUDES_US = re.compile(
    r"between\s+(?:certain\s+(?:of\s+)?(?:its|our|the\s+Company's)?\s*)?"
    r"(?:wholly[-\s]owned\s+)?foreign\s+(?:subsidiar\w+|affiliat\w+|entit\w+"
    r"|member\w*|jurisdiction\w*)"
    r"|among\s+(?:its\s+|our\s+)?foreign\s+(?:subsidiar\w+|affiliat\w+)"
    r"|from\s+one\s+foreign\s+(?:subsidiar\w+|affiliat\w+)\s+to\s+another", re.I)
UNNAMED_DEST = re.compile(
    r"(?:to|into)\s+a\s+(?:higher|lower)[-\s]?tax\w*\s+jurisdiction"
    r"|between\s+tax\s+jurisdictions?"
    r"|(?:to|into)\s+(?:a|another|certain)\s+(?:foreign\s+)?"
    r"(?:subsidiar\w+|affiliat\w+|jurisdiction\w*)"
    r"|(?:to|into)\s+(?:one\s+of\s+)?(?:its|our)\s+(?:foreign\s+)?"
    r"(?:subsidiar\w+|affiliat\w+)", re.I)

ACCOUNTS = ("retained earnings", "deferred tax asset", "deferred tax liability",
            "valuation allowance", "income tax expense", "tax benefit",
            "other non-current assets", "provision for income taxes",
            "goodwill", "current tax expense")

# Settled point 5: the effect can be a COST. Both vocabularies are matched and
# the sign is a field. A pattern anchored on benefit language alone builds a
# population biased toward low-tax destinations -- invisible in the output, and
# the wrong bias for an investor study.
BENEFIT_LANG = re.compile(
    r"(tax\s+benefit|benefit\s+from\s+income\s+tax|net\s+deferred\s+tax\s+asset"
    r"|deferred\s+tax\s+asset|increased?\s+retained\s+earnings"
    r"|reduction\s+(?:in|of|to)\s+(?:our\s+|the\s+)?(?:income\s+)?tax"
    r"|favorable\s+(?:income\s+)?tax)", re.I)
COST_LANG = re.compile(
    r"(tax\s+expense|tax\s+charge|tax\s+cost|deferred\s+tax\s+liabilit"
    r"|resulted\s+in\s+a\s+(?:tax\s+)?charge|incurred\s+(?:a\s+)?tax"
    r"|reduced?\s+retained\s+earnings|decreased?\s+retained\s+earnings"
    r"|unfavorable\s+(?:income\s+)?tax|one[-\s]time\s+(?:tax\s+)?charge)", re.I)
DTA_LANG = re.compile(r"deferred\s+tax\s+asset", re.I)
DTL_LANG = re.compile(r"deferred\s+tax\s+liabilit", re.I)

EFFECT_CUE = re.compile(
    r"(recorded|recognized|recognised|resulted\s+in|increase[ds]?\s+retained"
    r"|cumulative[-\s]effect|net\s+deferred\s+tax|tax\s+benefit|tax\s+expense"
    r"|tax\s+charge|deferred\s+tax\s+asset|deferred\s+tax\s+liabilit"
    r"|adjustment\s+of|charge\s+of|benefit\s+of|expense\s+of)", re.I)

ADOPTION = re.compile(
    r"(we\s+adopted|the\s+Company\s+adopted|upon\s+adoption|adoption\s+of\s+ASU"
    r"|we\s+completed|resulted\s+in|cumulative[-\s]effect|recorded"
    r"|modified\s+retrospective|intra-?entity\s+transfer\s+of\s+(?:certain\s+)?"
    r"(?:intellectual|IP|asset))", re.I)
FUTURE = re.compile(
    r"(will\s+be\s+effective|is\s+effective\s+for|effective\s+for\s+(?:the\s+)?"
    r"(?:Company|fiscal|annual)|we\s+are\s+(?:currently\s+)?evaluating"
    r"|does\s+not\s+expect|is\s+not\s+expected\s+to"
    r"|will\s+adopt|plans?\s+to\s+adopt|expects?\s+to\s+adopt"
    r"|anticipates?\s+record|estimates?\s+record|expects?\s+to\s+record"
    r"|anticipates?\s+recogni|would\s+result\s+in)", re.I)
PAST = re.compile(
    r"(upon\s+adoption|we\s+adopted|the\s+Company\s+adopted|adopted\s+ASU"
    r"|we\s+completed|was\s+recorded|were\s+recorded|resulted\s+in\s+a)", re.I)
CUMULATIVE = re.compile(
    r"(upon\s+adoption|modified\s+retrospective|cumulative[-\s]effect"
    r"|adjustment\s+(?:directly\s+)?to\s+(?:opening\s+)?retained\s+earnings"
    r"|transition\s+method|as\s+of\s+the\s+(?:date\s+of\s+)?adoption)", re.I)
CURRENT_XFER = re.compile(
    r"(we\s+completed\s+(?:an?\s+)?intra-?entity|completed\s+(?:an?\s+)?intra-?entity"
    r"|during\s+(?:the\s+)?(?:fiscal\s+)?(?:year|quarter)[^.]{0,60}"
    r"(?:transferr?ed|transfer\s+of|we\s+changed\s+our)"
    r"|we\s+changed\s+our\s+international\s+corporate\s+structure"
    r"|intra-?entity\s+(?:asset\s+)?transfer\s+of\s+(?:certain\s+)?(?:intellectual|IP))",
    re.I)

# ------------------------------------------------------------- sentences ----

_ABBR = {"no", "nos", "inc", "corp", "ltd", "co", "mr", "mrs", "ms", "dr", "st",
         "approx", "etc", "vs", "jr", "sr", "fig", "al", "dept", "est", "vol",
         "u.s", "e.g", "i.e", "u.k", "llc", "lp", "plc", "sa", "nv", "ag"}
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str):
    """(start, end) spans. Abbreviations and decimals must not split a sentence.

    A naive split on ". " breaks "ASU No. 2016-16" in half and puts the anchor
    and its amount in different candidates, which is the failure this whole
    script exists to stop doing.
    """
    spans, start = [], 0
    for m in _BOUNDARY.finditer(text):
        end = m.start()
        seg = text[start:end]
        tok = re.search(r"([A-Za-z][A-Za-z.]*)\.$", seg)
        if tok and tok.group(1).lower().rstrip(".") in _ABBR:
            continue
        if re.search(r"\b[A-Z]\.$", seg):        # a middle initial
            continue
        if end + 1 > start:
            spans.append((start, end + 1))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def strip_header(text: str) -> str:
    """Drop the Loughran-McDonald / SEC header so it cannot raise a candidate."""
    for tag in ("</Header>", "</SEC-Header>", "</SEC-HEADER>"):
        i = text.find(tag)
        if i != -1:
            return text[i + len(tag):]
    return text


def header_fields(text: str) -> dict:
    """CONFORMED PERIOD OF REPORT and FISCAL YEAR END, read from the filing."""
    head = text[:6000]
    out = {}
    m = re.search(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})", head)
    if m:
        out["period_of_report"] = m.group(1)
    m = re.search(r"FISCAL YEAR END:\s*(\d{4})", head)
    if m:
        out["fiscal_year_end"] = m.group(1)
    m = re.search(r"COMPANY CONFORMED NAME:\s*(.+)", head)
    if m:
        out["company"] = m.group(1).strip()
    return out


# ------------------------------------------------------- fiscal calendar ----

def _add_months(d: dt.date, n: int) -> dt.date:
    """Month arithmetic that keeps an end-of-month date at end of month.

    A fiscal year ending 31 January minus six months has to land on 31 July,
    not 31 June, and a 29 February year end has to survive a non-leap year.
    """
    total = (d.year * 12 + d.month - 1) + n
    y, m = divmod(total, 12)
    m += 1
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, min(d.day, last))


def fiscal_to_calendar(kind, fiscal_year, quarter, fye_date):
    """(start, end) calendar dates for a fiscal period, given the firm's own
    year end for THAT year. Returns (None, None) when the calendar is unknown --
    an unconverted period is left unconverted rather than guessed."""
    if fye_date is None or fiscal_year is None:
        return None, None
    if kind == "fiscal_year":
        return _add_months(fye_date, -12) + dt.timedelta(days=1), fye_date
    if kind in ("quarter", "quarter_q") and quarter:
        q_end = _add_months(fye_date, -3 * (4 - quarter))
        q_start = _add_months(q_end, -3) + dt.timedelta(days=1)
        return q_start, q_end
    return None, None


# ------------------------------------------------------------ extraction ----

def score_candidate(win: str) -> int:
    s = 0
    if MONEY.search(win):
        s += 3
    s += 2 * len(ADOPTION.findall(win))
    s -= 2 * len(FUTURE.findall(win))
    if re.search(r"retained\s+earnings", win, re.I):
        s += 2
    if DTA_LANG.search(win) or DTL_LANG.search(win):
        s += 1
    s += 4 * len(PAST.findall(win))
    return s


def disclosure_type(win: str) -> str:
    cur, cum = CURRENT_XFER.search(win), CUMULATIVE.search(win)
    if cur and not cum:
        return "current_period_transfer"
    if cum and not cur:
        return "adoption_cumulative_effect"
    if cur and cum:
        return ("current_period_transfer" if cur.start() < cum.start()
                else "adoption_cumulative_effect")
    return "unclear"


def amounts_in(text: str, anchor_len: int = 0, anchor_pos: int = 0):
    """Every money figure in the candidate, plus the effect-anchored pick.

    v1 returned one. Returning all of them is the point: when the answer key
    disagrees, the question is whether the right number was PRESENT and passed
    over, and only the full list can answer it.
    """
    all_vals, spans = [], []
    for m in MONEY.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        v *= _MULT.get(m.group(2).lower(), 1.0)
        all_vals.append(v)
        spans.append((m.start(), v, m.group(0)))
    cues = [m.start() for m in EFFECT_CUE.finditer(text)]
    # PREFERENCE ORDER. The disclosure is what the ANCHOR SENTENCE asserts, so a
    # figure inside it outranks one further down the window even when the latter
    # sits closer to an effect cue.
    #
    # Analog Devices is the case. Its anchor sentence reads "...resulted in an
    # increase in retained earnings of 331.0 million, by recording new deferred
    # tax assets from intra-entity transfers", and 331.0 million is the answer
    # key. Cue-distance alone picked 1.7 billion from later in the same window.
    # And WITHIN the anchor sentence, the figure nearest the TRANSFER PHRASE,
    # not the one nearest any effect cue -- a sentence can carry two figures
    # for two different events and only one of them belongs to the transfer.
    #
    # Gilead again: "a 202 million tax benefit recorded in 2018 related to
    # settlement of tax examinations, offset by a 588 MILLION deferred tax
    # charge in 2018 resulting from A TRANSFER OF ACQUIRED INTANGIBLE ASSETS
    # from a foreign subsidiary to the United States." Both figures sit beside
    # effect language; only 588 million sits beside the transfer, and 588
    # million is the answer key. Gartner's "28.3 million and 38.1 million,
    # respectively, related to INTERCOMPANY SALES OF CERTAIN INTELLECTUAL
    # PROPERTY" resolves the same way, to the 38.1 million the key wants.
    in_anchor = [(s, v, t) for s, v, t in spans if s < anchor_len]
    best_anchored = best_any = None
    for start, v, txt in spans:
        if best_any is None or v > best_any[0]:
            best_any = (v, txt)
        near = min((abs(start - c) for c in cues), default=None)
        if near is not None and near <= 160:
            if best_anchored is None or near < best_anchored[2]:
                best_anchored = (v, txt, near)
    if in_anchor:
        cued_in_anchor = [(s, v, t) for s, v, t in in_anchor
                          if any(abs(s - c) <= 160 for c in cues)]
        pool = cued_in_anchor or in_anchor
        s, v, t = min(pool, key=lambda p: abs(p[0] - anchor_pos))
        best = (v, t, "anchor_sentence_nearest_transfer_phrase"
                if cued_in_anchor else "anchor_sentence_no_effect_cue")
    elif best_anchored:
        best = (best_anchored[0], best_anchored[1], "anchored_to_effect_language")
    elif best_any:
        best = (best_any[0], best_any[1], "largest_in_candidate")
    else:
        best = (None, "", "")
    # A magnitude word with no figure in front of it is a number the CORPUS
    # removed, not one the firm did not state. 12% of them, 46% of filings.
    stripped = sum(1 for m in MAGNITUDE.finditer(text)
                   if not any(s <= m.start() < s + len(t) + 2
                              for s, _v, t in spans))
    return all_vals, best, stripped


def periods_in(text: str, anchor_sentence: str):
    """Every period phrase, and a primary preferring the anchor sentence."""
    found = []
    for pat, kind in PERIOD_PATS:
        for m in pat.finditer(text):
            if kind == "period_ended":
                mon, day, yr = m.group(1).lower(), int(m.group(2)), int(m.group(3))
                found.append(dict(kind=kind, text=m.group(0), pos=m.start(),
                                  fiscal_year=None, quarter=None,
                                  cal=(yr, _MONTHNUM[mon], day)))
            elif kind == "quarter":
                q = {"first": 1, "second": 2, "third": 3, "fourth": 4}[m.group(1).lower()]
                found.append(dict(kind="quarter", text=m.group(0), pos=m.start(),
                                  fiscal_year=int(m.group(2)), quarter=q, cal=None))
            elif kind == "quarter_q":
                found.append(dict(kind="quarter", text=m.group(0), pos=m.start(),
                                  fiscal_year=int(m.group(2)),
                                  quarter=int(m.group(1)[1]), cal=None))
            elif kind == "month":
                mon, yr = m.group(1).lower(), int(m.group(2))
                found.append(dict(kind="month", text=m.group(0), pos=m.start(),
                                  fiscal_year=None, quarter=None,
                                  cal=(yr, _MONTHNUM[mon], 0)))
            else:
                found.append(dict(kind="fiscal_year", text=m.group(0), pos=m.start(),
                                  fiscal_year=int(m.group(1)), quarter=None, cal=None))
    # de-duplicate overlapping matches, keeping the most specific
    found.sort(key=lambda d: (d["pos"], PERIOD_PATS_ORDER[d["kind"]]))
    kept, taken = [], []
    for f in found:
        if any(abs(f["pos"] - p) < 4 for p in taken):
            continue
        taken.append(f["pos"])
        kept.append(f)
    primary = None
    if anchor_sentence:
        in_anchor = [f for f in kept if f["text"].lower() in anchor_sentence.lower()]
        if in_anchor:
            primary = sorted(in_anchor,
                             key=lambda d: PERIOD_PATS_ORDER[d["kind"]])[0]
    if primary is None and kept:
        primary = sorted(kept, key=lambda d: (PERIOD_PATS_ORDER[d["kind"]], d["pos"]))[0]
    return kept, primary


PERIOD_PATS_ORDER = {"period_ended": 0, "quarter": 1, "month": 2, "fiscal_year": 3}


# The preposition immediately in front of a country name is the cheapest and
# most reliable destination signal there is, and the cue list did not have it.
# Gilead: "a transfer of acquired intangible assets from a foreign subsidiary TO
# THE UNITED STATES" -- no phrase in DEST_CUE fires, and the destination is
# stated as plainly as it can be.
#
# The preposition is RECORDED rather than collapsed, because "to Ireland" and
# "from Ireland" are opposite facts and goal 2 is a question about direction.
# "from" is a source, never a destination, and is labelled as such.
# The determiner slot has to admit more than "the". Adobe's FY2020 10-K says
# "intra-entity transfers of certain IP rights TO OUR IRISH SUBSIDIARY" -- a
# destination stated as plainly as Gilead's -- and the old pattern, which
# allowed only "to the X", missed it and filed Adobe under "no destination".
# Same for "to its Irish subsidiary", "to a foreign subsidiary", "to one of its
# subsidiaries in Switzerland". A possessive or article between the preposition
# and the place name changes nothing about whether a place was named.
PREP_BEFORE = re.compile(
    r"\b(to|into|in|within|from|out\s+of)\s+"
    r"(?:(?:the|our|its|their|a|an|one\s+of\s+(?:its|our|the))\s+)?"
    r"(?:wholly[-\s]owned\s+|foreign\s+|certain\s+|various\s+)*"
    r"(?:subsidiar\w+\s+in\s+|affiliates?\s+in\s+|entit\w+\s+in\s+)?$", re.I)
# "to" and "into" point somewhere. "in" does NOT, on its own: a 10-K says "in
# the United States" on nearly every page, and reading that as a destination was
# producing false US hits out of risk factors, cash-flow statements and the
# stripped tax footnote. "in" counts only when a DEST_CUE is also present
# ("realized in Ireland"), which is how Salesforce's Ireland is reached.
_DEST_PREPS = {"to", "into"}
_WEAK_PREPS = {"in", "within"}
# A country name used as an ADJECTIVE is not a place the IP went, and this was
# the whole of the remaining false-positive rate on "into the United States":
#
#   REGN  "positively impacted, compared TO THE U.S. FEDERAL STATUTORY RATE,
#          primarily by the sale of non-inventory related assets BETWEEN
#          FOREIGN SUBSIDIARIES"          <- the transfer is explicitly NOT to the US
#   BSX   "increased current tax expense related TO THE U.S. TAXATION of..."
#   BF.B  "reduction to the provisional repatriation U.S. TAX CHARGE"
#
# Each has "to ... U.S." in it and none of them states a destination. What
# separates them from Gilead's "from a foreign subsidiary to the United States"
# is the word after the country: a tax noun, not a full stop.
#
# The abbreviation matters here: "U.S." is matched without its closing period
# (the word boundary falls before it), so the guard has to step over that period
# before looking at the next word, or "U.S. federal statutory rate" reads as a
# destination.
ADJECTIVAL_AFTER = re.compile(
    r"\.?\s*(federal|statutory|state|tax|taxes|taxation|income|GAAP|dollars?"
    r"|generally|treasury|government|laws?|holders|shareholders|persons?"
    r"|markets?|customers|sales|revenues?|operations|business(?:es)?|domestic"
    r"|securities|economy|inflation|gross|source[ds]?|border)\b", re.I)


def destinations_in(text: str, anchor_len: int = 0, anchor_pos: int = 0):
    """Jurisdictions, how each was reached, and how far it sits from the anchor.

    DISTANCE IS THE TEST THAT WORKS ON A STRIPPED TABLE. Two of the remaining
    false "United States" destinations came from deferred-tax and rate-
    reconciliation tables (DTSI, ZNGA) that Loughran-McDonald left behind as one
    long run of line-item labels. A digit-density test does not catch those,
    because the digits are exactly what the corpus removed -- the table is
    invisible as a table. But the anchor phrase and the country name end up
    hundreds of characters apart in the blob, where in a real disclosure they
    are in the same clause:

      GILD  "...transfer of acquired intangible assets from a foreign
             subsidiary to the United States"                       ~55 chars
      MSFT  "...transferred certain intangible properties from our Puerto Rico
             subsidiary to the U.S."                                ~60 chars
    """
    cued, plain, prepped = [], [], []
    detail = []
    in_anchor = set()
    dist = {}

    def look(j, m):
        before = text[max(0, m.start() - 90):m.start()]
        prep_m = PREP_BEFORE.search(before)
        prep = (prep_m.group(1).lower().replace(" ", "") if prep_m else "")
        if ADJECTIVAL_AFTER.match(text, m.end()):
            plain.append(j)
            detail.append((j, "adjectival"))
            return "plain"
        if prep in _DEST_PREPS or DEST_CUE.search(before):
            how = f"prep:{prep}" if prep in _DEST_PREPS else "cued"
            (prepped if prep in _DEST_PREPS else cued).append(j)
            detail.append((j, how))
            if m.start() < anchor_len:
                in_anchor.add(j)
            d = abs(m.start() - anchor_pos)
            dist[j] = min(dist.get(j, 10 ** 9), d)
            return "prep" if prep in _DEST_PREPS else "cued"
        plain.append(j)
        detail.append((j, f"prep:{prep}" if prep else "mentioned_only"))
        return "plain"

    for j in JURISDICTIONS:
        for m in re.finditer(rf"\b{re.escape(j)}\b", text, re.I):
            look(j, m)
    us_kind = ""
    for m in US_CUED_ONLY.finditer(text):
        if re.match(r"United\s+States", text[m.start():], re.I):
            continue          # already counted through JURISDICTIONS
        k = look("United States", m)
        us_kind = k if k != "plain" else us_kind
    dest, basis = ("", "")
    if prepped:
        dest, basis = prepped[0], "prep_to"
    elif cued:
        dest, basis = cued[0], "cued"
    elif plain:
        dest, basis = plain[0], "mentioned_only"
    seen, allj = set(), []
    for j, how in detail:
        tag = f"{j}({how})"
        if tag not in seen:
            seen.add(tag)
            allj.append(tag)
    us = any(j == "United States" and how in ("prep:to", "prep:into", "cued")
             for j, how in detail)
    return (dest, basis, allj, us, ("United States" in in_anchor), bool(in_anchor),
            dist.get("United States", ""), dist.get(dest, "") if dest else "")


def sign_of(text: str):
    nb, nc = len(BENEFIT_LANG.findall(text)), len(COST_LANG.findall(text))
    if nb and nc:
        direction = "mixed"
    elif nb:
        direction = "benefit"
    elif nc:
        direction = "cost"
    else:
        direction = "none"
    dta, dtl = bool(DTA_LANG.search(text)), bool(DTL_LANG.search(text))
    which = "both" if dta and dtl else "DTA" if dta else "DTL" if dtl else "none"
    return direction, nb, nc, which


# A cheap literal gate in front of the expensive anchor. Every alternative in
# TRANSFER_ANCHOR contains one of these substrings, so a filing holding none of
# them cannot match and is skipped before the big regex or the sentence splitter
# ever touches it. This is a speed change only -- if a pattern is added to the
# anchor, a literal for it MUST be added here or it will silently never fire.
_GATE_FIXED = ("2016-16", "2016 -16", "2016- 16", "2016 - 16",
               "intra-entity", "intra entity", "intraentity",
               "intra-group", "intra group", "intragroup",
               "intercompany", "inter company",
               "sold intellectual",
               "non-inventory", "non inventory", "noninventory",
               "assets between")
# The transfer-of-IP family cannot be enumerated any more, because the modifier
# slot is now open ("transfer of ACQUIRED intangible assets"). So the gate takes
# the coarse conjunction instead: a transfer word AND an IP word, anywhere in
# the filing. It over-admits heavily -- most 10-Ks contain both -- and that is
# the correct direction for a gate whose only job is to be a superset. Its
# behaviour is checked against the anchor on a random sample in
# `gate_leak_check`, and a leak there is a bug, not a tuning question.
_GATE_MOVE = ("transfer", "transferr", "sale of", "sales of", "sold",
              "consolidat", "centraliz", "centralis")
_GATE_IP = ("intangible", "intellectual", " ip")   # " ip" also admits " ipo" etc: harmless


def gate(low: str) -> bool:
    if any(k in low for k in _GATE_FIXED):
        return True
    return (any(k in low for k in _GATE_MOVE)
            and any(k in low for k in _GATE_IP))


# ---- false-positive FAMILIES: flagged, never dropped ---------------------------
# Phase B's precision sample (3,001 non-DI filings, 136 flagged, every one read) found
# two families the anchor matches that are not intra-entity transfers of assets at all.
# They are FLAGGED rather than removed, so the raw candidate file still carries every
# match with provenance (A3) and the population filter decides. Both only fire when the
# sentence carries no tax-consequence language, so a real ASU 2016-16 sentence that
# happens to mention common control -- Baxter's "accelerates the recognition of income
# tax consequences for asset transfers between entities under common control" -- is
# not flagged.
_TAXY = re.compile(r"income\s+tax|tax\s+(?:consequence|effect|benefit|expense|charge|basis)"
                   r"|deferred\s+tax|2016\s*-?\s*16|intellectual\s+propert|intangible", re.I)
_COMMON_CONTROL = re.compile(r"under\s+common\s+control", re.I)
_ELIM_POLICY = re.compile(r"intra[-\s]?entity\s+transactions?", re.I)


def fp_family(sentence: str, anchor_text: str) -> str:
    """'' for a clean candidate, else the name of the false-positive family.

    common_control   ASC 805-50 transfers of net assets between entities under common
                     control -- Kinder Morgan, American Airlines, Martin Midstream,
                     PBF Logistics, Aedan, DISH. Martin Midstream scored 18 and survived
                     every score threshold, which is why this is a flag and not a score.
    elimination      "intra-entity transactions" as consolidation or equity-method
                     policy -- Cintas, EOS, Milestone, EchoStar.
    """
    if _TAXY.search(sentence):
        return ""
    if _COMMON_CONTROL.search(sentence):
        return "common_control"
    if _ELIM_POLICY.search(anchor_text):
        return "elimination"
    return ""


# ---- windowed anchor search: same matches, a fraction of the work ----------------
# Profiled 21 September: the anchor regex was 83-85% of run time. Python tries each of
# its ~25 alternatives at every character of a 200-page filing, and the full sweep is
# ~240,000 filings on a 2-core machine that cannot keep a process alive between calls.
#
# Every alternative in TRANSFER_ANCHOR contains at least one of the literals below, so
# a match can only exist within reach of one. The regex is therefore run only inside
# windows of +/-WIN characters around each literal, merged where they overlap. Using
# finditer(flat, a, b) rather than slicing keeps word boundaries correct at the window
# edge. WIN is set well above the longest possible match.
#
# If an alternative is ever added to TRANSFER_ANCHOR, its literal MUST be added here,
# exactly as with the gate -- and `leak_check` must be re-run. A leak is a bug.
_NEED_LOWER = ("2016-16", "2016 -16", "2016- 16", "2016 - 16", "2016 16", "201616",
               "intra", "intercompany", "inter company",
               "intellectual", "intangible",
               "non-inventory", "non inventory", "noninventory",
               "asset between", "assets between")
_NEED_IP = re.compile(r"\bIP\b")
WIN = 400


def anchor_hits(flat: str, full: bool = False):
    """Every anchor match in `flat`, in order. `full=True` scans everything."""
    if full:
        return list(TRANSFER_ANCHOR.finditer(flat))
    low = flat.lower()
    pos = []
    for lit in _NEED_LOWER:
        i = low.find(lit)
        while i != -1:
            pos.append(i)
            i = low.find(lit, i + 1)
    pos.extend(m.start() for m in _NEED_IP.finditer(flat))
    if not pos:
        return []
    pos.sort()
    spans = []
    for p in pos:
        a, b = max(0, p - WIN), min(len(flat), p + WIN)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    found = {}
    for a, b in spans:
        for m in TRANSFER_ANCHOR.finditer(flat, a, b):
            found.setdefault(m.start(), m)
    return [found[k] for k in sorted(found)]


_FULL_SCAN = False   # set True only for leak checks


def candidates_for(flat: str):
    """One candidate per anchor SENTENCE. Nothing is dropped."""
    low = flat.lower()
    if not gate(low):
        return []
    hits = anchor_hits(flat, full=_FULL_SCAN)
    if not hits:
        return []
    spans = split_sentences(flat)
    starts = [s for s, _ in spans]
    out, seen = [], set()
    for hit in hits:
        i = bisect.bisect_right(starts, hit.start()) - 1
        if i < 0:
            continue
        if i in seen:
            continue
        seen.add(i)
        a_s, a_e = spans[i]
        anchor_sentence = flat[a_s:a_e]
        # Defect 3: carry the following sentences, for the retained-earnings
        # effect. Defect 2: stop before any sentence naming another standard.
        lo, hi = i, i
        for j in (i - 1,):
            if j >= 0 and not OTHER_STD.search(flat[spans[j][0]:spans[j][1]]):
                lo = j
        for j in (i + 1, i + 2):
            if j < len(spans) and not OTHER_STD.search(flat[spans[j][0]:spans[j][1]]):
                hi = j
            else:
                break
        # DESTINATION GETS A LONGER REACH THAN THE AMOUNT, and Salesforce is why.
        # Its disclosure runs: "In the second quarter of fiscal 2021, we changed our
        # international corporate structure, which included the transfer of certain
        # intangible property between foreign affiliates resulting in a net tax
        # benefit of $2.0 billion..." and then, several sentences later, "We believe
        # that it is more likely than not the deferred tax assets will be realized in
        # IRELAND." Two sentences forward -- the right reach for an amount -- never
        # gets there, and Salesforce was filed under "no destination" while naming one.
        #
        # The amount stays tight to the anchor sentence, because a figure further off
        # belongs to something else. A destination does not work that way: it is
        # stated once, wherever the paragraph puts it. So this reaches six sentences,
        # still stopping at the next standard, and every destination carries its
        # distance from the transfer phrase so a far one can be discounted.
        dhi = i
        for j in range(i + 1, min(i + 7, len(spans))):
            if OTHER_STD.search(flat[spans[j][0]:spans[j][1]]):
                break
            dhi = j
        out.append(dict(idx=i, offset=hit.start(), anchor_text=hit.group(0),
                        fp_family=fp_family(anchor_sentence, hit.group(0)),
                        anchor_sentence=anchor_sentence,
                        dest_text=flat[a_s:spans[dhi][1]],
                        # WHAT IS READ FOR AN AMOUNT: the anchor sentence and
                        # what FOLLOWS it. Not what precedes it.
                        #
                        # Gartner's FY2020 10-K is the case. The anchor sentence
                        # states the answer outright -- "the Company recorded a
                        # net tax benefit of approximately 28.3 million and 38.1
                        # million, respectively, related to intercompany sales
                        # of certain intellectual property" -- and the sentence
                        # BEFORE it is the quarterly-results table, which
                        # Loughran-McDonald left behind as a wall of digits with
                        # no sentence break in it: "First Second Third Fourth
                        # Revenues 1,018,891 973,135 ...". Including it put
                        # 30.8 million from that table in front of the 38.1
                        # million the disclosure actually asserts.
                        #
                        # The preceding sentence is kept as context in its own
                        # column, where it can be read but cannot be mistaken
                        # for the disclosure.
                        effect_text=flat[a_s:spans[hi][1]],
                        anchor_in_eff=hit.start() - a_s,
                        prev_sentence=(flat[spans[lo][0]:a_s] if lo != i else ""),
                        text=flat[spans[lo][0]:spans[hi][1]]))
    return out


# Table residue: Loughran-McDonald removes tables, but not all of them, and what
# survives arrives as one enormous "sentence" of digits with no verb in it. A
# figure read out of that is a table cell, not a disclosure, so it is flagged
# rather than trusted.
def looks_like_table(text: str) -> bool:
    """Table residue, including tables whose figures the corpus removed.

    Digit density catches a surviving table (REGN's five-year Selected Financial
    Data: 31% digits). It cannot catch a STRIPPED one, because the digits are
    exactly what Loughran-McDonald took out -- REGN's rate reconciliation reads
    "Foreign State () Foreign () Total current tax expense Deferred: Federal ()
    State () () () Foreign ()" at 1.4% digits and is plainly not a sentence.

    What survives stripping is the parentheses that held the negatives, and the
    run of column labels with no verb. Either signal is enough.
    """
    n = len(text)
    if n < 250:
        return False
    digits = sum(c.isdigit() for c in text)
    if n >= 400 and digits / n > 0.14:
        return True
    # a stripped table: many empty parens, few sentence stops
    parens = text.count(")")
    stops = text.count(". ")
    if parens >= 5 and parens > stops * 2:
        return True
    return text.count("( )") + text.count("()") >= 3


# ------------------------------------------------------------------ main ----

def load_population(which: str):
    """cik -> {ticker, hand_transfer_year, datadate}."""
    pop = {}
    if DI_FIRMS.exists() and which in ("di", "all"):
        with DI_FIRMS.open() as fh:
            rd = csv.DictReader(fh, delimiter="\t")
            for r in rd:
                cik = (r.get("cik") or "").strip().lstrip("0")
                if cik:
                    pop[cik] = {"ticker": (r.get("tic") or "").strip(),
                                "datadate": (r.get("datadate") or "").strip(),
                                "hand_transfer_year": ""}
    if GOLD_JSON.exists():
        for g in json.loads(GOLD_JSON.read_text()):
            cik = (g.get("cik") or "").lstrip("0")
            if not cik:
                continue
            rec = pop.setdefault(cik, {"ticker": g.get("ticker", ""),
                                       "datadate": "", "hand_transfer_year": ""})
            rec["hand_transfer_year"] = g.get("hand_transfer_year") or ""
            rec.setdefault("ticker", g.get("ticker", ""))
            if not rec.get("ticker"):
                rec["ticker"] = g.get("ticker", "")
    return pop


def make_fye_for(fye, pop):
    """The fiscal-year-end lookup, as a closure over one fiscal calendar."""
    def fye_for(cik, year):
        """The firm's fiscal year end for THAT fiscal year, and where it came from."""
        if year is None:
            return None, ""
        tbl = fye.get(cik) or {}
        if year in tbl:
            return tbl[year], "10-K header, same year"
        # nearest 10-K year end, month/day carried across -- the year end moves,
        # so the nearest year is the best available statement of it
        if tbl:
            near = min(tbl, key=lambda y: abs(y - year))
            if abs(near - year) <= 3:
                d = tbl[near]
                last = calendar.monthrange(year, d.month)[1]
                return dt.date(year, d.month, min(d.day, last)), \
                    f"10-K header, {near} year end carried"
        dd = (pop.get(cik) or {}).get("datadate_date")
        if dd:
            last = calendar.monthrange(year, dd.month)[1]
            return dt.date(year, dd.month, min(dd.day, last)), \
                "di_firm_years datadate (single year)"
        return None, ""

    return fye_for


FIELDS = ["ticker", "cik", "company", "form", "filing_date",
          "period_of_report", "fiscal_year_end_header", "file",
          "candidate_rank", "n_candidates", "score",
          "anchor_text", "anchor_offset", "fp_family",
          "disclosure_type", "date_usable_as_transfer_date",
          "period_text", "period_kind", "period_fiscal_year",
          "period_cal_start", "period_cal_end", "period_cal_year",
          "fye_used", "fye_source", "periods_all",
          "amount_best", "amount_best_text", "amount_basis",
          "amounts_all", "n_amounts", "n_stripped_magnitudes",
          "effect_direction", "n_benefit_cues", "n_cost_cues", "dta_dtl",
          "destination", "destination_basis", "destinations_all",
          "destination_is_us", "destination_excludes_us",
          "destination_unnamed_form", "us_in_anchor_sentence",
          "us_chars_from_transfer_phrase", "dest_chars_from_transfer_phrase",
          "destination_in_anchor_sentence", "destinations_wide_window",
          "accounts_affected", "hand_transfer_year",
          "anchor_sentence_chars", "table_residue",
          "anchor_sentence", "prev_sentence", "candidate_text"]


def candidate_rows(f, fye_for, g):
    """Every output row for one filing: one per candidate, all Phase A fields.

    Pulled out of main() on 21 September so the Phase A run and the full-population
    sweep execute the SAME code. `f` is dict(cik, name, hdr, cands, form); `fye_for`
    comes from make_fye_for(); `g` is the firm's population record, or {} for a firm
    outside the Double Irish set.
    """
    cik, hdr = f["cik"], f["hdr"]
    date_m = re.search(r"(\d{8})_", f["name"])
    scored = []
    for c in f["cands"]:
        scored.append((score_candidate(c["text"]), c))
    scored.sort(key=lambda t: (-t[0], t[1]["offset"]))
    for rank, (score, c) in enumerate(scored, start=1):
        text = c["text"]            # full window, for the reader
        eff = c["effect_text"]      # anchor sentence onward, for reading
        all_vals, best, stripped = amounts_in(
            eff, anchor_len=len(c["anchor_sentence"]),
            anchor_pos=c["anchor_in_eff"])
        kept, primary = periods_in(eff, c["anchor_sentence"])
        # TWO destination reads, kept apart on purpose.
        #
        # The one that counts is over the effect window -- the anchor
        # sentence and the sentences that follow it, which is where
        # Salesforce's "realized in Ireland" and Gilead's "to the
        # United States" both sit. Widening it to the whole candidate
        # produced United States hits out of risk factors, cash-flow
        # statements and the stripped tax footnote, on filings whose
        # disclosure names no destination at all.
        #
        # The wide read is still recorded, in its own column, because
        # it is a lead worth following by hand. It is not evidence.
        (dest, dbasis, dall, us_cued, us_same_sent, dest_same_sent,
         us_dist, dest_dist) = destinations_in(
             c["dest_text"], anchor_len=len(c["anchor_sentence"]),
             anchor_pos=c["anchor_in_eff"])
        wide_all = destinations_in(text)[2]
        direction, nb, nc, dta_dtl = sign_of(eff)
        p_text = p_kind = ""
        p_fy = p_start = p_end = p_cal_year = None
        fye_used = fye_src = ""
        if primary:
            p_text, p_kind = primary["text"], primary["kind"]
            p_fy = primary["fiscal_year"]
            if primary["cal"]:
                y, mo, dy = primary["cal"]
                p_cal_year = y
                if dy:
                    p_start = p_end = dt.date(y, mo, dy)
                else:
                    p_start = dt.date(y, mo, 1)
                    p_end = dt.date(y, mo, calendar.monthrange(y, mo)[1])
                fye_src = "stated as a calendar date"
            else:
                fd, fye_src = fye_for(cik, p_fy)
                fye_used = fd.isoformat() if fd else ""
                p_start, p_end = fiscal_to_calendar(
                    p_kind, p_fy, primary["quarter"], fd)
                if p_end:
                    p_cal_year = p_end.year
        dtype = disclosure_type(text)
        yield {
            "ticker": g.get("ticker", ""), "cik": cik,
            "company": hdr.get("company", ""), "form": f["form"],
            "filing_date": date_m.group(1) if date_m else "",
            "period_of_report": hdr.get("period_of_report", ""),
            "fiscal_year_end_header": hdr.get("fiscal_year_end", ""),
            "file": f["name"].split("/")[-1],
            "candidate_rank": rank, "n_candidates": len(scored),
            "score": score,
            "anchor_text": c["anchor_text"], "anchor_offset": c["offset"],
            "fp_family": c.get("fp_family", ""),
            "disclosure_type": dtype,
            "date_usable_as_transfer_date": (
                "yes" if dtype == "current_period_transfer" else ""),
            "period_text": p_text, "period_kind": p_kind,
            "period_fiscal_year": p_fy or "",
            "period_cal_start": p_start.isoformat() if p_start else "",
            "period_cal_end": p_end.isoformat() if p_end else "",
            "period_cal_year": p_cal_year or "",
            "fye_used": fye_used, "fye_source": fye_src,
            "periods_all": "; ".join(k["text"] for k in kept[:8]),
            "amount_best": best[0] if best[0] is not None else "",
            "amount_best_text": best[1], "amount_basis": best[2],
            "amounts_all": "; ".join(f"{v:.0f}" for v in all_vals[:20]),
            "n_amounts": len(all_vals),
            "n_stripped_magnitudes": stripped,
            "effect_direction": direction, "n_benefit_cues": nb,
            "n_cost_cues": nc, "dta_dtl": dta_dtl,
            "destination": dest, "destination_basis": dbasis,
            "destinations_all": "; ".join(dall[:8]),
            "destination_is_us": "yes" if us_cued else "",
            "destination_excludes_us": (
                "yes" if EXCLUDES_US.search(c["anchor_sentence"]) else ""),
            "destination_unnamed_form": (
                (m.group(0)[:60] if (m := UNNAMED_DEST.search(c["anchor_sentence"]))
                 else "")),
            # The strongest form of the claim: the destination is named
            # in the SAME SENTENCE as the transfer phrase, so nothing
            # sits between the two facts.
            "us_in_anchor_sentence": "yes" if us_same_sent else "",
            "us_chars_from_transfer_phrase": us_dist,
            "dest_chars_from_transfer_phrase": dest_dist,
            "destination_in_anchor_sentence": "yes" if dest_same_sent else "",
            "destinations_wide_window": "; ".join(wide_all[:10]),
            "accounts_affected": "; ".join(
                a for a in ACCOUNTS if re.search(re.escape(a), eff, re.I)),
            "hand_transfer_year": g.get("hand_transfer_year", ""),
            "anchor_sentence_chars": len(c["anchor_sentence"]),
            "table_residue": "yes" if looks_like_table(eff) else "",
            "anchor_sentence": c["anchor_sentence"][:1500],
            "prev_sentence": c["prev_sentence"][:600],
            "candidate_text": text[:2500],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", default="di", choices=("di", "all"),
                    help="di = the Double Irish firms plus the gold set (Phase A)")
    ap.add_argument("--forms", default="10-K,10-Q")
    ap.add_argument("--only", default="", help="comma-separated tickers, for spot tests")
    ap.add_argument("--limit-filings", type=int, default=0)
    ap.add_argument("--out", default="")
    # The shell this runs in is capped at a few minutes per invocation, so the
    # corpus is worked one zip at a time and the rows appended. The fiscal
    # calendar, though, has to be global -- a firm's year end for fiscal 2021
    # may only be stated in a filing sitting in a different zip -- so it is
    # built once by --mode fye (which reads only the SEC header of each filing,
    # not the filing) and loaded by every extract chunk.
    ap.add_argument("--mode", default="extract", choices=("extract", "fye"))
    ap.add_argument("--zips", default="", help="comma-separated subset of the corpus zips")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--start", type=int, default=0,
                    help="index into this zip's filtered filing list (for chunking)")
    ap.add_argument("--count", type=int, default=0, help="how many filings this chunk")
    args = ap.parse_args()
    zips = [z.strip() for z in args.zips.split(",") if z.strip()] or ZIPS

    out_cand = Path(args.out) if args.out else OUT_CAND
    pop = load_population(args.population)
    only = {t.strip().upper() for t in args.only.split(",") if t.strip()}
    if only:
        pop = {c: r for c, r in pop.items() if (r["ticker"] or "").upper() in only}
    forms = tuple(f.strip() for f in args.forms.split(","))
    print(f"population: {len(pop)} CIKs   forms: {','.join(forms)}")

    stats = collections.Counter()
    filings = []          # one dict per filing that produced candidates
    fye = collections.defaultdict(dict)   # cik -> {calendar_year: date}

    if args.mode == "fye":
        for zp in zips:
            p = HERE / zp
            if not p.exists():
                print(f"  (missing {zp})")
                continue
            z = zipfile.ZipFile(p)
            for name in z.namelist():
                if not (name.endswith(".txt") and "_10-K_" in name):
                    continue
                mm = re.search(r"edgar_data_(\d+)_", name)
                if not mm:
                    continue
                cik = mm.group(1).lstrip("0")
                if args.population != "all" and cik not in pop:
                    continue
                with z.open(name) as fh:      # header only: no full decompress
                    head = fh.read(8000).decode("utf-8", errors="replace")
                por = header_fields(head).get("period_of_report", "")
                if len(por) == 8:
                    try:
                        d = dt.date(int(por[:4]), int(por[4:6]), int(por[6:8]))
                        fye[cik][d.year] = d
                    except ValueError:
                        pass
                stats["10-K headers read"] += 1
            z.close()
        existing = {}
        if OUT_FYE.exists() and args.append:
            for r in csv.DictReader(OUT_FYE.open()):
                existing[(r["cik"], int(r["calendar_year"]))] = r["fiscal_year_end"]
        for cik, tbl in fye.items():
            for y, d in tbl.items():
                existing[(cik, y)] = d.isoformat()
        with OUT_FYE.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["cik", "ticker", "calendar_year", "fiscal_year_end"])
            for (cik, y), d in sorted(existing.items()):
                w.writerow([cik, (pop.get(cik) or {}).get("ticker", ""), y, d])
        print(f"10-K headers read {stats['10-K headers read']:,}")
        print(f"wrote {OUT_FYE.name}  ({len(existing):,} firm-years)")
        return

    # extract mode: load the fiscal calendar built by --mode fye
    if OUT_FYE.exists():
        for r in csv.DictReader(OUT_FYE.open()):
            try:
                fye[r["cik"]][int(r["calendar_year"])] = dt.date.fromisoformat(
                    r["fiscal_year_end"])
            except (ValueError, KeyError):
                pass
        print(f"fiscal calendar loaded: "
              f"{sum(len(v) for v in fye.values()):,} firm-years")

    for zp in zips:
        p = HERE / zp
        if not p.exists():
            print(f"  (missing {zp})")
            continue
        z = zipfile.ZipFile(p)
        selected = []
        for name in z.namelist():
            if not name.endswith(".txt"):
                continue
            if not any(f"_{f}_" in name for f in forms):
                continue
            m = re.search(r"edgar_data_(\d+)_", name)
            if not m:
                continue
            cik = m.group(1).lstrip("0")
            if args.population != "all" and cik not in pop:
                continue
            selected.append((name, cik))
        selected.sort()
        lo = args.start
        hi = lo + args.count if args.count else len(selected)
        print(f"  {zp}: {len(selected):,} filings for this population; "
              f"this chunk [{lo}:{min(hi, len(selected))}]")
        for name, cik in selected[lo:hi]:
            stats["filings read"] += 1
            try:
                raw = z.read(name).decode("utf-8", errors="replace")
            except Exception:
                stats["unreadable"] += 1
                continue

            hdr = header_fields(raw)
            por = hdr.get("period_of_report", "")
            # PASS 1, done inline: the firm's own fiscal calendar, per YEAR,
            # read from the filing itself. This is what makes the conversion
            # move when the year end moves.
            if por and len(por) == 8:
                try:
                    d = dt.date(int(por[:4]), int(por[4:6]), int(por[6:8]))
                    form = next((f for f in forms if f"_{f}_" in name), "")
                    if form == "10-K":
                        fye[cik][d.year] = d
                except ValueError:
                    pass

            body = strip_header(raw)
            flat = re.sub(r"\s+", " ", body)
            cands = candidates_for(flat)
            if not cands:
                continue
            stats["filings with >=1 candidate"] += 1
            if not ASU_1616.search(flat):
                stats["  reached WITHOUT the standard being named"] += 1
            stats["candidates"] += len(cands)
            filings.append(dict(cik=cik, name=name, hdr=hdr, cands=cands,
                                form=next((f for f in forms if f"_{f}_" in name), "")))
            if args.limit_filings and len(filings) >= args.limit_filings:
                break
        z.close()
        if args.limit_filings and len(filings) >= args.limit_filings:
            break

    # datadate fallback, one year per firm, from di_firm_years_Claude.txt
    for cik, rec in pop.items():
        dd = rec.get("datadate") or ""
        m = re.match(r"(\d{1,2})([a-z]{3})(\d{4})", dd, re.I)
        if m:
            mon = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                   "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11,
                   "dec": 12}.get(m.group(2).lower())
            if mon:
                try:
                    rec["datadate_date"] = dt.date(int(m.group(3)), mon, int(m.group(1)))
                except ValueError:
                    pass

    fye_for = make_fye_for(fye, pop)

    # ------------------------------------------------------------- write --
    fields = FIELDS

    n_rows = 0
    append = args.append and out_cand.exists()
    with out_cand.open("a" if append else "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if not append:
            w.writeheader()
        for f in filings:
            for row in candidate_rows(f, fye_for, pop.get(f["cik"], {})):
                w.writerow(row)
                n_rows += 1
    # NOTE: extract mode never rewrites the fiscal calendar. It is global and
    # built once by --mode fye; a chunk writing its own would leave the map
    # holding one zip's firm-years and silently break every other chunk's dates.

    print(f"\nfilings read                     {stats['filings read']:,}")
    print(f"  with at least one candidate    {stats['filings with >=1 candidate']:,}")
    print(f"    reached without naming ASU   {stats['  reached WITHOUT the standard being named']:,}")
    print(f"  candidates emitted             {stats['candidates']:,}")
    d = max(stats["filings with >=1 candidate"], 1)
    print(f"  candidates per matched filing  {stats['candidates']/d:.1f}")
    print(f"\n{'appended to' if append else 'wrote'} {out_cand.name}  ({n_rows:,} rows this chunk)")


if __name__ == "__main__":
    main()
