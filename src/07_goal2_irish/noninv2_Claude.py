"""Fast version: locate candidate positions in RAW BYTES, normalise only local
windows. Avoids re.sub over whole documents, which was the bottleneck in the
2017 boilerplate year."""
import zipfile, re, os, sys, csv
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
B_NONINV=re.compile(rb"non[-\s]?inventory", re.I)
B_AOTI  =re.compile(rb"(sale|sales|sold|transfer|transfers|transferred|transferring)\s+(?:of\s+)?"
                    rb"(?:certain\s+)?assets\s+other\s+than\s+inventory", re.I)
B_CITE  =re.compile(rb"2016\s*-?\s*16|Topic\s*740|Accounting\s+Standards\s+Update|ASU\b|Income\s+Taxes\s*\(", re.I)
B_ASSERT=re.compile(rb"\b(completed|recorded|recognized|resulted|occurred|impacted|benefit|expense|charge)\b",re.I)
AMT=re.compile(r"(?<![\d,.])(\d{1,4}(?:[,.]\d+)?)\s*(billion|million)\b",re.I)
def norm(b): return " ".join(b.decode('utf-8','replace').split())
rows=[]; zq=sys.argv[1]; Y=os.environ.get('YEAR')
z=zipfile.ZipFile(os.path.join(BASE,zq)); nseen=0; ndeep=0
for n in z.namelist():
    if not n.endswith('.txt'): continue
    base=os.path.basename(n); parts=base.split('_')
    form=parts[1] if len(parts)>1 else ''
    if form not in ('10-K','10-Q','10-K-A'): continue
    if Y and not n.startswith(Y): continue
    cik=re.search(r'edgar_data_(\d+)_',n)
    if not cik: continue
    try: raw=z.read(n)
    except Exception: continue
    nseen+=1
    cand=[]
    for m in B_NONINV.finditer(raw):
        a=max(0,m.start()-300); b=min(len(raw),m.end()+360)
        w=raw[a:b]
        if B_ASSERT.search(w): cand.append(('non-inventory',w))
    for m in B_AOTI.finditer(raw):
        if B_CITE.search(raw[max(0,m.start()-110):m.start()]): continue
        a=max(0,m.start()-300); b=min(len(raw),m.end()+360)
        w=raw[a:b]
        if B_ASSERT.search(w): cand.append(('assets-other-than-inventory',w))
    if not cand: continue
    ndeep+=1
    seen=set()
    for fam,w in cand:
        seg=norm(w); k=seg[230:330]
        if k in seen: continue
        seen.add(k)
        rows.append(dict(zip=zq,cik=cik.group(1),form=form,date=base[:8],family=fam,
            amounts="; ".join(f"{a} {b}" for a,b in AMT.findall(seg)[:5]), excerpt=seg))
out=os.path.join(BASE,'dta_probe',f'noninv2_{zq[:-4]}{("_"+Y.replace("/","")) if Y else ""}_Claude.csv')
with open(out,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh,fieldnames=['zip','cik','form','date','family','amounts','excerpt']); w.writeheader(); w.writerows(rows)
print(f"{zq} {Y or 'all'}: scanned {nseen}, with candidates {ndeep}, rows {len(rows)}, "
      f"filings {len({(r['cik'],r['date']) for r in rows})}, firms {len({r['cik'] for r in rows})} -> {os.path.basename(out)}")
