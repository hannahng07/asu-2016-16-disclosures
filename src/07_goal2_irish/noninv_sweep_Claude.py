"""Recall test: how many filings describe the TRANSACTION using the standard's own
definitional language -- 'non-inventory related assets' / 'assets other than
inventory' as an asserted event -- rather than naming IP? REGN cost us this."""
import zipfile, re, os, sys, csv
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
# 'non-inventory' never appears in the ASU title, so it is a clean discriminator.
NONINV=re.compile(r"non[-\s]?inventory", re.I)
# 'assets other than inventory' IS the ASU title -> require an assertion AND no
# standard-citation within the preceding 90 chars.
AOTI=re.compile(r"(sale|sales|sold|transfer|transfers|transferred|transferring)\s+(?:of\s+)?"
                r"(?:certain\s+)?assets\s+other\s+than\s+inventory", re.I)
CITE=re.compile(r"2016\s*-?\s*16|Topic\s*740|Accounting\s+Standards\s+Update|ASU\b|Income\s+Taxes\s*\(", re.I)
ASSERT=re.compile(r"\b(completed|recorded|recognized|resulted|occurred|impacted|benefit|expense|charge)\b",re.I)
AMT=re.compile(r"(?<![\d,.])(\d{1,4}(?:[,.]\d+)?)\s*(billion|million)\b",re.I)
rows=[]
for zq in sys.argv[1:]:
    try: z=zipfile.ZipFile(os.path.join(BASE,zq))
    except Exception as e: print("skip",zq,e,flush=True); continue
    nseen=0
    for n in z.namelist():
        if not n.endswith('.txt'): continue
        base=os.path.basename(n); form=base.split('_')[1] if '_' in base else ''
        if form not in ('10-K','10-Q','10-K-A'): continue
        _y=os.environ.get('YEAR')
        if _y and not base.startswith(_y): continue
        cik=re.search(r'edgar_data_(\d+)_',n)
        if not cik: continue
        try: raw=z.read(n)
        except Exception: continue
        nseen+=1
        low=raw.lower()
        if (b'non-inventory' not in low and b'non inventory' not in low
            and b'other than inventory' not in low): continue
        t=re.sub(r'\s+',' ',raw.decode('utf-8','replace'))
        hits=[]
        for m in NONINV.finditer(t):
            seg=t[max(0,m.start()-260):m.end()+320]
            if not ASSERT.search(seg): continue
            hits.append(('non-inventory',seg))
        for m in AOTI.finditer(t):
            pre=t[max(0,m.start()-90):m.start()]
            if CITE.search(pre): continue
            seg=t[max(0,m.start()-260):m.end()+320]
            if not ASSERT.search(seg): continue
            hits.append(('assets-other-than-inventory',seg))
        seen=set()
        for fam,seg in hits:
            k=seg[200:300]
            if k in seen: continue
            seen.add(k)
            rows.append(dict(zip=zq,cik=cik.group(1),form=form,date=base[:8],family=fam,
                amounts="; ".join(f"{a} {b}" for a,b in AMT.findall(seg)[:5]),
                excerpt=" ".join(seg.split())))
    print(f"  {zq}: scanned {nseen} filings, cumulative hits {len(rows)}",flush=True)
out=os.path.join(BASE,'dta_probe',f'noninv_{sys.argv[1][:-4]}{("_"+os.environ["YEAR"]) if os.environ.get("YEAR") else ""}_Claude.csv')
with open(out,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh,fieldnames=['zip','cik','form','date','family','amounts','excerpt']); w.writeheader(); w.writerows(rows)
print(f"rows {len(rows)}  filings {len({(r['cik'],r['date']) for r in rows})}  firms {len({r['cik'] for r in rows})} -> {os.path.basename(out)}")
