"""Apply round-3 corrections to the workbook. Overlay only - the frame is untouched."""
import csv, os, re
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

BASE = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
WB = os.path.join(BASE, 'TRACKER105_ALL_TRANSFERS_Claude.xlsx')
COR = os.path.join(BASE, 'dta_probe', 'amount_corrections3_Claude.csv')

cors = list(csv.DictReader(open(COR, encoding='utf-8-sig', errors='replace')))
wb = load_workbook(WB)
ws = wb['Transfers']
hdr = [c.value for c in ws[1]]
ix = {h: i + 1 for i, h in enumerate(hdr)}

TIER = {'in_sentence': None, 'DTA_inferred': 'E_DTA_INFERRED'}
FILL = {'in_sentence': 'C6EFCE', 'DTA_inferred': 'FFF2CC',
        'adoption_in_sentence': 'F2F2F2', 'not_separable': 'FCE4D6', 'none': 'FFC7CE'}

moved, updated, superseded = [], [], []
for c in cors:
    t, y, act = c['ticker'].strip(), c['transfer_year'].strip(), c['action'].strip()
    hits = []
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=ix['ticker']).value or '').strip() != t:
            continue
        ry = str(ws.cell(row=r, column=ix['transfer year']).value or '').strip()
        if y and ry != y:
            continue
        if not y and ry:
            continue
        hits.append(r)
    if not hits:
        # the year may be new (WDAY gets a year for the first time)
        for r in range(2, ws.max_row + 1):
            if str(ws.cell(row=r, column=ix['ticker']).value or '').strip() == t:
                hits = [r]
                break
    if not hits:
        print('NO ROW for %s %s' % (t, y))
        continue
    for r in hits:
        if act in ('MOVE_TO_ADOPTION', 'SUPERSEDE'):
            ws.cell(row=r, column=ix['disclosure tier']).value = (
                'MOVED_TO_ADOPTION' if act == 'MOVE_TO_ADOPTION' else 'SUPERSEDED_not_an_event')
            ws.cell(row=r, column=ix['amount usd']).value = c['amount_of_record'] or ''
            ws.cell(row=r, column=ix['amount basis']).value = c['amount_basis'] or 'none'
            (moved if act == 'MOVE_TO_ADOPTION' else superseded).append('%s %s' % (t, y or '-'))
        else:
            if c['date_of_record']:
                ws.cell(row=r, column=ix['transfer date stated']).value = c['date_of_record']
            if y:
                ws.cell(row=r, column=ix['transfer year']).value = y
            if c['destination_of_record']:
                ws.cell(row=r, column=ix['destination']).value = c['destination_of_record']
                ws.cell(row=r, column=ix['destinations all']).value = c['destination_of_record']
                ws.cell(row=r, column=ix['destination disclosed']).value = (
                    'No' if 'not stated' in c['destination_of_record'].lower() else 'Yes')
                ws.cell(row=r, column=ix['countries basis']).value = (
                    'not_stated' if 'not stated' in c['destination_of_record'].lower()
                    else 'destination_stated')
            if c['to_US_of_record']:
                ws.cell(row=r, column=ix['to US']).value = c['to_US_of_record']
            ws.cell(row=r, column=ix['amount usd']).value = c['amount_of_record'] or ''
            if c['sign_of_record']:
                ws.cell(row=r, column=ix['effect direction']).value = c['sign_of_record']
            ws.cell(row=r, column=ix['amount basis']).value = c['amount_basis']
            ws.cell(row=r, column=ix['amount source']).value = c['amount_basis']
            if c['amount_basis'] == 'DTA_inferred':
                ws.cell(row=r, column=ix['disclosure tier']).value = 'E_DTA_INFERRED'
            elif c['amount_basis'] == 'in_sentence':
                dd = str(ws.cell(row=r, column=ix['destination disclosed']).value or '')
                ws.cell(row=r, column=ix['disclosure tier']).value = (
                    'A_FULL' if dd == 'Yes' else 'B_AMOUNT_NO_COUNTRY')
            elif c['amount_basis'] in ('not_separable', 'none'):
                ws.cell(row=r, column=ix['disclosure tier']).value = 'C_COUNTRY_NO_AMOUNT'
            if c['quote']:
                ws.cell(row=r, column=ix['of record quote']).value = c['quote']
                ws.cell(row=r, column=ix['figures in anchor']).value = (
                    'stated in the asserting sentence (see of record quote)'
                    if c['amount_basis'] == 'in_sentence'
                    else 'NO figure in any asserting sentence - value from Compustat')
            updated.append('%s %s' % (t, y or '-'))
        prev = str(ws.cell(row=r, column=ix['correction note']).value or '')
        ws.cell(row=r, column=ix['correction note']).value = (
            prev + ' || ROUND 3: ' + c['note']).strip(' |')
        f = FILL.get(c['amount_basis'], 'FFFFFF')
        for col in range(1, len(hdr) + 1):
            ws.cell(row=r, column=col).fill = PatternFill('solid', fgColor=f)
            ws.cell(row=r, column=col).alignment = Alignment(vertical='top', wrap_text=True)

print('updated: %s' % ', '.join(sorted(set(updated))))
print('moved to adoption: %s' % ', '.join(sorted(set(moved))))
print('superseded: %s' % ', '.join(sorted(set(superseded))))

from collections import Counter
rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
j = {h: i for i, h in enumerate(hdr)}
print('\namount basis now:', dict(Counter(str(r[j['amount basis']]) for r in rows)))
print('tiers now:', dict(Counter(str(r[j['disclosure tier']]) for r in rows)))
wb.save(WB)
print('saved')
