import zipfile, re, os, sys
import pandas as pd
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
T=pd.read_csv(os.path.join(BASE,'tracker_firms_resolved_Claude.csv'))
cm={str(int(c)):t for t,c in zip(T.tick,T.cik) if pd.notna(c)}
STD=re.compile(r"2016\s*-?\s*16")
ADOPT=re.compile(r"\badopt",re.I)
DATE=re.compile(r"(?:(first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(?:year\s+)?(\d{4}))|"
                r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})|"
                r"fiscal\s+(?:year\s+)?(\d{4})",re.I)
PAST=re.compile(r"\badopted\b|\bwe\s+adopt(?:ed)?\b|\badoption\s+of\s+(?:this|the)\s+standard\s+resulted",re.I)
ZIPS=sys.argv[1:]
rows=[]
for zq in ZIPS:
    try: z=zipfile.ZipFile(os.path.join(BASE,zq))
    except Exception as e: print("skip",zq,e,flush=True); continue
    for n in z.namelist():
        if not n.endswith('.txt'): continue
        mm=re.search(r'edgar_data_(\d+)_',n)
        if not mm or mm.group(1) not in cm: continue
        base=os.path.basename(n); date=base[:8]; form=base.split('_')[1]
        if form not in ('10-K','10-Q'): continue
        t=re.sub(r'\s+',' ',z.read(n).decode('utf-8','replace'))
        # split into sentences cheaply, keep those naming the standard AND an adoption verb
        for m in STD.finditer(t):
            a=max(0,m.start()-500); b=min(len(t),m.end()+500); seg=t[a:b]
            if not ADOPT.search(seg): continue
            if not PAST.search(seg): continue
            d=DATE.findall(seg)
            if not d: continue
            rows.append(dict(tick=cm[mm.group(1)],form=form,fdate=date,
                dates="; ".join(" ".join(x for x in tup if x) for tup in d[:4]),
                seg=" ".join(seg.split())[:300]))
o=pd.DataFrame(rows)
if len(o):
    o=o.drop_duplicates(['tick','dates']).sort_values(['tick','fdate']).groupby('tick',group_keys=False).head(8)
    f=os.path.join(BASE,'dta_probe',f'adopt2_{os.path.basename(ZIPS[0])[:-4]}_Claude.csv')
    o.to_csv(f,index=False); print("firms",o.tick.nunique(),"rows",len(o),"->",os.path.basename(f))
else: print("none")
