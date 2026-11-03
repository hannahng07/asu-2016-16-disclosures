# ASU 2016-16 disclosures in U.S. 10-K filings

Code archive for the U.S. 10-K workstream of the Grant and Nguyen research project on intercompany transfers of intellectual property (IP), carried out through the MATCH program at Villanova University.

> **Status: archival snapshot.** The scripts are unchanged copies of what was run. **They won't run as-is from this layout**, and most of the data they read isn't in this repository. See [Limitations](#limitations) and `docs/REPRODUCIBILITY.md` before running anything.

## Research question

ASU 2016-16 (*Income Taxes: Intra-Entity Transfers of Assets Other Than Inventory*) changed how U.S. firms account for the tax effect of moving assets, most often IP, between their own subsidiaries. Firms disclose these transfers in their 10-K and 10-Q filings, but not in a standard form. This project asks:

1. **Identification.** Which U.S. firm-years disclose an ASU 2016-16 or intra-entity IP transfer? This population is the input to a study of how investors respond to the disclosures.
   - **1a. Destination.** Where a firm discloses a transfer, does it say where the IP went?
2. **The Double Irish subset.** Did firms that used the "Double Irish" tax structure move IP *into* the United States? Their Irish transfer dates are independently verified, so here the answer can be checked.

## Methodology

The work runs in two phases:

- **Phase A: calibrate where the answer is known.** Tune detection on the Double Irish firms, whose transfer years are verified, until it catches the confirmed cases.
- **Phase B: open it to the full population.** Sweep all U.S. filers. The measure then becomes detection recall and precision.

Principles the pipeline is built on (set out in `docs/PROJECT_INSTRUCTIONS.md`):

- **Anchor on transfer language, not only on the standard.** Many disclosures never cite "ASU 2016-16". The anchor patterns come from the RA's notebook.
- **Read 10-Qs as well as 10-Ks.** Some disclosures, and some figures, appear only in a quarterly filing.
- **Keep every candidate sentence.** The extractor emits every candidate with its provenance instead of picking one per filing, so a reviewer or answer key can choose.
- **Separate adoption from transfer.** Many mentions are catch-up adjustments on adopting the standard, not the transfer itself. Each row records which it is, and whether its date can be used as a transfer date.
- **Convert fiscal periods to calendar dates per firm and per year.** Fiscal year-ends differ between firms and sometimes change.
- **Capture the sign of the tax effect.** A transfer can produce a deferred tax asset (DTA) or a deferred tax liability (DTL). Matching only "benefit" language would bias the population toward transfers into low-tax jurisdictions.
- **Report every rate with its denominator.** Detection (was the disclosure found?) and amount extraction (was the right figure read?) are different measures and are never quoted as one.

**Data sources:** the Loughran-McDonald cleaned 10-X corpus (2016–2024), the SEC Financial Statement and Notes data sets (XBRL), Compustat via WRDS for DTA balances, and Calcbench for Exhibit 21 subsidiary lists.

## Technical components

- **Text extractor** (`01_extract/extract_asu_v2_Claude.py`): regex-based candidate extraction from the cleaned 10-X corpus. The corpus strips tables and dollar signs, so amounts are matched on magnitude words ("million", "billion").
- **Disclosure classification and timing:** labels each disclosure by type, separates transfers from adoption, and maps fiscal periods to calendar dates.
- **XBRL cross-check:** joins text results to firms' own structured tags for the ASU 2016-16 adjustment, an independent check on extracted amounts.
- **Validation framework:** scores detection and amounts against hand-read filings and a strict answer key, and calibrates an AI reader against hand labels before using it where no answer is known.
- **Population build:** sweeps the corpus, maps co-registrants, links events and builds a control group.
- **Double Irish / U.S.-inbound analysis:** a sweep for IP moving into the U.S., a DTA-jump screen to date transfers for adoption-only firms, and the handoff files for the Irish-records side of the project.
- **Exhibit 21 workstream** (closed): Irish subsidiaries extracted from 10-K subsidiary lists and merged with Calcbench exports.

## Workflow

```
01_extract  →  02_population  →  03_validation  →  04_corrections  →  06_deliverables
 candidate      firm-year          measure against     one-off patches     Excel
 sentences      population         hand-read sets      to the population   deliverables
                                         ↓
                               05_scans (secondary scans)
                               07_goal2_irish (Double Irish / U.S.-inbound)
```

## Repository structure

| Folder | Contents |
|---|---|
| `src/01_extract/` | Text extractor, disclosure classifier, transfer timing, amount components, anchor probe, SEC Notes and XBRL probes |
| `src/02_population/` | Population sweep and build, notes text, co-registrant map, event links, control group, analysis file, Compustat pull list |
| `src/03_validation/` | Validation against hand-read notes, AI-reader production, Phase B precision, identification proof, transfer-year and federal/foreign tests |
| `src/04_corrections/` | One-off patches to the population file, in run order (see the README there; most of these scripts are held back, see below) |
| `src/05_scans/` | Secondary scans: critical audit matters, rate reconciliation, IP provenance and value, gross vs net, intangibles, balance-sheet sign |
| `src/06_deliverables/` | Builders for the Excel deliverables |
| `src/07_goal2_irish/` | Goal 2: U.S.-inbound sweep, DTA screen, disclosure register, Irish handoff |
| `src/closed_exhibit21/` | Exhibit 21 workstream (closed and delivered) |
| `notebooks/` | The RA's latest exploratory notebook, the source of the anchor patterns in use |
| `docs/` | Project instructions, kickoff note, session notes, `REPRODUCIBILITY.md`, `DATA_MANIFEST.md` |

**Authorship.** Hannah Nguyen worked on this project as a research assistant in Villanova's MATCH program. The notebook is her exploratory work (through May 2026) and the source of the anchor patterns in use. The scripts in `src/` were developed afterwards in AI-assisted working sessions; the `_Claude` suffix marks them.

## Data and restrictions

Not in this repository:

- **Raw corpus** (~15 GB of Loughran-McDonald 10-X zips): too large, and available from the public source.
- **Licensed data** (CRSP/Compustat from WRDS, Calcbench) and every output built from it.
- **Answer keys, gold sets and hand-labelled firm-level data.**
- **Unpublished drafts and correspondence.**
- **All outputs and deliverables**, until each is approved.
- **32 scripts that hard-code hand-adjudicated firm-level values** (correction tables, firm verdicts, seed sentences, CIK maps). They're kept locally and listed in `.gitignore` until approved.

`docs/DATA_MANIFEST.md` lists every excluded file and where it lives.

## Limitations

**Reproducibility.** See `docs/REPRODUCIBILITY.md`:

- Scripts use hard-coded paths from the original working environments and import each other as if they were in one folder.
- Several outputs have no producing script in the project folder and can't be regenerated.
- The validation scripts can't be scored without the excluded answer keys and gold sets.
- Python 3.10 with `pandas` and `openpyxl` (`requirements.txt`). The notebook ran on Python 3.13 and also needs `numpy`, `requests`, `textstat`, `tqdm` and a licensed Calcbench API client. Package versions weren't recorded.

**Interpretation:**

- **Absence in a 10-K is not evidence of absence.** Disclosure is required only when the effect is material, so the 10-K can confirm a transfer but never rule one out.
- **The 10-K amount is a tax effect, not an IP value.** It can corroborate the Irish-records figures, not verify them.

**Open before this is final:**

- Which of the two `population_filings` versions is authoritative (16 rows differ).
- Approval of the merged `10K_WORKSTREAM.md`; the working note had split into two copies covering different date ranges.
