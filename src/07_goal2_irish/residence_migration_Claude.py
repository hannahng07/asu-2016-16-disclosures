"""RESIDENCE MIGRATION: the detection surface the Irish Agent handed us.

Their point, which we had missed entirely: 16 of the 37 firms exited by RESIDENCE
MIGRATION rather than by moving IP (5 "residence migration only" + 11 "IP transfer out +
residence migration"). For those the Irish tax note changes rate on a printed date, and
the US side records the same change as a shift in the FOREIGN RATE DIFFERENTIAL rather
than as a transaction. So a firm can exit the structure with no transfer sentence and no
deferred-tax jump - which is exactly why our transfer-anchored and DTA-anchored detectors
found nothing for several of these.

They have also said a rate-reconciliation change is as good an answer as a transfer date.

This searches all 37 firms for:
  RESIDENCE   tax-residence and redomiciliation language, with any date in the sentence
  RATE_RECON  a foreign-rate-differential or statutory-rate line discussed in narrative
              text, where a change is attributed to a restructuring or residence change
  POST_2021   for the three right-censored firms (BMRN, HZNP, MENT), any evidence the
              structure ended or continued - now reaching FY2024 filings, because the
              2025 corpus year has appeared since our last sweep
"""
import zipfile, re, os, csv
from collections import defaultdict

BASE = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
OUT = os.path.join(BASE, 'dta_probe', 'residence_migration_Claude.csv')

# the 37, with the channel they flagged
FIRMS = {}
for r in csv.DictReader(open(os.path.join(BASE, 'DATE_REQUEST_TO_10K_WORKSTREAM_2026-10-09.csv'),
                             encoding='utf-8-sig', errors='replace')):
    FIRMS[r['ticker'].strip()] = (r['us_parent'].strip(), r['exit_channel'].strip(),
                                  r['haven'].strip(), r['exit_min'].strip(),
                                  r['exit_max'].strip())

# ticker -> cik, from the tracker
CIK = {}
for r in csv.DictReader(open(os.path.join(BASE, 'tracker_firms_resolved_Claude.csv'),
                             encoding='utf-8', errors='replace')):
    t = r['tick'].strip()
    c = (r['cik'] or '').strip()
    if t in FIRMS and c:
        try:
            CIK[str(int(float(c)))] = t
        except ValueError:
            pass
# NetScout, for their NTCT question
CIK['1078075'] = 'NTCT'
FIRMS.setdefault('NTCT', ('NETSCOUT SYSTEMS INC', 'their adjudication question',
                          '', '2015', '2018'))
print('firms requested: %d | resolved to a cik: %d' % (len(FIRMS), len(CIK)))
missing = sorted(set(FIRMS) - set(CIK.values()))
if missing:
    print('NO CIK (cannot search): %s' % ', '.join(missing))

RESIDENCE = re.compile(
    r"(?:became|become|becoming|is|was|ceased\s+to\s+be|no\s+longer)\s+"
    r"(?:an?\s+)?(?:Ir(?:ish|eland)|U\.?S\.?|United\s+States|domestic|foreign)?\s*"
    r"tax\s+residen\w+|"
    r"tax\s+residen(?:ce|cy|t)\s+(?:of|in|changed|change|was\s+changed|moved)|"
    r"change\s+in\s+(?:the\s+)?tax\s+residen\w+|"
    r"re-?domicil\w+|migrat\w+\s+(?:its|our|the)\s+(?:tax\s+)?residen\w+|"
    r"changed\s+(?:its|our)\s+(?:tax\s+)?residen\w+|"
    r"resident\s+(?:of|in)\s+Ireland|Irish\s+tax\s+resident", re.I)
RATE_RECON = re.compile(
    r"foreign\s+rate\s+differential|foreign\s+(?:income\s+)?tax\s+rate\s+differential|"
    r"rate\s+differential|statutory\s+rate\s+of\s+the\s+jurisdiction", re.I)
CAUSE = re.compile(
    r"restructur\w+|reorganiz\w+|realign\w+|residen\w+|redomicil\w+|"
    r"intra[-\s]?(?:entity|group|company)|intercompany|migrat\w+|"
    r"change\s+in\s+(?:the\s+)?(?:mix|jurisdictional)", re.I)
STRUCT_END = re.compile(
    r"(?:liquidat\w+|dissolv\w+|wound\s+up|winding\s+up|struck\s+off|"
    r"ceased\s+operations|no\s+longer\s+(?:in\s+)?(?:existence|operating|active))|"
    r"(?:Bermuda|Cayman|Bahamas|Isle\s+of\s+Man|Jersey)[^.;]{0,120}?"
    r"(?:liquidat|dissolv|no\s+longer|ceased|transferr?ed|merged)", re.I)
HAVEN = re.compile(r"Bermuda|Cayman|Bahamas|Isle\s+of\s+Man|\bJersey\b", re.I)
DATE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\s+\d{1,2},?\s+(?:19|20)\d{2}|"
    r"(?:first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(?:19|20)?\d{2,4}|"
    r"(?:effective|with\s+effect\s+from|as\s+of)\s+[^.;]{0,30}?(?:19|20)\d{2}|"
    r"\b(?:19|20)\d{2}\b")
SENT = re.compile(r"(?<=[.;])\s+")
ZIPS = ['10-X_C_2016-2020.zip', '10-X_C_2021.zip', '10-X_C_2022.zip',
        '10-X_C_2023.zip', '10-X_C_2024.zip', '10-X_C_2025.zip']
CENSORED = {'BMRN', 'HZNP', 'MENT'}

rows = []
seen_zip = []
for zq in ZIPS:
    p = os.path.join(BASE, zq)
    if not os.path.exists(p):
        continue
    seen_zip.append(zq)
    z = zipfile.ZipFile(p)
    for n in z.namelist():
        if not n.endswith('.txt'):
            continue
        m = re.search(r'edgar_data_(\d+)_', n)
        if not m or m.group(1) not in CIK:
            continue
        tk = CIK[m.group(1)]
        base = os.path.basename(n)
        parts = base.split('_')
        form = parts[1] if len(parts) > 1 else '?'
        if form not in ('10-K', '10-Q', '10-K-A'):
            continue
        t = " ".join(z.read(n).decode('utf-8', 'replace').split())
        seen = set()
        for s in SENT.split(t):
            if len(s) < 45 or len(s) > 620:
                continue
            kind = None
            if RESIDENCE.search(s):
                kind = 'RESIDENCE'
            elif RATE_RECON.search(s) and CAUSE.search(s):
                kind = 'RATE_RECON'
            elif tk in CENSORED and STRUCT_END.search(s) and HAVEN.search(s):
                kind = 'STRUCTURE_END'
            elif tk in CENSORED and HAVEN.search(s) and base[:4] >= '2022':
                kind = 'HAVEN_MENTION_POST2021'
            if not kind:
                continue
            k = (kind, re.sub(r'\d', '#', s[:95]))
            if k in seen:
                continue
            seen.add(k)
            ds = sorted({d.group(0) for d in DATE.finditer(s)})
            rows.append(dict(ticker=tk, cik=m.group(1), channel=FIRMS[tk][1],
                             haven=FIRMS[tk][2], window='%s-%s' % (FIRMS[tk][3], FIRMS[tk][4]),
                             form=form, date=base[:8], kind=kind,
                             dates_in_sentence=' | '.join(ds[:4]), sentence=s[:430]))

rows.sort(key=lambda r: (r['ticker'], r['kind'], r['date']))
with open(OUT, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=['ticker', 'cik', 'channel', 'haven', 'window',
                                       'form', 'date', 'kind', 'dates_in_sentence',
                                       'sentence'])
    w.writeheader()
    w.writerows(rows)

print('corpus years searched: %s' % ', '.join(seen_zip))
from collections import Counter
print('hits: %d across %d firms | %s'
      % (len(rows), len({r['ticker'] for r in rows}),
         dict(Counter(r['kind'] for r in rows))))

print('\n' + '=' * 78)
print('RESIDENCE LANGUAGE - the new surface. Firms with a DATE in the sentence first.')
print('=' * 78)
g = defaultdict(list)
for r in rows:
    if r['kind'] == 'RESIDENCE':
        g[r['ticker']].append(r)
for tk in sorted(g, key=lambda x: (not any(r['dates_in_sentence'] for r in g[x]), x)):
    v = g[tk]
    print('\n%-6s  channel=%-38s window=%s' % (tk, v[0]['channel'][:38], v[0]['window']))
    shown = 0
    for r in sorted(v, key=lambda x: (not x['dates_in_sentence'], x['date'])):
        if shown >= 3:
            break
        shown += 1
        print('   %-6s %s  dates: %s' % (r['form'], r['date'],
                                         r['dates_in_sentence'] or '(none)'))
        print('      %s' % r['sentence'][:300])

print('\n' + '=' * 78)
print('THE THREE RIGHT-CENSORED FIRMS: did the structure end, or continue past 2021?')
print('=' * 78)
for tk in ('BMRN', 'HZNP', 'MENT'):
    v = [r for r in rows if r['ticker'] == tk and
         r['kind'] in ('STRUCTURE_END', 'HAVEN_MENTION_POST2021')]
    print('\n%-6s haven=%-16s  %d hit(s)' % (tk, FIRMS.get(tk, ('', '', '?'))[2], len(v)))
    for r in sorted(v, key=lambda x: x['date'])[:5]:
        print('   [%s] %-6s %s' % (r['kind'][:14], r['form'], r['date']))
        print('      %s' % r['sentence'][:290])
print('\nwrote %s' % os.path.basename(OUT))
