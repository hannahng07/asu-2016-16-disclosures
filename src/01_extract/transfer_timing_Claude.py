#!/usr/bin/env python3
r"""WHEN the transfer happened -- which is not when the firm disclosed it.

WHY THIS EXISTS
---------------
Most first disclosures in the frame fall in 2017-2019, and most of those are ASU 2016-16
adoption catch-ups: the firm books, in one go, the tax effect of transfers it made in
EARLIER years. Apple is the settled example -- 2.7bn of deferred tax assets recorded in
Q1 2019 for a 2015 transfer. Reading the filing date as the transfer date would put the
event three to four years late for a large part of the population, and for an investor
study that is the difference between an event and a coincidence.

So every effect filing gets a separate reading of WHEN, with the basis recorded:

    stated          the sentence says when the transfer happened -- "in the second and
                    fourth quarters of 2021, we completed intercompany transfers"
    current_period  the transfer belongs to the period the filing reports on: the firm
                    is reporting it as it happens, so the filing's own period is the date
    pre_adoption    an adoption catch-up. The transfers happened at some point BEFORE
                    the adoption date, and the filing does not say when. The adoption
                    date is therefore an UPPER BOUND and nothing more -- the field is
                    named as a bound so it cannot be mistaken for a date
    unknown         nothing in the sentence dates anything

WHAT THIS DOES NOT DO
---------------------
It does not guess. A pre-adoption catch-up gets no transfer year, because the filing does
not contain one. For those firms the instrument is the deferred tax asset jump in
Compustat, not this corpus -- that work is outside this module.

THE ISSUANCE TRAP
-----------------
"In October 2016, the FASB issued ASU 2016-16..." is in a third of these filings, and it
is the date the STANDARD was issued. Taken as a period phrase it dates a third of the
population to October 2016. Any period phrase sitting next to issuance language is
discarded here.
"""
from __future__ import annotations

import re

import extract_asu_v2_Claude as E

# issuance of the standard, never a transfer or an adoption
ISSUED = re.compile(r"FASB\s+issued|issued\s+ASU|was\s+issued|Board\s+issued|"
                    r"issued\s+(?:its\s+)?(?:new\s+|updated\s+)?(?:accounting\s+)?"
                    r"(?:standards?\s+)?(?:update|guidance)", re.I)
# the event itself. STRONG names the transfer; WEAK names the restructuring around it and
# is only consulted when nothing strong is near a date -- ViacomCBS's "in connection with a
# reorganization" sits next to "the 2018 federal tax return", three clauses from the transfer
TRANSFER_CUE_STRONG = re.compile(
    r"\b(?:transferr?ed|transfers?|sale|sales|sold|migrat\w+|licens\w+|contribut\w+)\b", re.I)
TRANSFER_CUE_WEAK = re.compile(
    r"\brestructur\w+\b|\breorganiz\w+\b|\bimplement\w+\b|\balign\w+\b"
    r"|\blegal\s+entit\w+\b|\b(?:corporate|tax)\s+structure\b", re.I)
TRANSFER_CUE = re.compile(TRANSFER_CUE_STRONG.pattern + "|" + TRANSFER_CUE_WEAK.pattern, re.I)
ADOPT_CUE = re.compile(r"\badopt\w*\b|\beffective\s+date\b|\bupon\s+adoption\b", re.I)
# a transfer that is explicitly NOT in the reporting period
PAST_CUE = re.compile(r"\b(?:prior\s+to|before|preceding|previously|historical\w*|"
                      r"that\s+occurred\s+(?:in|prior)|occurred\s+before)\b", re.I)
# an adoption catch-up: the tax effect of transfers made BEFORE the adoption date
CATCHUP = re.compile(
    r"cumulative[-\s]effect|modified\s+retrospective|transition\s+method|upon\s+adoption"
    r"|prior\s+to\s+(?:the\s+)?adoption|as\s+of\s+the\s+beginning\s+of\s+the\s+period"
    r"|catch[-\s]?up"
    # read 22 Sep on 30 stated years: two escaped as transfers. VF Corp's "early adopted
    # ... in the first quarter of 2017, which resulted in a cumulative adjustment" and
    # Constellation's "in the first quarter of fiscal 2019, we recognized a net increase in
    # our March 1, 2018, opening retained earnings" both date the ADOPTION
    r"|cumulative\s+(?:catch[-\s]?up\s+)?adjustment|early\s+adopted"
    # read 22 Sep on 14 inferred dates: 6 of them were adoption catch-ups whose sentence
    # never says "cumulative effect" -- it says the firm adopted and retained earnings
    # moved (Albany, Oxford, DMC), or an auditor says the method changed (Halliburton)
    r"|changed\s+its\s+method\s+of\s+account"
    r"|(?:opening|beginning)\s+(?:balance\s+of\s+)?(?:retained\s+earnings|accumulated\s+deficit)",
    re.I)
# the accounts an adoption adjustment lands in: with "adopted" in the same sentence this is
# a catch-up, whether or not the words "cumulative effect" appear
BALANCE = re.compile(r"retained\s+earnings|accumulated\s+deficit|prepaid\s+(?:income\s+)?tax", re.I)
# a rate table or a year-over-year comparison: the years in it are column headings, not
# the date of anything (CrowdStrike's provision-for-income-taxes table, Confluent's)
NUMERIC = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
# the firm saying the event is in the period this filing reports on
CURRENT_CUE = re.compile(
    r"during\s+the\s+(?:current\s+)?(?:quarter|period|year|three|six|nine|fiscal)"
    r"|(?:year|quarter|period|months)\s+ended|in\s+the\s+current\s+(?:quarter|period|year)"
    r"|for\s+the\s+(?:three|six|nine|twelve)\s+months", re.I)
TRANSFER_CUE_EXTRA = re.compile(r"implement\w+|align\w+|legal\s+entit|corporate\s+structure"
                                r"|tax\s+structure|initiative", re.I)
NEAR = 130          # characters between a cue and the period phrase it dates

# the extractor's period patterns miss two forms that turn up in transfer sentences:
# a plural quarter ("in the second and fourth quarters of 2021" -- Uber) and a bare year
# ("transferred the intellectual property in 2015")
EXTRA_PATS = [
    # "during the fourth quarter 2019" -- no "of" (Alexion)
    (re.compile(r"\b(?:first|second|third|fourth)\s+quarter\s+(?:of\s+)?(?:fiscal\s+)?"
                r"(?:year\s+)?((?:19|20)\d{2})", re.I), "quarter"),
    # "on November 1, 2018" -- Agilent gives the transfer date this way and the extractor's
    # patterns only read a full date after the word "ended"
    (re.compile(r"\b(?:on|effective|dated)\s+(?:january|february|march|april|may|june|july|"
                r"august|september|october|november|december)\s+\d{1,2},?\s+((?:19|20)\d{2})",
                re.I), "period_ended"),
    (re.compile(r"\bfor\s+(?:the\s+)?(?:fiscal\s+)?(?:year\s+)?((?:19|20)\d{2})\b(?!\s*-)",
                re.I), "year"),
    (re.compile(r"\b(?:first|second|third|fourth)(?:\s*,?\s*(?:and\s+)?(?:first|second|"
                r"third|fourth))*\s+quarters\s+of\s+(?:fiscal\s+)?(?:year\s+)?(\d{4})",
                re.I), "quarter"),
    (re.compile(r"\b(?:in|during|of)\s+(?:the\s+)?(?:calendar\s+|fiscal\s+)?(?:year\s+)?"
                r"((?:19|20)\d{2})\b(?!\s*-)", re.I), "year"),
]


def _phrases(sentence: str):
    """Every period phrase in the sentence, with position and calendar year."""
    out = []
    for pat, kind in list(E.PERIOD_PATS) + EXTRA_PATS:
        for m in pat.finditer(sentence):
            year = None
            for g in m.groups():
                if g and str(g).isdigit() and len(str(g)) == 4:
                    year = int(g)
            if not year:
                continue
            if any(abs(m.start() - o["pos"]) < 4 for o in out):
                continue
            out.append({"text": m.group(0), "pos": m.start(), "year": year, "kind": kind})
    out.sort(key=lambda d: d["pos"])
    return out


def _issuance(sentence: str, p):
    """True if this phrase is the date the STANDARD was issued."""
    lo, hi = max(0, p["pos"] - 90), min(len(sentence), p["pos"] + 90)
    return bool(ISSUED.search(sentence[lo:hi]))


def _past(sentence: str, p):
    """True if the phrase is explicitly a PAST period ('that occurred in 2015')."""
    return bool(PAST_CUE.search(sentence[max(0, p["pos"] - 60):p["pos"] + 30]))


def _nearest(sentence: str, phrases, cue: re.Pattern, near=None):
    """The phrase closest to a cue word, within `near` characters and the same clause.

    A semicolon ends the clause: ViacomCBS lists "a reorganization of our international
    operations; tax benefits of 44 million realized in connection with the preparation of
    the 2018 federal tax return", and without the clause test the reorganization dates
    itself from the tax return two clauses later.
    """
    best, dist = None, (near or NEAR) + 1
    for m in cue.finditer(sentence):
        for p in phrases:
            lo, hi = sorted((p["pos"], m.start()))
            if ";" in sentence[lo:hi]:
                continue
            d = hi - lo
            if d < dist:
                best, dist = p, d
    return best


def timing(sentence: str, record_type: str, tdate: str = "",
           filing_fyear=None, is_effect: bool = True) -> dict:
    """What the sentence says about WHEN, and on what basis."""
    s = " ".join((sentence or "").split())
    out = {"transfer_timing": "unknown", "transfer_year": "", "transfer_year_basis": "",
           "transfer_year_upper_bound": "", "adoption_year_stated": "",
           "transfer_period_text": ""}
    if not s or not is_effect:
        return out
    if len(NUMERIC.findall(s)) >= 8:
        # too many loose figures for the year to be attached to anything in particular
        out["transfer_year_basis"] = "not dated: the sentence is a table or a rate comparison"
        return out
    phrases = [p for p in _phrases(s) if not _issuance(s, p)]
    # the adoption date is read only from a phrase that is not marked as a past period --
    # "upon adoption we recorded ... transfers that occurred in 2015" adopts in some other
    # year and transfers in 2015, and taking 2015 as the adoption year loses the transfer
    adopt = _nearest(s, [p for p in phrases if not _past(s, p)], ADOPT_CUE, near=70)
    if adopt:
        out["adoption_year_stated"] = adopt["year"]
    catchup = bool(CATCHUP.search(s)) or record_type == "adoption_catchup"
    if not catchup and ADOPT_CUE.search(s) and BALANCE.search(s):
        catchup = True

    def stated(p, why):
        out.update(transfer_timing="stated", transfer_year=p["year"],
                   transfer_year_basis=why, transfer_year_upper_bound=p["year"],
                   transfer_period_text=p["text"])
        return out

    # 1. an adoption catch-up says WHEN IT ADOPTED, and that is not when it transferred.
    # Entergy's "recorded an adjustment to retained earnings of 56 million as of January 1,
    # 2018 for the cumulative-effect ... from intra-entity asset transfers" would otherwise
    # read as a 2018 transfer. The only escape is a past year attached to the transfer
    # itself ("transfers that occurred in 2015").
    if catchup:
        past = [p for p in phrases
                if _past(s, p)
                and TRANSFER_CUE_STRONG.search(s[max(0, p["pos"] - 90):p["pos"] + 90])
                and (not adopt or p["year"] != adopt["year"])]
        if past:
            return stated(min(past, key=lambda p: p["year"]),
                          "a past transfer year named inside an adoption catch-up")
        ub = out["adoption_year_stated"] or (filing_fyear or "")
        out.update(transfer_timing="pre_adoption",
                   transfer_year_basis="not stated: catch-up on transfers made before adoption",
                   transfer_year_upper_bound=ub)
        return out

    # 2. the sentence dates the transfer itself
    tp = _nearest(s, phrases, TRANSFER_CUE_STRONG) or _nearest(s, phrases, TRANSFER_CUE_WEAK)
    if tp is not None and adopt is not None and tp["pos"] == adopt["pos"]:
        tp = None
    if tp is not None:
        return stated(tp, "stated in the asserting sentence")
    # the sentence names exactly one period and does assert a transfer: that period is the
    # only candidate date it has, even if the words sit further apart than NEAR
    # (Twitter: "In the year ended December 31, 2019, we recorded an income tax benefit of
    # 1.21 billion ... from intra-entity transfers of intangible assets")
    # the fallback is for a SHORT sentence with one date in it. In a long one, the single
    # remaining phrase can belong to a clause that has nothing to do with the transfer --
    # ViacomCBS's "the preparation of the 2018 federal tax return", three clauses away
    live = [p for p in phrases]
    if len(live) == 1 and len(s) <= 300 and TRANSFER_CUE.search(s):
        return stated(live[0], "the only period in the asserting sentence")
    tdate = str(tdate or "").strip()
    if tdate and tdate.lower() != "nan":
        m = re.search(r"(\d{4})", tdate)
        if m:
            return stated({"year": int(m.group(1)), "text": tdate},
                          "transfer-date phrase in the anchor sentence")
    if PAST_CUE.search(s):
        out.update(transfer_timing="pre_adoption",
                   transfer_year_basis="the firm says the transfer preceded this filing, "
                                       "without giving a year",
                   transfer_year_upper_bound=(filing_fyear or ""))
        return out

    # 3. no date at all. If the sentence reports on the filing's own period, the period is
    # the best available date -- but it is an INFERENCE and is labelled as one, unless the
    # sentence explicitly says "during the quarter" / "for the year ended ...".
    if phrases and CURRENT_CUE.search(s):
        # the sentence names a reporting period ("the three months ended March 31, 2020")
        # and nothing closer to the transfer. That period beats the filing's own fiscal
        # year, which for a 10-Q comparative would be a year out (Choice Hotels)
        p = min(phrases, key=lambda p: p["pos"])
        out.update(transfer_timing="current_period", transfer_year=p["year"],
                   transfer_year_basis="the reporting period named in the sentence",
                   transfer_year_upper_bound=p["year"], transfer_period_text=p["text"])
        return out
    if filing_fyear:
        out.update(transfer_timing="current_period_inferred", transfer_year=filing_fyear,
                   transfer_year_basis="INFERRED: the filing's own period, not stated",
                   transfer_year_upper_bound=filing_fyear)
    return out


FIXTURE = [
    ("To align our structure to our evolving operations, in the second and fourth quarters of 2021, we completed intercompany transfers of certain intangible assets.",
     "current_period_transfer", 2021, "stated"),                                    # Uber
    ("In August 2023, we completed an intra-entity asset transfer of certain intellectual property between two of our wholly owned foreign subsidiaries.",
     "current_period_transfer", 2023, "stated"),                                    # DexCom
    ("In December 2019, we completed a Dutch legal entity restructuring project, which resulted in an intra-entity transfer of certain intangible assets and intellectual property.",
     "current_period_transfer", 2019, "stated"),                                    # Koppers
    ("We adopted ASU 2016-16 as of January 1, 2018 using a modified retrospective transition method, resulting in a 701 million reclassification of unrecognized income tax effects related to asset transfers that occurred prior to adoption from other current and non-current assets to opening retained earnings.",
     "adoption_catchup", "", "pre_adoption"),                                       # Alphabet
    ("In October 2016, the FASB issued ASU 2016-16 and the Company recorded a cumulative-effect adjustment upon adoption.",
     "adoption_catchup", "", "pre_adoption"),                                       # issuance trap
    ("Entergy recorded an adjustment to retained earnings of 56 million as of January 1, 2018 for the cumulative-effect of the recognition of the deferred tax assets arising from intra-entity asset transfers.",
     "current_period_transfer", "", "pre_adoption"),
    ("During the fourth quarter of 2014, the Company implemented an initiative to better align its legal entity and tax structure with its operational footprint outside of the U.S.",
     "current_period_transfer", 2014, "stated"),                                    # Mastercard
    ("Upon adoption we recorded deferred tax assets for intra-entity transfers of intellectual property that occurred in 2015.",
     "adoption_catchup", 2015, "stated"),
    ("In the year ended December 31, 2019, we recorded an income tax benefit of 1.21 billion related to the establishment of deferred tax assets from intra-entity transfers of intangible assets.",
     "current_period_transfer", 2019, "stated"),                                    # Twitter
    ("(3) VF early adopted the accounting standards update regarding intra-entity transfers in the first quarter of 2017, which resulted in a cumulative adjustment to retained earnings and reduction in other assets in the Consolidated Balance Sheet at January 1, 2017 of 237.8 million.",
     "current_period_transfer", "", "pre_adoption"),                                # VF Corp
    ("Based on our assessment of intra-entity asset transfers that are in scope and the related deferred income taxes, in the first quarter of fiscal 2019, we recognized a net increase in our March 1, 2018, opening retained earnings and deferred tax assets of 2.2 billion.",
     "current_period_transfer", "", "pre_adoption"),                                # Constellation
    ("Provision for Income Taxes The following shows the provision for income taxes for fiscal 2022, as compared to fiscal 2021 (in thousands, except percentages): Year Ended January 31, Change 2022 2021 Provision for income taxes 72,355 4,760 67,595 1,420 the increase relates to an intra-entity transfer of intellectual property.",
     "current_period_transfer", "", "unknown"),                                     # CrowdStrike table
    ("The restructuring along with the application of the new accounting rules under ASU 2016-16, intra-entity transfer of assets on November 1, 2018, resulted in a 299 million tax benefit in the first quarter of fiscal year 2019.",
     "current_period_transfer", 2018, "stated"),                                    # Agilent
    ("For 2019, we recorded a benefit for income taxes of 9 million, reflecting an effective income tax rate of (0.3), which included discrete items such as a deferred tax benefit of 768 million resulting from the transfer of intangible assets between our subsidiaries in connection with a reorganization of our international operations; tax benefits of 44 million realized in connection with the preparation of the 2018 federal tax return, based on further clarity provided by the United States government.",
     "current_period_transfer", 2019, "current_period_inferred"),                   # ViacomCBS: right year, weak basis
    ("The effective income tax rate for the three months ended March 31, 2020 was lower than the U.S. federal income tax rate of 21.0 primarily due to the impact of our international reorganization in accordance with ASU 2016-16, which provides guidance on recognition of current income tax consequences for intercompany asset transfers (other than inventory) at the time of transfer.",
     "current_period_transfer", 2020, "current_period"),                            # Choice Hotels
    ("During the fourth quarter 2019, we completed an intra-entity asset transfer of certain intellectual property to an Irish subsidiary within our captive foreign partnership.",
     "current_period_transfer", 2019, "stated"),                                    # Alexion
    ("The Company adopted this update effective January 1, 2018, which resulted in a decrease of 0.5 million to deferred tax liabilities, with an offsetting increase to Retained earnings.",
     "current_period_transfer", "", "pre_adoption"),                                # Albany International
    ("As discussed in Note 14 to the consolidated financial statements, the Company changed its method of accounting for deferred income taxes related to intra-entity transfers other than inventory effective January 1, 2017.",
     "current_period_transfer", "", "pre_adoption"),                                # Halliburton
    ("The Company recorded a 38 million reduction in income tax expense in the quarter ended April 1, 2017 as a result of an intercompany transfer of intellectual property.",
     "current_period_transfer", 2017, "stated"),                                    # Kellogg
]

if __name__ == "__main__":
    bad = []
    for s, rec, want_year, want_timing in FIXTURE:
        g = timing(s, rec, filing_fyear=(2019 if want_timing == "current_period_inferred"
                                         else None))
        if (g["transfer_year"] or "") != want_year or g["transfer_timing"] != want_timing:
            bad.append((g, want_year, want_timing, s[:80]))
    print(f"fixture: {len(FIXTURE) - len(bad)} of {len(FIXTURE)} as read")
    for g, wy, wt, s in bad:
        print(f"  got {g['transfer_timing']}/{g['transfer_year']} "
              f"want {wt}/{wy}  {s}")
