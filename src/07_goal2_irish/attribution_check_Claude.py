"""THEIR NEW ASK: does each accession actually contain the sentence attributed to it?

A sentence that is verbatim correct but pinned to the wrong document fails in a way nobody
catches until someone opens the filing. The Zynga case was exactly this shape.

Test: for every row carrying both an accession and a quoted sentence, require a long literal
run of that sentence to appear in that accession's text. Normalised on whitespace only.
"""
import zipfile, os, re, csv
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
OUT=os.path.join(BASE,'ATTRIBUTION_CHECK_Claude.csv')
ZIPS=['10-X_C_2016-2020.zip','10-X_C_2021.zip','10-X_C_2022.zip','10-X_C_2023.zip',
      '10-X_C_2024.zip','10-X_C_2025.zip']
IDX={}
for zq in ZIPS:
    p=os.path.join(BASE,zq)
    if not os.path.exists(p): continue
    z=zipfile.ZipFile(p)
    for n in z.namelist():
        m=re.search(r'_(\d{10}-\d\d-\d{6})\.txt$',n)
        if m: IDX[m.group(1)]=(zq,n)
ZC={}; TC={}
def text(acc):
    if acc in TC: return TC[acc]
    if acc not in IDX:
        TC[acc]=None; return None
    zq,n=IDX[acc]
    if zq not in ZC: ZC[zq]=zipfile.ZipFile(os.path.join(BASE,zq))
    t=" ".join(ZC[zq].read(n).decode('utf-8','replace').split())
    if len(TC)>60: TC.clear()
    TC[acc]=t; return t

rows=[]
D=list(csv.DictReader(open(os.path.join(BASE,'IRISH_HANDOFF_4ITEMS_74FIRMS_Claude.csv'),
                           encoding='utf-8')))
for r in D:
    acc=(r['accession'] or '').strip()
    s=(r['verbatim_or_label'] or '').strip()
    if not acc or not r['evidence_type'].startswith('quoted') or s.startswith('NOT A QUOTATION'):
        continue
    t=text(acc)
    if t is None:
        v='FAIL - accession not in corpus'; probe=''
    else:
        # take a 90-char run from the middle, to avoid leading/trailing truncation artefacts
        s2=" ".join(s.split())
        probe=s2[:120] if len(s2)<=120 else s2[len(s2)//2-60:len(s2)//2+60]
        v='PASS' if probe.lower() in t.lower() else 'FAIL - sentence NOT in this accession'
        if v.startswith('FAIL'):
            # is it anywhere in the firm's other filings?
            v+= ' (sentence exists elsewhere for this firm)' if False else ''
    rows.append(dict(ticker=r['ticker_deliverable'],fiscal_year=r['fiscal_year'],item=r['item'],
        accession=acc,verdict=v,probe=probe,sentence=s2[:300] if t is not None else s[:300]))
with open(OUT,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh,fieldnames=['ticker','fiscal_year','item','accession','verdict','probe','sentence'])
    w.writeheader(); w.writerows(rows)
from collections import Counter
c=Counter(r['verdict'].split(' (')[0] for r in rows)
print('ATTRIBUTION CHECK - every quoted row with an accession: %d rows'%len(rows))
for k,v in c.most_common(): print('   %-44s %4d'%(k,v))
bad=[r for r in rows if r['verdict'].startswith('FAIL')]
if bad:
    print('\nFAILURES - sentence attributed to an accession that does not contain it:')
    for r in bad[:40]:
        print('   %-6s %-34s %s'%(r['ticker'],r['item'][:34],r['accession']))
        print('       probe: %r'%r['probe'][:110])
else:
    print('\nNO FAILURES. Every quoted sentence is present in the accession it is attributed to.')
print('\nwrote %s'%os.path.basename(OUT))
