"""Post-filter the 827 full-corpus US-inbound hits.

Post-filtering rather than re-sweeping, so the raw candidate set stays on disk with its
provenance and every rejection is auditable. Reject families were read off a random
sample of tier-A hits, not guessed:

  goodwill_segment  - "Goodwill of 3,795.5 million was assigned to the US Brands
                      segment" / "we have assigned goodwill to our US Retail ...
                      segments". Segment allocation of goodwill, not a transfer.
                      This was 4 of 10 in the sample - the dominant new family.
  earnings_repat    - "we may take advantage of opportunities where we are able to
                      repatriate these earnings to the U.S." BADREP caught
                      "repatriate cash/funds/earnings" but not "repatriate THESE
                      earnings".
  goods_movement    - "products sold internationally that may be re-imported to U.S.
                      retailers", "shipped and invoiced to a U.S.-based intermediary".
                      Physical goods, not assets.
  law_summary       - paragraphs reciting the TCJA's provisions rather than the firm's
                      own transaction.
"""
import csv, os, re, zipfile, json
from collections import defaultdict, Counter

BASE  = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
PROBE = os.path.join(BASE, 'dta_probe')
SRC   = os.path.join(PROBE, 'usin_all_hits_Claude.csv')
OUT   = os.path.join(PROBE, 'usin_all_filtered_Claude.csv')

REJ = [
 ('goodwill_segment', re.compile(
    r"goodwill[^.]{0,200}?assign\w+[^.]{0,120}?segment|"
    r"assign\w+[^.]{0,60}?goodwill|"
    r"assigned\s+to\s+(?:the|our)\s+(?:U\.S\.?|US|United\s+States)\s+"
    r"(?:[A-Z][a-z]+\s+){0,3}(?:segment|reportable|Retail|Brands|Specialized)", re.I)),
 ('earnings_repat', re.compile(
    r"repatriat\w*\s+(?:these|those|such|its|our|their|the|any|all|certain)?\s*"
    r"(?:earnings|profits|income|cash|funds|dividends)|"
    r"earnings\s+(?:could|would|can|may|will)\s+be\s+repatriat", re.I)),
 ('goods_movement', re.compile(
    r"re[-\s]?imported|shipped\s+and\s+invoiced|wholesale\s+distributor|"
    r"end\s+consumers|freight|customs\s+dut", re.I)),
 ('law_summary', re.compile(
    r"was\s+(?:added|enacted|eliminated|repealed)\s*;|"
    r"a\s+limitation\s+on\s+the\s+deduction|"
    r"will\s+be\s+subject\s+to\s+U\.S\.\s+tax\s+to\s+the\s+extent", re.I)),
 ('hypothetical', re.compile(
    r"\b(?:if|should|were)\s+we\s+(?:to\s+)?(?:transfer|repatriat|move)|"
    r"\bwe\s+(?:may|might|could|would)\s+(?:elect\s+to\s+)?(?:transfer|repatriat|move)\b|"
    r"no\s+(?:current\s+)?(?:plan|intention)\s+to\s+(?:transfer|repatriat)", re.I)),
]

# an assertion that a transfer actually HAPPENED, in the firm's own voice
ASSERT = re.compile(
    r"\b(?:transferr?ed|sold|completed|contributed|assigned|repatriated|realigned|"
    r"moved|relocated|migrated|executed|entered\s+into)\b", re.I)
IPWORD = re.compile(r"intellectual\s+propert|intangible(?:s\b|\s+propert|\s+asset)|\bIP\b", re.I)

rows = list(csv.DictReader(open(SRC, encoding='utf-8', errors='replace')))
print('raw hits: %d  firms: %d' % (len(rows), len({r['cik'] for r in rows})))

kept, rejected = [], []
for r in rows:
    w = r['excerpt']
    why = None
    for name, pat in REJ:
        if pat.search(w):
            why = name
            break
    if why:
        r['reject'] = why
        rejected.append(r)
    else:
        r['reject'] = ''
        r['asserts'] = 'yes' if ASSERT.search(w) else 'no'
        r['ip_named'] = 'yes' if IPWORD.search(w) else 'no'
        kept.append(r)

print('\nrejected %d:' % len(rejected), dict(Counter(r['reject'] for r in rejected)))
print('kept %d  (tier %s)' % (len(kept), dict(Counter(r['tier'] for r in kept))))
print('kept, asserted + IP named: %d' %
      len([r for r in kept if r['asserts'] == 'yes' and r['ip_named'] == 'yes']))

# ---- resolve CIK -> registrant name from the population frame, then the filing header
names = {}
pop = os.path.join(BASE, 'population_filings_Claude.csv')
if os.path.exists(pop):
    for r in csv.DictReader(open(pop, encoding='utf-8', errors='replace')):
        c = (r.get('cik') or '').strip()
        nm = (r.get('company') or r.get('coname') or r.get('company_name')
              or r.get('conm') or r.get('ticker') or '').strip()
        if c and nm and c not in names:
            names[c] = nm
print('\nnames from population frame: %d' % len(names))

for r in kept:
    r['company'] = names.get(r['cik'], '')

FIELDS = ['tier', 'cik', 'company', 'form', 'date', 'asserts', 'ip_named',
          'dest_phrase', 'excerpt']
with open(OUT, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction='ignore')
    w.writeheader()
    w.writerows(sorted(kept, key=lambda x: (x['tier'], -int(x['asserts'] == 'yes'),
                                            x['cik'], x['date'])))

with open(OUT.replace('filtered', 'rejected'), 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=['reject'] + FIELDS[:5] + ['dest_phrase', 'excerpt'],
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(rejected)

# ---- firm-level roll-up of the strongest class
best = defaultdict(list)
for r in kept:
    if r['tier'] == 'A' and r['asserts'] == 'yes':
        best[r['cik']].append(r)
print('\nTIER A + ASSERTED: %d rows across %d firms' %
      (sum(len(v) for v in best.values()), len(best)))
for c, v in sorted(best.items(), key=lambda kv: -len(kv[1])):
    v2 = sorted(v, key=lambda x: x['date'])
    print('  cik %-9s %-26s n=%-3d %s..%s' %
          (c, (names.get(c, '') or '?')[:26], len(v), v2[0]['date'], v2[-1]['date']))
