# Data manifest: files kept out of the repository

Everything below stays in the original project folder, `~/Desktop/VILLANOVA/asu-disclosure-analysis/`
(paths are relative to it). It is listed here so the repository records what exists and where.
The full file-by-file list, with SHA-256 hashes, is `_review/FILE_MANIFEST.csv`.

## Raw corpus (5 files, 14,648.5 MB)

Loughran-McDonald cleaned 10-X (Notre Dame Software Repository for Accounting and Finance). Re-download from the source.

- `10-X_C_2016-2020.zip` (7,947.3 MB)
- `10-X_C_2021.zip` (1,611.5 MB)
- `10-X_C_2022.zip` (1,780.7 MB)
- `10-X_C_2023.zip` (1,697.0 MB)
- `10-X_C_2024.zip` (1,611.9 MB)

## Raw sample filings (1 files, 0.6 MB)

Sample EDGAR filings (public).

- `Example_ASU.zip` (0.6 MB)

## Licensed / licensed-derived (30 files, 183.3 MB)

CRSP/Compustat via WRDS, or Calcbench, or values computed from them. Licence terms restrict sharing.

- `ASUdata_CRSP_Compustat_May25.dta` (140.5 MB)
- `Calcbench Data Query Export_DTAs and DTLS.xlsx` (1.5 MB)
- `Calcbench_FY2019_Q1.docx` (0.3 MB)
- `asu_analysis_firms_Claude.csv` (0.6 MB)
- `asu_analysis_firms_Claude.dta` (1.7 MB)
- `control_firms_Claude.csv` (0.7 MB)
- `control_group_summary_Claude.csv` (0.0 MB)
- `dta_probe/adoption_only_clock_Claude.csv` (0.0 MB)
- `dta_probe/adoption_only_dta_Claude.csv` (0.0 MB)
- `dta_probe/adoption_only_dta_Claude.txt` (0.0 MB)
- `dta_probe/adoption_only_locations_Claude.csv` (0.0 MB)
- `dta_probe/adoption_quarter_test_Claude.csv` (0.0 MB)
- `dta_probe/compustat_txdbaq_jumps_Claude.csv` (0.0 MB)
- `dta_probe/compustat_txdbaq_jumps_v2_Claude.csv` (0.0 MB)
- `dta_probe/dta_jumps_Claude.csv` (0.0 MB)
- `dta_probe/dta_screen_all105_Claude.csv` (0.1 MB)
- `dta_probe/reader_packet_index_Claude.csv` (0.0 MB)
- `dta_probe/step2_dta_Claude.csv` (0.0 MB)
- `dta_probe/txdbaq_jumps_with_adoption_Claude.csv` (0.0 MB)
- `dta_probe/txdbaq_jumps_with_adoption_v2_Claude.csv` (0.0 MB)
- `ex21_calcbench_2013_Claude.csv` (0.1 MB)
- `ex21_calcbench_2014_Claude.csv` (0.1 MB)
- `ex21_calcbench_2015_Claude.csv` (0.1 MB)
- `ex21_calcbench_2016_Claude.csv` (0.1 MB)
- `ex21_calcbench_ALLYEARS_Claude.csv` (0.5 MB)
- `ex21_merged_subsidiaries_Claude.csv` (2.9 MB)
- `link_event_coverage_Claude.csv` (0.0 MB)
- `population_filings_linked_Claude.csv` (8.6 MB)
- `population_filings_linked_Claude.dta` (25.2 MB)
- `population_firms_event_Claude.csv` (0.1 MB)

## Unpublished draft / third-party document (6 files, 0.8 MB)

Paper drafts, appendix drafts, example documents, co-author review notes, and a third-party paper.

- `AH2.pdf` (0.4 MB)
- `Appendix ASU 2016-16.docx` (0.2 MB)
- `Example ASU disclosures.docx` (0.1 MB)
- `Example Deliverable ASU 2016-16.docx` (0.0 MB)
- `Hannah/BG and HN - Review of Small Sample for Code Updates (03.12.26) .docx` (0.0 MB)
- `Intercompany IP Transfers and Information Asymmetry (02.19.24).docx` (0.1 MB)

## Answer key / gold set (10 files, 0.1 MB)

Ground-truth labels used to score the extractor.

- `phaseB_heldout40_Claude.csv` (0.0 MB)
- `phaseB_heldout40_v3_Claude.csv` (0.0 MB)
- `phaseB_training40_Claude.csv` (0.0 MB)
- `reader_gold_Claude.csv` (0.0 MB)
- `reader_gold_amount_Claude.csv` (0.0 MB)
- `tenk_answer_key_CORRECTIONS_Claude.md` (0.0 MB)
- `tenk_answer_key_Claude.json` (0.0 MB)
- `tenk_answer_key_Claude_ORIGINAL_pre20260917.json` (0.0 MB)
- `tenk_gold_set_Claude.csv` (0.0 MB)
- `tenk_gold_set_Claude.json` (0.0 MB)

## Hand-labelled / RA research data (110 files, 141.1 MB)

Hand-collected, adjudicated, AI-reader or RA-built firm-level data.

- `reader_*` AI-reader packets, answers and scores at top level: 69 files, 3.8 MB
- `CORRECTIONS_PENDING_APPROVAL_Claude.csv` (0.0 MB)
- `Deferredtaxes_IPtransfers_DIfirms_handcollected.xlsx` (0.1 MB)
- `Hannah/asuZipfile.xlsx` (77.8 MB)
- `Hannah/asu_scrape_2016to2020v2.xlsx` (4.0 MB)
- `Hannah/asu_v2.xlsx` (5.0 MB)
- `Hannah/asu_v3.xlsx` (4.2 MB)
- `Hannah/asu_v4.xlsx` (4.2 MB)
- `Hannah/asu_v5.xlsx` (4.1 MB)
- `Hannah/asu_v6.xlsx` (5.4 MB)
- `Hannah/asu_v7.xlsx` (4.7 MB)
- `Hannah/asu_v8.xlsx` (5.2 MB)
- `Hannah/vurf_v1.xlsx` (0.0 MB)
- `IRISH_transfer_dates_for_10K_verification_2026-09-18.csv` (0.0 MB)
- `Summary of Analyst Reports and IP transfers.xlsx` (0.0 MB)
- `ai_pilot_heldout40_Claude.txt` (0.0 MB)
- `ai_pilot_stated30_Claude.txt` (0.0 MB)
- `amount_adjudication_pack_Claude.csv` (0.1 MB)
- `amount_disagreements_10k_adjudicated_Claude.csv` (0.0 MB)
- `amount_disagreements_v2_adjudicated_Claude.csv` (0.0 MB)
- `amount_notes_disagreements_adjudicated_Claude.csv` (0.1 MB)
- `asu_scrape_2016to2020v2.xlsx` (16.6 MB)
- `asu_scrape_example.xlsx` (0.0 MB)
- `asu_v2.xlsx` (4.0 MB)
- `asuexample.xlsx` (0.0 MB)
- `di_firm_years_Claude.txt` (0.0 MB)
- `dta_probe/amount_corrections3_Claude.csv` (0.0 MB)
- `dta_probe/amount_corrections_Claude.csv` (0.0 MB)
- `dta_probe/hznp_answers_Claude.csv` (0.0 MB)
- `dta_probe/reader_verdicts_ALL_classified_Claude.csv` (0.7 MB)
- `dta_probe/reader_verdicts_b_json_Claude.tar.gz` (0.1 MB)
- `dta_probe/reader_verdicts_b_merged_Claude.csv` (0.2 MB)
- `dta_probe/reader_verdicts_c_json_Claude.tar.gz` (0.1 MB)
- `dta_probe/reader_verdicts_c_merged_Claude.csv` (0.2 MB)
- `dta_probe/reader_verdicts_json_Claude.tar.gz` (0.0 MB)
- `dta_probe/reader_verdicts_merged_Claude.csv` (0.3 MB)
- `dta_probe/usin_all_adjudicated_Claude.csv` (0.1 MB)
- `irish_cik_bridge_Claude.csv` (0.0 MB)
- `tracker_ciks_Claude.json` (0.0 MB)
- `tracker_firms_resolved_Claude.csv` (0.0 MB)
- `tracker_x_frame_Claude.csv` (0.0 MB)
- `us_verdict_yes_adjudicated_Claude.csv` (0.0 MB)

## Unrelated coursework (6 files, 0.1 MB)

Python practice notebooks.

- `Python Practice/05 Notes Regular Expressions.ipynb` (0.0 MB)
- `Python Practice/Foreign Operational Disclosures (for sharing).ipynb` (0.0 MB)
- `Python Practice/Module+2+(Python+3).ipynb` (0.0 MB)
- `Python Practice/Regex with Pandas and Named Groups.ipynb` (0.0 MB)
- `Python Practice/Working+With+Text.ipynb` (0.0 MB)
- `Python Practice/declaration_of_independence.txt` (0.0 MB)

## Intermediate and secondary analysis files (746 files, 273.4 MB)

Working files, chunked sweep outputs and secondary analyses. The scripts in `src/` regenerate them, given the inputs above.

- `(top level)`: 66 files, 123.7 MB
- `anchor_probe_parts/`: 34 files, 0.0 MB
- `dta_probe/`: 100 files, 45.2 MB
- `notes_text_parts/`: 40 files, 3.2 MB
- `notes_text_parts_all/`: 56 files, 8.8 MB
- `notes_text_parts_dest/`: 56 files, 9.4 MB
- `notes_text_parts_v2/`: 56 files, 1.5 MB
- `notes_text_parts_v3/`: 56 files, 3.4 MB
- `pkt_tar/`: 2 files, 4.6 MB
- `sweep_parts/`: 240 files, 71.0 MB
- `xbrl_parts/`: 40 files, 2.5 MB

## Superseded or generated (310 files, 125.0 MB)

Backups, pre-fix copies, older script and notebook versions, duplicate script copies, `__pycache__/`, `.DS_Store`.

## Pending a decision (not copied)

- `10K_WORKSTREAM-VUDM0CBY3.md` (0.3 MB): merge source; proposed merge in _review/10K_WORKSTREAM_MERGED_PROPOSED.md
- `10K_WORKSTREAM.md` (0.3 MB): merge source; proposed merge in _review/10K_WORKSTREAM_MERGED_PROPOSED.md
- `population_filings_Claude-VUDM0CBY3.csv` (13.1 MB): two versions differ on 16 rows; see _review/POPULATION_FILINGS_DISCREPANCY_SUMMARY.md
- `population_filings_Claude.csv` (13.1 MB): two versions differ on 16 rows; see _review/POPULATION_FILINGS_DISCREPANCY_SUMMARY.md
- `population_filings_Claude.dta` (72.8 MB): Stata copy dated 23 Sep, older than both CSVs
