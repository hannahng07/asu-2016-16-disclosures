# Reproducibility limitations

This repository is an **archival snapshot**. The scripts are byte-for-byte copies of what was run (each copy's SHA-256 is recorded in `_review/FILE_MANIFEST.csv`). They were not edited to fit the new layout, so **they won't run as-is from this repository.** The sections below explain why.

## 1. Hard-coded file locations
The scripts were written for one flat working folder. They find their files in four different ways:

| How the script finds files | Scripts | What breaks here |
|---|---|---|
| `~/mnt/Grant and Nguyen/` (home-relative mount) | 40 | That folder doesn't exist on most machines |
| The script's own folder (`Path(__file__).parent`) | 38 | Inputs are no longer next to the script; they were in the flat project folder |
| Bare filenames relative to the current directory | 18 | Work only if run from a folder that holds every input and output |
| `~/h74/ciks.json` (`07_goal2_irish/build_register_Claude.py`) | 1 | That file was never in the project folder |
| `/mnt/user-data/outputs/` (`06_deliverables/build_phaseA_workbook.py`) | 1 | A path from a different (hosted) environment |

**Scripts import each other by module name**, and some of those modules now sit in different `src/` subfolders. For example, `02_population/build_population_Claude.py` imports `amount_components_Claude`, `disclosure_class_Claude` and `transfer_timing_Claude` from `01_extract/`, plus `build_identification_proof_Claude` and `build_transfer_year_Claude` from `03_validation/`. Python won't find these unless all scripts are on one path.

Making the scripts run from this layout (for example, one shared `paths.py` and package imports) is a separate change. It hasn't been made or approved.

## 2. Outputs with no producing script in the project folder
These outputs exist, but no script in the original folder writes them. They were most likely produced in another working environment, since several scripts point at `~/mnt/Grant and Nguyen` and `~/h74`. **They can't be regenerated from this repository.**

| Output | Date | Notes |
|---|---|---|
| `IRISH_HANDOFF_4ITEMS_74FIRMS_Claude.csv` | 2 Nov | Includes the 2 Nov GILTI fix; `attribution_check` only reads it |
| `SENTENCE_OF_RECORD_FOR_IRISH_READER_Claude.csv` | 22 Oct | Input to `build_register` |
| `VERBATIM_SENTENCES_FOR_IRISH_READER_Claude.csv` | 22 Oct | |
| `ITEM1_ASU2016_16_FOR_IRISH_READER_Claude.csv` | 16 Oct | |
| `COVERAGE_POPULATION_74FIRMS_Claude.csv` | 22 Oct | Input to `build_register` |
| `READER_WORKLIST_74_FIRMS_2026-10-16.csv` | 16 Oct | Input to `build_register` |
| `APPENDIX5_NEW4_EVIDENCE_Claude.csv` | 30 Oct | |
| `APPENDIX5_ROWS_NEW4_Claude.csv` | 30 Oct | |
| `NEW4_FIRMS_10K_SWEEP_Claude.csv` | 23 Oct | |
| `STEP3c_NULLS_RETESTED_Claude.csv` | 22 Oct | |
| `STEP4_US_INBOUND_RESWEEP_Claude.csv` | 23 Oct | |
| `FDII_ETR_20FIRMS_Claude.csv` | 16 Oct | |
| `WDAY_ETR_FY2014_FY2024_Claude.csv` | 19 Oct | |
| `WDAY_PROFIT_AND_ETR_FY2018_FY2024_Claude.csv` | 21 Oct | |
| `MSFT_EX21_IRISH_ENTITIES_1994_2026_Claude.csv` | 15 Oct | |
| `utb_jumps_Claude.csv` | 8 Oct | |
| `Annual_returns_2014_worklist_Claude.xlsx` | 18 Sep | |
| `gilti_onset.csv` | — | Mentioned in the workstream note; not in the folder |

**Partial:** `GOAL2_US_INBOUND_IP_Claude.csv` is patched in place by `goal2_amounts`, `goal2_add_fullsweep` and `goal2_avgo`, but the script that first built it isn't in the folder.

**Because of this, `build_register_Claude.py` can't be re-run either.** It reads three of the files above, plus `~/h74/ciks.json`.

## 3. Inputs that aren't in the repository
- **Raw corpus:** `10-X_C_2016-2020/2021/2022/2023/2024.zip` (Loughran-McDonald cleaned 10-X, ~15 GB). `dta_probe/REGRESSION_TEST_Claude.py` also lists `10-X_C_2025.zip`, which isn't in the project folder.
- **Licensed data:** `ASUdata_CRSP_Compustat_May25.dta` (WRDS) and the Calcbench exports. Every output built from them is kept out as well.
- **Answer keys, gold sets and hand-labelled data:** the strict answer key, the gold set, DI firm identifiers, Irish transfer dates, AI-reader answers and adjudications. The validation scripts can't be scored without them.
- See `DATA_MANIFEST.md` for where each excluded file lives.

## 4. Which version of the core dataset is current hasn't been decided
- `population_filings_Claude.csv` and `population_filings_Claude-VUDM0CBY3.csv` differ on 16 rows. The second has the 8–9 Oct corrections described in the workstream note; the first doesn't. Neither is in the repository until one is confirmed. See `_review/POPULATION_FILINGS_DISCREPANCY_SUMMARY.md`.
- `04_corrections/apply_dta_findings_Claude.py` reproduces 8 of those 16 row changes. The Targa, DTS and Zynga changes (8 rows) were made by code that isn't in the project folder.
- The workstream note has the same split. Its two halves are combined in `_review/10K_WORKSTREAM_MERGED_PROPOSED.md`, pending approval.
- The 16 Oct–2 Nov outputs may have been built from the uncorrected version (see the merge report, item C2). Treat them as unverified until that is checked.
- `population_filings_Claude.dta` (23 Sep) is older than both CSVs.

## 5. Software
Scripts ran on Python 3.10 (from `__pycache__` tags) with `pandas` and `openpyxl`. The notebook ran on Python 3.13 and uses `numpy`, `requests`, `textstat`, `tqdm` and the Calcbench API client, which needs a licensed account. Package versions weren't recorded.
