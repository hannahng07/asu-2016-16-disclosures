# What to pull from WRDS, and why — 22 September 2026

`compustat_pull_list_Claude.csv` is the firm list: 842 CIKs, 333 in the population
(at least one filing that records the effect of an intra-entity transfer) and 509 in the
comparison group (adopted ASU 2016-16, never recorded an effect).

## The problem this solves

238 of the 333 population firms **never state when the transfer happened**. Their
disclosure is an adoption catch-up: in 2017–2019 they booked, in one entry, the tax
effect of transfers made in earlier years. The 10-K gives the amount and the adoption
date; it does not give the transfer date, and no amount of work on the text will produce
one, because the sentence does not contain it.

The instrument for those firms is the balance sheet. Under the old rule an intra-entity
transfer created a **prepaid tax asset / deferred charge** that was amortised until the
asset left the group; on adoption that balance was written off and deferred tax assets
appeared instead. So the transfer shows up as a jump in the deferred-charge balance in
the year it happened — years **before** the disclosure.

## Why it cannot be done with what is on disk

- `Calcbench Data Query Export_DTAs and DTLS.xlsx` starts at **Q1 2018**, which is at or
  after adoption for nearly every firm here, and is sparse: for the 126 undated firms it
  covers, only 278 rows carry a `NoncurrentTaxAsset` value.
- The Loughran-McDonald corpus on this machine starts in **2016**, so the pre-adoption
  years are not in the text either.
- The SEC notes datasets on disk start at **2018q1**. 2016 and 2017 were never downloaded.

## The pull

Keyed on `cik` in the file (10-digit; join through `comp.company` to gvkey).
Window: `pull_year_start` to `pull_year_end` per firm, roughly the eight years before the
disclosure. A single pull of **2008–2024** for all 842 firms is simpler and not much
larger.

**Compustat annual (`comp.funda`), standard filters (`indfmt='INDL'`, `datafmt='STD'`,
`popsrc='D'`, `consol='C'`):**

    gvkey datadate fyear fyr cik tic conm
    txdba    deferred tax asset - non-current      <- the post-adoption balance
    txndb    net deferred tax asset
    txdb     deferred taxes - balance sheet
    txdc     deferred taxes - income statement
    aco  ao  prepaid and other assets              <- where the old deferred charge sat
    txp  txt txfed txfo txdfed txdfo               <- tax expense split, for the sign
    at  sale  ni  xrd  intan  gdwl                 <- controls
    fic  loc                                        <- incorporation, for destination work

**Compustat quarterly (`comp.fundq`)** for the same firms and window, at least
`txdbq txdbaq atq saleq niq` — quarterly dates the jump far better than annual, and the
10-Q is where several of these disclosures live.

**CRSP link (`crsp.ccmxpf_lnkhist`)**: `gvkey lpermno linktype linkprim linkdt linkenddt`,
keeping `linktype in ('LU','LC')` and `linkprim in ('P','C')`. The event date on our side
is `filing_date`; `first_effect_date` is the recommended first-disclosure event.

## What to do with it when it lands

For each undated firm, take the deferred-charge / DTA series over the window and find the
largest jump relative to total assets. The transfer year is the jump year, and the
**already-known** adoption-year amount is the cross-check: the catch-up written off at
adoption should be close to the accumulated balance built up by that jump.

Firms with a stated transfer year (95 of 333) are the validation set — the jump should
land on the year they state.
