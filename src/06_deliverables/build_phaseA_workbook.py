#!/usr/bin/env python3
"""Assemble the Phase A deliverable workbook from the CSVs."""
import csv, sys
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
SRC = Path("/mnt/user-data/uploads/Grant and Nguyen")
OUT = Path("/mnt/user-data/outputs/Phase_A_deliverable_Claude.xlsx")

INK = "1B1E1C"; MUTED = "6B716D"; RULE = "D7DAD4"
HEAD_FILL = PatternFill("solid", fgColor="1B3A34")
BAND = PatternFill("solid", fgColor="F2F4F2")
US_FILL = PatternFill("solid", fgColor="DDEBE7")
F = "Arial"

STATUS_ORDER = ["us_destination_confirmed", "other_destination_named",
                "disclosed_no_destination", "adoption_only",
                "outside_verified_window", "not_detected", "no_verified_year"]

def read(name):
    with (SRC / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def sheet(wb, title, rows, widths=None, wrap_cols=(), freeze="A2", note=None):
    ws = wb.create_sheet(title)
    r0 = 1
    if note:
        ws.cell(1, 1, note).font = Font(name=F, size=9, italic=True, color=MUTED)
        ws.cell(1, 1).alignment = Alignment(vertical="center")
        r0 = 3
        freeze = f"A{r0+1}"
    cols = list(rows[0])
    for j, c in enumerate(cols, 1):
        cell = ws.cell(r0, j, c)
        cell.font = Font(name=F, size=9, bold=True, color="FFFFFF")
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[r0].height = 30
    for i, r in enumerate(rows, r0 + 1):
        for j, c in enumerate(cols, 1):
            v = r.get(c, "")
            if isinstance(v, str) and v and c not in wrap_cols:
                try:
                    v = float(v) if ("." in v or "e" in v.lower()) else int(v)
                except ValueError:
                    pass
            cell = ws.cell(i, j, v)
            cell.font = Font(name=F, size=9, color=INK)
            cell.alignment = Alignment(vertical="top",
                                       wrap_text=c in wrap_cols)
            if isinstance(v, float):
                cell.number_format = '#,##0;(#,##0);-'
            if i % 2 == 0:
                cell.fill = BAND
    for j, c in enumerate(cols, 1):
        w = (widths or {}).get(c, min(max(12, len(c) + 3), 26))
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = freeze
    ws.auto_filter.ref = f"A{r0}:{get_column_letter(len(cols))}{r0 + len(rows)}"
    return ws

wb = Workbook(); wb.remove(wb.active)

# ---------------------------------------------------------------- README --
rd = wb.create_sheet("Read me first")
rd.column_dimensions["A"].width = 3
rd.column_dimensions["B"].width = 104
lines = [
 ("Phase A deliverable — U.S. 10-K Project", "h1"),
 ("Double Irish subset: what each firm's own 10-K and 10-Q filings disclose about "
  "intercompany IP transfers. Built 17 September 2026.", "p"),
 ("", "p"),
 ("THE CEILING ON EVERYTHING IN THIS FILE", "h2"),
 ("ASU 2016-16 disclosure is required only when the effect is MATERIAL. A firm can "
  "transfer intellectual property and say nothing at all. 'not_detected' and "
  "'disclosed_no_destination' mean the filings are silent — NOT that no transfer "
  "happened. The 10-K can confirm a transfer; it can never refute one.", "warn"),
 ("", "p"),
 ("THE ORDER THE TWO STEPS HAVE TO RUN IN", "h2"),
 ("Fix the year from the filing's own words FIRST, then read the deferred tax lines in "
  "that year and nowhere else. Run unrestricted, the federal-vs-foreign rule made 51 US "
  "calls on a set of firms that overwhelmingly transferred into Ireland and 30 of them "
  "were wrong. Every error was a spurious US call; not one non-US call was wrong. The "
  "federal deferred line moves for NOLs, valuation allowances, SAB 118 and CARES, so in "
  "an arbitrary year a large federal movement means almost nothing. The foreign line is "
  "quiet unless something international happened.", "warn"),
 ("With the year fixed first the rule makes 5 US calls instead of 51, and the ones it "
  "drops are the ones that were wrong. Whether the survivors are RIGHT is a separate "
  "question this sample cannot answer — see the null model below. Read 'Transfer year' "
  "before any other tab.", "p"),
 ("", "p"),
 ("WHAT EACH TAB HOLDS", "h2"),
 ("Transfer year — THE tab. One row per firm: the year the transfer is first RECORDED, "
  "the sentence that says so, the sentence that carries the amount, and the deferred "
  "tax call for that year. Shaded where a destination answer exists.", "p"),
 ("Transfer year, all years — every year with evidence, its tier, and why a deferred "
  "tax call was or was not reported. The suppressed calls are visible here, never "
  "silently dropped.", "p"),
 ("US call test — the only test in the project that can tell a US call from a non-US "
  "one. Nine firm-years whose text names a destination, with the deferred tax lines "
  "printed either side of the event so the reading is visible rather than summarised. "
  "Three US, five non-US, one naming both. Read it before quoting any destination "
  "number.", "p"),
 ("Combined signals — the earlier unrestricted view, kept for comparison only. Its "
  "US calls are the ones the constraint removes. Do not quote it.", "p"),
 ("Retrospective adopters — recognition date vs transfer date. Zero of 23 firms state "
  "the transfer date in the adoption note.", "p"),
 ("Destination validation — extraction scored against the hand-collected transferee "
  "country, with the circularity caveat.", "p"),
 ("Identification proof — THE headline tab. One row per firm PER YEAR, 2018-2021, "
  "graded. 25 firm-years across 19 firms carry a sentence the firm asserts in its "
  "own voice together with a figure we stand behind; those rows are shaded. "
  "Everything else carries the reason it falls short.", "p"),
 ("DI firms — one row per Double Irish firm (78). The headline table. Every field "
  "carries the sentence it came from and the filing it is in.", "p"),
 ("Evidence — every candidate sentence inside each firm's verified transfer window "
  "(656). The backing for the DI firms tab.", "p"),
 ("Fed vs foreign — Brian's test: does the deferred tax movement corroborate where "
  "the IP went? Read the caveats on that tab before using it.", "p"),
 ("Fed vs foreign panel — the underlying firm-year deferred tax lines (177).", "p"),
 ("All candidates — every candidate sentence found anywhere, ranked, with provenance "
  "(2,120). Nothing is discarded; this is the recall-first output.", "p"),
 ("", "p"),
 ("STATUS VALUES, STRONGEST EVIDENCE FIRST", "h2"),
 ("us_destination_confirmed — the US is named in the SAME SENTENCE as the transfer "
  "phrase. 4 firms: DTSI, GILD, MSFT, ZNGA.", "p"),
 ("other_destination_named — a jurisdiction is pointed at ('to X', 'realized in X') "
  "in or beside the transfer sentence. 6 firms.", "p"),
 ("disclosed_no_destination — a transfer disclosure with no destination stated. 26.", "p"),
 ("adoption_only — only the modified-retrospective catch-up, no current-period "
  "transfer. Its date CANNOT be used as a transfer date. 9.", "p"),
 ("outside_verified_window — disclosures exist, none within a year of the verified "
  "transfer date. 11.", "p"),
 ("not_detected — no candidate sentence in any filing. 16. Most stopped filing after "
  "being acquired; the rest are below materiality.", "p"),
 ("no_verified_year — no hand transfer year to narrow to. 6.", "p"),
 ("", "p"),
 ("HOW GOOD IS IT — each rate with its denominator", "h2"),
 ("READ THE NULL MODEL BEFORE THE RATE. Scored against the hand-verified transferee "
  "country the destination call is right 20 of 21 — and answering 'non-US' every time "
  "scores 21 of 21 on the same set. Every Double Irish firm transferred to Ireland, so "
  "the sample contains no US-only transferee at all and CANNOT tell a US call from a "
  "non-US one. The 20-of-21 is not evidence the method works and must not be quoted as "
  "accuracy. Same shape as settled point 5: calibrating on the DI firms cannot surface "
  "what only the broader population contains.", "warn"),
 ("The one label that does discriminate is the filing's own words, where the firm names "
  "the destination — independent of the XBRL the rule reads, and it contains US cases. "
  "There the rule agrees with the text on 9 of 10 firm-years raw and 9 of 9 reported, "
  "with ZERO conflicts in either direction. But only THREE firm-years in the whole "
  "corpus have a firm naming the United States as the destination — Gilead 2018, "
  "Microsoft fiscal 2022, Zynga 2020 — and the rule stays silent on Zynga. See the "
  "'US call test' tab: two observations, no percentage.", "p"),
 ("What the US arm does show is direction. Gilead's transfer INTO the United States "
  "produced a $588m deferred tax CHARGE — a DTL, not a DTA, the cost case settled "
  "point 5 warns about — and the rule caught it, because it reads the SIZE of the "
  "movement and never anchors on benefit language. Zynga's miss is a size problem, not "
  "a direction problem: its federal line moved $4m and its foreign line $27m, both "
  "under the $50m floor. That floor is a market-cap filter in disguise and will drop "
  "small disclosing firms silently when Phase B opens.", "p"),
 ("The band that admits a US call — the federal movement must be 0.3x to 5x the "
  "disclosed effect — was calibrated on 11 observations and then scored on those same "
  "firms. It rests on a mechanism (the disclosed tax effect IS the deferred movement "
  "the transfer causes, so an 11x gap is a different event) rather than a fitted "
  "threshold, but it is untested out of sample.", "warn"),
 ("Transfer year, current-period transfers, vs the hand year: 10 of 18 exact, 16 of 18 "
  "within one year. Adoption catch-ups are NOT scored this way — the catch-up date is "
  "not the transfer date, and the lag is reported instead.", "p"),
 ("The hand transfer year is among the years the method reaches for 28 of 44 firms "
  "(64%), and is a STRONGLY identified year for 16 of 44 (36%).", "p"),
 ("Detection: 53 of 63 gold tickers with a CIK and a hand transfer year (84%).", "p"),
 ("Amount: 12 of 13 answer-key tickers matched by the top-ranked candidate (92%). "
  "The right figure is present in SOME candidate for 13 of 13 — that is a RECALL "
  "figure with provenance, not the match rate, and must not be quoted as one.", "p"),
 ("Destination: 191 of 2,120 candidates point at a jurisdiction; 10 firms named.", "p"),
 ("Every figure above is a RECALL rate measured on firms known to have transferred "
  "IP. Precision has never been measured and is the gate to Phase B.", "warn"),
 ("", "p"),
 ("FOUR THINGS THAT GOVERN HOW THE AMOUNT IS READ", "h2"),
 ("1. The amount is a TAX EFFECT, not an IP value. Never reconcile it to the Irish "
  "accounts' IP figure.", "p"),
 ("2. The adoption date is not the transfer date. Apple recorded $2.7bn in Q1 2019 "
  "for a 2015 transfer.", "p"),
 ("3. The effect can be a COST. Gilead's US transfer produced a $588m deferred tax "
  "CHARGE; Synopsys booked a $130.5m DECREASE in retained earnings.", "p"),
 ("4. A blank amount often means the corpus removed the figure, not that the firm "
  "disclosed none. Loughran-McDonald strips tables by design.", "p"),
 ("", "p"),
 ("SOURCES", "h2"),
 ("Text: Loughran-McDonald cleaned 10-X, 2016–2024, forms 10-K and 10-Q. "
  "2,205 filings read for this population, 677 carried a candidate.", "p"),
 ("Amounts cross-checked against SEC Financial Statement and Notes Data Sets "
  "(XBRL), keyed on AdjustmentsForNewAccountingPronouncements="
  "AccountingStandardsUpdate201616.", "p"),
]
r = 1
for text, kind in lines:
    c = rd.cell(r, 2, text)
    if kind == "h1":
        c.font = Font(name=F, size=16, bold=True, color=INK); rd.row_dimensions[r].height = 26
    elif kind == "h2":
        c.font = Font(name=F, size=10, bold=True, color="1B3A34"); rd.row_dimensions[r].height = 22
    elif kind == "warn":
        c.font = Font(name=F, size=9, bold=True, color="9A3412")
        c.alignment = Alignment(wrap_text=True, vertical="top"); rd.row_dimensions[r].height = 46
    else:
        c.font = Font(name=F, size=9, color=INK)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        rd.row_dimensions[r].height = 26 if len(text) > 95 else 14
    r += 1
rd.sheet_view.showGridLines = False

# --------------------------------------------------------- TRANSFER YEAR --
ty = read("asu_v2_transfer_year_Claude.csv")
ty.sort(key=lambda r: (r["first_recorded_year"] == "", r["destination"] == "",
                       r["ticker"]))
ws = sheet(wb, "Transfer year", ty,
           widths={"THE_SENTENCE": 78, "THE_AMOUNT_SENTENCE": 70, "ticker": 9,
                   "hand_transferee_country": 26, "all_qualifying_years": 30,
                   "strongly_identified_years": 20, "first_recorded_type": 20,
                   "dtadtl_basis": 16, "destination_source": 20},
           wrap_cols=("THE_SENTENCE", "THE_AMOUNT_SENTENCE"),
           note="STEP 1 THEN STEP 2. first_recorded_year is the EARLIEST year the firm "
                "is found recording a transfer in its own words with the period named "
                "in that same sentence. The deferred tax call is then read in that "
                "year only. first_recorded_type matters: an adoption_catchup books the "
                "tax effect of transfers that already happened, so its year is a "
                "RECORDING date and not a transfer date. Blank first_recorded_year "
                "means evidence exists but no year is strong enough to date it — see "
                "all_qualifying_years and the all-years tab.")
dcol = list(ty[0]).index("destination") + 1
for i in range(4, 4 + len(ty)):
    if ws.cell(i, dcol).value in ("US", "non-US"):
        for j in range(1, len(ty[0]) + 1):
            ws.cell(i, j).fill = US_FILL

tya = read("asu_v2_transfer_year_years_Claude.csv")
tya.sort(key=lambda r: (r["year_is_strongly_identified"] == "", r["ticker"],
                        int(r["event_year"])))
ws = sheet(wb, "Transfer year, all years", tya,
           widths={"THE_SENTENCE": 74, "THE_AMOUNT_SENTENCE": 66, "ticker": 9,
                   "evidence_basis": 30, "dtadtl_suppressed_reason": 42,
                   "dtadtl_confidence": 24, "period_in_sentence": 16,
                   "record_type": 20, "transfer_date_stated_in_sentence": 20},
           wrap_cols=("THE_SENTENCE", "THE_AMOUNT_SENTENCE"),
           note="Every firm-year with evidence, strongest first. evidence_tier 1 = the "
                "firm asserts a completed event AND the amount is there; 2 = asserted, "
                "figure stripped by the corpus; 3 = transfer prose with the amount in "
                "the sentence; 4 = XBRL tag only; 5 = prose only. "
                "period_in_sentence is the second condition and it is the one that was "
                "silently wrong before: 'transfer_date_not_record_date' marks a "
                "sentence that names BOTH dates and where the extractor took the "
                "transfer one. dtadtl_suppressed_reason says why a call the rule would "
                "have made is not reported.")
scol = list(tya[0]).index("year_is_strongly_identified") + 1
for i in range(4, 4 + len(tya)):
    if ws.cell(i, scol).value == "yes":
        for j in range(1, len(tya[0]) + 1):
            ws.cell(i, j).fill = US_FILL

# --------------------------------------------------------- US CALL TEST --
ut = read("asu_v2_us_call_test_Claude.csv")
ORD = {"US": 0, "both": 1, "non-US": 2}
ut.sort(key=lambda r: (ORD.get(r["text_destination"], 3), r["ticker"]))
ws = sheet(wb, "US call test", ut,
           widths={"THE_SENTENCE": 88, "ticker": 9, "rule_basis": 24,
                   "gated_out_because": 34, "text_destination": 16,
                   "effect_sign": 12, "verdict": 12},
           wrap_cols=("THE_SENTENCE",),
           note="The only test here that separates a US call from a non-US one. The "
                "hand-verified countries cannot do it — every Double Irish firm went to "
                "Ireland, so 'non-US' every time scores 100% on them. These nine "
                "firm-years were chosen by READING all 70 candidates flagged as "
                "US-destination across 13 firms; most of that flag is the US federal "
                "statutory rate line sitting near a transfer phrase, not a destination. "
                "THREE genuine US cases exist in the whole corpus. Gilead's is a "
                "deferred tax CHARGE, not a benefit — the cost case — and the rule "
                "caught it. Zynga's movement is under the $50m floor and is missed.")
vcol = list(ut[0]).index("verdict") + 1
BAD = PatternFill("solid", fgColor="F6DFD6")
for i in range(4, 4 + len(ut)):
    v = ws.cell(i, vcol).value
    fill = US_FILL if v == "AGREES" else BAD if v == "CONFLICTS" else None
    if fill:
        for j in range(1, len(ut[0]) + 1):
            ws.cell(i, j).fill = fill

# ------------------------------------------------------ COMBINED SIGNALS --
comb = read("asu_v2_combined_firmyear_Claude.csv")
comb.sort(key=lambda r: (r["destination_best_available"] == "",
                         r["ticker"], int(r["fiscal_year"])))
ws = sheet(wb, "Combined signals", comb,
           widths={"text_sentence": 74, "ticker": 9, "hand_transferee_country": 26,
                   "xbrl_largest_tag": 34, "dtadtl_basis": 18,
                   "destination_source": 20, "destination_best_available": 18},
           wrap_cols=("text_sentence",),
           note="SUPERSEDED — kept only so the constraint can be seen working. This is "
                "the unrestricted view: the deferred tax rule run in every year a firm "
                "had any evidence. It makes 51 US calls and 30 of them are wrong. The "
                "'Transfer year' tab is the one to use.")
dcol = list(comb[0]).index("destination_best_available") + 1
for i in range(4, 4 + len(comb)):
    if ws.cell(i, dcol).value in ("US", "non-US"):
        for j in range(1, len(comb[0]) + 1):
            ws.cell(i, j).fill = US_FILL

# --------------------------------------------------- IDENTIFICATION PROOF --
proof = read("asu_v2_identification_proof_Claude.csv")
GRADE = {"A": 0, "B": 1, "C": 2, "-": 3}
win = [r for r in proof if 2018 <= int(r["year"]) <= 2021]
win.sort(key=lambda r: (GRADE[r["sentence_grade"]], GRADE[r["amount_grade"]],
                        r["ticker"], int(r["year"])))
ws = sheet(wb, "Identification proof", win,
           widths={"THE_SENTENCE": 78, "THE_AMOUNT_SENTENCE": 70, "ticker": 9,
                   "sentence_basis": 28, "amount_basis_graded": 30,
                   "us_evidence": 26, "sentence_file": 34, "amount_file": 34},
           wrap_cols=("THE_SENTENCE", "THE_AMOUNT_SENTENCE"),
           note="One row per firm PER YEAR, 2018-2021 — a firm can transfer more than "
                "once. Sorted best evidence first. SENTENCE A = the firm asserts a "
                "completed event in its own voice. AMOUNT A = the figure comes from "
                "the transfer sentence itself. us_verdict 'no' means the sentence "
                "excludes the US (e.g. 'between foreign subsidiaries') — a real "
                "answer, not silence.")
sg = list(win[0]).index("sentence_grade") + 1
ag = list(win[0]).index("amount_grade") + 1
GOOD = PatternFill("solid", fgColor="DDEBE7")
for i in range(4, 4 + len(win)):
    if ws.cell(i, sg).value == "A" and ws.cell(i, ag).value in ("A", "B"):
        for j in range(1, len(win[0]) + 1):
            ws.cell(i, j).fill = GOOD

# ------------------------------------------------------------- DI firms --
deliv = read("asu_v2_di_deliverable_Claude.csv")
deliv.sort(key=lambda r: (STATUS_ORDER.index(r["status"]) if r["status"] in STATUS_ORDER else 9,
                          r["ticker"]))
ws = sheet(wb, "DI firms", deliv,
           widths={"destination_sentence": 70, "amount_sentence": 70, "ticker": 9,
                   "status": 25, "us_sentence": 50},
           wrap_cols=("destination_sentence", "amount_sentence", "us_sentence"),
           note="One row per Double Irish firm. Sorted by strength of evidence. "
                "'not_detected' is silence in the filings, not absence of a transfer.")
scol = list(deliv[0]).index("status") + 1
for i in range(4, 4 + len(deliv)):
    if ws.cell(i, scol).value == "us_destination_confirmed":
        for j in range(1, len(deliv[0]) + 1):
            ws.cell(i, j).fill = US_FILL

# ------------------------------------------------ RETROSPECTIVE ADOPTERS --
sheet(wb, "Retrospective adopters", read("asu_v2_retrospective_Claude.csv"),
      widths={"THE_ADOPTION_TEXT": 82, "ticker": 9, "recognition_period_text": 22,
              "adoption_method": 22, "file": 34},
      wrap_cols=("THE_ADOPTION_TEXT",),
      note="Modified-retrospective adopters: WHEN THE TAX WAS RECOGNISED versus when "
           "the transfer happened. ZERO of 23 firms state the transfer date in the "
           "adoption note — the date in these rows is the recognition date and CANNOT "
           "be used as a transfer date. Prospective adopters (BSX) are the exception: "
           "no catch-up, so their dates ARE usable.")

# ------------------------------------------------ DESTINATION VALIDATION --
sheet(wb, "Destination validation", read("asu_v2_destination_validation_Claude.csv"),
      widths={"hand_transferee_country": 30, "ticker": 9, "hand_deferred_tax_id": 26,
              "my_destinations_named": 24, "destination_agreement": 18},
      note="Extraction vs the hand-collected transferee country. The extractor is "
           "right 9 of 10 times it names a destination and silent on 54 of 64 firms — "
           "but a search of the 10-K text nearest each silent firm's transfer year "
           "found the country present in only 1 of 33, and that one spurious. The "
           "destination is genuinely not in the 10-K. PART OF THIS CHECK IS CIRCULAR: "
           "some hand countries were themselves read off the 10-Ks.")

# ------------------------------------------------------------- Evidence --
sheet(wb, "Evidence", read("asu_v2_di_evidence_Claude.csv"),
      widths={"anchor_sentence": 80, "ticker": 9},
      wrap_cols=("anchor_sentence",),
      note="Every candidate inside each firm's verified transfer window. "
           "in_window='' means an adoption catch-up kept regardless of year.")

# -------------------------------------------------------- Fed vs foreign --
sheet(wb, "Fed vs foreign", read("asu_v2_fedfor_summary_Claude.csv"),
      widths={"verdict": 40, "ticker": 9, "text_status": 24, "dominance": 16},
      note="Does the deferred tax movement corroborate the destination? The test "
           "EXCLUDES well and CONFIRMS poorly: 6 firm-years where the foreign line "
           "dominates, ZERO where federal does — including ZNGA, whose text says the "
           "IP came back to the U.S. Gilead reads ambiguous because its prose names "
           "BOTH Ireland and the US. TCJA contaminates fiscal 2017-2018. n=11.")

sheet(wb, "Fed vs foreign panel", read("asu_v2_fedfor_panel_Claude.csv"),
      widths={"company": 30, "ticker": 9},
      note="Annual DeferredFederalIncomeTaxExpenseBenefit and "
           "DeferredForeignIncomeTaxExpenseBenefit per firm-year, from SEC Notes XBRL.")

# -------------------------------------------------------- All candidates --
cands = read("asu_v2_candidates_Claude.csv")
drop = {"candidate_text", "prev_sentence", "destinations_wide_window"}
cands = [{k: v for k, v in r.items() if k not in drop} for r in cands]
sheet(wb, "All candidates", cands,
      widths={"anchor_sentence": 80, "ticker": 9, "file": 40, "amounts_all": 24},
      wrap_cols=("anchor_sentence",),
      note="Every candidate sentence found, ranked within its filing. Nothing "
           "discarded — candidate_rank=1 reproduces a one-row-per-filing extractor. "
           "Full text columns are in asu_v2_candidates_Claude.csv.")

wb.save(OUT)
print("wrote", OUT, OUT.stat().st_size, "bytes")
print("sheets:", wb.sheetnames)
