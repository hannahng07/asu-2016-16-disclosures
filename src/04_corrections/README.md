# Corrections to `population_filings_Claude.csv`

These are one-off patches, not a reusable pipeline step. Each one edits `population_filings_Claude.csv` in place (after writing a dated backup) and changes specific filings, identified by CIK and filing date. Where an amount moved, the old value is kept in `amount_original` with a note in `correction_note`.

Run order, as recorded in the workstream note and the script headers:

| # | Script | Date | What it did | Backup it wrote |
|---|---|---|---|---|
| 1 | `apply_corrections_Claude.py` | 24 Sep | Priority-1 corrections from `CORRECTIONS_PENDING_APPROVAL_Claude.csv` | `…_BACKUP_pre_corrections20260924.csv` |
| 2 | `apply_corrections_p2345_Claude.py` | 25 Sep | Priorities 2, 3 and 5 | `…_BACKUP_pre_p2345_20260925.csv` |
| 3 | `apply_corrections_p4_Claude.py` | 25 Sep | Priority 4: firms and filings missing from the frame | — |
| – | `amount_of_record_preview_Claude.py` | 25 Sep | **Preview only.** Tested a rule-based amount-of-record fix; the rule failed and wasn't applied | — |
| 4 | `apply_amount_of_record_Claude.py` | 30 Sep | Hand-adjudicated amount of record for 27 flagged firms | `…_BACKUP_pre_aor_20260930.csv` |
| 5 | `apply_dta_findings_Claude.py` | 8 Oct | HZNP, Stryker, PepsiCo, AbbVie (DTA findings) | `…_BACKUP_pre_dta_20261008.csv` |
| 6 | *(not in folder)* | 8–9 Oct | Targa, DTS, Zynga | — |

**Note:** step 6 has no script, and the copy of `population_filings_Claude.csv` that should hold steps 5–6 is in dispute. See `docs/REPRODUCIBILITY.md` §4.

All scripts here except `amount_of_record_preview_Claude.py` hard-code hand-adjudicated firm-level values. They're kept out of Git tracking (`.gitignore`) until that is approved.
