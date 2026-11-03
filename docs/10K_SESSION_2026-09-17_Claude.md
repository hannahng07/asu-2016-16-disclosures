# Workstream 3 — session note, 17 September 2026

Phase A jobs **A3** (stop choosing one sentence per filing) and **A4** (convert
fiscal periods to calendar dates). Nothing existing was overwritten: `extract_asu_2016_16_Claude.py`,
`asu_2016_16_extracted_Claude.csv`, the gold set, the answer key and `Hannah/`
are untouched.

## New files

| file | what it is |
|---|---|
| `extract_asu_v2_Claude.py` | the candidate extractor — one row per anchor sentence, ranked, nothing discarded |
| `validate_asu_v2_Claude.py` | the measurement, every rate printed with its denominator |
| `summarize_asu_v2_Claude.py` | one row per DI firm — A1's hit/miss table |
| `asu_v2_candidates_Claude.csv` | 2,112 candidates across 677 filings, 62 tickers |
| `asu_v2_fye_map_Claude.csv` | the per-firm per-year fiscal calendar, 555 firm-years |
| `asu_v2_di_firm_summary_Claude.csv` | 78 DI firms, one row each |

Population: the 80 CIKs in `di_firm_years_Claude.txt` plus the gold set, forms
10-K and 10-Q, all five corpus zips — 2,205 filings read.

## The headline numbers, and what each one is over

**These are two different things and must not be quoted as one.**

**Detection** — goal 1's number:

    gold tickers with a CIK and a hand transfer year, detected     53 of 63   (84%)
    the same measure on v1                                                     81%

**Amount**, against the strict 13-ticker answer key — four questions, four numbers:

    key amount = amount_best of the RANK-1 candidate               11 of 13   (85%)
    key amount = amount_best of ANY candidate                      11 of 13   (85%)
    key amount PRESENT in some candidate (recall with provenance)  12 of 13   (92%)
    v1 as last run, same key                                        3 of 13   (23%)

The first line is the one comparable to the 23%. **The third is a recall figure,
not an accuracy one** — it says the right number is in the file with the sentence
it came from, not that the code chose it. Quoting it as "the match rate" would be
the 36% mistake committed a second time.

**Year**, calendar, after conversion, over the 53 detected tickers with a hand year:

    a calendar year parsed for at least one candidate              50 of 53   (94%)
    EXACT hand year among the candidate years                      25 of 53   (47%)
    within one year                                                33 of 53   (62%)

restricted to `current_period_transfer` (9 tickers): **7 of 9 exact**. The
adoption-versus-transfer classification is still doing real work.

"Among the candidate years" is a recall test across every candidate, not a single
dated answer, and is not comparable to a one-row-per-filing rate.

**The cost of not choosing:** 3.1 candidates per matched filing (median 2, max 19).

## Where the amount gain actually came from

Not the anchor. Three selection rules, each written against a filing that proved it:

1. **Read forward from the anchor sentence, not backward.** Gartner's answer is in
   its own sentence — "the Company recorded a net tax benefit of approximately 28.3
   million and 38.1 million, respectively, related to intercompany sales of certain
   intellectual property" — and the sentence *before* it is the quarterly results
   table, which the corpus left as a wall of digits with no sentence break. Reading
   it put 30.8 million from that table ahead of the 38.1 million in the key.
2. **Prefer the figure inside the anchor sentence.** Analog Devices states 331.0
   million there; cue-distance alone reached past it to 1.7 billion.
3. **Within the sentence, take the figure nearest the TRANSFER PHRASE, not the
   nearest effect cue.** Gilead: "a 202 million tax benefit ... related to settlement
   of tax examinations, offset by a **588 million** deferred tax charge ... resulting
   from **a transfer of acquired intangible assets**". Both sit beside effect
   language; only one sits beside the transfer.

## A4 — the fiscal calendar, built without Compustat

`di_firm_years_Claude.txt` holds one row per firm, so it cannot date per year. The
calendar is read from the filings instead: every Loughran-McDonald file carries its
SEC header, and `CONFORMED PERIOD OF REPORT` on a 10-K is that firm's fiscal year
end. 555 firm-years, and it moves with the firm because it is read from the firm.

Checks: Salesforce fiscal 2021 ends 2021-01-31, Adobe fiscal 2020 ends 2020-11-27,
Apple fiscal 2020 ends 2020-09-26. **16 of 77 firms show a year end that moves**,
including the two the workstream note named — HRB 30 Apr → 30 Jun, VMW 31 Dec → 31
Jan — plus 52/53-week drift in AAPL, INTC, ADI, WDC, MXIM.

Of the dated candidates, 817 state a calendar date outright and 411 were converted
from a header year end. `fye_source` records which, per row, so a date resting on a
carried-forward year end is never silently equal to one read from the filing.

## Goal 2 — four firms say the IP went INTO the United States

Strict test: a candidate that points at a jurisdiction ("to X" / "into X" / a
destination cue) where the jurisdiction is the US **and is named in the same
sentence as the transfer phrase**. Four firms, all four read by eye:

- **GILD**, FY2019 and FY2020 10-Ks — *"In 2018, we recorded a deferred tax charge
  of 588 million related to a transfer of acquired intangible assets from a foreign
  subsidiary to the United States."* Also *"a deferred tax benefit of 1.2 billion
  related to intangible asset transfers from a foreign subsidiary to Ireland and the
  United States."*
- **MSFT**, 10-Q Oct 2021 — *"In the first quarter of fiscal year 2022, we
  transferred certain intangible properties from our Puerto Rico subsidiary to the
  U.S. The transfer ... resulted in a 3.3 billion net income tax benefit."*
- **ZNGA**, FY2021 10-K — *"In the third quarter of 2020, we completed an
  intra-entity transfer of certain intellectual property rights **back to the U.S.**"*
- **DTSI**, FY2015 10-K — the rate reconciliation carries the line item
  **"Foreign IP transfer to US 147.4"**. No prose, no standard named. This is the
  REGN form again.

**MTSI is not one of them**, and is interesting anyway: *"an intra-entity transfer of
a license for intellectual property **to a higher taxed jurisdiction** that received
a tax basis step-up"* — destination named but not identified, amount stripped by the
corpus ("totaling million").

Coverage is thin and should be quoted as such: a destination is pointed at in
**91 of 2,112 candidates (4%)**, over **40 of 677 filings (6%)**. This is A2's job
and it needs the labelled set.

## The anchor gap that mattered, and why it mattered more than one ticker

Gilead's 588 million was **absent from every candidate** on the first full pass. The
anchor admitted only *certain / the / its / our* between "of" and the IP noun, so
"transfer of **acquired** intangible assets" did not match, and the noun-compound
form "intangible **asset transfers** from" did not either. Two patterns fixed it.

The reason this is worth writing down: the missed disclosure was a **cost** (a
deferred tax charge, not a benefit) whose destination was the **United States**.
That is settled point 5 and goal 2 at the same time. The blind spot was correlated
with exactly the disclosures the study most needs, and a correlated blind spot does
not show up in an output file — it shows up as a population that looks clean and is
biased. Worth re-checking deliberately when Phase B opens.

## Settled point 5 — cost cases exist inside the DI set

The project instructions say every Double Irish case seen so far is a DTA. Three in
this run are not:

- **GILD** — deferred tax **charge** of 588 million, IP into the US.
- **SNPS** — *"the Company recorded a decrease of approximately 130.5 million in
  retained earnings ... with a corresponding decrease in prepaid taxes related to the
  unamortized tax expense"*. That is the answer key's SNPS figure, and it is a cost.
- **MTSI** — transfer "to a higher taxed jurisdiction".

`effect_direction` and `dta_dtl` are now fields. Caveat on both: across all 2,112
candidates the direction reads benefit 540 / mixed 192 / cost 157 / none 1,223, and
a good share of the "cost" rows are boilerplate describing what the standard does
("Prior to the adoption of ASU 2016-16, a company will defer ... income tax expense")
rather than a firm reporting one. The field is a filter, not a finding.

## The two answer-key failures, read

- **MCHP (155.5m)** — present in a candidate, not the one `amount_best` picked.
  Selection, recoverable from `amounts_all` by anyone reading the file.
- **MCK (105m)** — **not in the corpus anywhere near transfer language.** Every
  occurrence of "105 million" in MCK's filings is litigation, buybacks, a pension
  settlement or a headquarters relocation. This is a data-side miss, not a code one:
  either the corpus stripped it, or the figure came from outside 2016–2022, or the
  hand note took it from another source. Worth settling, since MCK is 1 of the 13.

## One thing I got wrong, recorded because the rule says to

I flagged DTSI and ZNGA as false-positive US destinations on the strength of a
truncated preview that looked like table residue, and started building a heuristic
to suppress them. Reading the full sentences showed **both are real** — Zynga says
"back to the U.S." outright, and DTS's rate reconciliation has a line item named
"Foreign IP transfer to US". The table-residue suspicion was about to discard two of
the four findings the goal-2 question is actually about. The corpus strips the
figures out of a table, which is precisely what stops a stripped table looking like
one.

## Next, in order

1. **A2 — destination.** 4% of candidates is the weakest number here. The
   preposition test ("to X" / "into X") is new and works; the guard against
   adjectival country names ("compared to the U.S. **federal statutory rate**",
   "related to the U.S. **taxation** of") removed the REGN/BSX/BF.B false positives.
   Widening beyond that needs labels.
2. **A5 — OMI and EZPW**, still unread.
3. **MCK**, to a 10-Q or raw EDGAR.
4. **MCHP**, a selection case with a known answer — the cheapest remaining test of
   the ranking.

Phase B stays shut until A5 is done and the confirmed cases are all caught.
