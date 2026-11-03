# The U.S. 10-K Project — instructions

Paste as the project's custom instructions.

> **UPDATED 17 SEPTEMBER 2026.** Four statements below are now out of date. Read this
> first; `10K_WORKSTREAM.md` has the evidence for each.
>
> - **Detection is 84%** (53 of 63 gold tickers with a CIK and a hand year), not 81%,
>   reading 10-K *and* 10-Q.
> - **The amount rate is 12 of 13** against the strict key, at rank 1 — not 3 of 13.
>   The v1 extractor scores 4 of 13 on the same key. The right figure is present in
>   some candidate for 13 of 13, which is a RECALL figure and is not the match rate.
> - **The answer key was corrected.** MCK was 105,000,000; McKesson discloses
>   152,000,000, four times over. Original preserved; see
>   `tenk_answer_key_CORRECTIONS_Claude.md`. Rates quoted against the old key are one
>   ticker pessimistic.
> - **"Invest in the extractor, not the raw archive" is superseded for AMOUNTS.** The
>   SEC's Financial Statement **and Notes** Data Sets carry the stripped figures,
>   free and structured, keyed on
>   `AdjustmentsForNewAccountingPronouncements=AccountingStandardsUpdate201616`.
>   Apple's $2.7bn / $2.6bn / −$128m all return exactly. It supplies no DESTINATION,
>   so goals 1a and 2 remain with the text extractor.
>
> Also: **OMI and EZPW both disclosed nothing** — zero mentions of "2016-16" in any
> spelling across 36 filings each. A5 is closed.


---

## The assignment

**Identify firms that disclose ASU 2016-16 / intercompany IP transfers in their US
10-K filings.** Code already exists; the job is to improve the identification.

Two related goals:

**1. Identify ALL companies making these disclosures.** A standalone project on how
this information affects investors. **Identification is the deliverable** — the
population of disclosing firm-years has to be right.

**1a. Within a disclosure, capture whether the firm says WHERE the IP went.**

**2. The Double Irish subset — did these firms transfer IP INTO the United States?**
Here the transfer dates are already verified, so the search can be narrowed to specific
years and a wrong answer can be detected.

**Do goal 2 first.** It is the only part with ground truth. Get the code catching every
confirmed case, then open it up to the full population. Calibrating on the cases whose
answer is known is what makes the wide sweep believable.

The Irish statutory work lives in other projects and is **not to be altered**. It can and
should be *used* — it supplies the verified IP transfer dates and the list of affected
firms, which is what makes Phase A possible. Read from it; write nothing back to it.

## What "good" means here — and the metric that has been reported is the wrong one

**For goal 1, the number that matters is DETECTION: was this filing correctly
identified as containing a transfer disclosure, and was one not there wrongly claimed?**
Recall and precision on the disclosure itself. An investor-response study is biased by
missed disclosures and contaminated by false ones; the extracted amount barely enters.

**The 23% figure in this project measures something else — AMOUNT extraction.** It is
the share of tickers where the right dollar figure came out of the right sentence. That
is the binding constraint for the *dissertation* use and is close to irrelevant for
goal 1. Do not let the two be quoted as one number. Detection currently runs at **81%**
against what firms actually disclose, and that is the figure goal 1 lives or dies on.

Stating which denominator a rate is over is the standing rule in this project, and
these two rates are exactly why.

## Four things that govern everything, and are not up for rediscovery

**1. The 10-K amount is a TAX BENEFIT, not an IP value.** The two sources report
different quantities about the same event — the Irish accounts state the IP value
acquired, the 10-K states the tax benefit recognised. Salesforce: $24bn of IP in the
Irish accounts against "a net tax benefit of $2.0 billion" in the 10-K. At 12.5% that
is the right order of magnitude and **not an identity**. The extracted figure is
`asu_amount`, a tax effect, validated against Brian's hand-read 10-K notes — 10-K
figures compared with 10-K figures. **Never reconcile it to the Irish IP value.** It
can corroborate (a $2bn tax benefit is not a trivial transfer); it cannot verify.

**2. Absence in a 10-K is never evidence of absence.** ASU 2016-16 disclosure is
required only when the effect is **material**. A firm can transfer IP and say nothing.
REGN, YELP and INSM never mention the standard or any transfer language across 28–29
filings each — those are not extraction failures. **The 10-K can confirm a transfer;
it can never refute one.** This is the ceiling on the whole workstream and belongs in
any write-up of it.

**3. The adoption date is not the transfer date.** 46% of ASU 2016-16 mentions are
adoption catch-ups under the modified retrospective method. Apple recorded $2.7bn of
DTAs in Q1 2019 for a transfer dated 2015 — real disclosure, right amount, four years
late. Every row carries `disclosure_type` and `date_usable_as_transfer_date` so nothing
downstream can confuse them. For adoption-only firms, the instrument is the **deferred
tax asset jump** — track the DTA balance backwards and date the transfer to the jump.

**4. The disclosure often does not cite ASU 2016-16 at all.** Adobe's FY2020 10-K
mentions the standard zero times and carries the entire disclosure anyway. **Anchor on
the transfer language, not the standard** — the ASU is one route in, not the route.
Hannah's anchor is the one in use, and the "OF" in `intercompany transfers of` is what
keeps it precise (it excludes "intercompany transfer pricing"). Switching to it took
matched filings 359 → 546 and destination capture 8% → 17%.

**5. The tax effect can be a COST, not a benefit — a DTL, not a DTA.** Every Double Irish
case seen so far records a deferred tax **asset**: IP moves to a low-tax destination, the
stepped-up basis outweighs the tax triggered, net benefit. **The broader population will
not all look like that.** A transfer into a higher-tax jurisdiction — including into the
United States — or out of a low-tax one can produce a net tax cost, a deferred tax
liability, or current tax expense on the gain.

**Treat this as a sample-selection risk, not a missing field.** A pattern anchored on
benefit language builds a population biased toward transfers into low-tax jurisdictions,
which is the wrong bias for an investor-response study and would be invisible in the
output. Therefore: match cost language as well ("tax expense", "tax charge", "income tax
expense of", "resulted in a tax cost", "deferred tax liability"); capture the **sign** of
the effect and whether it is a **DTA or DTL** as fields in their own right; and check this
deliberately when Phase B opens, because **calibrating on the DI firms cannot surface it —
they are all DTA cases.** For goal 2, a DTL is itself a signal that IP may have moved
*into* the US.

## Where things actually stand — measured, not asserted

**Honest match rate: 23%, not 36%.** The earlier validator asked "does any extracted
amount equal any number in the hand note?" — and those notes are long free-text
excerpts carrying revenue and prior-year figures, so coincidences scored as successes.
Gartner counted as correct holding 6.8m / 8m / 13.7m against a true answer of 38.1m.
`tenk_answer_key_Claude.json` fixes it: only amounts stated in a sentence carrying
**both** tax-effect and transfer language. 13 tickers qualify. **Against that key:
3 of 13.**

**Detection is 81% and is not the constraint.** Extending the anchor took detection
from 546 to 594 filings and moved the match rate barely at all.

**The constraint is SENTENCE SELECTION.** The right filing is found and the wrong
sentence inside it is read:

    IT    want  38,100,000   got 6,800,000 / 8,000,000 / 13,700,000
    SNPS  want 130,500,000   got 22,800,000 / 24,000,000 / 27,000,000
    MNST  want 165,100,000   got 6,600,000 / 12,300,000 / 4,200,000,000

One window is kept per filing, the highest-scoring, and the right sentence often sits
in a lower-scoring one.

## The open jobs, in order

**Phase A — calibrate on the Double Irish subset, where the answer is known.**

**A1. Catch every confirmed case.** The DI firms have verified transfer dates, so the
search narrows to specific years and a miss is visible. Work the confirmed list until
the code finds all of them. `di_firm_years_Claude.txt` gives the identifiers,
`tenk_answer_key_Claude.json` the strict amounts, `tenk_gold_set_Claude.csv` the hand
notes.

**A2. Did the IP go INTO the United States?** For the DI firms this is the question —
the unwindings frequently brought IP back onshore. The destination cue list is currently
narrow by design and captures a destination on only 7–17% of hits. Widening it needs the
labelled set to keep it honest, and "United States" is the destination this phase cares
about.

**A3. Stop choosing one sentence per filing.** Emit **every** candidate with its amount,
date, jurisdiction and provenance; let the answer key or a person select. Recall with
provenance beats precision that silently discards the right answer. Binding constraint
on the amount, not a large change.

**A4. Convert fiscal periods to calendar dates using `datadate`.** "The second quarter
of fiscal 2021" is meaningless without the filer's calendar — Salesforce's is roughly
**August 2020**, Adobe's fiscal 2020 ends November, Apple's September. And **US fiscal
year ends move** (HRB 30 Apr → 30 Jun in 2022; VMW 31 Dec → 31 Jan in 2017), so the
conversion is per firm **and** per year. This moves the year-match rate on its own, and
it is what makes "narrow to the verified year" work at all.

**A5. Read OMI and EZPW.** 28 filings each, anchor never fires. OMI mentions the
standard twice, EZPW three times. Establish whether they disclosed and were missed, or
never disclosed.

**Phase B — open it to the full population.**

Only once Phase A catches the confirmed cases. Then the measure switches from amount
accuracy to **detection recall and precision** over all US MNEs, and the output is the
population of disclosing firm-years plus, where stated, the destination.

## The corpus, and its one severe property

`10-X_C_*.zip` — Loughran-McDonald cleaned 10-X, ~15 GB over 2016–2024. Notre Dame
strips tables **by design**: "We exclude tables because they are usually not the focus
of textual analysis."

- **No dollar signs at all.** Apple's FY2020 10-K: 339,866 characters, 9,225 digits,
  zero `$`. A money pattern anchored on `$` matches nothing — that is a corpus property,
  not a parsing bug. The magnitude word has to carry the match.
- **12% of magnitude words lose their figure**, affecting 46% of filings. Adobe's
  sentence reads "related tax benefits of million and billion".
- **But the numbers are mostly there.** Of 26 gold tickers with a hand amount, 22 have
  every hand figure present somewhere in the cleaned corpus. **The 23% is a reading
  problem, not a data problem** — so the investment is the extractor, not the 514 GB
  raw archive. Fetch raw 10-X later, for the adoption window, once extraction stops
  being the constraint.

**10-Q filings are not optional.** Apple's matching figure is in a 10-Q; the FY2018
10-K carries only a forecast. Adobe's $224m survived in the 10-Q and was stripped from
the 10-K. Run with `--forms 10-K,10-Q`.

**DTA balances: use Compustat, not this corpus.** The tax footnote survives as text with
every figure removed. A DTA balance is recoverable from roughly 11% of filings. Brian
has Compustat, joined on `gvkey`. Each source for what it actually holds.

## What exists — do not rebuild it

- `extract_asu_2016_16_Claude.py` — the current extractor, validated against the gold
  set on every run.
- `tenk_gold_set_Claude.csv` — 72 tickers, 46 with a hand-read 10-K note.
- `tenk_answer_key_Claude.json` — the strict key, 13 tickers. This is what a match is
  measured against.
- `di_firm_years_Claude.txt` — the authoritative identifiers: gvkey, datadate, fyear,
  tic, cusip, cik. 77 DI firms, 74 with filings. It corrected 17 wrong identifiers in
  the earlier gold set, including DELL, which had picked up LyondellBasell's CIK.
- `Hannah/` — ten notebook iterations and `asu_v2`..`asu_v8`. `asu_v8.xlsx` has 10,000
  rows. Her anchor patterns are in `Looking for ASUs 05-04.ipynb` and are the ones in
  use.
- `10K_WORKSTREAM.md` — the detailed working note. Read it before changing the
  extractor.

## Closed — do not reopen

**Exhibit 21.** Delivered to Colin Walsh. §16 of the pipeline record is the full
account. The finding worth keeping: about **half of 10-Ks carry the subsidiary list
inline** with Name / State of Incorporation tables (158 of 300 sampled 2021 filings).

**The name-dropout test** for appended documents — failed, with a spot-check that
wrongly passed it.

## Working rules

Ask before changing any dataset. Never state a rate without saying what its denominator
is — the 36% that became 23% is why. Read the disagreements before believing any rate,
and treat a number that flatters the method with the same suspicion as one that does
not. Any signal is better than nothing, provided its provenance is recorded.
