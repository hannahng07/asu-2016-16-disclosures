#!/usr/bin/env python3
r"""The deliverable: a linkable data frame of disclosing filings and firms.

Brian, 21 September: *"ultimately, I want to be able to export the code's data frame and
have a usable set that I can link to firm-level data from Compustat and the system with
stock price changes. In the data frame, we'd ideally be able to identify the first time
that this disclosure is mentioned, along with the amounts, and all the other data from
Phase A."*

TWO TABLES, BECAUSE THERE ARE TWO QUESTIONS
--------------------------------------------
    population_filings_Claude   one row per (firm, filing) with any clean mention
                                -> the unit of an event study: each filing is an event
    population_firms_Claude     one row per FIRM that ever mentions it
                                -> first mention, first effect, first amount, history

Both come out as CSV and as Stata .dta, with a codebook naming every column.

WHO IS IN THE POPULATION
-------------------------
A filing is classified by what it ASSERTS (disclosure_class_Claude.py):

    effect               the firm records a consequence or asserts a transfer
    adoption_no_effect   adopted, and says it had no material effect
    adoption             adopted, and says nothing about an effect
    standard             describes the standard, forecasts, or evaluates

**The population of disclosing firms is `ever_effect == 1`.** ASU 2016-16 was mandatory,
so "we adopted it" is near-universal in 2018 and says nothing about a transfer. The
adoption-only firms stay in the firm table, flagged, because they are a natural
comparison group: exposed to the same rule, with nothing to book.

This replaced a score threshold on 21 September. Score could not separate a disclosure
from boilerplate -- Hyatt's "we are currently evaluating the impact" scored 7 -- and on
the first-mention column, which picks each firm's EARLIEST filing and so concentrates on
the 2016-17 boilerplate wave, boilerplate dominated.

HOW TO LINK THEM
-----------------
    Compustat   cik (10-digit, zero-padded, as comp.company stores it) -> gvkey; then
                gvkey + datadate onto funda (10-K) or fundq (10-Q). `datadate` is the
                filing's own period of report. `fyear` follows COMPUSTAT's rule -- a
                fiscal year ending January to May belongs to the previous calendar
                year -- which is not the SEC's label.
    CRSP        gvkey -> permno through the CCM link table, valid on `filing_date`.
    The event   `filing_date` is when the market could first read it -- not the
                transfer date and not the period described. Those are separate columns.
    Key         (cik, accession). One accession can carry several registrants.

gvkey and ticker are filled only for the Double Irish firms, where they are known.

LEFT CENSORING
---------------
The corpus starts January 2016 and a firm enters at its first filing. A firm whose first
effect falls in its first observed filings may have disclosed earlier; `*_left_censored`
flags fewer than four prior filings, and `n_prior_filings` lets a stricter rule be used.

Writes: population_filings_Claude.csv / .dta
        population_firms_Claude.csv   / .dta
        population_codebook_Claude.csv
        population_by_year_Claude.csv   denominators: filings and firms read per year
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import re
import sys
from pathlib import Path

import pandas as pd

import build_identification_proof_Claude as P
import build_transfer_year_Claude as T
import disclosure_class_Claude as K
import transfer_timing_Claude as TT
import amount_components_Claude as AC
import extract_asu_v2_Claude as E

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
HERE = Path(__file__).resolve().parent
PARTS = HERE / "sweep_parts"
MANIFEST = HERE / "sweep_manifest_Claude.csv"
FYE = HERE / "sweep_fye_Claude.csv"
DI = HERE / "di_firm_years_Claude.txt"
GRADE = {"A": 0, "B": 1, "C": 2, "-": 3}
XBRL = {}
USV = {"yes": 0, "no": 1, "unnamed": 2, "not_stated": 3}
# how a destination was established, strongest first: "to Ireland" beats a cue phrase in
# the window, which beats the country merely appearing somewhere nearby
DBASIS = {"prep_to": 0, "prep_from": 1, "cued": 2, "mentioned_only": 3, "": 4}
CENSOR_MIN_PRIOR = 4


def iso8(s):
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""


def fyear_compustat(d):
    """Compustat: a fiscal year ending Jan-May belongs to the previous calendar year."""
    return (d.year if d.month >= 6 else d.year - 1) if d else None


def load_fye():
    fye = collections.defaultdict(list)
    for r in csv.DictReader(FYE.open(encoding="utf-8")):
        s = r["period_of_report"]
        if len(s) == 8 and s.isdigit():
            try:
                fye[r["cik"]].append(dt.date(int(s[:4]), int(s[4:6]), int(s[6:])))
            except ValueError:
                pass
    return {k: sorted(set(v)) for k, v in fye.items()}


def fiscal_year_end_for(fye, cik, datadate):
    """The fiscal year a period belongs to ends at the next 10-K year end."""
    if not datadate:
        return None
    for d in fye.get(cik, []):
        if d >= datadate and (d - datadate).days <= 370:
            return d
    return None


def load_di():
    out = {}
    if DI.exists():
        for r in csv.DictReader(DI.open(encoding="utf-8"), delimiter="\t"):
            c = (r.get("cik") or "").strip().lstrip("0")
            if c:
                out[c] = {"gvkey": (r.get("gvkey") or "").strip(),
                          "ticker": (r.get("tic") or "").strip()}
    return out


def following_text(c):
    """What comes after the anchor sentence inside the candidate window."""
    ct, an = c.get("candidate_text", "") or "", c.get("anchor_sentence", "") or ""
    i = ct.find(an[:120]) if an else -1
    return ct[i + len(an):] if i >= 0 else ""



# --- the SIGN, read next to the figure rather than across the sentence (22 Sep) ---
# Gilead's FY2018 sentence carries a 202m tax BENEFIT from a tax settlement and, in the
# same breath, the 588m deferred tax CHARGE from the transfer. Counting cue words across
# the whole sentence called it "mixed" and recorded a DTA. The transfer's own effect is a
# cost, and the sign is settled point 5 of the project: a population that reads costs as
# benefits is biased toward low-tax destinations.
_COST_PHRASE = re.compile(r"increase\s+in\s+(?:income\s+)?tax\s+expense|tax\s+charge|"
                          r"\bcharge\b|\bexpense\b|\bcost\b|\baccrual\b|\bliabilit",
                          re.I)
_BEN_PHRASE = re.compile(r"decrease\s+in\s+(?:income\s+)?tax\s+expense|reduction\s+in\s+"
                         r"(?:income\s+)?tax\s+expense|tax\s+benefit|\bbenefit\b|"
                         r"deferred\s+tax\s+asset", re.I)
_DTL_PHRASE = re.compile(r"deferred\s+tax\s+liabilit|\bDTL\b|deferred\s+tax\s+charge", re.I)
_DTA_PHRASE = re.compile(r"deferred\s+tax\s+asset|\bDTA\b", re.I)


def sign_near(sentence, value, window=90):
    """(direction, dta_dtl) from the words around the chosen figure, or ('','')."""
    if value in (None, "") or not sentence:
        return "", ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "", ""
    texts = set()
    for unit, div in (("billion", 1e9), ("million", 1e6), ("thousand", 1e3), ("", 1)):
        x = v / div
        if x < 0.001 or x > 1e6:
            continue
        for form in (f"{x:,.1f}", f"{x:,.2f}", f"{x:,.0f}", f"{x:.1f}", f"{x:.0f}"):
            texts.add(form.rstrip("0").rstrip(".") if "." in form else form)
    hits = []
    for t in texts:
        for m in re.finditer(re.escape(t) + r"\b", sentence):
            hits.append(m)
    if not hits:
        return "", ""
    m = hits[0]
    near = sentence[max(0, m.start() - window):m.end() + window]
    cost, ben = bool(_COST_PHRASE.search(near)), bool(_BEN_PHRASE.search(near))
    direction = "cost" if (cost and not ben) else ("benefit" if (ben and not cost) else "")
    if cost and ben:            # both present: the nearer one wins
        c = min((abs(x.start() - m.start()) for x in _COST_PHRASE.finditer(near)), default=999)
        b = min((abs(x.start() - m.start()) for x in _BEN_PHRASE.finditer(near)), default=999)
        direction = "cost" if c < b else "benefit"
    dd = "DTL" if _DTL_PHRASE.search(near) else ("DTA" if _DTA_PHRASE.search(near) else "")
    return direction, dd


# a magnitude word with no figure in front of it: the corpus stripped the number out of
# this very sentence ("increasing retained earnings by million"). The amount picker then
# reaches past the hole and takes a neighbouring figure -- on the filings where both a
# text amount and a like-for-like tagged amount exist, the text figure is wrong 4 times
# in 5 when the sentence is stripped, against 1 in 7 when it is not.
STRIPPED = re.compile(r"\b(?:of|by|to|approximately|totaling|totalling)\s+"
                      r"(?:approximately\s+)?(?:million|billion|thousand)\b", re.I)


def agree(text_amt, xbrl_amt, rank=None, tol=0.05):
    """'yes' / 'no' / 'different_line_item' / '' -- do the two figures match.

    Tolerance is rounding-aware: a 10-K that writes "0.4 million" has rounded to the
    nearest 0.1m, so 400,000 against a tagged 427,000 is the same number written twice,
    not a disagreement. Without this, rounding alone produced a fifth of the mismatches.
    """
    if text_amt in (None, "") or xbrl_amt in (None, "") or not xbrl_amt:
        return ""
    # only compare like for like. A rank-3 or rank-4 fact is a BALANCE or an account that
    # moved, not the adjustment the sentence reports, so a mismatch there is two different
    # quantities rather than an error: Microsoft's 557m net cumulative effect against a
    # 2.8bn deferred tax asset balance is both figures being right.
    if rank is not None and str(rank) not in ("1", "2", "1.0", "2.0"):
        return "different_line_item"
    try:
        r = float(text_amt) / float(xbrl_amt)
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    try:
        a, x = abs(float(text_amt)), abs(float(xbrl_amt))
    except (TypeError, ValueError):
        return ""
    # the granularity the text was written at: 0.4 million -> 0.05m, 13 million -> 0.5m
    gran = 0.5 * 10 ** (len(str(int(a))) - 1) if a else 0
    if abs(a - x) <= max(tol * x, gran * 0.1):
        return "yes"
    return "yes" if (1 - tol) <= r <= (1 + tol) else "no"


def load_xbrl():
    """(cik, accession) -> the XBRL fact chosen for that filing, if any."""
    p = HERE / "xbrl_amounts_Claude.csv"
    if not p.exists():
        return {}
    out = {}
    for r in csv.DictReader(p.open(encoding="utf-8")):
        out[(r["cik"].lstrip("0"), r["accession"].replace("-", ""))] = r
    return out


def enrich(c):
    """Phase A's judgment on one candidate, plus what it asserts."""
    sg, sb = P.grade_sentence(c)
    ag, _ = P.grade_amount(c)
    uv, ue = P.us_verdict(c)
    tier, _ = T.tier_of(c)
    pis = T.period_in_sentence(c)
    kls, ksent = K.klass_window(c["anchor_sentence"], following_text(c))
    amt = None
    if kls == "effect":
        # the amount is read from the sentence that CARRIES the effect -- which may be
        # the sentence after the anchor -- and only from an effect-class candidate, so
        # Hyatt's evaluation note never inherits an unrelated 311 million
        v, _ = P.pick_amount(P.trim_furniture(ksent), c["anchor_text"],
                             c.get("candidate_text", ""))
        if v is None and ksent == c["anchor_sentence"] and c["amount_best"] and ag in ("A", "B"):
            v, _ = P.pick_amount(P.trim_furniture(c["anchor_sentence"]), c["anchor_text"],
                                 c.get("candidate_text", ""))
        amt = v
    m = T.TRANSFER_WHEN.search(c["anchor_sentence"] or "")
    c.update({
        "_score": int(c["score"] or 0), "_clean": not c.get("fp_family"),
        "_sg": sg, "_sb": sb, "_ag": ag, "_amt": amt, "_uv": uv, "_ue": ue,
        "_tier": tier,
        "_strong": tier in (1, 2, 3) and pis in ("yes", "yes_redated_from_sentence"),
        "_record": ("adoption_catchup" if T.ADOPTION.search(c["anchor_sentence"] or "")
                    else "current_period_transfer"),
        "_tdate": (m.group(1).strip() if m else ""),
        "_std": bool(E.ASU_1616.search(c.get("candidate_text", "") or "")),
        "_class": kls, "_class_sentence": " ".join(ksent.split()),
        # an effect that ASSERTS a past transfer rather than recording one this period
        "_assert": (kls == "effect" and K.assertion_only(ksent)),
    })
    return c


def firstof(rs):
    return rs[0] if rs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-dta", action="store_true")
    a = ap.parse_args()

    fye, di = load_fye(), load_di()
    # A JOINT FILING: one accession under several CIKs -- a holding company and its
    # subsidiaries in one combined 10-K, or a family of trusts in one 10-Q. Each CIK is
    # a registrant that made the disclosure, so each keeps its row.
    coreg = collections.Counter(r["accession"] for r in
                                csv.DictReader(MANIFEST.open(encoding="utf-8")))

    bf, n_cand = collections.defaultdict(list), 0
    for p in sorted(glob.glob(str(PARTS / "cand_*.csv"))):
        for c in csv.DictReader(open(p, encoding="utf-8")):
            n_cand += 1
            bf[(c["cik"], c["accession"])].append(enrich(c))
    global XBRL
    XBRL = load_xbrl()
    logs = []
    for p in sorted(glob.glob(str(PARTS / "log_*.csv"))):
        logs.extend(csv.DictReader(open(p, encoding="utf-8")))

    # ---------------------------------------------------------------- filings
    F = []
    for (cik, acc), cs in bf.items():
        clean = [c for c in cs if c["_clean"]]
        if not clean:
            continue
        c0 = cs[0]
        best = min(clean, key=lambda c: (K.RANK[c["_class"]], GRADE[c["_sg"]], -c["_score"]))
        eff = [c for c in clean if c["_class"] == "effect"]
        withamt = [c for c in eff if c["_amt"] is not None]
        ba = (min(withamt, key=lambda c: (GRADE[c["_ag"]], -c["_score"])) if withamt else None)
        # The destination is decided INSIDE the asserting sentence, not across the filing.
        # Taking the most US-ish candidate anywhere in the filing put Cadence's FY2019
        # 10-K down as a US destination on a rate-table line ("Intercompany transfers of
        # intangible property rights", with a cued "United States" 157 characters away)
        # while seven candidates in the same filing read "to our Irish subsidiary". That
        # is the exact bias goal 2 cannot carry: a sweep that resolves ties towards the US
        # manufactures US destinations. Effect candidates first, then the sentence grade,
        # then how the destination was established -- a preposition on the country beats a
        # cue in the window, which beats a bare mention.
        xb = XBRL.get((cik.lstrip("0"), acc.replace("-", "")))
        # ---- the components. One entry moves several accounts; read them all, type
        # them, and let the headline be a documented CHOICE rather than an accident of
        # which clause the picker reached first.
        tcomp = []
        for c in (eff or []):
            # NOT passing a units hint, and the reason is measured. The "(in thousands)"
            # header the corpus strips sits at the top of the statement, thousands of
            # characters from the sentence; the candidate window is 400-660 characters and
            # never reaches it. Wiring AC.units_hint() to that window changed 8 effect
            # filings, fixed 0 against the filers' XBRL and broke 2. `AC.components` takes
            # a `units` argument and `AC.units_hint` is kept for the day the window is
            # widened in a re-sweep; until then the hint is not available and guessing
            # the unit is worse than flagging it (see the `Unit check` column).
            tcomp.extend(AC.components(c["_class_sentence"]))
        comps = AC.merge(tcomp, AC.from_xbrl(xb.get("xbrl_components", "") if xb else ""))
        hv, ht, hb = AC.headline(comps)
        by_type = {}
        for c in comps:
            if c["value"] is not None and c["type"] not in by_type:
                by_type[c["type"]] = c["value"] * (c["sign"] if c["sign"] else 1)
        comp_fields = {
            "amount_components": AC.as_text(comps),
            "n_amount_components": len([c for c in comps if c["value"] is not None]),
            "amount_headline": hv if hv is not None else "",
            "amount_component_type": ht,
            "amount_component_basis": hb,
            "amount_stripped_components": len([c for c in comps if c["value"] is None]),
            "amt_retained_earnings": by_type.get("retained_earnings", ""),
            "amt_tax_pl": by_type.get("tax_pl", ""),
            "amt_deferred_tax_asset": by_type.get("deferred_tax_asset", ""),
            "amt_deferred_tax_liability": by_type.get("deferred_tax_liability", ""),
            "amt_prepaid": by_type.get("prepaid", ""),
            "amt_valuation_allowance": by_type.get("valuation_allowance", ""),
            "amt_other_assets": by_type.get("other_assets", ""),
            "amt_noncontrolling_interest": by_type.get("noncontrolling_interest", ""),
        }
        # ---- WHICH FIGURE IS `amount`, decided 23 September by measurement.
        # Two parsers have been running side by side. `pick_amount` is the older
        # positional one; the typed component parser reads the whole entry and picks a
        # headline in a fixed order. Where a filing's disclosure moves several accounts,
        # the positional picker takes whichever clause it reaches first: Broadcom's
        # amount was the 67m prepaid leg, not the 252m charged to accumulated deficit;
        # Sunrun's was the 378.5m prepaid reversal, not the 0.3m cumulative effect.
        #
        # Scored against the filers' own XBRL tags on the 288 10-K effect filings that
        # carry one (agreement within 2%):
        #     pick_amount                                 207 right of 269 emitted (77%)
        #     headline when the parser parsed, else pick   232 right of 286 emitted (81%)
        #     always headline                              228  -- worse, because a
        #         sentence the component parser cannot read leaves no headline at all
        # A further guard (blank the amount when nothing parsed AND the sentence carries
        # no magnitude word) was tried and dropped: it changed precision by nothing and
        # lost two right answers.
        # PROVENANCE, tried and REVERTED 23 September. The worry was that `comps` merges
        # the text components with the filer's XBRL ones, so a headline taken from it
        # could be an XBRL figure wearing a text label. Reading the headline off the text
        # components only, and letting the merged one stand in as `xbrl_component` when
        # the sentence carried nothing, MEASURED WORSE: emissions rose 719 -> 742 on the
        # checkable set and agreement fell from 88% to 81%, because a rank-agnostic
        # merged component is a poorer choice than the rank<=3 tagged fact the old path
        # already used. The "text" count did not move at all, which says the headline was
        # coming from the sentence in the first place. Left as it was.
        n_comp_ok = len([c for c in comps if c["value"] is not None])
        text_amt = (hv if (n_comp_ok >= 1 and hv is not None)
                    else (ba["_amt"] if ba else None))
        uvb = min(eff or clean, key=lambda c: (GRADE[c["_sg"]], DBASIS.get(
            (c.get("destination_basis") or "").strip(), 9), -c["_score"]))
        por = iso8(c0["period_of_report"])
        dd = dt.date.fromisoformat(por) if por else None
        fe = dd if c0["form"] == "10-K" else fiscal_year_end_for(fye, cik, dd)
        d = di.get(cik, {})
        F.append({
            "cik": f"{int(cik):010d}", "accession": acc, "form": c0["form"],
            "filing_date": iso8(c0["filing_date"]), "company": c0["company"],
            "datadate": por,
            "fiscal_year_end": fe.isoformat() if fe else "",
            "fyear": fyear_compustat(fe) or "",
            "n_coregistrants": coreg.get(acc, 1),
            "joint_filing": 1 if coreg.get(acc, 1) > 1 else 0,
            "double_irish": 1 if cik in di else 0,
            "gvkey": d.get("gvkey", ""), "ticker": d.get("ticker", "") or c0.get("ticker", ""),
            "disclosure_class": best["_class"],
            "is_effect": 1 if eff else 0,
            "n_candidates": len(cs), "n_clean": len(clean),
            "max_score": max(c["_score"] for c in clean),
            "sentence_grade": best["_sg"], "evidence_tier": best["_tier"],
            "strongly_identified": 1 if any(c["_strong"] for c in eff) else 0,
            "record_type": best["_record"],
            "evidence_kind": ("assertion_of_past_transfer"
                              if (eff and all(c["_assert"] for c in eff))
                              else ("recorded_effect" if eff else "")),
            "names_the_standard": 1 if any(c["_std"] for c in clean) else 0,
            "period_text": best["period_text"], "period_cal_year": best["period_cal_year"],
            "transfer_date_stated": next((c["_tdate"] for c in clean if c["_tdate"]), ""),
            # the transfer-date phrase must come from the SAME candidate whose sentence is
            # being dated -- taking any candidate's date let Twitter's 2019 benefit inherit
            # a 2018 date from an unrelated sentence in the same filing
            **TT.timing(best["_class_sentence"], best["_record"], best["_tdate"],
                        filing_fyear=(fyear_compustat(fe) or ""),
                        is_effect=bool(eff)),
            **comp_fields,
            "amount": (None if (ba and text_amt is not None and xb and eff
                                and int(xb["xbrl_tag_rank"]) <= 3
                                and STRIPPED.search(ba["_class_sentence"] or ""))
                       else (text_amt if ba else "")) or (
                float(xb["xbrl_amount"]) if (xb and eff and int(xb["xbrl_tag_rank"]) <= 3)
                else ""),
            # where the figure came from. The corpus strips tables, so for 163 effect
            # filings the only number that exists is the one the filer tagged in XBRL.
            "amount_source": (
                "xbrl_text_was_stripped"
                if (ba and text_amt is not None and xb and eff
                    and int(xb["xbrl_tag_rank"]) <= 3
                    and STRIPPED.search(ba["_class_sentence"] or ""))
                else "text_after_strip"
                if (ba and text_amt is not None
                    and STRIPPED.search(ba["_class_sentence"] or ""))
                else "text" if (ba and text_amt is not None) else
                              ("xbrl" if (xb and eff and int(xb["xbrl_tag_rank"]) <= 3)
                               else "")),
            "amount_grade": (ba["_ag"] if (ba and text_amt is not None) else
                             ("X" if (xb and eff and int(xb["xbrl_tag_rank"]) <= 3) else "")),
            "xbrl_amount": (xb["xbrl_amount"] if xb else ""),
            "xbrl_tag": (xb["xbrl_tag"] if xb else ""),
            "xbrl_tag_rank": (xb["xbrl_tag_rank"] if xb else ""),
            "xbrl_dta_dtl": (xb["xbrl_dta_dtl"] if xb else ""),
            "xbrl_components": (xb.get("xbrl_components", "") if xb else ""),
            # XBRL as a CHECK on the text, not only as a filler. Where both exist they
            # agree 78% of the time; the disagreements are worth reading, because the
            # text picker is sometimes grabbing the wrong figure in the sentence
            # (Boston Scientific: 4.1bn from the sentence against a 55m tagged
            # cumulative effect).
            "amount_agrees_with_xbrl": ("text_was_stripped" if (
                ba and ba["_amt"] is not None and xb and eff
                and int(xb["xbrl_tag_rank"]) <= 3
                and STRIPPED.search(ba["_class_sentence"] or "")) else agree(
                (ba["_amt"] if ba else None),
                (float(xb["xbrl_amount"]) if xb and xb["xbrl_amount"] else None),
                (xb["xbrl_tag_rank"] if xb else None))),
            "effect_direction": (sign_near(ba["_class_sentence"], ba["_amt"])[0]
                                 if ba else "") or (ba or best)["effect_direction"],
            "dta_dtl": ((sign_near(ba["_class_sentence"], ba["_amt"])[1] if ba else "")
                        or (ba or best)["dta_dtl"]
                        or (xb["xbrl_dta_dtl"] if xb else "")),
            "sign_basis": ("read beside the figure" if (ba and any(
                sign_near(ba["_class_sentence"], ba["_amt"]))) else "cue counts across the window"),
            "us_verdict": uvb["_uv"], "destination": uvb["_ue"] or uvb["destination"],
            # every destination the filing's EFFECT sentences name, not just the chosen
            # one: a 10-K can carry two transfers to two places (Gilead's 2018 charge and
            # its 2019 transfer to Ireland sit in different filings, but nothing stops
            # them sharing one)
            "destinations_in_effect_sentences": "; ".join(sorted(
                {(c["_ue"] or c["destination"] or "").strip()
                 for c in (eff or clean)} - {""})),
            "us_verdicts_all": "; ".join(sorted({c["_uv"] for c in (eff or clean)})),
            "fp_candidates_dropped": len(cs) - len(clean),
            "sentence": best["_class_sentence"][:1500],
            "anchor_sentence": " ".join(best["anchor_sentence"].split())[:1500],
            "amount_sentence": (ba["_class_sentence"][:1500] if ba else ""),
            "file": c0["file"],
        })
    F.sort(key=lambda r: (r["cik"], r["filing_date"], r["accession"]))

    # ------------------------------------------------------------------ firms
    hist = collections.defaultdict(list)
    for l in logs:
        hist[l["cik"].lstrip("0")].append(iso8(l["filing_date"]))
    hist = {k: sorted(v) for k, v in hist.items()}

    def censor(cik, date):
        h = hist.get(cik.lstrip("0"), [])
        prior = sum(1 for x in h if x < date)
        return (h[0] if h else ""), prior, (1 if prior < CENSOR_MIN_PRIOR else 0)

    byc = collections.defaultdict(list)
    for r in F:
        byc[r["cik"]].append(r)
    R = []
    for cik, rs in byc.items():
        rs.sort(key=lambda r: (r["filing_date"], r["accession"]))
        eff = [r for r in rs if r["is_effect"]]
        ado = [r for r in rs if r["disclosure_class"] in ("adoption", "adoption_no_effect")]
        noe = [r for r in rs if r["disclosure_class"] == "adoption_no_effect"]
        evl = [r for r in rs if r["disclosure_class"] == "evaluating"]
        exp = [r for r in rs if r["disclosure_class"] == "expected_effect"]
        dated = [r for r in eff if r["transfer_timing"] in ("stated", "current_period")
                 and r["transfer_year"] != ""]
        st = [r for r in eff if r["transfer_timing"] == "stated"]
        strong = [r for r in eff if r["strongly_identified"]]
        amt = [r for r in eff if r["amount"] != ""]
        e0, s0, a0, d0 = firstof(eff), firstof(strong), firstof(amt), firstof(ado)
        v0, t0 = firstof(evl), (min(dated, key=lambda r: int(r["transfer_year"]))
                                if dated else None)
        first_in, prior, cens = censor(cik, e0["filing_date"]) if e0 else ("", "", "")
        if not e0:
            first_in = (hist.get(cik.lstrip("0")) or [""])[0]
        R.append({
            "cik": cik, "company": rs[-1]["company"],
            "double_irish": rs[0]["double_irish"],
            "gvkey": rs[0]["gvkey"], "ticker": rs[0]["ticker"],
            "ever_effect": 1 if eff else 0,
            "ever_adoption": 1 if ado else 0,
            "ever_adoption_no_effect": 1 if noe else 0,
            "first_filing_in_corpus": first_in,
            "first_any_mention_date": rs[0]["filing_date"],
            "first_any_mention_class": rs[0]["disclosure_class"],
            "first_adoption_date": d0["filing_date"] if d0 else "",
            "first_effect_date": e0["filing_date"] if e0 else "",
            "first_effect_accession": e0["accession"] if e0 else "",
            "first_effect_form": e0["form"] if e0 else "",
            "first_effect_datadate": e0["datadate"] if e0 else "",
            "first_effect_fyear": e0["fyear"] if e0 else "",
            "first_effect_record_type": e0["record_type"] if e0 else "",
            "first_effect_joint_filing": e0["joint_filing"] if e0 else "",
            "first_effect_sentence": e0["sentence"] if e0 else "",
            "n_prior_filings": prior,
            "first_effect_left_censored": cens,
            "first_strong_date": s0["filing_date"] if s0 else "",
            "first_strong_sentence": s0["sentence"] if s0 else "",
            "first_amount_date": a0["filing_date"] if a0 else "",
            "first_amount": a0["amount"] if a0 else "",
            "first_amount_grade": a0["amount_grade"] if a0 else "",
            "first_amount_direction": a0["effect_direction"] if a0 else "",
            "first_amount_dta_dtl": a0["dta_dtl"] if a0 else "",
            "first_amount_sentence": a0["amount_sentence"] if a0 else "",
            "max_amount": max((r["amount"] for r in amt), default=""),
            "last_effect_date": eff[-1]["filing_date"] if eff else "",
            "n_effect_filings": len(eff),
            "n_effect_10k": sum(1 for r in eff if r["form"] == "10-K"),
            "n_effect_10q": sum(1 for r in eff if r["form"] == "10-Q"),
            "effect_years": " ".join(sorted({r["filing_date"][:4] for r in eff})),
            "referred_period_years": " ".join(sorted({str(r["period_cal_year"])
                                                      for r in eff if r["period_cal_year"]})),
            "ever_strong": 1 if strong else 0,
            "ever_amount": 1 if amt else 0,
            # destination by year, so a firm that moved IP to Ireland in one year and to
            # the United States in another is not collapsed into a single verdict
            "destinations_by_year": "; ".join(
                f"{y}:{d}" for y, d in sorted(
                    {str(r["transfer_year"] or r["fyear"] or r["filing_date"][:4]):
                     (r["destination"] or "not stated") for r in eff}.items())),
            "ever_us_destination": 1 if any(r["us_verdict"] == "yes" for r in eff) else 0,
            "ever_non_us_destination": 1 if any(r["us_verdict"] == "no" for r in eff) else 0,
            "ever_cost": 1 if any(r["effect_direction"] == "cost" or r["dta_dtl"] == "DTL"
                                  for r in eff) else 0,
            "ever_xbrl_tagged": 1 if any(r["xbrl_amount"] != "" for r in rs) else 0,
            "n_amount_disagrees_xbrl": sum(1 for r in eff
                                           if r["amount_agrees_with_xbrl"] == "no"),
            "n_amounts_from_xbrl": sum(1 for r in eff if r["amount_source"] == "xbrl"),
            "ever_assertion_only": 1 if (eff and all(
                r["evidence_kind"] == "assertion_of_past_transfer" for r in eff)) else 0,
            "ever_current_transfer": 1 if any(r["record_type"] == "current_period_transfer"
                                              for r in eff) else 0,
            # ---- the boilerplate wave, kept apart from the population (22 Sep)
            "ever_evaluating": 1 if evl else 0,
            "n_evaluating_filings": len(evl),
            "first_evaluating_date": v0["filing_date"] if v0 else "",
            "first_evaluating_sentence": v0["sentence"] if v0 else "",
            "days_evaluating_to_effect": ((dt.date.fromisoformat(e0["filing_date"])
                                           - dt.date.fromisoformat(v0["filing_date"])).days
                                          if (v0 and e0) else ""),
            "ever_expected_effect": 1 if exp else 0,
            "first_expected_effect_date": firstof(exp)["filing_date"] if exp else "",
            # ---- WHEN the transfer happened, which is not when it was disclosed (22 Sep)
            "first_transfer_year": t0["transfer_year"] if t0 else "",
            "first_transfer_year_basis": t0["transfer_year_basis"] if t0 else "",
            "first_transfer_timing": (e0["transfer_timing"] if e0 else ""),
            "transfer_years_stated": " ".join(sorted({str(r["transfer_year"]) for r in st
                                                      if r["transfer_year"] != ""})),
            "transfer_years_dated": " ".join(sorted({str(r["transfer_year"]) for r in dated})),
            "transfer_year_upper_bound": min((str(r["transfer_year_upper_bound"])
                                              for r in eff
                                              if r["transfer_year_upper_bound"] != ""),
                                             default=""),
            "transfer_date_never_stated": 1 if (eff and not dated) else 0,
            "n_effect_pre_adoption": sum(1 for r in eff
                                         if r["transfer_timing"] == "pre_adoption"),
            # the lag is only meaningful WITHIN one filing: first_transfer_year can come
            # from a later filing than the first effect, which made this negative for 22
            # firms. It is left empty unless the first effect filing dates itself.
            "years_disclosure_after_transfer": (
                (int(e0["filing_date"][:4]) - int(e0["transfer_year"]))
                if (e0 and str(e0["transfer_year"]).isdigit()) else ""),
        })
    R.sort(key=lambda r: (-r["ever_effect"], r["first_effect_date"] or "9999", r["cik"]))

    # ------------------------------------------------------------ denominators
    Y = collections.defaultdict(lambda: {"f": 0, "firms": set(), "ef": 0, "efirms": set(),
                                         "af": set()})
    effk = {(r["cik"].lstrip("0"), r["accession"]) for r in F if r["is_effect"]}
    adok = {(r["cik"].lstrip("0"), r["accession"]) for r in F
            if r["disclosure_class"] in ("adoption", "adoption_no_effect")}
    for l in logs:
        y, k = l["filing_date"][:4], (l["cik"].lstrip("0"), l["accession"])
        Y[y]["f"] += 1
        Y[y]["firms"].add(l["cik"])
        if k in effk:
            Y[y]["ef"] += 1
            Y[y]["efirms"].add(l["cik"])
        if k in adok:
            Y[y]["af"].add(l["cik"])
    byyear = [{"year": y, "filings_read": v["f"], "firms_read": len(v["firms"]),
               "effect_filings": v["ef"], "effect_firms": len(v["efirms"]),
               "adoption_only_firms": len(v["af"] - v["efirms"]),
               "pct_firms_effect": round(100 * len(v["efirms"]) / max(len(v["firms"]), 1), 2)}
              for y, v in sorted(Y.items())]

    # ------------------------------------------------------------------ write
    fdf, rdf, ydf = pd.DataFrame(F), pd.DataFrame(R), pd.DataFrame(byyear)
    for df in (fdf, rdf):
        bad = [c for c in df.columns if len(c) > 32 or not re.fullmatch(r"[A-Za-z_]\w*", c)]
        if bad:   # pandas would rename these SILENTLY and the .dta would stop matching
            raise SystemExit(f"column names Stata would rename: {bad}")
    fdf.to_csv(HERE / "population_filings_Claude.csv", index=False)
    rdf.to_csv(HERE / "population_firms_Claude.csv", index=False)
    ydf.to_csv(HERE / "population_by_year_Claude.csv", index=False)
    if not a.no_dta:
        for df, name in ((fdf, "population_filings_Claude"), (rdf, "population_firms_Claude")):
            out = df.copy()
            for col in out.columns:
                if out[col].dtype == object:
                    out[col] = out[col].fillna("").astype(str)
            longs = [c for c in out.columns if out[c].dtype == object
                     and out[c].str.len().max() > 2000]
            out.to_stata(HERE / f"{name}.dta", write_index=False, version=118,
                         convert_strl=longs)
    write_codebook()

    nf, nfirm = len(logs), len({l["cik"] for l in logs})
    ne = sum(1 for r in F if r["is_effect"])
    pop = [r for r in R if r["ever_effect"]]
    print(f"read: {nf:,} filings, {nfirm:,} firms, {n_cand:,} candidates")
    print(f"filings with any clean mention: {len(F):,}")
    for k in ("effect", "expected_effect", "adoption_no_effect", "adoption",
              "evaluating", "standard"):
        print(f"   class {k:<19}{sum(1 for r in F if r['disclosure_class']==k):>6,}")
    print(f"\nPOPULATION -- firms with at least one EFFECT filing: {len(pop):,} "
          f"({len(pop)/nfirm:.1%} of {nfirm:,} firms read), {ne:,} effect filings; "
          f"Double Irish among them: {sum(r['double_irish'] for r in pop)}")
    nc = sum(r["first_effect_left_censored"] for r in pop)
    print(f"  first effect LEFT-CENSORED: {nc:,}; a clean first effect for {len(pop)-nc:,}")
    print(f"  with an amount: {sum(r['ever_amount'] for r in pop):,};  strongly identified: "
          f"{sum(r['ever_strong'] for r in pop):,};  a COST / DTL: {sum(r['ever_cost'] for r in pop):,};"
          f"  names the US: {sum(r['ever_us_destination'] for r in pop):,}")
    tw = collections.Counter(r["transfer_timing"] for r in F if r["is_effect"])
    print(f"  WHEN the transfer happened, across {ne:,} effect filings: "
          + ", ".join(f"{k} {v:,}" for k, v in tw.most_common()))
    nd = sum(1 for r in pop if r["first_transfer_year"] != "")
    lag = [r["years_disclosure_after_transfer"] for r in pop
           if r["years_disclosure_after_transfer"] != ""]
    print(f"  firms with a DATED transfer: {nd:,} of {len(pop):,}; "
          f"never dated (catch-up only): {sum(r['transfer_date_never_stated'] for r in pop):,}")
    if lag:
        print(f"  years from transfer to first disclosure: median "
              f"{sorted(lag)[len(lag)//2]}, max {max(lag)} (n={len(lag)})")
    nv = sum(1 for r in R if r["ever_evaluating"])
    nvo = sum(1 for r in R if r["ever_evaluating"] and not r["ever_effect"])
    print(f"EVALUATING (\"we are assessing the impact\") -- {nv:,} firms, "
          f"{sum(1 for r in F if r['disclosure_class']=='evaluating'):,} filings; "
          f"{nvo:,} of them never disclose an effect")
    print(f"COMPARISON GROUP -- adoption only, never an effect: "
          f"{sum(1 for r in R if r['ever_adoption'] and not r['ever_effect']):,} firms "
          f"(of which say 'no material effect': "
          f"{sum(1 for r in R if r['ever_adoption_no_effect'] and not r['ever_effect']):,})")
    print("\nby filing year (denominators are filings and firms READ that year):")
    print(ydf.to_string(index=False))


CODEBOOK = [
    ("cik", "both", "SEC Central Index Key, 10-digit zero-padded string. Join to Compustat comp.company.cik -> gvkey"),
    ("accession", "filings", "SEC accession number. NOT unique alone: a joint filing carries several CIKs. Primary key is (cik, accession)"),
    ("form", "filings", "10-K or 10-Q. Amendments are not in the corpus"),
    ("filing_date", "filings", "Date filed with the SEC (YYYY-MM-DD). THE EVENT DATE for stock-price work"),
    ("company", "both", "Company name from the filing header (latest filing, in the firm table)"),
    ("datadate", "filings", "The filing's period of report = Compustat datadate. Join gvkey+datadate to funda (10-K) or fundq (10-Q)"),
    ("fiscal_year_end", "filings", "End of the fiscal year the filing belongs to (for a 10-Q, the next 10-K year end)"),
    ("fyear", "filings", "Compustat fiscal year: year of fiscal_year_end, minus 1 when it ends January-May. NOT the SEC label"),
    ("n_coregistrants", "filings", "CIKs sharing this accession. >1 = a joint filing (holding company plus subsidiaries, or a family of trusts)"),
    ("joint_filing", "filings", "1 if the accession is filed under more than one CIK. A co-registrant subsidiary may have no traded stock"),
    ("double_irish", "both", "1 if the firm is in the Double Irish population"),
    ("gvkey", "both", "Compustat gvkey where already known (Double Irish firms only); otherwise join via cik"),
    ("ticker", "both", "Ticker where already known (Double Irish firms only)"),
    ("disclosure_class", "filings", "What the filing asserts, strongest first: effect / expected_effect (a sized forecast) / adoption_no_effect / adoption / standard. Precision of effect: 38 of 40 on a held-out read, 21 Sep 2026. See disclosure_class_Claude.py"),
    ("is_effect", "filings", "1 if the filing records a consequence or asserts a transfer. THE POPULATION DEFINITION"),
    ("n_candidates", "filings", "Anchor matches in the filing, including flagged false-positive families"),
    ("n_clean", "filings", "Anchor matches with no false-positive family flag"),
    ("max_score", "filings", "Highest candidate score. Kept for reference; it does NOT define the population"),
    ("sentence_grade", "filings", "Phase A grade: A = firm asserts a completed event in its own voice; B = prose; C = table residue, forecast, auditor, backward reference"),
    ("evidence_tier", "filings", "Phase A tier: 1 asserted+amount, 2 asserted, 3 transfer prose+amount, 4 XBRL only, 5 prose only"),
    ("strongly_identified", "filings", "1 if an effect candidate is tier 1-3 AND the period dating it is inside the asserting sentence"),
    ("amount_agrees_with_xbrl", "filings", "yes/no ONLY where the tagged fact is the adjustment itself (tag rank 1-2), so the two are the same quantity; different_line_item where the tag is a balance or an account and the numbers are not comparable"),
    ("n_amount_disagrees_xbrl", "firms", "Effect filings where the text amount and the tagged amount disagree"),
    ("amount_components", "filings", "Every figure in the disclosure, typed by the account it belongs to and signed: type+=value; 'stripped' where the corpus removed the number but the account is known"),
    ("n_amount_components", "filings", "How many typed figures this filing yielded"),
    ("amount_stripped_components", "filings", "Accounts whose figure the corpus removed"),
    ("amount_headline", "filings", "The component chosen as the single figure, in the fixed order retained earnings > P&L tax effect > deferred tax asset > deferred tax liability > prepaid"),
    ("amount_component_type", "filings", "WHICH component amount_headline is. Never compare amounts across different types"),
    ("amount_component_basis", "filings", "How that figure found its account: nearest account, a 'respectively' list, or an XBRL tag"),
    ("amt_retained_earnings", "filings", "The cumulative-effect adjustment to retained earnings or accumulated deficit, signed"),
    ("amt_tax_pl", "filings", "The income tax benefit or expense recognised in the period, signed"),
    ("amt_deferred_tax_asset", "filings", "The deferred tax asset recognised, signed"),
    ("amt_deferred_tax_liability", "filings", "The deferred tax liability recognised, signed"),
    ("amt_prepaid", "filings", "The prepaid tax asset or deferred charge written off, signed"),
    ("amt_valuation_allowance", "filings", "Valuation allowance movement, signed"),
    ("amt_other_assets", "filings", "Other assets or liabilities moved, signed"),
    ("amt_noncontrolling_interest", "filings", "Noncontrolling interest moved, signed"),
    ("amount_source", "filings", "text = read from the sentence; xbrl = the tagged fact, where the sentence carried no figure; xbrl_text_was_stripped = the sentence's own figure was stripped by the corpus and the picker had reached for a neighbouring number, so the tagged fact is used instead; text_after_strip = the sentence was stripped and no tagged fact exists, so the text figure is the best available and should be treated as suspect"),
    ("xbrl_amount", "filings", "The amount from the filer's XBRL, chosen by tag rank (cumulative effect > quantified effect > deferred tax > account moved)"),
    ("xbrl_tag", "filings", "The XBRL element the amount came from. Read it before using the number"),
    ("xbrl_tag_rank", "filings", "1 cumulative-effect adjustment, 2 quantified effect, 3 deferred tax asset/liability, 4 account moved, 9 an equity total -- never the amount"),
    ("xbrl_components", "filings", "Every tagged component of the same adoption entry, tag=value, strongest tag first. The retained-earnings adjustment, the deferred tax asset and the prepaid written off are different numbers from one event -- pick the one the question needs"),
    ("xbrl_dta_dtl", "filings", "DTA or DTL read from the ELEMENT NAME, which states it outright"),
    ("ever_xbrl_tagged", "firms", "1 if any filing of this firm carries an ASU 2016-16 tagged fact"),
    ("n_amounts_from_xbrl", "firms", "Effect filings whose amount came from XBRL because the corpus stripped it"),
    ("evidence_kind", "filings", "recorded_effect = the firm books a consequence in this period; assertion_of_past_transfer = it states a past transfer (an obligation or an unrecorded deferred tax asset related to one) without recording anything now. Both are in the population; filter on this to drop the second"),
    ("ever_assertion_only", "firms", "1 if EVERY effect filing this firm has is an assertion rather than a recorded effect"),
    ("record_type", "filings", "adoption_catchup (books the effect of PAST transfers; not the transfer date) or current_period_transfer"),
    ("names_the_standard", "filings", "1 if 'ASU 2016-16' appears. Many real disclosures never name it"),
    ("period_text", "filings", "The period phrase the disclosure refers to, as written"),
    ("period_cal_year", "filings", "Calendar year of the period the disclosure REFERS to -- distinct from filing_date"),
    ("transfer_date_stated", "filings", "A transfer date stated inside the sentence, where the firm gives one"),
    ("amount", "filings", "Tax effect in dollars, read only from an effect sentence. A TAX EFFECT, never an IP value"),
    ("amount_grade", "filings", "A = from the transfer sentence itself; B = adjacent sentence with effect language"),
    ("effect_direction", "filings", "benefit or cost. A transfer into a higher-tax jurisdiction can be a COST"),
    ("dta_dtl", "filings", "DTA, DTL, both or none"),
    ("destinations_in_effect_sentences", "filings", "Every destination named by an effect sentence in this filing"),
    ("us_verdicts_all", "filings", "Every US verdict across this filing's effect candidates; more than one value means the filing carries more than one transfer"),
    ("destinations_by_year", "firms", "Destination per transfer year, e.g. '2018:not stated; 2019:Ireland'. A firm can transfer to different places in different years"),
    ("sign_basis", "filings", "Whether effect_direction/dta_dtl were read beside the chosen figure or from cue counts across the window"),
    ("us_verdict", "filings", "yes = US named as destination in the transfer sentence; no = excluded or another country; unnamed; not_stated. Read from the best EFFECT sentence in the filing, not from the most US-ish candidate anywhere in it"),
    ("destination", "filings", "The destination named, where one is"),
    ("fp_candidates_dropped", "filings", "Candidates flagged as a false-positive family (common control, elimination policy)"),
    ("sentence", "filings", "The sentence that earned the class -- for an effect, the sentence carrying it, which may follow the anchor"),
    ("anchor_sentence", "filings", "The sentence the anchor matched"),
    ("amount_sentence", "filings", "The sentence the amount was read from"),
    ("file", "filings", "Corpus file name"),
    ("ever_effect", "firms", "1 if any filing records an effect or asserts a transfer. THE POPULATION"),
    ("ever_adoption", "firms", "1 if any filing states adoption of ASU 2016-16"),
    ("ever_adoption_no_effect", "firms", "1 if any filing states adoption with no material effect -- a comparison group"),
    ("first_filing_in_corpus", "firms", "The firm's first filing of any kind in the corpus (2016 onward, or its IPO)"),
    ("first_any_mention_date", "firms", "Earliest filing with any clean candidate, whatever it says"),
    ("first_any_mention_class", "firms", "Class of that first mention"),
    ("first_adoption_date", "firms", "Earliest filing stating adoption"),
    ("first_effect_date", "firms", "Earliest filing recording an effect or asserting a transfer. RECOMMENDED EVENT DATE"),
    ("first_effect_accession", "firms", "Accession of that filing"),
    ("first_effect_form", "firms", "Form of that filing"),
    ("first_effect_datadate", "firms", "Compustat datadate of that filing"),
    ("first_effect_fyear", "firms", "Compustat fyear of that filing"),
    ("first_effect_record_type", "firms", "adoption_catchup or current_period_transfer"),
    ("transfer_timing", "filings", "WHEN the transfer happened: stated / current_period / pre_adoption (a catch-up: before adoption, date not given) / unknown"),
    ("transfer_year", "filings", "Calendar year of the TRANSFER where the filing dates it. Empty for pre_adoption catch-ups -- the filing does not say"),
    ("transfer_year_basis", "filings", "Where transfer_year came from. Read this before using the year"),
    ("transfer_year_upper_bound", "filings", "Transfers happened no later than this year. For a catch-up this is the adoption year and is NOT the transfer date"),
    ("adoption_year_stated", "filings", "Adoption year named in the sentence, where given"),
    ("transfer_period_text", "filings", "The period phrase that dated the transfer, as written"),
    ("first_transfer_year", "firms", "Earliest dated transfer year for the firm. THE TRANSFER DATE for event work, where it exists"),
    ("first_transfer_year_basis", "firms", "How first_transfer_year was established"),
    ("first_transfer_timing", "firms", "Timing basis of the FIRST effect filing"),
    ("transfer_years_stated", "firms", "Every transfer year the firm states outright"),
    ("transfer_years_dated", "firms", "Every transfer year, stated or from the reporting period"),
    ("transfer_year_upper_bound", "firms", "Earliest upper bound across the firm's effect filings"),
    ("transfer_date_never_stated", "firms", "1 if no filing dates a transfer: adoption catch-up only. Use the Compustat deferred tax asset jump instead"),
    ("n_effect_pre_adoption", "firms", "Effect filings that are catch-ups on pre-adoption transfers"),
    ("years_disclosure_after_transfer", "firms", "Years between the transfer and its disclosure, measured INSIDE the first effect filing. Empty when that filing does not date the transfer"),
    ("ever_evaluating", "firms", "1 if the firm ever said it was evaluating the standard's impact, before disclosing anything"),
    ("n_evaluating_filings", "firms", "Filings in the evaluating class"),
    ("first_evaluating_date", "firms", "First time the firm said it was assessing the standard. A dated pre-disclosure signal, NOT a disclosure"),
    ("first_evaluating_sentence", "firms", "That sentence, verbatim"),
    ("days_evaluating_to_effect", "firms", "Days from first evaluating to first effect. Empty if either is missing"),
    ("ever_expected_effect", "firms", "1 if the firm ever gave a sized forecast of the effect before recording it"),
    ("first_expected_effect_date", "firms", "First sized forecast"),
    ("first_effect_joint_filing", "firms", "1 if that filing was a joint filing"),
    ("first_effect_sentence", "firms", "The first effect sentence, verbatim"),
    ("n_prior_filings", "firms", "Filings by the firm before its first effect. The clean history behind calling it FIRST"),
    ("first_effect_left_censored", "firms", "1 if fewer than 4 prior filings: may have disclosed before the corpus could see it"),
    ("first_strong_date", "firms", "Earliest strongly identified effect filing"),
    ("first_strong_sentence", "firms", "That sentence, verbatim"),
    ("first_amount_date", "firms", "Earliest effect filing with an amount read"),
    ("first_amount", "firms", "That amount, in dollars (tax effect)"),
    ("first_amount_grade", "firms", "Its grade"),
    ("first_amount_direction", "firms", "benefit or cost"),
    ("first_amount_dta_dtl", "firms", "DTA / DTL named with it"),
    ("first_amount_sentence", "firms", "The sentence it came from, verbatim"),
    ("max_amount", "firms", "Largest amount across the firm's effect filings"),
    ("last_effect_date", "firms", "Latest effect filing"),
    ("n_effect_filings", "firms", "Effect filings, all forms"),
    ("n_effect_10k", "firms", "... of which 10-K"),
    ("n_effect_10q", "firms", "... of which 10-Q"),
    ("effect_years", "firms", "Calendar years with an effect filing"),
    ("referred_period_years", "firms", "Calendar years the effect disclosures REFER to. More than one can mean more than one transfer"),
    ("ever_strong", "firms", "1 if any effect is strongly identified"),
    ("ever_amount", "firms", "1 if any amount was read"),
    ("ever_us_destination", "firms", "1 if any effect names the US as destination in the transfer sentence"),
    ("ever_non_us_destination", "firms", "1 if any effect excludes the US or names another country"),
    ("ever_cost", "firms", "1 if any effect is a cost or names a DTL"),
    ("ever_current_transfer", "firms", "1 if any effect is a current-period transfer rather than an adoption catch-up"),
]


def write_codebook():
    with (HERE / "population_codebook_Claude.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["column", "table", "description"])
        w.writerows(CODEBOOK)


if __name__ == "__main__":
    main()
