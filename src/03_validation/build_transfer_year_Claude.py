#!/usr/bin/env python3
r"""Two steps, in order: fix the year, then read the deferred tax lines in that year.

Brian, 18 September, after seeing the unrestricted panel: *"yes, current isn't usable.
so the goal would be 1) Strongly identify the year in which the transfer is first
recorded (including - getting the sentence that describes the amount). In that year
only, look at the CHANGES in US/Foreign DTAs/DTLs."*

WHY THE ORDER MATTERS, AND WHAT BROKE WITHOUT IT
------------------------------------------------
Running the federal-versus-foreign test on every fiscal year a firm had any evidence
in produced 86 answers and 51 of them "US" — on a set of firms that overwhelmingly
transferred INTO Ireland. Scored against the hand-verified transferee country:

    non-US calls   25   wrong  0    (100%)
    US calls       51   wrong 30    ( 41%)

Every single error was a spurious US call. Restricted to the hand transfer year the
same rule was right 20 of 21. The reason is structural rather than statistical: the
federal deferred line moves for reasons that have nothing to do with an IP transfer —
NOL releases, valuation allowances, SAB 118 remeasurement, CARES carrybacks — so in an
arbitrary year a large federal movement means almost nothing. The foreign line is
quiet unless something international happened, which is why a dominant FOREIGN movement
survives in any year and a dominant FEDERAL one does not.

So the federal line is only interpretable inside a year the text has independently
nailed down. That is the whole design of this script: STEP 1 nails the year from the
filing's own words, STEP 2 reads the deferred tax lines there and nowhere else.

STEP 1 — WHAT COUNTS AS "STRONGLY IDENTIFIED"
----------------------------------------------
Two independent conditions, because they fail independently.

**The evidence tier** — is this a firm recording something, or text about a standard?

  1  the firm asserts a completed transfer or adoption in its own voice AND the
     disclosure carries the amount
  2  the firm asserts it, but no figure survived the corpus
  3  transfer prose without a first-person assertion, amount read from the transfer
     sentence itself — Microsoft's "we also paid 3.5 billion related to the transfer
     of intangible properties" lands here
  4  no usable prose, but an XBRL fact tagged
     AdjustmentsForNewAccountingPronouncements=AccountingStandardsUpdate201616
  5  transfer prose, nothing else

Announcement text is excluded outright. "In October 2016, the FASB issued ASU 2016-16,
which requires entities to recognize..." appears in Salesforce, Apple and Microsoft
filings with a figure attached, and taking it at face value dates every one of them to
2016 — three to five years before anything was recorded.

**The period has to come from the sentence itself.** This is what actually broke the
first cut, and it broke it silently. Regeneron's tier-1 sentence is *"Our effective tax
rate for 2018 was positively impacted ... by the sale of non-inventory related assets
between foreign subsidiaries"* — dated by the extractor to 2017, from a period phrase
somewhere else on the page. McKesson's adoption entry was dated to 2016 the same way;
Synopsys's to 2017. All three had a correct row in the same table, and taking the
earliest one took the wrong one. A year is only strongly identified when the period
phrase that dates it appears INSIDE the sentence that asserts the event.

  year_strongly_identified  =  tier in (1, 2, 3)  AND  period phrase in the sentence

RECORDED IS NOT TRANSFERRED, AND THE SCORING HAS TO SAY SO
-----------------------------------------------------------
Settled point 3 of the project: the adoption date is not the transfer date. A modified
retrospective adopter books, in one entry, the tax effect of transfers that already
happened — Apple's $2.7bn in the December 2018 quarter for a 2015 transfer. So
`first_recorded_year` and the hand sheet's transfer year are answers to different
questions, and scoring one against the other as if they were the same thing would
report a real and correct four-year gap as an error. Each row therefore carries
`record_type`, and the two kinds are scored apart:

    current_period_transfer   recorded year should EQUAL the hand year — scored
    adoption_catchup          recorded year should be AT OR AFTER it — reported as
                              a lag, never as right or wrong

FIRST RECORDED, NOT ONLY RECORDED
----------------------------------
`first_recorded_year` is the EARLIEST strongly identified year, which is what Brian
asked for. But the test is opened for EVERY strongly identified year, not only the
first, because several firms transferred more than once and the later events are real:
Microsoft's fiscal 2022 Puerto Rico-to-US transfer is a separate event from its 2019
Irish one, and Zynga's 2020 transfer back to the US is the unwinding of the transfer
the hand sheet records. A design that only ever looked at the first year would call
those firms' later transfers invisible.

STEP 2 — THE CALENDAR JOIN THAT HAS TO BE RIGHT
------------------------------------------------
The text dates an EVENT (Apple's adoption entry sits in the quarter ended 28 December
2018); the deferred tax lines are annual and dated at the firm's FISCAL YEAR END
(Apple's is 28 September 2019). Joining 2018 to 2018 reads Apple's deferred tax lines
one full year before the entry. The event date is therefore mapped to the annual period
that CONTAINS it, using the firm's own period end dates as they appear in the XBRL,
rather than any rule about which month the year ends in.

Writes: asu_v2_transfer_year_Claude.csv   (one row per firm)
        asu_v2_transfer_year_years_Claude.csv   (every qualifying year, per firm)
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

import build_identification_proof_Claude as P

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
CAND = HERE / "asu_v2_candidates_Claude.csv"
GEO = [HERE / "sec_notes_v2_Claude_GEOTAX.csv",
       HERE / "sec_notes_asu_all_Claude_GEOTAX.csv"]
ASU = [HERE / "sec_notes_v2_Claude.csv", HERE / "sec_notes_asu_all_Claude.csv"]
HAND = HERE / "Deferredtaxes_IPtransfers_DIfirms_handcollected.xlsx"
OUT_FIRM = HERE / "asu_v2_transfer_year_Claude.csv"
OUT_YEAR = HERE / "asu_v2_transfer_year_years_Claude.csv"

FED = "DeferredFederalIncomeTaxExpenseBenefit"
FOR = "DeferredForeignIncomeTaxExpenseBenefit"
FLOOR = 5e7
RATIO = 3.0
XBRL_FLOOR = 1e6

# Text that describes the standard or forecasts an effect, rather than recording one.
# Kept separate from the proof table's grading because there it only costs a grade;
# here it decides a DATE, and a wrong date is unrecoverable downstream.
ANNOUNCEMENT = re.compile(
    r"the\s+FASB\s+issued|FASB\s+issued\s+ASU|was\s+issued\s+in|this\s+(?:ASU|Update)\s+"
    r"(?:requires|is\s+effective)|requires\s+(?:an\s+)?entit\w+\s+to|will\s+be\s+effective"
    r"|is\s+effective\s+for|expects?\s+to\s+(?:record|recognize|adopt)|anticipat\w+\s+"
    r"(?:to\s+)?record|plans?\s+to\s+adopt|is\s+evaluating|are\s+(?:currently\s+)?evaluating"
    r"|will\s+adopt|prior\s+to\s+the\s+adoption|upon\s+adoption\s+of\s+the\s+new", re.I)
# ... unless the same sentence also says the firm actually did it.
DID_IT = re.compile(
    r"\b(?:we|the\s+Company|the\s+Corporation)\s+(?:adopted|completed|transferred|sold|"
    r"changed|consolidated|recorded|recognized|recognised)\b"
    r"|upon\s+adoption,?\s+(?:we|the\s+Company)"
    r"|as\s+a\s+result\s+of\s+the\s+adoption", re.I)


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def d8(s):
    s = (s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None


def diso(s):
    s = (s or "").strip()
    if len(s) < 10:
        return None
    try:
        return dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except ValueError:
        return None


# --------------------------------------------------------------------------- step 1

ADOPTION = re.compile(
    r"upon\s+adoption|(?:we|the\s+Company|the\s+Corporation)\s+(?:early\s+)?adopted"
    r"|as\s+a\s+result\s+of\s+the\s+adoption|adoption\s+of\s+(?:this|the)\s+"
    r"(?:amended\s+guidance|ASU|Update|standard)|cumulative[-\s]effect\s+adjustment"
    r"|modified[-\s]retrospective|beginning\s+balance\s+of\s+retained\s+earnings", re.I)
ISSUANCE = re.compile(r"the\s+fasb\s+issued|,?\s*the\s+fasb\b|was\s+issued|issued\s+asu", re.I)
# TCJA became law 22 December 2017 and SAB 118 gave a one-year measurement period, so
# any fiscal year ending inside this window carries federal remeasurement that has
# nothing to do with an IP transfer. It moves the FEDERAL line only, which is why the
# guard applies to US calls and not to foreign-dominant ones.
TCJA_LO, TCJA_HI = dt.date(2017, 12, 1), dt.date(2019, 6, 30)
# A US call has to be the same size as the effect the firm disclosed. The disclosed tax
# effect IS the deferred tax movement the transfer causes, so a federal line that moved
# eleven times that amount (Apple 2018: $30.9bn against a disclosed $2.7bn) did not move
# because of the transfer. Calibrated on 11 scored observations -- a mechanism, not a
# validated threshold, and the band is deliberately wide because of it.
SCALE_LO, SCALE_HI = 0.3, 5.0
# "...for the tax consequences relating to a transfer of IP that occurred in December
# 2016" — the transfer date, stated in the same sentence as the recording date. Worth
# capturing separately: it is the only place a retrospective adopter ever dates the
# underlying event, and settled point 3 says the two must never be conflated.
TRANSFER_WHEN = re.compile(
    r"(?:relating\s+to|related\s+to|resulting\s+from|that\s+(?:occurred|were\s+"
    r"(?:made|completed))|transferred)[^.]{0,90}?\b(?:in|during|on)\s+"
    r"((?:the\s+)?(?:first|second|third|fourth)?\s*(?:quarter\s+of\s+)?(?:fiscal\s+)?"
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)?\s*(?:19|20)\d{2})", re.I)
CONTINUING = re.compile(
    r"\bthe\s+amortization\b|amortization\s+of\s+(?:a\s+|the\s+)?(?:deferred\s+tax|"
    r"intangible|the\s+tax)|continue[sd]?\s+to\s+amortiz|annual\s+amortization", re.I)
_WS = re.compile(r"\s+")


def norm(s):
    return _WS.sub(" ", (s or "").lower()).strip()


def period_in_sentence(c):
    """Did the period phrase that DATES this candidate come out of the sentence?

    Regeneron, McKesson and Synopsys were each mis-dated by one to three years by a
    period phrase picked up from elsewhere on the page. Cheap to test, and it is the
    difference between a usable year and a wrong one.
    """
    pt = norm(c["period_text"])
    if not pt:
        return "no"
    s = norm(c["anchor_sentence"])
    if pt in s:
        # McKesson's sentence runs the issuance and the entry together: "In December
        # 2016, the FASB issued ... Upon adoption we recorded 152 million of deferred
        # tax assets". The period IS in the sentence and dates the wrong one of the two.
        i = s.find(pt)
        if ISSUANCE.search(s[i:i + len(pt) + 70]):
            return "no"
        # An adoption entry has two dates in one sentence and they are not
        # interchangeable. McKesson: "Upon adoption ... we recorded 152 million of
        # deferred tax assets ... relating to a transfer ... in December 2016." The
        # period phrase there is the TRANSFER date; the catch-up was booked in fiscal
        # 2019. For an adoption row the period has to sit next to the adoption verb.
        m = ADOPTION.search(s)
        if m and not (i < m.start() or abs(i - m.start()) <= 60):
            return "transfer_date_not_record_date"
        return "yes"
    # "Q1 2019" vs "the first quarter of 2019", "During fiscal 2021" vs "fiscal 2021"
    core = re.sub(r"^(in|during|the|for|as\s+of)\s+", "", pt)
    if core and core in s:
        return "yes"
    if norm(c["prev_sentence"]) and pt in norm(c["prev_sentence"]):
        return "prev_sentence"
    return "no"


SENT_PERIOD = re.compile(
    r"\b(?:in|during|for|as\s+of)\s+((?:the\s+)?(?:first|second|third|fourth)?\s*"
    r"(?:quarter\s+of\s+)?(?:fiscal\s+(?:year\s+)?)?"
    r"(?:january|february|march|april|may|june|july|august|september|october|"
    r"november|december)?\s*((?:19|20)\d{2}))"
    r"|\b((?:the\s+)?(?:year|period)s?\s+ended\s+\w+\s+\d{1,2},?\s+((?:19|20)\d{2}))"
    # "The 2018 effective tax rate included a 588 million deferred tax charge..." --
    # a very common disclosure form that names its year without any preposition
    r"|\bthe\s+(((?:19|20)\d{2}))\s+(?:effective\s+tax\s+rate|provision|income\s+tax|"
    r"tax\s+rate|income\s+taxes)",
    re.I)


def sentence_period(c):
    """Re-date a candidate from a period phrase inside its own sentence.

    Gilead's *"In 2018, we recorded a deferred tax charge of 588 million related to a
    transfer of acquired intangible assets from a foreign subsidiary to the United
    States"* was dated 2017 by a phrase elsewhere on the page. Demoting it is right;
    throwing the year away is not, because the sentence states it. This recovers one
    of only three firm-years in the whole corpus where a firm names the US as the
    destination -- the scarcest evidence in the project.
    """
    s = norm(c["anchor_sentence"])
    ad = ADOPTION.search(s)
    for m in SENT_PERIOD.finditer(s):
        g = m.groups()
        phrase = (next((x for x in (g[0], g[2], g[4]) if x), "")).strip()
        year = next((x for x in (g[1], g[3], g[5]) if x), None)
        if not year:
            continue
        if ISSUANCE.search(s[m.start():m.end() + 70]):
            continue          # "in October 2016, the FASB issued"
        if ad and not (m.start() < ad.start() or abs(m.start() - ad.start()) <= 60):
            continue          # the transfer date inside an adoption sentence
        return int(year), phrase
    return None, ""


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_QTR_END = {"first": 3, "second": 6, "third": 9, "fourth": 12}


def redated_event(rd, year):
    """Turn a re-dated phrase into (event date, fiscal-year hint).

    "fiscal 2021" names the annual period ENDING in 2021 and is passed as a hint, so a
    January or June year end is not pushed into the wrong period. Everything else is a
    calendar date and is resolved as one.
    """
    phrase = rd[1]
    if "fiscal" in phrase:
        return dt.date(year, 12, 31), year
    for name, mo in _MONTHS.items():
        if name in phrase:
            return dt.date(year, mo, 28), None
    for name, mo in _QTR_END.items():
        if name in phrase:
            return dt.date(year, mo, 28), None
    return dt.date(year, 12, 31), None


def tier_of(c):
    """Evidence tier for one candidate, and the reason. 0 = does not qualify."""
    txt = c["anchor_sentence"] or ""
    if ANNOUNCEMENT.search(txt) and not DID_IT.search(txt):
        return 0, "announcement_or_boilerplate"
    if CONTINUING.search(txt):
        # Brown-Forman's fiscal 2015 rate note reports "the amortization (15 million in
        # fiscal 2015 and 5 million in fiscal 2014) of a deferred tax benefit that
        # resulted from ... an intercompany transfer of assets on January 1, 2013".
        # That is a prior transfer still running through the rate, not a new recording,
        # and taking it at face value dates the firm five years early.
        return 5, "continuing_amortization_of_a_prior_transfer"
    sg, sb = P.grade_sentence(c)
    ag, ab = P.grade_amount(c)
    if c["table_residue"] == "yes":
        return 0, "table_residue"
    if sg == "A" and ag in ("A", "B"):
        return 1, f"asserted_event_with_amount:{ab}"
    if sg == "A":
        return 2, f"asserted_event_no_amount:{ab}"
    if sg == "B" and ag == "A" and sb == "transfer_prose_no_assertion":
        return 3, "transfer_prose_amount_in_sentence"
    if sg == "B" and sb == "transfer_prose_no_assertion":
        return 5, "transfer_prose_only"
    return 0, f"weak:{sg}/{sb}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=40)
    args = ap.parse_args()

    cands = list(csv.DictReader(CAND.open(encoding="utf-8")))
    tick_cik = {}
    for c in cands:
        if c["ticker"] and c["cik"]:
            tick_cik.setdefault(c["ticker"], c["cik"].lstrip("0"))

    # ---- qualifying candidates, bucketed firm x event calendar year
    buckets = collections.defaultdict(list)
    for c in cands:
        if not c["ticker"] or not c["period_cal_year"]:
            continue
        try:
            y = int(c["period_cal_year"])
        except ValueError:
            continue
        if not (2015 <= y <= 2024):
            continue
        t, why = tier_of(c)
        if not t:
            continue
        pis, rd = period_in_sentence(c), None
        if pis in ("no", "prev_sentence", "transfer_date_not_record_date"):
            ry, phrase = sentence_period(c)
            if ry and 2015 <= ry <= 2024:
                y, pis, rd = ry, "yes_redated_from_sentence", (ry, phrase)
        buckets[(c["ticker"], y)].append((t, why, c, pis, rd))

    # ---- XBRL ASU-member facts (tier 4 evidence, and never stripped)
    xb = collections.defaultdict(list)
    cik_tick = {v: k for k, v in tick_cik.items()}
    for p in ASU:
        if not p.exists():
            continue
        for r in csv.DictReader(p.open(encoding="utf-8")):
            if r["why"] != "asu_member":
                continue
            tic = cik_tick.get((r["cik"] or "").lstrip("0"))
            v = f(r.get("value"))
            d = d8(r.get("ddate"))
            if not tic or v is None or d is None or abs(v) < XBRL_FLOOR:
                continue
            xb[(tic, d.year)].append((abs(v), v, r["tag"], r["form"], r["filed"], d))

    # ---- annual deferred tax panel, keyed on the firm's own period end dates
    panel = collections.defaultdict(dict)        # cik -> date -> {fed, for}
    for p in GEO:
        if not p.exists():
            continue
        for r in csv.DictReader(p.open(encoding="utf-8")):
            if r["tag"] not in (FED, FOR):
                continue
            if r.get("segments") or (r.get("qtrs") or "") != "4":
                continue
            d = d8(r.get("ddate"))
            v = f(r.get("value"))
            if d is None or v is None:
                continue
            cell = panel[(r["cik"] or "").lstrip("0")].setdefault(d, {})
            fld = "fed" if r["tag"] == FED else "for"
            if fld not in cell or abs(v) > abs(cell[fld]):
                cell[fld] = v

    def annual_period(cik, event_date, fiscal_hint=None):
        """The annual period that CONTAINS the event, and the one before it."""
        ds = sorted(panel.get(cik, {}))
        if not ds:
            return None, None
        if fiscal_hint:
            same = [d for d in ds if d.year == fiscal_hint]
            if not same:
                return None, None
            cur = same[-1]
        else:
            if event_date is None:
                return None, None
            after = [d for d in ds if d >= event_date and (d - event_date).days <= 370]
            if not after:
                return None, None
            cur = after[0]
        prior = [d for d in ds if 300 <= (cur - d).days <= 430]
        return cur, (prior[-1] if prior else None)

    # ---- hand sheet
    hd = pd.read_excel(HAND, sheet_name="Sheet1").dropna(subset=["Ticker"])
    hand = {}
    for _, r in hd.iterrows():
        t = str(r["Ticker"]).strip()
        y = r.get("Transfer Year (based on DTA/DTL beneift)")
        try:
            y = int(y)
        except (TypeError, ValueError):
            y = None
        hand[t] = (y, str(r.get("Transferee Country", "") or "").strip())

    NON_US_RE = (r"ireland|irish|malta|bermuda|cayman|switzerland|singapore|netherlands"
                 r"|luxembourg|puerto rico|israel|hong kong|united kingdom")

    def hand_class(c):
        c = (c or "").lower()
        if not c or c in ("nan", "tbd") or "n/a" in c:
            return ""
        us = bool(re.search(r"\bu\.?s\.?a?\b|united states", c))
        nu = bool(re.search(NON_US_RE, c))
        return "both" if (us and nu) else "US" if us else "non-US" if nu else "other"

    # ---- assemble
    year_rows = []
    firms = sorted({t for t, _ in buckets} | {t for t, _ in xb})
    for tic in firms:
        cik = tick_cik.get(tic, "")
        years = sorted({y for (t, y) in buckets if t == tic}
                       | {y for (t, y) in xb if t == tic})
        for y in years:
            got = buckets.get((tic, y), [])
            tags = sorted(xb.get((tic, y), []), reverse=True)
            # a re-dated year is as good as a natively-dated one: both came out of the
            # sentence, and every candidate in this bucket already agrees on the year,
            # so within it the EVIDENCE TIER is what should decide
            PIS = {"yes": 0, "yes_redated_from_sentence": 0, "prev_sentence": 1,
                   "transfer_date_not_record_date": 2, "no": 3}
            rd = None
            if got:
                # a candidate whose period phrase is in its own sentence dates the year;
                # one whose period came from elsewhere on the page does not
                best = min(got, key=lambda g: (PIS[g[3]], g[0], -float(g[2]["score"] or 0)))
                tier, why, c, pis, rd = best
                # the amount, and the sentence that carries it, may sit on a different
                # candidate in the same year than the best sentence does
                withamt = [g for g in got if g[2]["amount_best"]
                           and P.grade_amount(g[2])[0] in ("A", "B")]
                amt_c = (min(withamt, key=lambda g: (P.RANK[P.grade_amount(g[2])[0]],
                                                     PIS[g[3]], g[0]))[2]
                         if withamt else None)
                if amt_c is None and c["amount_best"]:
                    amt_c = c
            else:
                tier, why, c, amt_c, pis = (4, "xbrl_tag_only", None, None, "no")
            if got and tier > 3 and tags:
                tier, why = 4, "xbrl_tag_only"
            rec_type = ("adoption_catchup" if c and ADOPTION.search(c["anchor_sentence"] or "")
                        else "current_period_transfer" if c else "xbrl_only")
            # the transfer date, where the sentence gives one alongside the record date
            tds = ""
            if c:
                m = TRANSFER_WHEN.search(c["anchor_sentence"] or "")
                if m:
                    tds = (m.group(1) or "").strip()

            if rd:
                # re-dated from the sentence: "fiscal 2021" names the annual period
                # ending in 2021, a bare "in April 2020" names a calendar date
                ev, fiscal_hint = redated_event(rd, y)
            else:
                ev = (diso(c["period_cal_end"]) if c else None) or (
                    tags[0][5] if tags else dt.date(y, 12, 31))
                fiscal_hint = None
            cur_d, prior_d = annual_period(cik, ev, fiscal_hint)
            cur = panel.get(cik, {}).get(cur_d, {}) if cur_d else {}
            pri = panel.get(cik, {}).get(prior_d, {}) if prior_d else {}
            fed, forn = cur.get("fed"), cur.get("for")
            pf, pfo = pri.get("fed"), pri.get("for")
            dfed = abs(fed - pf) if None not in (fed, pf) else None
            dfor = abs(forn - pfo) if None not in (forn, pfo) else None
            if dfed is None or dfor is None:
                raw, basis = "", "no_baseline"
            elif max(dfed, dfor) < FLOOR:
                raw, basis = "", f"below_{int(FLOOR/1e6)}m_floor"
            elif dfor >= RATIO * max(dfed, 1.0):
                raw, basis = "non-US", f"foreign {dfor/max(dfed,1.0):.1f}x"
            elif dfed >= RATIO * max(dfor, 1.0):
                raw, basis = "US", f"federal {dfed/max(dfor,1.0):.1f}x"
            else:
                raw, basis = "", f"balanced {dfor/max(dfed,1.0):.1f}x"

            year_rows.append({
                "ticker": tic, "cik": cik, "event_year": y,
                "evidence_tier": tier, "evidence_basis": why,
                "period_in_sentence": pis, "record_type": rec_type,
                "transfer_date_stated_in_sentence": tds,
                "event_date_used": ev.isoformat() if ev else "",
                "annual_period_end": cur_d.isoformat() if cur_d else "",
                "prior_period_end": prior_d.isoformat() if prior_d else "",
                "period_text": c["period_text"] if c else "",
                "period_redated_to": rd[1] if rd else "",
                "form": c["form"] if c else (tags[0][3] if tags else ""),
                "filed": c["filing_date"] if c else (tags[0][4] if tags else ""),
                "THE_SENTENCE": (c["anchor_sentence"][:600] if c else ""),
                "amount": amt_c["amount_best"] if amt_c else "",
                "amount_grade": P.grade_amount(amt_c)[0] if amt_c else "",
                "amount_direction": amt_c["effect_direction"] if amt_c else "",
                "amount_dta_dtl": amt_c["dta_dtl"] if amt_c else "",
                "THE_AMOUNT_SENTENCE": (amt_c["anchor_sentence"][:600] if amt_c else ""),
                "amount_form": amt_c["form"] if amt_c else "",
                "amount_filed": amt_c["filing_date"] if amt_c else "",
                "xbrl_facts": len(tags),
                "xbrl_largest_amount": tags[0][1] if tags else "",
                "us_verdict_text": P.us_verdict(c)[0] if c else "",
                "us_evidence_text": P.us_verdict(c)[1] if c else "",
                "deferred_federal": fed if fed is not None else "",
                "deferred_foreign": forn if forn is not None else "",
                "delta_federal": dfed if dfed is not None else "",
                "delta_foreign": dfor if dfor is not None else "",
                "dtadtl_raw": raw, "dtadtl_basis": basis,
                "tcja_window": "yes" if any(
                    d and TCJA_LO <= d <= TCJA_HI for d in (cur_d, prior_d)) else "",
                "n_candidates": len(got),
            })

    # ---- THE CONSTRAINT: a call is only reported where the year is strongly identified
    for r in year_rows:
        strong = (r["evidence_tier"] in (1, 2, 3)
                  and r["period_in_sentence"] in ("yes", "yes_redated_from_sentence"))
        r["year_is_strongly_identified"] = "yes" if strong else ""
        a, dfed = f(r["amount"]), f(r["delta_federal"])
        scale = abs(dfed / a) if (a and dfed) else None
        r["federal_move_over_disclosed_amount"] = round(scale, 2) if scale else ""
        r["dtadtl_confidence"] = ""
        if not strong:
            if r["dtadtl_raw"] == "non-US":
                r["dtadtl_call"] = "non-US"
                r["dtadtl_confidence"] = "medium: year not strongly identified"
                r["dtadtl_suppressed_reason"] = ""
            else:
                r["dtadtl_call"] = ""
                r["dtadtl_suppressed_reason"] = (
                    f"suppressed ({r['dtadtl_raw']}): year not strongly identified"
                    if r["dtadtl_raw"] else "")
        elif r["dtadtl_raw"] == "US" and (scale is None or not (SCALE_LO <= scale <= SCALE_HI)):
            r["dtadtl_call"] = ""
            r["dtadtl_suppressed_reason"] = (
                "suppressed (US): no amount to scale against" if scale is None else
                f"suppressed (US): federal line moved {scale:.1f}x the disclosed effect")
        elif strong:
            r["dtadtl_call"] = r["dtadtl_raw"]
            r["dtadtl_suppressed_reason"] = ""
            r["dtadtl_confidence"] = ("medium: TCJA/SAB 118 window" if r["tcja_window"]
                                      else "high")
        tv = r["us_verdict_text"]
        r["destination"] = ("US" if tv == "yes" else "non-US" if tv == "no"
                            else r["dtadtl_call"] or ("unnamed" if tv == "unnamed" else ""))
        r["destination_source"] = ("10-K text" if tv in ("yes", "no")
                                   else "deferred tax lines" if r["dtadtl_call"]
                                   else "text says unnamed" if tv == "unnamed" else "none")

    # ---- one row per firm
    byfirm = collections.defaultdict(list)
    for r in year_rows:
        byfirm[r["ticker"]].append(r)
    firm_rows = []
    for tic, rs in sorted(byfirm.items()):
        st = sorted((r for r in rs if r["year_is_strongly_identified"]),
                    key=lambda r: r["event_year"])
        any_q = sorted(rs, key=lambda r: (r["evidence_tier"], r["event_year"]))
        first = st[0] if st else None
        hy, hc = hand.get(tic, (None, ""))
        fr = first["event_year"] if first else ""
        yrs = {r["event_year"] for r in rs}
        firm_rows.append({
            "ticker": tic, "cik": tick_cik.get(tic, ""),
            "first_recorded_year": fr,
            "first_recorded_type": first["record_type"] if first else "",
            "first_recorded_tier": first["evidence_tier"] if first else "",
            "best_available_year": fr or (any_q[0]["event_year"] if any_q else ""),
            "strongly_identified_years": "; ".join(str(r["event_year"]) for r in st),
            "all_qualifying_years": "; ".join(
                f"{r['event_year']}(T{r['evidence_tier']})" for r in
                sorted(rs, key=lambda r: r["event_year"])),
            "hand_transfer_year": hy or "",
            "hand_year_in_strong_years": ("" if not hy else
                                          "yes" if hy in {r["event_year"] for r in st}
                                          else "no"),
            "hand_year_in_any_year": ("" if not hy else "yes" if hy in yrs else "no"),
            "lag_recorded_minus_hand": (fr - hy) if (hy and fr != "") else "",
            "year_matches_hand": ("" if not (hy and fr != "") else
                                  "exact" if fr == hy else
                                  "within_1" if abs(fr - hy) <= 1 else "no"),
            "hand_transferee_country": hc,
            "hand_country_class": hand_class(hc),
            "amount": first["amount"] if first else "",
            "amount_grade": first["amount_grade"] if first else "",
            "THE_SENTENCE": first["THE_SENTENCE"] if first else "",
            "THE_AMOUNT_SENTENCE": first["THE_AMOUNT_SENTENCE"] if first else "",
            "annual_period_end": first["annual_period_end"] if first else "",
            "delta_federal": first["delta_federal"] if first else "",
            "delta_foreign": first["delta_foreign"] if first else "",
            "dtadtl_call": first["dtadtl_call"] if first else "",
            "dtadtl_basis": first["dtadtl_basis"] if first else "",
            "destination": first["destination"] if first else "",
            "destination_source": first["destination_source"] if first else "",
        })

    for path, rows in ((OUT_YEAR, year_rows), (OUT_FIRM, firm_rows)):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    # ------------------------------------------------------------------ reporting
    print(f"wrote {OUT_YEAR.name}  ({len(year_rows)} firm-years)")
    print(f"wrote {OUT_FIRM.name}  ({len(firm_rows)} firms)\n")

    print("STEP 1 -- evidence tier of each firm-year "
          f"(denominator {len(year_rows)} firm-years):")
    for k, n in sorted(collections.Counter(r["evidence_tier"] for r in year_rows).items()):
        s = sum(1 for r in year_rows
                if r["evidence_tier"] == k and r["year_is_strongly_identified"])
        print(f"  tier {k}   {n:>4}   of which the period is in the sentence: {s}")
    print("  years re-dated from the sentence:",
          sum(1 for r in year_rows
              if r["period_in_sentence"] == "yes_redated_from_sentence"))
    strongf = [r for r in firm_rows if r["first_recorded_year"] != ""]
    print(f"\n  firm-years strongly identified: "
          f"{sum(1 for r in year_rows if r['year_is_strongly_identified'])} of {len(year_rows)}")
    print(f"  firms with at least one:        {len(strongf)} of {len(firm_rows)}")

    withhand = [r for r in firm_rows if r["hand_transfer_year"]]
    cov = [r for r in withhand if r["first_recorded_year"] != ""]
    print(f"\nSTEP 1 SCORED -- does the method reach the hand transfer year at all? "
          f"(n={len(withhand)} firms with a hand year)")
    for k, n in collections.Counter(r["hand_year_in_any_year"] for r in withhand).most_common():
        print(f"  hand year appears somewhere in my evidence: {k:<4} {n:>3} "
              f"({n/len(withhand):.0%})")
    for k, n in collections.Counter(r["hand_year_in_strong_years"] for r in withhand).most_common():
        print(f"  hand year is a STRONGLY identified year:    {k:<4} {n:>3} "
              f"({n/len(withhand):.0%})")

    cur = [r for r in cov if r["first_recorded_type"] == "current_period_transfer"]
    ado = [r for r in cov if r["first_recorded_type"] == "adoption_catchup"]
    print(f"\n  first_recorded_year vs hand year, CURRENT-PERIOD transfers only "
          f"(n={len(cur)}; the adoption catch-ups are not comparable and are below):")
    for k, n in collections.Counter(r["year_matches_hand"] for r in cur).most_common():
        print(f"    {k:<10} {n:>3}   ({n/max(len(cur),1):.0%})")
    lags = sorted(r["lag_recorded_minus_hand"] for r in ado
                  if isinstance(r["lag_recorded_minus_hand"], int))
    if lags:
        print(f"\n  ADOPTION CATCH-UPS (n={len(lags)}): recorded minus hand transfer year")
        print(f"    {dict(collections.Counter(lags))}   "
              f"(negative means the catch-up predates the hand year -- worth reading)")

    print("\nSTEP 2 -- deferred tax call, WITH the constraint "
          f"(denominator {len(year_rows)} firm-years):")
    raw = collections.Counter(r["dtadtl_raw"] for r in year_rows if r["dtadtl_raw"])
    kept = collections.Counter(r["dtadtl_call"] for r in year_rows if r["dtadtl_call"])
    print(f"  raw calls the rule would make anywhere: "
          f"US {raw['US']}, non-US {raw['non-US']}")
    print(f"  calls reported after the constraint:    "
          f"US {kept['US']}, non-US {kept['non-US']}")

    # score the reported calls against the hand country
    hcls = {t: hand_class(c) for t, (_, c) in hand.items()}
    sc = [r for r in year_rows if r["dtadtl_call"] and hcls.get(r["ticker"])]
    def ok(r):
        h = hcls[r["ticker"]]
        return h == "both" or h == r["dtadtl_call"]
    # THE NULL MODEL FIRST, because without it the next number reads as a result.
    # Every Double Irish firm transferred to Ireland, so a constant "non-US" answer
    # scores near perfectly on this sample and the method's rate has to beat it.
    null = sum(1 for r in sc if hcls[r["ticker"]] in ("non-US", "both"))
    print(f"\nSTEP 2 SCORED against the hand transferee country "
          f"(n={len(sc)} calls on {len({r['ticker'] for r in sc})} firms):")
    print(f"  >>> NULL MODEL: answering 'non-US' every time scores {null} of {len(sc)} "
          f"({null/max(len(sc),1):.0%}) <<<")
    print("      hand classes present:",
          dict(collections.Counter(hcls[r["ticker"]] for r in sc)),
          "-- a US-only transferee does not appear in this sample at all, so this set"
          "\n      cannot tell a US call from a non-US one. Read the text test below.")
    for call in ("US", "non-US"):
        s = [r for r in sc if r["dtadtl_call"] == call]
        if s:
            g = sum(1 for r in s if ok(r))
            print(f"  {call:<7} calls {len(s):>3}   right {g:>3}   ({g/len(s):.0%})")
    s1 = [r for r in sc if r["year_is_strongly_identified"]]
    if s1:
        g = sum(1 for r in s1 if ok(r))
        print(f"  of those, in a strongly identified year: {g} of {len(s1)} ({g/len(s1):.0%})")
    bad = [r for r in sc if not ok(r)]
    if bad:
        print("  the calls that are wrong, so they can be read rather than counted:")
        for r in bad:
            print(f"    {r['ticker']:<6}{r['event_year']}  called {r['dtadtl_call']:<7}"
                  f"hand says {hand[r['ticker']][1][:28]:<30}{r['dtadtl_basis']}")
            print(f"        {r['THE_SENTENCE'][:190]}")
    inhand = [r for r in sc if hand[r["ticker"]][0] == r["event_year"]]
    if inhand:
        g = sum(1 for r in inhand if ok(r))
        print(f"\n  restricted to the HAND TRANSFER YEAR: {g} of {len(inhand)} "
              f"({g/len(inhand):.0%})")
    print("\n  why US calls were dropped:")
    for k, n in collections.Counter(
            r["dtadtl_suppressed_reason"].split(":")[1].strip().split(" the ")[0]
            for r in year_rows
            if r["dtadtl_raw"] == "US" and not r["dtadtl_call"]).most_common():
        print(f"    {k:<44} {n}")
    print("\n  reported calls by confidence, and how they score:")
    for conf in ("high", "medium"):
        s = [r for r in sc if r["dtadtl_confidence"].split(":")[0] == conf]
        allc = sum(1 for r in year_rows
                   if r["dtadtl_call"] and r["dtadtl_confidence"].split(":")[0] == conf)
        g = sum(1 for r in s if ok(r))
        print(f"    {conf:<8} {allc:>3} calls, {len(s)} scored, "
              f"{g} right" + (f" ({g/len(s):.0%})" if s else ""))

    # The only label in this project that can separate a US call from a non-US one:
    # the filing's own words, where the firm names the destination. Independent of the
    # XBRL the rule reads, and it contains actual US cases.
    tx = [r for r in year_rows if r["us_verdict_text"] in ("yes", "no") and r["dtadtl_raw"]]
    txr = [r for r in tx if r["dtadtl_call"]]
    def want(r):
        return "US" if r["us_verdict_text"] == "yes" else "non-US"
    print(f"\nSTEP 2 SCORED against the 10-K TEXT where the firm names the destination "
          f"(n={len(tx)} raw, {len(txr)} reported):")
    print(f"  raw rule agrees with the text:      "
          f"{sum(1 for r in tx if r['dtadtl_raw'] == want(r))} of {len(tx)}")
    print(f"  reported calls agree with the text: "
          f"{sum(1 for r in txr if r['dtadtl_call'] == want(r))} of {len(txr)}")
    usn = sum(1 for r in txr if want(r) == "US")
    print(f"  of which the text says US: {usn}   <-- the discriminating observations, "
          f"and the whole basis for trusting a US call")

    print("\nDESTINATION, best available source, strongly identified years only:")
    t1 = [r for r in year_rows if r["year_is_strongly_identified"]]
    for k, n in collections.Counter(r["destination_source"] for r in t1).most_common():
        print(f"  {k:<22} {n:>4}")

    print("\n--- first recorded year, one line per firm "
          f"(showing {args.show} of {len(firm_rows)}) ---")
    print(f"{'tic':<7}{'first':<7}{'hand':<6}{'type':<10}{'hand yr':<9}{'amount':>10}  "
          f"{'A':<2}{'call':<8}{'hand country'}")
    for r in sorted(firm_rows, key=lambda r: (r["hand_year_in_strong_years"] != "no",
                                              r["ticker"]))[:args.show]:
        a = f(r["amount"])
        am = "" if a is None else (f"{a/1e9:.2f}bn" if abs(a) >= 1e9 else f"{a/1e6:.0f}m")
        print(f"{r['ticker']:<7}{str(r['first_recorded_year']):<7}"
              f"{str(r['hand_transfer_year']):<6}"
              f"{(r['first_recorded_type'] or '-')[:9]:<10}"
              f"{('in:' + r['hand_year_in_strong_years']) if r['hand_transfer_year'] else '':<9}"
              f"{am:>10}  {r['amount_grade'] or '-':<2}"
              f"{(r['dtadtl_call'] or '-'):<8}{r['hand_transferee_country'][:24]}")


if __name__ == "__main__":
    main()
