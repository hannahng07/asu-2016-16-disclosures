"""THE DTA SCREEN across all 105 tracker firms, with its own confounds measured.

The logic generalises from the adoption-only build: because nobody restated, the ASU
catch-up lands in the adoption quarter and nowhere else, so any POSITIVE, MATERIAL jump in
the long-term DTA that falls outside both (a) the adoption quarter and (b) a transfer
quarter the firm itself stated, is a candidate undisclosed transfer.

This run also measures why it will be wrong, because that determines whether it is worth
using. Every jump is tagged with the first confound that applies:

  ANNUAL_INTERVAL   the two observations are >120 days apart, so catch-up and transfer
                    cannot be separated. txdbaq is year-end-only for many firms - the bug
                    that once hid MSFT, BSX, ALXN, GILD and META - so this is expected to
                    be the single largest category.
  POST_FY2021_174   on or after 2022: section 174 capitalised R&D dominates DTA growth
                    from then on. Arista's smooth ramp from 2022Q3 is the type case.
  TCJA_WINDOW       2017Q4-2018Q4: the Tax Cuts and Jobs Act remeasured every US DTA.
  DECREASE          a fall is amortisation or a valuation-allowance move, never a transfer.
  BELOW_FLOOR       under 20m and under 5% of the firm's own largest DTA balance.
  IN_ADOPTION_QTR   the catch-up. Expected, not a finding.
  IN_STATED_QTR     a transfer quarter the frame already records for that firm.
  CANDIDATE         survives all of the above.

The honest reading of the output is the ratio CANDIDATE : everything else. A screen whose
candidates are mostly confounded is a reading list, not a detector, and should be reported
as such.
"""
import os, re, csv
import pandas as pd
from collections import Counter, defaultdict

BASE = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
PROBE = os.path.join(BASE, 'dta_probe')
OUT = os.path.join(PROBE, 'dta_screen_all105_Claude.csv')

T = list(csv.DictReader(open(os.path.join(BASE, 'tracker_firms_resolved_Claude.csv'),
                             encoding='utf-8', errors='replace')))
tick = {}
for r in T:
    c = (r['cik'] or '').strip()
    if c:
        try:
            tick[str(int(float(c)))] = r['tick']
        except ValueError:
            pass
print('tracker firms with a cik: %d' % len(tick))

# transfer years the frame already records, per firm, so we do not re-flag known events
stated = defaultdict(set)
P = os.path.join(BASE, 'population_filings_Claude.csv')
for r in csv.DictReader(open(P, encoding='utf-8', errors='replace')):
    c = (r['cik'] or '').strip()
    if not c:
        continue
    try:
        c = str(int(float(c)))
    except ValueError:
        continue
    if c not in tick:
        continue
    if str(r.get('is_effect', '')).strip().lower() not in ('1', 'true', 'yes'):
        continue
    y = (r.get('transfer_year') or '').strip()
    if y:
        try:
            stated[c].add(int(float(y)))
        except ValueError:
            pass
print('firms with at least one stated transfer year: %d' % len(stated))

# adoption year: the frame's adoption_year_stated, else the first adoption_catchup filing
adopt = {}
for r in csv.DictReader(open(P, encoding='utf-8', errors='replace')):
    c = (r['cik'] or '').strip()
    if not c:
        continue
    try:
        c = str(int(float(c)))
    except ValueError:
        continue
    if c not in tick:
        continue
    a = (r.get('adoption_year_stated') or '').strip()
    if a:
        try:
            adopt.setdefault(c, int(float(a)))
            continue
        except ValueError:
            pass
    if (r.get('record_type') or '').strip() == 'adoption_catchup':
        fd = (r.get('filing_date') or '')[:4]
        if fd.isdigit():
            adopt.setdefault(c, int(fd))
print('firms with an adoption year: %d' % len(adopt))

df = pd.read_stata(os.path.join(BASE, 'ASUdata_CRSP_Compustat_May25.dta'),
                   convert_categoricals=False)
df['cik'] = df['cik'].astype(str).str.strip().str.lstrip('0')

rows = []
cov = Counter()
for cik, tk in sorted(tick.items(), key=lambda x: x[1]):
    g = df[df['cik'] == cik].sort_values('datadate')
    if g.empty:
        cov['no_compustat_rows'] += 1
        continue
    nn = g[g['txdbaq'].notna()][['datadate', 'txdbaq']]
    if len(nn) < 2:
        cov['fewer_than_2_txdbaq'] += 1
        continue
    # is this firm's series quarterly or annual?
    dts = [pd.Timestamp(str(d)[:10]) for d in nn['datadate']]
    gaps = [(dts[i + 1] - dts[i]).days for i in range(len(dts) - 1)]
    med = sorted(gaps)[len(gaps) // 2] if gaps else 999
    cov['series_quarterly' if med <= 120 else 'series_annual'] += 1
    base = float(nn['txdbaq'].max())
    floor = max(20.0, 0.05 * base)
    ay = adopt.get(cik)
    sy = stated.get(cik, set())
    prev = None
    for _, r in nn.iterrows():
        d = pd.Timestamp(str(r['datadate'])[:10])
        v = float(r['txdbaq'])
        if prev is not None:
            ch = v - prev[1]
            span = (d - prev[0]).days
            yr = d.year
            if ch < 0:
                tag = 'DECREASE'
            elif abs(ch) < floor:
                tag = 'BELOW_FLOOR'
            elif ay and prev[0].year <= ay <= yr:
                tag = 'IN_ADOPTION_QTR'
            elif any(prev[0].year <= s <= yr for s in sy):
                tag = 'IN_STATED_QTR'
            elif span > 120:
                tag = 'ANNUAL_INTERVAL'
            elif yr >= 2022:
                tag = 'POST_FY2021_174'
            elif (pd.Timestamp('2017-10-01') <= d <= pd.Timestamp('2018-12-31')):
                tag = 'TCJA_WINDOW'
            else:
                tag = 'CANDIDATE'
            rows.append(dict(firm=tk, cik=cik, from_date=str(prev[0].date()),
                             to_date=str(d.date()), interval_days=span,
                             change_musd=round(ch, 1), dta_base_musd=round(base, 1),
                             floor_musd=round(floor, 1), adoption_year=ay or '',
                             stated_years='|'.join(str(x) for x in sorted(sy)),
                             series=('quarterly' if med <= 120 else 'annual'), tag=tag))
        prev = (d, v)

with open(OUT, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print('\nFIRM COVERAGE of the 105:')
for k, v in sorted(cov.items(), key=lambda x: -x[1]):
    print('  %-22s %3d' % (k, v))

c = Counter(r['tag'] for r in rows)
tot = sum(c.values())
print('\nEVERY DTA INTERVAL TESTED: %d across %d firms'
      % (tot, len({r['firm'] for r in rows})))
for k, v in c.most_common():
    print('  %-18s %5d  %5.1f%%' % (k, v, 100.0 * v / tot))

cand = [r for r in rows if r['tag'] == 'CANDIDATE']
print('\nCANDIDATES: %d across %d firms' % (cand and len(cand) or 0,
                                            len({r['firm'] for r in cand})))
print('%-7s %-11s %-11s %5s %12s %-10s %s' %
      ('FIRM', 'FROM', 'TO', 'DAYS', 'CHANGE $m', 'SERIES', 'adopt/stated'))
for r in sorted(cand, key=lambda x: -x['change_musd']):
    print('%-7s %-11s %-11s %5d %12s %-10s %s/%s' %
          (r['firm'], r['from_date'], r['to_date'], r['interval_days'],
           '{:,.1f}'.format(r['change_musd']), r['series'],
           r['adoption_year'] or '-', r['stated_years'] or '-'))

# how much of the series is testable at all?
q = len([r for r in rows if r['series'] == 'quarterly'])
print('\nTESTABILITY: %.0f%% of intervals come from a quarterly series; '
      '%.0f%% are annual and cannot separate catch-up from transfer.'
      % (100.0 * q / tot, 100.0 * (tot - q) / tot))
print('wrote %s' % os.path.basename(OUT))
