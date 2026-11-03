# ASU 2016-16 disclosures in U.S. 10-K filings

Code archive for the U.S. 10-K workstream of the Grant and Nguyen project on intercompany IP transfers. It covers:

1. **Identification.** Find every firm-year that discloses an ASU 2016-16 / intra-entity IP transfer in its 10-K or 10-Q.
   1a. Within a disclosure, capture where the IP went.
2. **The Double Irish subset.** Did these firms move IP into the United States? Verified Irish transfer dates make this checkable.

`docs/PROJECT_INSTRUCTIONS.md` and `docs/START_HERE_kickoff_note.md` set out the goals, the settled findings and the working rules. The most important rule: **every rate is quoted with its denominator.**

> **Status: archival snapshot.** The scripts are unchanged copies of what was run, and **they won't run as-is from this layout.** They expect one flat working folder and data that isn't in this repository. See `docs/REPRODUCIBILITY.md` before running anything.

## Layout

| Folder | What's in it |
|---|---|
| `src/01_extract/` | Text extractor (`extract_asu_v2`), disclosure classifier, transfer timing, amount components, anchor probe, SEC Notes and XBRL probes |
| `src/02_population/` | Population sweep and build, notes text, co-registrant map, CIK and event links, control group, analysis file, Compustat pull list |
| `src/03_validation/` | Validation against the hand-read notes and answer key, AI-reader calibration and production, Phase B precision, identification proof, US-call and federal/foreign tests |
| `src/04_corrections/` | One-off patches applied to the population file, in order (see the README there) |
| `src/05_scans/` | Secondary scans: CAMs, rate reconciliation, IP provenance and value, gross vs net, intangibles, balance-sheet sign |
| `src/06_deliverables/` | Builders for the Excel deliverables |
| `src/07_goal2_irish/` | Goal 2 and the Irish handoff: US-inbound sweep, TRACKER105, handoff, disclosure register, regression test, DTA and adoption-only work |
| `src/closed_exhibit21/` | Exhibit 21 workstream (closed and delivered) |
| `notebooks/` | The RA's latest notebook (`Looking for ASUs 05-04`), the source of the anchor patterns in use |
| `docs/` | Project instructions, method notes, `REPRODUCIBILITY.md`, `DATA_MANIFEST.md` |

## What's not here, and why
- **Raw corpus** (~15 GB of Loughran-McDonald 10-X zips): too large, and available from the public source.
- **Licensed data** (CRSP/Compustat from WRDS, Calcbench) and every output built from it.
- **Answer keys, gold sets and hand-labelled firm-level data.**
- **Unpublished drafts.**
- **All outputs and deliverables**, until each is approved.
- **26 scripts that hard-code hand-adjudicated firm-level values** (correction tables, seed sentences, CIK maps). They are present locally but listed in `.gitignore` until approved.

`docs/DATA_MANIFEST.md` lists every excluded file and where it lives.

## Open questions before this is final
- Which of the two `population_filings` versions is authoritative (16 rows differ).
- Approval of the merged `10K_WORKSTREAM.md`. The note had split into two copies with different date ranges.

## Setup
Python 3.10 with `pandas` and `openpyxl` (`requirements.txt`). The notebook also needs `numpy`, `requests`, `textstat`, `tqdm` and a licensed Calcbench API client.
