"""Adjudicate the 55 tier-A asserted firms from the full-corpus US-inbound sweep.

Two jobs: resolve the CIKs the population frame does not name (by reading the
registrant name out of the filing itself), and tighten two further false-positive
families read off the excerpts:

  unremitted_hypothetical - "if these funds were repatriated to the U.S." The
      unremitted-foreign-earnings paragraph, in every 10-Q a firm files. This was
      Synchronoss (19 hits) and Varian (9) - both pure boilerplate. The first-round
      earnings_repat pattern only caught "repatriate <noun>", not "<noun> were
      repatriated".
  goods_import - "footwear is sold at foreign ports to 25 customers who then import
      the footwear into the United States". Physical goods again (Caleres, 6).
"""
import csv, os, re, zipfile, json
from collections import defaultdict, Counter

BASE  = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
PROBE = os.path.join(BASE, 'dta_probe')
SRC   = os.path.join(PROBE, 'usin_all_filtered_Claude.csv')
OUT   = os.path.join(PROBE, 'usin_all_adjudicated_Claude.csv')
NAMES = os.path.join(PROBE, 'usin_all_names_Claude.json')

REJ2 = [
 ('unremitted_hypothetical', re.compile(
    r"(?:funds|earnings|profits|cash|amounts|monies)\s+(?:were|was|are|is|be|"
    r"to\s+be|could\s+be|would\s+be|had\s+been)\s+repatriat|"
    r"permanently\s+reinvested|indefinitely\s+reinvested|"
    r"not\s+practic\w+\s+to\s+determine\s+the\s+unrecognized", re.I)),
 ('goods_import', re.compile(
    r"import\w*\s+(?:the\s+)?(?:\w+\s+){0,2}into\s+the\s+United\s+States|"
    r"foreign\s+ports|first[-\s]cost\s+transaction", re.I)),
]

rows = [r for r in csv.DictReader(open(SRC, encoding='utf-8', errors='replace'))]
tA = [r for r in rows if r['tier'] == 'A' and r['asserts'] == 'yes']
print('tier A asserted in: %d rows, %d firms' % (len(tA), len({r['cik'] for r in tA})))

keep, rej = [], []
for r in tA:
    why = next((n for n, p in REJ2 if p.search(r['excerpt'])), None)
    if why:
        r['reject2'] = why
        rej.append(r)
    else:
        r['reject2'] = ''
        keep.append(r)
print('rejected round 2: %d' % len(rej), dict(Counter(r['reject2'] for r in rej)))
print('firms fully rejected:',
      sorted({r['cik'] for r in rej} - {r['cik'] for r in keep}))
print('surviving: %d rows, %d firms' % (len(keep), len({r['cik'] for r in keep})))

# ---- resolve names for CIKs the frame did not name, from the filing header
need = sorted({r['cik'] for r in keep if not r['company']})
names = json.load(open(NAMES)) if os.path.exists(NAMES) else {}
need = [c for c in need if c not in names]
if need:
    HDR = re.compile(r"COMPANY\s+CONFORMED\s+NAME:\s*(.+)")
    want = {}
    for r in keep:
        if r['cik'] in need and r['cik'] not in want:
            want[r['cik']] = r['date']
    ZIPS = ['10-X_C_2016-2020.zip', '10-X_C_2021.zip', '10-X_C_2022.zip',
            '10-X_C_2023.zip', '10-X_C_2024.zip']
    for zq in ZIPS:
        p = os.path.join(BASE, zq)
        if not os.path.exists(p) or not want:
            continue
        z = zipfile.ZipFile(p)
        for n in z.namelist():
            if not n.endswith('.txt'):
                continue
            m = re.search(r'edgar_data_(\d+)_', n)
            if not m or m.group(1) not in want:
                continue
            head = z.read(n)[:4000].decode('utf-8', 'replace')
            hm = HDR.search(head)
            if hm:
                names[m.group(1)] = hm.group(1).strip()
                want.pop(m.group(1), None)
            else:
                # LM files often drop the SEC header; fall back to the first
                # all-caps-ish line of the body
                for line in head.split('\n')[:40]:
                    s = line.strip()
                    if 8 < len(s) < 70 and re.match(r"^[A-Z][A-Za-z0-9&.,'\- ]+$", s):
                        names[m.group(1)] = s
                        want.pop(m.group(1), None)
                        break
    json.dump(names, open(NAMES, 'w'))
for r in keep:
    if not r['company']:
        r['company'] = names.get(r['cik'], '')

FIELDS = ['cik', 'company', 'form', 'date', 'dest_phrase', 'excerpt']
with open(OUT, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction='ignore')
    w.writeheader()
    w.writerows(sorted(keep, key=lambda x: (x['cik'], x['date'])))

g = defaultdict(list)
for r in keep:
    g[r['cik']].append(r)
print('\n%-9s %-32s %-4s %s' % ('CIK', 'COMPANY', 'N', 'FIRST..LAST'))
for c, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    v2 = sorted(v, key=lambda x: x['date'])
    print('%-9s %-32s %-4d %s..%s' % (c, (v2[0]['company'] or '?')[:32], len(v),
                                      v2[0]['date'], v2[-1]['date']))
