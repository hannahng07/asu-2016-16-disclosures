#!/usr/bin/env python3
r"""Pull the INTANGIBLES deferred-tax lines from every SEC notes set.

WHY
---
`effect_direction` counts benefit/cost CUES IN THE SENTENCE. That is the
measurement settled point 5 warns will bias the population, and it is worse than
it looks: the word "benefit" sits inside the boilerplate itself -- "the income
tax consequences (expense or benefit) of an intercompany transfer" -- so the
sign signal is contaminated by the same boilerplate that beat PepsiCo's event
sentence on score.

Four independent findings now say the vocabulary sign is wrong:
  * Microchip signed COST on "a cumulative-effect INCREASE in deferred tax
    assets of approximately 1.58 billion"
  * Stryker's stored figure was the adoption DECREASE to retained earnings (a
    cost) while its FY2018 event was a $1.5bn BENEFIT -- opposite signs
  * a single transfer can produce a DTA *and* a DTL (Arista: +429.1 / -343.3)
  * MACOM transferred to a HIGHER tax jurisdiction and booked a BENEFIT

The vocabulary-free instrument is the intangibles line of the deferred tax
components table, which is XBRL numerics -- no text parsing:

    DeferredTaxAssetsGoodwillAndIntangibleAssets
    DeferredTaxLiabilitiesGoodwillAndIntangibleAssets[IntangibleAssets]

PepsiCo FY2018 straight out of num.tsv: DTA 0 -> 985,000,000 and DTL
3,169,000,000 -> 0. A $4.154bn swing toward ASSET = benefit, no adjective read.

Rule: the intangibles net position moves toward ASSET -> benefit; toward
LIABILITY -> cost.

Resumable: `device_bash` caps at 180s, so this does `--limit` zips per run and
records progress in intangibles_scan_state_Claude.json.
"""
import zipfile, csv, io, sys, re, json, os, glob
from pathlib import Path
csv.field_size_limit(min(sys.maxsize,2**31-1))
HERE=Path('.')
OUT=HERE/'intangibles_dtaxes_Claude.csv'
ST =HERE/'intangibles_scan_state_Claude.json'
TAG=re.compile(r"^DeferredTax(Assets|Liabilities).*(Intangible|Goodwill)",re.I)

def main():
    limit=int(sys.argv[1]) if len(sys.argv)>1 else 4
    zips=sorted(glob.glob('*_notes.zip'))
    st=json.load(open(ST)) if ST.exists() else {"done":[]}
    todo=[z for z in zips if z not in st["done"]][:limit]
    if not todo:
        print(f"all {len(zips)} notes sets scanned"); return
    rows=[]
    for zn in todo:
        z=zipfile.ZipFile(zn); sub={}
        with z.open('sub.tsv') as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh,'utf-8',errors='replace'),delimiter='\t'):
                sub[r['adsh']]=(r.get('cik','').lstrip('0'),r.get('form'),r.get('period'),r.get('fy'),r.get('fp'))
        n=0
        with z.open('num.tsv') as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh,'utf-8',errors='replace'),delimiter='\t'):
                t=r.get('tag','')
                if not TAG.match(t): continue
                if r.get('coreg'): continue          # parent-only
                if (r.get('qtrs') or '0') != '0': continue   # point-in-time balances
                s=sub.get(r['adsh'])
                if not s: continue
                try: v=float(r['value'])
                except (TypeError,ValueError): continue
                rows.append(dict(zipname=zn,adsh=r['adsh'],cik=s[0],form=s[1],period=s[2],
                                 fy=s[3],fp=s[4],tag=t,ddate=r['ddate'],value=v,
                                 side=('DTA' if re.match(r"DeferredTaxAssets",t,re.I) else 'DTL')))
                n+=1
        st["done"].append(zn); print(f"  {zn}: {n} intangibles deferred-tax facts")
    hdr=not OUT.exists()
    if rows:
        import pandas as pd
        pd.DataFrame(rows).to_csv(OUT,mode='a',header=hdr,index=False)
    json.dump(st,open(ST,'w'))
    print(f"cumulative: {len(st['done'])}/{len(zips)} notes sets")
main()
