#!/usr/bin/env python3
r"""There is no single "the amount". This reads the components and types them.

WHY
---
One ASU 2016-16 entry moves several things at once, and firms state two or three of them
in the same sentence:

    Broadcom     "a decrease in current and long-term prepaid tax expense of 67 million
                  and 199 million, respectively, an increase of 252 million to our
                  accumulated deficit and a decrease of 14 million to our
                  non-controlling interest"
    Baker Hughes "an increase to retained earnings of 25 million and an increase to
                  noncontrolling interest of 42 million"
    FedEx        "a 50 million income tax benefit and a 14 million adjustment to
                  retained earnings for the cumulative effect at adoption"
    MoneyGram    "a cumulative effect of 0.1 million to Retained loss, consisting of a
                  deferred charge of 1.3 million offset by a recording of deferred tax
                  balances of 1.2 million"

Picking one figure and calling it "the amount" meant the frame's number depended on
which clause the picker reached first, and it made XBRL look like it disagreed when it
had simply tagged a different component. So each figure is attached to the ACCOUNT it
belongs to and typed:

    retained_earnings   the cumulative-effect adjustment to retained earnings or
                        accumulated deficit -- the headline number for an adoption entry
    tax_pl              an income tax benefit or expense in the period -- the headline
                        for a current-period transfer
    deferred_tax_asset / deferred_tax_liability
    prepaid             the prepaid tax asset or deferred charge written off
    valuation_allowance
    other_assets, noncontrolling_interest, equity

HOW A FIGURE FINDS ITS ACCOUNT
-------------------------------
Nearest account phrase within a window, with two refinements that matter in practice:

  * "respectively" pairs a list of figures with a list of accounts IN ORDER, which is
    the only way to read Broadcom's 67 and 199
  * the sign comes from the verb attached to that account (increase / decrease /
    reduction / reversal / write-off), not from anywhere else in the sentence

A magnitude word with no figure in front of it ("increasing retained earnings by
million") is recorded as a STRIPPED component: the account is known, the number was
removed by the corpus, and that is worth knowing rather than guessing.

THE HEADLINE
------------
`headline()` picks one figure for the `amount` column, in a fixed and documented order:
retained earnings, then the P&L tax effect, then the deferred tax asset or liability,
then prepaid. The type that was chosen travels with it in `amount_component_type`, so
"the amount" is never anonymous again.
"""
from __future__ import annotations

import re

MAG = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mm": 1e6, "thousand": 1e3, "k": 1e3}

# an account, and the component type it implies. Order matters: the first match wins,
# so the more specific phrases come first.
ACCOUNTS = [
    ("retained_earnings", re.compile(
        r"retained\s+earnings|accumulated\s+deficit|retained\s+loss|"
        r"earnings\s+reinvested|retained\s+deficit|accumulated\s+earnings", re.I)),
    ("deferred_tax_liability", re.compile(
        r"deferred\s+(?:income\s+)?tax\s+liabilit\w+|\bDTLs?\b", re.I)),
    ("deferred_tax_asset", re.compile(
        r"deferred\s+(?:income\s+)?tax\s+assets?|\bDTAs?\b|deferred\s+tax\s+balances?", re.I)),
    ("valuation_allowance", re.compile(r"valuation\s+allowance", re.I)),
    ("prepaid", re.compile(
        r"prepaid\s+(?:income\s+)?tax\w*|prepaid\s+expense\w*|deferred\s+charges?|"
        r"income\s+tax\w*\s+receivable|prepaid\s+tax\s+expense", re.I)),
    ("tax_pl", re.compile(
        r"income\s+tax\s+(?:benefit|expense|provision)|tax\s+(?:benefit|expense|charge)|"
        r"provision\s+for\s+income\s+taxes|discrete\s+tax\s+(?:benefit|expense)", re.I)),
    ("noncontrolling_interest", re.compile(r"non[-\s]?controlling\s+interests?", re.I)),
    ("other_assets", re.compile(
        r"other\s+(?:current\s+|non[-\s]?current\s+|long[-\s]?lived\s+)?assets|"
        r"other\s+liabilit\w+", re.I)),
    ("equity", re.compile(r"stockholders.?\s+equity|shareholders.?\s+equity|"
                          r"total\s+equity", re.I)),
]
NEG = re.compile(r"\b(?:decreas\w+|reduc\w+|reversal|reversed|wrote\s+off|write[-\s]off|"
                 r"charged?\s+to|charge|eliminat\w+|derecogni\w+|lower\w*)\b", re.I)
POS = re.compile(r"\b(?:increas\w+|recogni[sz]\w+|recorded|established|addition\w*|"
                 r"benefit)\b", re.I)
FIG = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand|bn|mm)?\b",
                 re.I)
# a magnitude word with no figure in front of it: the corpus took the number out
STRIP = re.compile(r"(?:\bof|\bby|\bto|\ban?|approximately|totaling|totalling)\s+"
                   r"(?:approximately\s+)?(billion|million|thousand)\b", re.I)
YEARISH = re.compile(r"^(?:19|20)\d\d$")
WINDOW = 120

# XBRL element names -> the same component types
XBRL_TYPES = [
    ("retained_earnings", re.compile(r"CumulativeEffect|RetainedEarnings|"
                                     r"CumulativeEffectOfChangeOnEquity|"
                                     r"EffectOfAdoptionQuantification", re.I)),
    ("deferred_tax_liability", re.compile(r"DeferredTaxLiabilit|DeferredIncomeTaxLiabilit",
                                          re.I)),
    ("deferred_tax_asset", re.compile(r"DeferredTaxAsset|DeferredIncomeTaxAsset|"
                                      r"DeferredTaxAssetsLiabilitiesNet", re.I)),
    ("valuation_allowance", re.compile(r"ValuationAllowance", re.I)),
    ("prepaid", re.compile(r"PrepaidExpense|DeferredCharge|IncomeTaxesReceivable", re.I)),
    ("tax_pl", re.compile(r"IncomeTaxExpenseBenefit|CurrentIncomeTaxExpenseBenefit", re.I)),
    ("noncontrolling_interest", re.compile(r"NoncontrollingInterest", re.I)),
    ("other_assets", re.compile(r"OtherAssets|OtherLiabilities", re.I)),
    ("equity", re.compile(r"StockholdersEquity|MembersEquity", re.I)),
]
# the order a single headline figure is chosen in
HEADLINE_ORDER = ["retained_earnings", "tax_pl", "deferred_tax_asset",
                  "deferred_tax_liability", "prepaid", "valuation_allowance",
                  "other_assets", "equity", "noncontrolling_interest"]


def _accounts_in(s):
    """Every account phrase in the sentence: (position, type).

    A phrase inside another phrase is dropped: "prepaid tax expense" contains "tax
    expense", and letting both stand made Broadcom's 199 million a P&L item.
    """
    out, spans = [], []
    for kind, pat in ACCOUNTS:
        for m in pat.finditer(s):
            if any(m.start() >= a and m.end() <= b for a, b in spans):
                continue
            spans.append((m.start(), m.end()))
            out.append((m.start(), kind))
    out.sort()
    return out


def _sign(s, at):
    """+1 / -1 / 0 from the verb closest in front of the account phrase."""
    lo = max(0, at - 90)
    seg = s[lo:at + 40]
    n = [m.start() for m in NEG.finditer(seg)]
    p = [m.start() for m in POS.finditer(seg)]
    if not n and not p:
        return 0
    if not n:
        return 1
    if not p:
        return -1
    return -1 if max(n) > max(p) else 1


# page furniture the corpus leaves inside a sentence, and a rate table
PAGEBREAK = re.compile(r"\b\d{1,3}\s+Table\s+of\s+Contents\b|\bTable\s+of\s+Contents\b",
                       re.I)
LOOSE_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")


# ---------------------------------------------------------------- the stripped unit
# Loughran-McDonald removes tables, and with them the "(in thousands)" header that gave
# every figure in the statement its unit. What survives is a bare number: LogMeIn's
# cumulative-effect adjustment reads 99,702 and is 99.7 million; Workday's reads 625 and
# is 625 million. Taken at face value they are wrong by three orders of magnitude, and
# wrong in a way no reader of the output would question.
#
# The header itself often survives in the RUNNING TEXT of the window, a few hundred
# characters from the sentence -- "(In thousands)", "(amounts in thousands)", "(dollars
# in thousands)". That is an observation about the document, not a guess, so it is used
# as the unit when the figure carries no magnitude word of its own.
UNITS_PHRASE = re.compile(
    r"\(\s*(?:dollars|amounts|figures|numbers)?\s*in\s+(thousands|millions|billions)\b[^)]{0,60}\)"
    r"|\b(?:dollars|amounts|figures)\s+in\s+(thousands|millions|billions)\b", re.I)
UNITS_MAG = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}


def units_hint(window: str):
    """The unit the surrounding table declared, or None. The LAST one before the end of
    the window wins: a filing quotes several statements and the nearest header governs."""
    last = None
    for m in UNITS_PHRASE.finditer(window or ""):
        last = (m.group(1) or m.group(2) or "").lower()
    return UNITS_MAG.get(last)


def components(sentence: str, units=None):
    """Every figure in the sentence, typed by the account it belongs to.

    `units` is the multiplier the surrounding table declared, from units_hint().
    It is applied ONLY to figures that carry no magnitude word of their own.
    """
    s = " ".join(PAGEBREAK.sub(" ", sentence or "").split())
    if not s:
        return []
    # a rate reconciliation or a balance-sheet extract: the figures are column entries and
    # attaching them to the nearest words produces confident nonsense (Dana, Kennametal)
    if len(LOOSE_NUM.findall(s)) >= 8:
        return []
    accts = _accounts_in(s)
    if not accts:
        return []
    out = []

    # "A and B, respectively" -- pair the figures with the accounts in order
    resp = [m.start() for m in re.finditer(r"\brespectively\b", s, re.I)]
    used = set()
    for r in resp:
        figs = [m for m in FIG.finditer(s[:r]) if not YEARISH.match(m.group(1))][-3:]
        near = [(p, k) for p, k in accts if p < r][-len(figs):] if figs else []
        if len(figs) >= 2 and len(near) == len(figs):
            for m, (p, k) in zip(figs, near):
                v, known = _value(m, s, units)
                if v is None:
                    continue
                used.add(m.start())
                out.append({"type": k, "value": v, "sign": _sign(s, p),
                            "scale_known": known, "basis": "respectively list",
                            "text": m.group(0)})

    # the number inside a standard's name is not a figure. "ASU 2016-16" yields a bare
    # 16 that the year guard misses, and once a units hint is in play a stray 16 becomes
    # 16,000. Anything sitting immediately after a standard reference is skipped.
    STD_REF = re.compile(r"(?:20\d\d\s*-\s*|ASU\s*(?:No\.\s*)?|ASC\s*|Topic\s*|"
                         r"IAS\s*|IFRS\s*|No\.\s*)$", re.I)
    for m in FIG.finditer(s):
        if m.start() in used:
            continue
        if YEARISH.match(m.group(1)) and not m.group(2):
            continue
        if STD_REF.search(s[max(0, m.start() - 14):m.start()]):
            continue
        v, known = _value(m, s, units)
        if v is None:
            continue
        # a figure usually sits IN FRONT of the account it belongs to -- "a 14 million
        # adjustment to retained earnings" -- so an account that follows within reach
        # beats a nearer one behind it. Without this, FedEx's 14m attaches to the
        # "income tax benefit" 25 characters earlier and retained earnings loses its
        # figure entirely.
        # English puts the figure on either side of the account, and the preposition in
        # front of the figure says which: "an increase to retained earnings OF 25
        # million" points BACK, while "a 14 million adjustment to retained earnings"
        # points FORWARD. Getting this wrong cost FedEx its retained-earnings figure in
        # one direction and Baker Hughes its two in the other.
        # "...of 14 million TO our non-controlling interest": a preposition immediately
        # after the figure points forward and beats the "of" in front of it
        # "from" is excluded on purpose: it names the SOURCE, not the account the figure
        # lands in -- "a net deferred tax benefit of 188.8 million FROM deferred tax
        # assets" is a P&L figure, and reading it forward made it a balance (Analog Devices)
        fwd = bool(re.match(r"\s*(?:to|in|into|within)\b", s[m.end():m.end() + 14],
                            re.I))
        back = (not fwd) and bool(re.search(
            r"\b(?:of|by|totalling|totaling|approximately|to)\s*$",
            s[max(0, m.start() - 18):m.start()], re.I))
        best, dist = None, WINDOW + 1
        for p, k in accts:
            if ";" in s[min(p, m.start()):max(p, m.start())]:
                continue
            behind = p < m.start()
            want_behind = back and not fwd
            d = abs(p - m.start()) + (0 if behind == want_behind else 45)
            if d < dist:
                best, dist = (p, k), d
        if best is None:
            continue
        out.append({"type": best[1], "value": v, "sign": _sign(s, best[0]),
                    "scale_known": known, "basis": "nearest account",
                    "text": m.group(0)})

    # figures the corpus removed: the account is known, the number is gone
    for m in STRIP.finditer(s):
        best, dist = None, WINDOW + 1
        for p, k in accts:
            d = abs(p - m.start())
            if d < dist:
                best, dist = (p, k), d
        if best:
            out.append({"type": best[1], "value": None, "sign": _sign(s, best[0]),
                        "scale_known": True, "basis": "STRIPPED by the corpus",
                        "text": m.group(0)})
    return out


def _value(m, s, units=None):
    """(value, scale_known). A bare number in this corpus has no units: the tables are
    gone, so "1,281" may be 1,281 or 1,281 thousand and nothing in the sentence says
    which. Such a figure is returned with scale_known=False and yields to the filer's
    tagged value when one exists."""
    raw = m.group(1).replace(",", "")
    try:
        n = float(raw)
    except ValueError:
        return None, True
    unit = (m.group(2) or "").lower()
    if unit:
        return n * MAG[unit], True
    # a bare four-digit number in the year range is a year, comma or not: "2,018"
    if raw.isdigit() and 1900 <= int(raw) <= 2100:
        return None, True
    # a bare number inside a sentence that is quoting millions elsewhere is left as is:
    # the corpus has no dollar signs, so scale cannot be guessed. Only take bare numbers
    # that look like a stated figure in thousands (Cognex's "5,961,000").
    if units:
        # the table this figure came out of declared its unit and the corpus removed the
        # header; the number is in those units. Capped at a figure that is already
        # implausible as a unit-less count, so a genuine dollar figure is never inflated.
        if n < 1e6:
            return n * units, True
    return (n, False) if n >= 1000 else (None, True)


def from_xbrl(components_field: str):
    """The tagged facts, typed the same way. `tag=value; tag=value` as the join emits."""
    out = []
    for part in (components_field or "").split(";"):
        if "=" not in part:
            continue
        tag, _, val = part.partition("=")
        try:
            v = float(val)
        except ValueError:
            continue
        if v == 0:
            continue
        kind = next((k for k, pat in XBRL_TYPES if pat.search(tag)), None)
        if kind:
            out.append({"type": kind, "value": abs(v), "sign": (1 if v > 0 else -1),
                        "scale_known": True, "basis": f"xbrl:{tag.strip()}",
                        "text": tag.strip()})
    return out


def merge(text_comps, xbrl_comps):
    """Text first -- except where the text figure has no units.

    The corpus strips the table headers along with the tables, so a bare "1,281" could be
    dollars or thousands (Tennant: the tagged fact says 1,281,000). Where the text figure
    carries no magnitude word and the filer tagged the same component, the tagged value
    replaces it.
    """
    by_type = {}
    for c in text_comps:
        by_type.setdefault(c["type"], []).append(c)
    out = list(text_comps)
    for c in xbrl_comps:
        same = [t for t in by_type.get(c["type"], []) if t["value"] is not None]
        if not same:
            out.append(c)
            by_type.setdefault(c["type"], []).append(c)
        elif all(not t.get("scale_known", True) for t in same):
            for t in same:
                out.remove(t)
                by_type[c["type"]].remove(t)
            c = dict(c, basis=c["basis"] + " (text figure had no units)")
            out.append(c)
            by_type[c["type"]].append(c)
    return out


def headline(comps):
    """One figure for the `amount` column, in a fixed order. Returns (value, type, basis)."""
    for kind in HEADLINE_ORDER:
        hits = [c for c in comps if c["type"] == kind and c["value"] is not None]
        if hits:
            c = max(hits, key=lambda x: x["value"])
            return c["value"], kind, c["basis"]
    return None, "", ""


def as_text(comps, limit=8):
    return "; ".join(
        f"{c['type']}{'+' if c['sign'] > 0 else ('-' if c['sign'] < 0 else '')}="
        f"{'stripped' if c['value'] is None else format(c['value'], '.0f')}"
        for c in comps[:limit])


FIXTURE = [
    ("The adoption of this guidance resulted in a decrease in current and long-term prepaid tax expense of 67 million and 199 million, respectively, an increase of 252 million to our accumulated deficit and a decrease of 14 million to our non-controlling interest.",
     {"prepaid": 67e6, "retained_earnings": 252e6, "noncontrolling_interest": 14e6}),   # Broadcom
    ("The effect of the adoption of the standard was an increase to retained earnings of 25 million and an increase to noncontrolling interest of 42 million as of January 1, 2018.",
     {"retained_earnings": 25e6, "noncontrolling_interest": 42e6}),                     # Baker Hughes
    ("As a result of this new guidance, during 2018 we recorded a 50 million income tax benefit and a 14 million adjustment to retained earnings for the cumulative effect at adoption.",
     {"tax_pl": 50e6, "retained_earnings": 14e6}),                                      # FedEx
    ("The modified retrospective approach resulted in a cumulative effect of 0.1 million to Retained loss, consisting of a deferred charge of 1.3 million offset by a recording of deferred tax balances of 1.2 million.",
     {"retained_earnings": 0.1e6, "prepaid": 1.3e6, "deferred_tax_asset": 1.2e6}),      # MoneyGram
    ("We recorded a net cumulative-effect adjustment that resulted in an increase in retained earnings of 557 million, which reversed the previous deferral of income tax consequences and recorded new deferred tax assets of 2.8 billion.",
     {"retained_earnings": 557e6, "deferred_tax_asset": 2.8e9}),                        # Microsoft
    ("The Company adopted this standard in the current quarter resulting in a cumulative effect of 0.4 million increase to Earnings reinvested in the business; an increase of 3.0 million to Deferred Tax Assets; a decrease of 3.7 million to Prepaid Expense and Other Current Assets.",
     {"retained_earnings": 0.4e6, "deferred_tax_asset": 3.0e6, "prepaid": 3.7e6}),      # Sensient
    ("We adopted ASU 2016-16 effective January 1, 2018 using the modified retrospective method and we recognized a cumulative-effect adjustment increasing retained earnings by million.",
     {"retained_earnings": None}),                                                      # Brinks, stripped
]

if __name__ == "__main__":
    bad = 0
    for s, want in FIXTURE:
        got = {}
        for c in components(s):
            if c["type"] not in got:
                got[c["type"]] = c["value"]
        for k, v in want.items():
            g = got.get(k, "MISSING")
            ok = (g is None and v is None) or (isinstance(g, float) and v is not None
                                               and abs(g - v) <= 0.02 * v)
            if not ok:
                bad += 1
                print(f"  {k}: got {g} want {v}   [{s[:60]}...]")
    print(f"fixture: {sum(len(w) for _, w in FIXTURE) - bad} of "
          f"{sum(len(w) for _, w in FIXTURE)} components as read")
