#!/usr/bin/env python3
r"""What a disclosure ASSERTS -- the test that decides who is in the population.

WHY THIS EXISTS
---------------
Built 21 September after reading the first full population. A candidate's SCORE could
not separate a real disclosure from boilerplate: Hyatt's "we are currently evaluating the
impact of adopting ASU 2016-16" scored 7, Unifirst's "In October 2016, the FASB issued
updated guidance..." scored 6, and both became their firm's "first disclosure". On the
precision sample that problem was diluted; on the first-mention column -- which selects
each firm's EARLIEST filing, and so concentrates on the 2016-17 boilerplate wave -- it
dominated. Score measures how much a passage looks like the topic, not what it says.

And ASU 2016-16 was MANDATORY. Nearly every US registrant adopted it in 2018. A firm
saying "we adopted ASU 2016-16" has told us about a compliance date, not about a
transfer. Counting that as a disclosure turns the population into "firms that mentioned a
mandatory standard".

THE FOUR CLASSES, strongest first
----------------------------------
    effect               the firm records a consequence or asserts a transfer, in the
                         past tense, in its own voice, in an intra-entity context:
                         "Entergy recorded an adjustment to retained earnings of 56
                         million ... from intra-entity asset transfers"; "we recognized a
                         gain on the transfer of intellectual property to our Irish
                         subsidiary"; "we changed our international corporate structure"
    expected_effect      a forecast of an effect ("we expect ... a 10-15 million
                         increase to accumulated deficit") -- exposure, not a record
    adoption_no_effect   the firm adopted it and says it had no (material) effect --
                         a natural comparison group: exposed to the rule, nothing to book
    adoption             the firm adopted it and says nothing about an effect
    standard             describes the standard, forecasts, or evaluates

`effect` is the population definition.

THE SENTENCE AFTER THE ANCHOR
------------------------------
The classic disclosure puts the standard first and the effect second: "[ASU 2016-16
accelerates the recognition of ...] Upon adoption, we recorded a 66 million increase to
retained earnings." So the one or two sentences following the anchor are read as well --
but only when they visibly continue the same disclosure (they open "Upon adoption", "As a
result", or name the standard or an intra-entity transfer). Without that guard, Hyatt's
evaluation sentence followed by an unrelated 311 million would read as an effect.

MEASURED, 21 September, on the fixed-seed sample (133 flagged filings): 41 filings
classify as `effect`, 38 of which were read as genuine. The three that were not are
Mohawk (a tax authority's allegation about an acquiree's IP transfer), Cardinal Health
(a third-party IP agreement) and Ironwood (boilerplate). Known misses: Theravance,
Orthofix, Darden -- effects stated in a form these patterns do not reach.
"""
from __future__ import annotations

import re

# a span that may cross the decimal point in "2.7 billion" -- without this, Apple's
# "recorded 2.7 billion of net deferred tax assets" stops at the "." and never matches
_NP = r"(?:[^.]|\.(?=\d))"
_V = r"(?:recorded|recognized|recognised|booked|reflected|realized|recording|recognizing|reversed)"

EFFECT = re.compile(
    rf"\b{_V}\b{_NP}{{0,140}}?(?:deferred\s+tax|tax\s+(?:benefit|expense|charge|provision)|"
    r"income\s+tax|retained\s+earnings|accumulated\s+deficit|cumulative[-\s]effect|"
    r"\bgain\b|\bloss\b|adjustment|reduction|decrease|increase|step[-\s]up|prepaid)"
    r"|cumulative[-\s]effect\s+adjustment\s+(?:of|to|directly|decreasing|increasing|that|"
    r"which|reducing|resulting)"
    # the figure can sit between the noun and the account: Amazon's "an increase of
    # approximately 250 million to retained earnings and deferred tax assets"
    r"|(?:increase|decrease|reduction|adjustment)s?\s+(?:of\s+(?:approximately\s+|about\s+)?"
    r"[\d.,]+\s*(?:million|billion|thousand)?\s+)?(?:in|to|of)\s+(?:the\s+|our\s+|its\s+)?"
    r"(?:opening\s+|beginning\s+)?(?:balance\s+of\s+)?(?:retained\s+earnings|accumulated\s+deficit)"
    r"|result(?:ed|ing|s)?\s+in\s+(?:(?:a|an)\b|approximately|\d)" + _NP + r"{0,80}?(?:benefit|expense|charge|"
    r"increase|decrease|adjustment|deferred|reduction|gain|reclassification|write[-\s]?off|"
    r"retained\s+earnings|accumulated\s+deficit)"
    r"|(?:impact|effect)\s+of\s+(?:the\s+)?adoption\b" + _NP + r"{0,80}?\bwas\s+(?:a|an)\s+"
    r"(?:reclassification|reduction|increase|decrease|adjustment|net)"
    # "a 588 million deferred tax charge on previously acquired intangible assets resulting
    # from a transfer of these assets between wholly owned subsidiaries" (Gilead FY2018):
    # the transfer is named without the words intra-entity or intercompany, and the effect
    # is a CHARGE. Missing it is the cost-side blind spot the project warns about.
    r"|(?:as\s+a\s+result\s+of|related\s+to|relating\s+to|resulting\s+from|due\s+to|from)\s+"
    r"(?:a|an|the|these|certain|our|its)?\s*(?:intra[-\s]?entity\s+|intercompany\s+|"
    r"inter[-\s]company\s+|intra[-\s]?group\s+|internal\s+|intra[-\s]?company\s+)?"
    r"transfers?\s+of\b"
    r"|(?:as\s+a\s+result\s+of|related\s+to|relating\s+to|resulting\s+from|due\s+to|offset\s+by|driven\s+by|"
    r"attributable\s+to|associated\s+with)\s+(?:the\s+|an?\s+|certain\s+|our\s+)?"
    r"(?:intra[-\s]?entity|intercompany|inter[-\s]company|intra[-\s]?group)\s+"
    r"(?:transfers?|sales?|asset)"
    r"|\b(?:completed|transferred|sold|undertook|implemented|executed|effected|changed|"
    r"consolidated|restructured|reorganized|migrated|licensed)\b" + _NP + r"{0,100}?"
    r"(?:intellectual\s+propert|intangible|\bIP\b|legal\s+entity|tax\s+structure|"
    r"corporate\s+structure|restructuring|reorganization)", re.I)

STANDARD = re.compile(
    r"the\s+FASB\s+issued|FASB\s+issued|issued\s+ASU|"
    r"(?:this|the|new)\s+(?:ASU|update|guidance|standard|amendments?|amended\s+guidance)\s+"
    r"(?:will\s+(?:now\s+)?)?(?:require|requires|eliminates?|removes?|simplif|improv|clarif|"
    r"amends?|accelerates?|provides?|instructs?)"
    r"|is\s+effective\s+for|will\s+be\s+effective|effective\s+for\s+(?:fiscal|annual|public|interim)"
    r"|(?:currently\s+)?(?:is|are|were|was)\s+(?:currently\s+)?evaluating|will\s+require"
    r"|would\s+require|under\s+(?:current|prior|existing|previous|the\s+prior)\s+"
    r"(?:GAAP|guidance|rules)|prohibit(?:s|ed|ion)|early\s+adoption\s+(?:is\s+)?permitted"
    r"|must\s+be\s+applied|(?:expects?|anticipates?)\s+to|will\s+adopt|plans?\s+to\s+adopt", re.I)

NO_EFFECT = re.compile(
    r"no\s+(?:material\s+|significant\s+)?(?:impact|effect)|did\s+not\s+have\s+(?:a|any)\s+"
    r"(?:material\s+|significant\s+)?(?:impact|effect)|did\s+not\s+have\s+(?:a|any)\s+"
    r"(?:material|significant)|not\s+(?:have\s+)?(?:a\s+)?(?:material|significant)\s+"
    r"(?:impact|effect)|(?:was|were|is)\s+(?:not\s+material|immaterial)"
    r"|did\s+not\s+result\s+in\s+(?:a|any)|no\s+(?:cumulative[-\s]effect|adjustment)", re.I)

ADOPTED = re.compile(
    # case-sensitive name, as in FIRM_PAST -- under re.I "[A-Z]\w+ adopted" matched
    # "is required to BE adopted", which is the rule, not the firm
    r"(?:\b(?:we|the\s+company|the\s+corporation)|(?-i:\b[A-Z][A-Za-z&.\-]+))\s+(?:early\s+)?adopted\b"
    r"|\bupon\s+(?:the\s+)?adoption\b|\bwas\s+adopted\b|\b(?:early\s+)?adopted\s+(?:ASU|the\s+"
    r"(?:ASU|standard|guidance|update|amendments?))", re.I)

CONTINUES = re.compile(
    # Starbucks puts the effect in the sentence after the heading: "The primary impact of
    # the adoption was an increase to deferred income taxes, net of 227.6 million"
    r"^\s*the\s+(?:primary\s+)?(?:impact|effect)\s+of\s+(?:the\s+|our\s+)?adopt"
    r"|^\s*(?:as\s+a\s+result|upon\s+(?:the\s+)?adoption|the\s+adoption|in\s+connection\s+with"
    r"|accordingly|consequently|this\s+(?:adoption|resulted|update|guidance|change)|"
    r"(?:we|the\s+company)\s+(?:adopted|recorded|recognized))"
    r"|2016\s*-?\s*16|intra[-\s]?entity|intercompany|intra[-\s]?group|cumulative[-\s]effect"
    r"|upon\s+adoption|modified\s+retrospective", re.I)
_SPLIT = re.compile(r"(?<=[a-z0-9)\]])\.\s+(?=[A-Z(])")
# a continuation sentence that names ANOTHER standard is not this disclosure continuing.
# Cisco's anchor is a footnote about ASC 606 reclassifications, and the sentence after it
# reads "We recognized a 152 million benefit ... relating to indirect effects from the
# adoption of ASC 606" -- a revenue-standard effect that was being read, amount and all,
# as an intra-entity transfer effect. Found in the held-out read of 23 September.
OTHER_STD = re.compile(
    r"\bASC\s*606\b|\bASU\s*(?:No\.\s*)?201[0-9]\s*-\s*(?!16\b)\d{2}\b"
    r"|revenue\s+from\s+contracts\s+with\s+customers|\bASC\s*842\b|\bASU\s*2016-02\b"
    r"|lease\s+accounting|credit\s+losses|\bCECL\b", re.I)

# ---- added 21 September, after a fresh random read of 40 population first-effects
# scored ~9 genuine of 40. The single biggest leak was the standard's own TRANSITION
# sentence, copied into hundreds of filings:
#   "The amendments ... should be applied on a modified retrospective basis through a
#    cumulative-effect adjustment directly to retained earnings as of the beginning of
#    the period of adoption."
# EFFECT matched "cumulative-effect adjustment directly" and read the rule's
# INSTRUCTIONS as the firm recording something. The rest were forecasts, third-party
# sales, table residue and generic descriptions of the rule.
TRANSITION = re.compile(
    r"(?:should|must|shall|will|would)\s+be\s+(?:applied|adopted|recorded|recognized)"
    r"|(?:is|are)\s+required\s+to\s+be\s+(?:applied|adopted)|required\s+to\s+(?:be\s+)?appl"
    r"|applied\s+(?:on|using)\s+a\s+modified\s+retrospective"
    r"|as\s+of\s+the\s+beginning\s+of\s+the\s+(?:period|fiscal\s+year|year)\s+of\s+adoption"
    r"|requires?\s+(?:that\s+|than\s+)?(?:an?\s+)?(?:entit|compan|the\s+recognition|recognition)"
    r"|(?:is|are)\s+recognized\s+in\s+the\s+period\s+in\s+which|for\s+example"
    r"|\bIAS\s+12\b|ASU\s*(?:No\.\s*)?2016\s*-?\s*16\s+(?:requires|will\s+require|eliminates|"
    r"removes|simplifies|improves|clarifies|changes)", re.I)
FUTURE = re.compile(
    r"\bwill\b|\bwould\b|\bexpects?\b|\bexpected\b|\banticipat|\bestimat|\bintends?\b"
    r"|\bplans?\s+to\b|\bcould\b|\bmay\s+(?:result|have)", re.I)
# an effect only counts in an intra-entity or adoption context -- Rite Aid's "sale of the
# related distribution center and non-inventory assets resulted in a pre-tax gain" and
# MiMedx's divestiture "transfer of intangible assets" are third-party transactions
INTRA = re.compile(
    r"intra[-\s]?entity|intercompany|inter[-\s]company|intra[-\s]?group|2016\s*-?\s*16"
    r"|(?:to|from|between)\s+(?:our|its|a|an|certain|the)?\s*(?:\w+\s+){0,2}"
    r"(?:subsidiar|affiliate|entities)|legal\s+entit|corporate\s+structure|tax\s+structure"
    r"|upon\s+(?:the\s+)?adoption|the\s+adoption|\badopted\b|modified\s+retrospective"
    r"|cumulative[-\s]effect|step[-\s]up\s+in\s+(?:local\s+)?tax\s+basis"
    # -- added 22 Sep. "internal transfer of certain intangible assets" (Bristol-Myers
    #    Squibb) is an intra-entity transfer written without either word. The noun must
    #    follow immediately, so "internal controls", "internal use software" and
    #    "internal investigation" cannot reach it.
    r"|internal\s+(?:transfers?|sales?|restructurings?|reorganizations?)\b", re.I)
# INTRA is deliberately loose: it lets "upon adoption", "cumulative-effect" and
# "modified retrospective" stand in for the topic, because the FIRM_PAST route already
# requires the firm to be the subject, and a firm saying "we recorded X upon adoption"
# inside an ASU 2016-16 anchor is talking about this standard. The impersonal route below
# has no such anchor, and those same words fit ASC 606, ASU 2016-09 and the lease standard
# exactly as well -- which is what 31 of 136 unread promotions turned out to be. So the
# impersonal route requires the topic NAMED.
INTRA_STRICT = re.compile(
    r"intra[-\s]?entity|intercompany|inter[-\s]company|intra[-\s]?group|2016\s*-?\s*16"
    r"|internal\s+(?:transfers?|sales?|restructurings?|reorganizations?)"
    r"|(?:to|from|between)\s+(?:our|its|a|an|certain|the)?\s*(?:\w+\s+){0,2}"
    r"(?:subsidiar|affiliate|entities)|legal\s+entit|corporate\s+structure|tax\s+structure",
    re.I)
# a "sentence" that is mostly figures is a stripped table, not an assertion. The same
# instrument the amount parser uses against rate tables, at the same order of threshold:
# Gilead's tax-expense table carries 92 numbers in 132 words.
NUMS = re.compile(r"\b\d[\d,.]*\b")
MAX_NUMS = 12

# The subject must be the FIRM: "we", "the Company", or a capitalised name -- matched
# case-SENSITIVELY. Under re.I, [A-Z]\w+ matched any word, so the transition text's
# passive "adjustment RECORDED in retained earnings" read as a firm recording something.
# The verb must also take an object: a verb followed straight by "in/to/directly/as" is
# passive ("recorded in retained earnings"), which is the rule talking, not the firm.
_SUBJ = r"(?:\b(?:we|the\s+company|the\s+corporation|the\s+registrant)|(?-i:\b[A-Z][A-Za-z&.\-]+))"
_PASSIVE = r"(?!\s+(?:in|to|directly|as|on|at|within|through|against|by)\b)"
FIRM_PAST = re.compile(
    _SUBJ + r"\s+(?:has\s+|had\s+)?"
    r"(?:recorded|recognized|recognised|completed|transferred|sold|adopted|changed|"
    r"implemented|booked|reflected|reversed|wrote\s+off)\b" + _PASSIVE + r"|\bresult(?:ed|ing)\s+in\b"
    r"|upon\s+(?:the\s+)?adoption,?\s+(?:we|the\s+company|[A-Z][\w&.\-]+)\s+(?:recorded|recognized)"
    # a stated past period is the firm reporting what happened (Waters: "the change in the
    # valuation allowance during the year ended December 31, 2018 is primarily due to the
    # write-off of a valuation allowance to Retained Earnings ... intra-entity transfers")
    r"|during\s+the\s+(?:fiscal\s+)?(?:year|quarter|period|three\s+months|nine\s+months)\s+ended"
    # Progress: "the impact of the adoption of ASU 2016-16 ... was a reclassification of
    # approximately [figure stripped] million to retained earnings"
    r"|(?:impact|effect)\s+of\s+(?:the\s+|our\s+)?adoption\b" + _NP + r"{0,80}?\bwas\s+(?:a|an)\b"
    # a past-period rate driver (Akamai: "these benefits were partially offset by an
    # intercompany sale of intellectual property")
    r"|\b(?:were|was)\s+(?:partially\s+|primarily\s+|largely\s+|mainly\s+)?(?:offset|driven|caused)\s+by"
    # "The 2018 provision for income taxes INCLUDED A 588 million deferred tax charge ...":
    # a past-tense statement of what the firm's own numbers contain
    r"|\b(?:included|includes|reflects|reflected)\s+(?:a|an)\s+[^.]{0,80}?"
    r"(?:charge|benefit|expense|adjustment|asset|liabilit)"
    # a rate driver stated for a past period: "the 2018 effective tax rate was further
    # decreased ..., offset by a 588 million deferred tax charge"
    r"|\b(?:partially\s+)?offset\s+by\s+(?:a|an)\s"
    r"|\b(?:rate|provision|expense|benefit|charge)\b[^.]{0,60}?\bwas\s+(?:further\s+)?"
    r"(?:decreased|increased|reduced|impacted|lowered)", re.I)
TABLEISH = re.compile(r"(?:\(\s*[\d,.]+\s*\)?\s*){4,}|(?:\b\d[\d,.]*\s+){6,}|CONSOLIDATED\s+(?:STATEMENTS?|BALANCE)")
# a page break inside a sentence ("... reduction to retained earnings as of February 4,
# 2018. 91 Table of Contents OXFORD INDUSTRIES ... (Continued)") is layout, not content --
# removed before classifying rather than treated as table residue (it cost Oxford)
PAGEBREAK = re.compile(r"\b\d{1,3}\s+Table\s+of\s+Contents\b|\bTable\s+of\s+Contents\b")
# a description of the OLD rule, in the past tense and often with the firm as subject
# (GoPro: "Prior to January 1, 2018, the Company recognized the income tax consequence of
# intra-entity asset transfers when the asset was sold to an outside party") -- an
# accounting policy, never an effect, whoever the subject is
OLDRULE = re.compile(
    r"(?:sold|transferred)\s+to\s+an?\s+(?:outside|third|unrelated)\s+part|otherwise\s+recovered"
    r"|^\s*(?:prior\s+to|before)\s+(?:the\s+)?(?:adoption|January|fiscal|\d{4})", re.I)
# ---- added 22 September. The catch-all `standard` class was holding two different
# things: a filing that merely reprints the rule, and a filing where the FIRM says it is
# working out what the rule will do to it ("we are currently evaluating the impact of
# ASU 2016-16 on our consolidated financial statements"). The second is dated, voluntary
# and firm-specific -- the first thing many firms ever say on the subject -- so it is a
# class of its own and can be studied as the pre-disclosure signal it is.
EVALUATING = re.compile(
    r"(?:we|the\s+company|the\s+corporation|management|the\s+registrant|(?-i:\b[A-Z][A-Za-z&.\-]+))\s+"
    r"(?:is|are|was|were|has\s+been|have\s+been)\s+(?:currently\s+|still\s+|in\s+the\s+process\s+of\s+)*"
    r"(?:evaluating|assessing|reviewing|determining|considering|studying)"
    r"|(?:is|are)\s+(?:currently\s+)?(?:being\s+)?(?:evaluated|assessed)\s+by\s+(?:us|the\s+company)"
    r"|(?:impact|effect)\s+of\s+(?:the\s+)?adoption\s+(?:is|has)\s+(?:not\s+yet\s+been|being)\s+"
    r"(?:determined|evaluated|assessed)|(?:have|has)\s+not\s+yet\s+(?:determined|evaluated|quantified)"
    r"|(?:do|does)\s+not\s+expect\s+(?:the\s+)?(?:adoption|this|these|such)"
    r"|(?:expects?|anticipates?)\s+(?:that\s+)?(?:the\s+)?adoption\s+(?:will|to)\b", re.I)

ACTED = re.compile(rf"\b{_V}\b|\bresult(?:ed|ing)\s+in\b|\bthe\s+result\s+was\b|\b(?:completed|transferred|sold|wrote\s+off)\b"
                   r"|\b(?:that|which)\s+(?:decreased|increased|reduced)\b|\bof\s+(?:certain\s+)?previously\s+deferred", re.I)
NO_EFFECT_EXTRA = re.compile(r"\bimmaterial\b", re.I)

# a figure: a digit that is not a year, or a magnitude word (the corpus strips many
# figures but leaves "million"). Used only to separate a sized forecast from a method note.
_YEARS = re.compile(r"\b(?:19|20)\d\d\b|\b20\d\d\s*-\s*\d\d\b|ASU\s*(?:No\.\s*)?\S+|Topic\s+\d+")
FIGURE = re.compile(r"\b(?:million|billion|thousand)\b|\d\s*%|\b\d{1,3}(?:,\d{3})+\b|\b\d+\.\d+\b", re.I)

# ---- added 22 September, on Brian's call. A firm can ASSERT a past transfer without
# recording anything in the period: Web.com's "an installment obligation of 11.7 million
# related to the fiscal 2012 intra-entity transfer of the intellectual property of our
# subsidiary Webs, Inc.", Viacom's "approximately 200 million of unrecorded net deferred
# tax assets, primarily related to an intra-entity transfer of assets". The population
# definition is "records a consequence OR asserts a transfer", so these belong in it --
# but they are a different kind of evidence, and the builder flags them as such
# (evidence_kind = assertion_of_past_transfer) so they can be excluded in one filter.
# Web.com also dates its transfer outright ("fiscal 2012"), which is the point: an
# assertion often carries the year a recorded effect does not.
ASSERTED = re.compile(
    r"(?:had|has|have|include[sd]?|including|carries|carried|maintain(?:s|ed)?|recognize[sd]?"
    r"|recorded|reflects?|reflected)\b" + _NP + r"{0,140}?"
    r"(?:deferred\s+tax|prepaid|obligation|liabilit|deferred\s+charge|valuation\s+allowance"
    r"|installment)" + _NP + r"{0,140}?"
    r"(?:related|relating|attributable|arising|resulting|due)\s+(?:to|from)\s+"
    r"(?:the\s+|an?\s+|its\s+|our\s+|certain\s+|these\s+)?(?:fiscal\s+\d{4}\s+|\d{4}\s+)?"
    r"(?:intra[-\s]?entity|intercompany|inter[-\s]company|intra[-\s]?group)\s+"
    r"(?:asset\s+|IP\s+|intellectual\s+property\s+)?(?:transfers?|sales?)", re.I)


def assertion_only(sentence: str) -> bool:
    """The sentence asserts a past transfer but records no effect in the period."""
    s = " ".join(PAGEBREAK.sub(" ", sentence or "").split())
    return bool(ASSERTED.search(s)) and not (EFFECT.search(s) and FIRM_PAST.search(s))


RANK = {"effect": 0, "expected_effect": 1, "adoption_no_effect": 2, "adoption": 3,
        "evaluating": 4, "standard": 5}


def klass(sentence: str) -> str:
    s = " ".join(PAGEBREAK.sub(" ", sentence or "").split())
    if TABLEISH.search(s) or len(s) > 900:
        return "standard"                      # table residue asserts nothing
    std = bool(STANDARD.search(s) or TRANSITION.search(s))
    noe = bool(NO_EFFECT.search(s) or NO_EFFECT_EXTRA.search(s))
    ado = bool(ADOPTED.search(s))
    fut = bool(FUTURE.search(s))
    firm = bool(FIRM_PAST.search(s))
    eff = bool(EFFECT.search(s)) and bool(INTRA.search(s))
    if noe and (ado or eff) and not (eff and firm and FIGURE.search(s) and not fut):
        # "did not have a material impact ... and we recorded an adjustment of 8 million
        # to beginning retained earnings" (PepsiCo) booked a sized effect: immaterial to
        # the firm is not the same as nothing recorded
        return "adoption_no_effect"
    if eff and ado and not FIGURE.search(s) and not ACTED.search(s):
        # "We adopted the guidance ... with a modified retrospective approach, a
        # cumulative-effect adjustment to equity as of the beginning of the period" names
        # the transition METHOD: no figure, nothing recorded (Sigma Designs, held-out read)
        return "adoption"
    if eff and firm and not fut and not OLDRULE.search(s):
        return "effect"
    if (eff and not fut and not OLDRULE.search(s) and not TRANSITION.search(s)
            and not STANDARD.search(s) and FIGURE.search(_YEARS.sub(" ", s))
            and INTRA_STRICT.search(s) and len(NUMS.findall(s)) < MAX_NUMS):
        # -- added 23 September, after reading all 94 filings this admits.
        # FIRM_PAST requires a named subject taking a verb, which is there to stop the
        # standard's own transition text ("adjustment RECORDED in retained earnings")
        # reading as the firm recording something. But firms report results in an
        # impersonal voice constantly:
        #   "the effective tax rate for the quarter benefited from a deferred tax benefit
        #    of 38 million resulting from intercompany transfers of intellectual property"
        # No subject, no verb the guard accepts, and unmistakably Kellogg's own result.
        # This route drops the subject requirement and replaces it with three others: a
        # figure must be present, and neither the standard's description nor its
        # transition language may be. MEASURED as a census, not a sample -- the anchor is
        # MEASURED on every filing it admits, twice. The first cut -- no INTRA_STRICT, no
        # number cap -- admitted 229 filings, of which 177 read as genuine, 34 could not be
        # told from ASC 606 or ASU 2016-09 adoption, and 19 were wrong: 77%, well under the
        # frame's own 95%. Requiring the topic to be NAMED and capping the figure count
        # admits 169, of which 160 are genuine: 95%, at a cost of 16 genuine filings the
        # guards throw out with them. That trade is the operating point, and <12 is the
        # loosest cap that reaches it rather than the best one found.
        return "effect"
    if (ASSERTED.search(s) and not fut and not TRANSITION.search(s)
            and not OLDRULE.search(s) and not TABLEISH.search(s)):
        # asserts a past transfer, records nothing this period -- in the population by
        # the definition, flagged as an assertion by the builder
        return "effect"
    if eff and fut and not TRANSITION.search(s) and FIGURE.search(_YEARS.sub(" ", s)):
        # a forecast only counts if it puts a size on the effect -- "we will adopt the new
        # standard using a modified retrospective approach with a cumulative-effect
        # adjustment" names the METHOD, not an expected effect, and is boilerplate
        return "expected_effect"               # a forecast of an effect: exposure, not a record
    if ado and not fut:
        return "adoption"
    if EVALUATING.search(s):
        # the firm speaking about the rule in its own voice, before it has anything to
        # report: dated, firm-specific, and NOT a disclosure of a transfer
        return "evaluating"
    return "standard"


def klass_window(anchor: str, following: str = ""):
    """(class, the sentence that earned it) over the anchor and its continuation."""
    best, where = klass(anchor), anchor
    for sent in _SPLIT.split(" ".join((following or "").split()))[:2]:
        if not sent.strip() or not CONTINUES.search(sent):
            continue
        if OTHER_STD.search(sent) and not re.search(r"2016\s*-?\s*16", sent):
            continue                      # a different standard's effect, not this one
        k = klass(sent)
        if RANK[k] < RANK[best]:
            best, where = k, sent
    return best, where


# ---------------------------------------------------------------- regression fixture
# Sentences read by hand on 21 September (the training read of 40 population first
# effects, plus the Double Irish firms the first tightening lost). Every rule change must
# keep all of these. `python disclosure_class_Claude.py` runs them. These are TRAINING
# cases: passing them says nothing about precision, which is measured on a held-out read.
FIXTURE = [
    ("We adopted ASU 2016-16 as of January 1, 2018 using a modified retrospective transition method, resulting in a 701 million reclassification of unrecognized income tax effects related to asset transfers that occurred prior to adoption from other current and non-current assets to opening retained earnings.", "effect"),  # Alphabet
    ("On January 1, 2017, the Company early adopted ASU 2016-16, Income Taxes (Topic 740): Intra-Entity Transfers of Assets Other Than Inventory ASU 2016-16 which records the effect of intra-entity transfers of assets other than inventory when the transfer occurs, resulting in 0.1 million charged to accumulated deficit upon adoption", "effect"),  # LogMeIn
    ("We adopted the provisions of this guidance during the first quarter of 2018; the adoption did not have a material impact on our financial statements and we recorded an adjustment of 8 million to beginning retained earnings", "effect"),  # PepsiCo
    ("Therefore, the impact of the adoption of ASU 2016-16 on our consolidated balance sheet was a reclassification of approximately million to retained earnings.", "effect"),  # Progress
    ("The impact of the adoption of this guidance resulted in a million reduction to retained earnings as of February 4, 2018. 91 Table of Contents OXFORD INDUSTRIES, INC. NOTES TO CONSOLIDATED FINANCIAL STATEMENTS (Continued) the guidance on the first day of Fiscal", "effect"),
    ("The change in the valuation allowance during the year ended December 31, 2018 is primarily due to the write-off of a valuation allowance to Retained Earnings for the tax effect related to intra-entity asset transfers.", "effect"),  # Waters
    ("The Company recorded the cumulative effect of the change as a decrease to retained earnings of approximately 13.3 million . The cumulative effect adjustment represents the recognition of unrecognized income tax effects from intra-entity transfers", "effect"),  # Cooper
    ("We recognized a gain on the transfer of intellectual property to our Irish subsidiary in the amount of 69.7 million.", "effect"),  # Orexigen
    ("As a result, Valley recorded a 15.4 million cumulative effect adjustment that reduced retained earnings effective January 1, 2018 to record net deferred tax liabilities related to pre-existing transactions.", "effect"),
    ("In December 2019, we completed a Dutch legal entity restructuring project, which resulted in an intra-entity transfer of certain intangible assets and intellectual property.", "effect"),  # Koppers
    ("Additionally, in December 2020, the Company completed an intra-entity asset transfer of certain intellectual property rights to an Irish subsidiary where its international business is headquartered.", "effect"),  # Twilio
    ("We adopted these provisions using the modified retrospective method recording a decrease of 6.3 million to retained earnings for the cumulative effect of the change, with a corresponding decrease to other assets.", "effect"),  # Darden
    ("With the adoption of ASU 2016-16 on January 1, 2017 the Company reversed net prepaid tax assets of 378.5 million and recorded the gross deferred tax assets associated with the historical intercompany sales of solar energy systems", "effect"),  # Sunrun
    ("These benefits were partially offset by an intercompany sale of intellectual property and state income taxes.", "effect"),  # Akamai
    ("We adopted the guidance in the first quarter of fiscal 2018 with a modified retrospective approach, a cumulative-effect adjustment to equity as of the beginning of the period in which the guidance is adopted", "adoption"),  # Sigma Designs (held-out false positive, added AFTER scoring)
    ("The Company adopted this standard in 2018 and the result was an increase to retained earnings of 1,038 .", "effect"),  # Valmont
    ("We adopted this guidance in the first quarter of fiscal year 2019 on a modified retrospective basis through a cumulative-effect adjustment of that decreased retained earnings as of 1 October 2018.", "effect"),  # Air Products, figure stripped
    ("We adopted ASU 2016-16 on October 1, 2018 using the modified retrospective approach with a cumulative effect adjustment directly to retained earnings.", "adoption"),  # Hill-Rom
    ("We are currently evaluating the impact of the adoption of ASU 2016-16 on our consolidated financial statements.", "evaluating"),
    ("The Company is currently evaluating the effect that the updated standard will have on its financial position and results of operations.", "evaluating"),
    ("The Company does not expect the adoption of ASU 2016-16 to have a material impact on its consolidated financial statements.", "evaluating"),
    ("In October 2016, the FASB issued ASU 2016-16, Income Taxes (Topic 740): Intra-Entity Transfers of Assets Other Than Inventory, which requires an entity to recognize the income tax consequences of an intra-entity transfer when the transfer occurs.", "standard"),
    ("The 2018 provision for income taxes included a 588 million deferred tax charge on previously acquired intangible assets resulting from a transfer of these assets between wholly owned subsidiaries.", "effect"),  # Gilead FY2018, a COST
    ("In addition, the 2018 effective tax rate was further decreased due to a 202 million tax benefit recorded in 2018 related to settlement of tax examinations, offset by a 588 million deferred tax charge in 2018 resulting from a transfer of acquired intangible assets between wholly owned subsidiaries.", "effect"),  # the same event in the MD&A
    ("We adopted this ASU in Q1 2018 with an increase of approximately 250 million to retained earnings and deferred tax assets net of valuation allowances.", "effect"),  # Amazon
    ("The primary impact of the adoption was an increase to deferred income taxes, net of 227.6 million and a cumulative catch-up adjustment to retained earnings.", "effect"),  # Starbucks
    ("Other obligations include an installment obligation of 11.7 million related to the fiscal 2012 intra-entity transfer of the intellectual property of our subsidiary Webs, Inc.", "effect"),  # Web.com, an assertion
    ("As of September 30, 2017, the Company had approximately 200 million of unrecorded net deferred tax assets, primarily related to an intra-entity transfer of assets.", "effect"),  # Viacom, an assertion
    ("Intercompany transactions were eliminated in consolidation.", "standard"),
    # -- added 23 September with the impersonal-voice route. The first is Kellogg, the
    #    sentence the route exists for; the second and third are what still must NOT pass.
    ("The effective tax rate for the quarter ended April 1, 2017 benefited from a deferred tax benefit of 38 million resulting from intercompany transfers of intellectual property.", "effect"),
    ("The amendments require an entity to recognize the income tax consequences of an intra-entity transfer of an asset other than inventory when the transfer occurs, with a cumulative-effect adjustment of the 2018 opening balance recorded in retained earnings.", "standard"),
    ("The cumulative effect of the adoption was recognized as an increase to retained earnings of 1 million as of January 1, 2018.", "standard"),  # names no standard: ASC 606 fits it too
    # -- added 22 September, from the reader run on the 144 tagged-but-silent firms.
    #    Bristol-Myers Squibb states amount, sign, destination and a transfer INTO the US
    #    in one sentence, and read as `standard` because neither INTRA nor EFFECT allowed
    #    the adjective "internal". The two guards below are why the widening is narrow.
    ("The nine months ended September 30, 2020 also includes an 853 million deferred tax charge resulting from an internal transfer of certain intangible assets to the U.S. and an additional 266 million GILTI tax charge upon finalization of the Otezla divestiture tax consequences with tax authorities.", "effect"),  # Bristol-Myers Squibb FY2020
    ("We maintain internal controls over financial reporting and our internal use software is amortized over three years.", "standard"),
    ("The Company completed an internal investigation and recorded a 5 million charge to retained earnings.", "standard"),
    ("We expect to record a cumulative-effect adjustment of approximately 10 to 15 million increasing accumulated deficit upon adoption of ASU 2016-16.", "expected_effect"),
    ("We adopted the new standard effective January 1, 2018, using the modified retrospective transition approach through a cumulative-effect adjustment to retained earnings as of the effective date, which was not material to our condensed consolidated financial statements.", "adoption_no_effect"),  # Facebook
    ("We adopted this new standard as of February 1, 2018 with an immaterial cumulative effect adjustment recorded in accumulated deficit as of February 1, 2018.", "adoption_no_effect"),  # Splunk
    ("The Company adopted ASU 2016-16 in the first quarter of fiscal year 2019.", "adoption"),  # Maxim
    ("We will adopt the new standard effective January 1, 2018, using the modified retrospective transition approach through a cumulative-effect adjustment to retained earnings as of the effective date", "standard"),  # Facebook 10-K
    ("The standard will be effective for us in the first quarter of 2018 and we will adopt the new standard using a modified retrospective approach with a cumulative-effect adjustment to retained earnings", "standard"),  # USG
    ("Prior to January 1, 2018, the Company recognized the income tax consequence of intra-entity asset transfers when the asset was sold to an outside party or otherwise recovered through use.", "standard"),  # GoPro
    ("The amendments in ASU 2016-16 should be applied on a modified retrospective basis through a cumulative-effect adjustment directly to retained earnings as of the beginning of the period of adoption.", "standard"),
    ("The new standard is required to be adopted in a modified retrospective approach, with a cumulative-effect adjustment recorded in retained earnings to write off any unamortized tax expense previously deferred", "standard"),  # Albany Molecular
    ("The impact of the sale of the related distribution center and non-inventory assets resulted in a pre-tax gain of approximately 19.0 million, which will be included in the results of operations", "standard"),  # Rite Aid
    ("On September 30, 2017, the Company completed the Stability Divestiture which resulted in the transfer of intangible assets acquired in 2016", "standard"),  # MiMedx
    ("For example, with the adoption of ASU No. 2016-16, effective January 1, 2018, the income tax effects of an intercompany transfer are recognized in the period in which the transfer occurs, rather than amortized over time", "standard"),  # Airbnb
    ("Specifically, IAS 12, Income Taxes, requires recognition of current and deferred income taxes resulting from an intra-entity transfer of any asset (including inventory) when the transfer occurs.", "standard"),
    ("4 Table of Contents FRESH DEL MONTE PRODUCE INC. AND SUBSIDIARIES CONSOLIDATED STATEMENTS OF SHAREHOLDERS EQUITY AND REDEEMABLE NONCONTROLLING INTEREST (Unaudited) (U.S. dollars in millions, except share data)", "standard"),
]

if __name__ == "__main__":
    bad = [(klass(t), w, t[:90]) for t, w in FIXTURE if klass(t) != w]
    print(f"fixture: {len(FIXTURE) - len(bad)} of {len(FIXTURE)} as read")
    for got, want, t in bad:
        print(f"  got {got:<18} want {want:<18} {t}")
