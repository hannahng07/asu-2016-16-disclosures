# Kick-off note — paste the text below as the first message in the U.S. 10-K Project


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

## The big picture

**The U.S. 10-K Project.** The goal is to **identify firms that disclose ASU 2016-16 /
intercompany IP transfers in their U.S. 10-K filings.** Code already exists and works;
the job is to improve the identification.

Two related goals:

**1. Identify ALL companies making these disclosures.** A standalone project on how this
information affects investors. **Identification is the deliverable** — the population of
disclosing firm-years has to be right.

**1a. Within a disclosure, capture whether the firm says WHERE the IP went.**

**2. The Double Irish subset — did these firms transfer IP INTO the United States?**
Here the transfer dates are already verified, so the search narrows to specific years
and a wrong answer is detectable.

**Start with goal 2.** It is the only part with ground truth. Get the code catching every
confirmed case first, then open it to the full population. Calibrating on cases whose
answer is known is what makes the wide sweep believable.

The Irish statutory work lives in other projects and is **not to be altered**. It can and
should be *used* — it is the source of verified IP transfer dates and of which firms are
affected, which is exactly what makes Phase A possible. Read from it; write nothing back
to it.

**This is not a standing start.** An RA, Hannah, built it through May 2026 — ten notebook
iterations, `asu_v8.xlsx` at 10,000 rows, and a set of anchor patterns still in use. A
later build sits on top and has been measured against a gold set. Everything is in
`Grant and Nguyen\`: corpus, notebooks, extractor, gold set, answer key, identifiers.
`10K_WORKSTREAM.md` is the detailed working note; read it before changing the extractor.

---

## What "good" means — and the number that gets quoted is the wrong one

**For goal 1 the metric is DETECTION:** was this filing correctly identified as carrying
a transfer disclosure, and was one not there wrongly claimed? Recall and precision on the
disclosure itself. An investor-response study is biased by missed disclosures and
contaminated by false ones. The dollar amount barely enters.

**The 23% figure in this project measures something else — AMOUNT extraction**, the share
of tickers where the right figure came out of the right sentence. That binds goal 2 and is
close to irrelevant to goal 1. Don't let them be quoted as one number.

**Detection currently runs at 81%** against what firms actually disclose. That is the
figure goal 1 lives on.

---

## Four things that are settled, and shouldn't be rediscovered

**1. The 10-K amount is a TAX BENEFIT, not an IP value.** Salesforce: $24bn of IP in the
Irish accounts against "a net tax benefit of $2.0 billion" in the 10-K. At 12.5% that's
the right order of magnitude and **not an identity**. Never reconcile the two — the 10-K
figure corroborates, it doesn't verify.

**2. Absence in a 10-K is never evidence of absence.** Disclosure is required only when
**material**. REGN, YELP and INSM never use the standard or any transfer language across
28–29 filings each — firms that didn't disclose, not extraction failures. **The 10-K can
confirm a transfer; it can never refute one.** That's the ceiling on the whole project and
belongs in the write-up.

**3. The adoption date is not the transfer date.** 46% of mentions are adoption catch-ups
under the modified retrospective method. Apple recorded $2.7bn of DTAs in Q1 2019 for a
transfer dated 2015 — real disclosure, right amount, four years late. For adoption-only
firms the instrument is the **deferred tax asset jump**: track the DTA balance backwards
and date the transfer to it.

**4. The disclosure often doesn't cite ASU 2016-16 at all.** Adobe's FY2020 10-K names the
standard zero times and carries the entire disclosure. **Anchor on transfer language, not
the standard.** Hannah's anchor is the one in use, and the "OF" in `intercompany transfers
of` is what keeps it precise — it excludes "intercompany transfer pricing". Switching to
it took matched filings 359 → 546 and destination capture 8% → 17%.

**5. The tax effect can be a COST, not a benefit — a DTL, not a DTA.** Every Double Irish
case seen so far records a deferred tax **asset**: IP moves to a low-tax destination, the
stepped-up basis is worth more than the tax triggered, and the net is a benefit. **The
broader population will not all look like that.** A transfer into a higher-tax
jurisdiction — including into the United States — or out of a low-tax one can produce a
net tax cost, a deferred tax liability, or current tax expense on the gain.

**This is a sample-selection risk, not just a missing field.** A pattern anchored on
benefit language ("tax benefit", "recorded deferred tax assets") builds a population
systematically biased toward transfers into low-tax jurisdictions — which is precisely the
wrong bias for a study of how these disclosures affect investors, and it would be invisible
in the output. So:

- Match cost language as well as benefit language — "tax expense", "tax charge", "income
  tax expense of", "resulted in a tax cost", "deferred tax liability".
- Capture the **sign** of the effect and whether it is a **DTA or a DTL** as fields in
  their own right. Direction is informative on its own, and for goal 2 a DTL is a signal
  that the IP may have moved *into* the US.
- Calibrating only on the DI firms will not surface this, because they are all DTA cases.
  **Check it deliberately when Phase B opens** rather than waiting for it to show up.

---

## Where it stands

**Detection is 81% and is not the constraint.** Extending the anchor took matched filings
from 546 to 594 and moved the amount match rate barely at all.

**The amount constraint is sentence selection.** The right filing is found and the wrong
sentence inside it is read:

    IT    want  38,100,000   got 6,800,000 / 8,000,000 / 13,700,000
    SNPS  want 130,500,000   got 22,800,000 / 24,000,000 / 27,000,000
    MNST  want 165,100,000   got 6,600,000 / 12,300,000 / 4,200,000,000

One window is kept per filing, the highest-scoring, and the right sentence often sits in a
lower-scoring one.

**The 23% is honest and hard-won.** An earlier 36% was the validator flattering itself: it
asked whether *any* extracted amount equalled *any* number in the hand note, and those
notes are long excerpts carrying revenue and prior-year figures. Gartner scored correct
while holding 6.8m, 8m and 13.7m against a true answer of 38.1m.

---

## The jobs, in order

**Phase A — calibrate on the Double Irish subset, where the answer is known.**

1. **Catch every confirmed case.** Verified transfer dates narrow the search to specific
   years and make a miss visible. `di_firm_years_Claude.txt` has the identifiers,
   `tenk_answer_key_Claude.json` the strict amounts, `tenk_gold_set_Claude.csv` the hand
   notes.
2. **Did the IP go INTO the United States?** For these firms that's the question — the
   unwindings frequently brought IP back onshore. Destination is captured on only 7–17% of
   hits and the cue list is narrow by design; widening it needs the labelled set to stay
   honest.
3. **Stop choosing one sentence per filing.** Emit every candidate with its amount, date,
   jurisdiction and provenance; let the answer key or a person select. Recall with
   provenance beats precision that silently discards the right answer.
4. **Convert fiscal periods with `datadate`.** "The second quarter of fiscal 2021" is
   meaningless without the filer's calendar — Salesforce's is roughly **August 2020**,
   Adobe's fiscal 2020 ends November, Apple's September. US fiscal year ends **move** (HRB
   30 Apr → 30 Jun in 2022; VMW 31 Dec → 31 Jan in 2017), so it's per firm **and** per
   year. This is what makes "narrow to the verified year" work at all.
5. **Read OMI and EZPW.** 28 filings each, anchor never fires. Establish whether they
   disclosed and were missed, or never disclosed.

**Phase B — open it to the full population.** Only once Phase A catches the confirmed
cases. The measure then switches to detection recall and precision across all US MNEs, and
the output is the population of disclosing firm-years plus, where stated, the destination.

---

## The corpus, and its one severe property

`10-X_C_*.zip` — Loughran-McDonald cleaned 10-X, 2016–2024. Notre Dame strips tables **by
design**.

- **No dollar signs anywhere.** Apple's FY2020 10-K: 9,225 digits, zero `$`. A pattern
  anchored on `$` matches nothing — corpus property, not a bug. The magnitude word has to
  carry the match.
- **12% of magnitude words lose their figure**, affecting 46% of filings. Adobe's sentence
  reads "related tax benefits of million and billion".
- **But the numbers are mostly there** — 22 of 26 gold tickers have every hand figure
  present somewhere. **So the gap is a reading problem, not a data problem**, and the
  investment is the extractor, not the 514 GB raw archive. Raw 10-X comes later, for the
  adoption window, once extraction stops being the constraint.

**10-Q filings are not optional.** Apple's matching figure is in a 10-Q; the FY2018 10-K
has only a forecast. Adobe's $224m survived in the 10-Q and was stripped from the 10-K.
Run `--forms 10-K,10-Q`.

**DTA balances come from Compustat, not this corpus.** The tax footnote survives with every
figure removed — balances are recoverable from about 11% of filings. Join on `gvkey`.

---

## What exists — do not rebuild it

`extract_asu_2016_16_Claude.py` (the extractor) · `tenk_gold_set_Claude.csv` (72 tickers,
46 with a hand-read note) · `tenk_answer_key_Claude.json` (the strict key, 13 tickers —
what a match is measured against) · `di_firm_years_Claude.txt` (gvkey, datadate, fyear,
tic, cusip, cik for 77 DI firms; it corrected 17 wrong identifiers, including a DELL entry
that had picked up LyondellBasell's CIK) · `Hannah/` (ten notebooks, `asu_v2`..`asu_v8`).

## Closed — do not reopen

**Exhibit 21**, delivered to Colin Walsh. Worth keeping from it: about half of 10-Ks carry
the subsidiary list inline, 158 of 300 sampled 2021 filings. And the **name-dropout test**
for appended documents, which failed with a spot-check that wrongly passed it.

## Working rules

Ask before changing any dataset. Never state a rate without its denominator — the 36% that
turned out to be 23%, and detection versus amount, are both why. Read the disagreements
before believing any rate, and treat a number that flatters the method with the same
suspicion as one that doesn't. Any signal beats nothing, provided its provenance is
recorded.
