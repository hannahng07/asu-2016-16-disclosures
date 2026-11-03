import zipfile, re, os, sys
import pandas as pd
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
T=pd.read_csv(os.path.join(BASE,'tracker_firms_resolved_Claude.csv'))
cm={str(int(c)):t for t,c in zip(T.tick,T.cik) if pd.notna(c)}
# "adopted ASU 2016-16 ..." with a date or a quarter, in either order
A=re.compile(r"(?:we|the\s+company|company)?\s*(?:early\s+)?adopt(?:ed|ion\s+of)\s+(?:(?:ASU|Accounting\s+Standards\s+Update)\s*(?:No\.\s*)?)?2016\s*-?\s*16"
             r"(?:[^.;]{0,200}?)(?:(?:as\s+of|effective(?:\s+as\s+of)?|on|in|beginning)\s+"
             r"(?:the\s+)?(?:(?:first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(?:year\s+)?\d{4}|"
             r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|"
             r"fiscal\s+(?:year\s+)?\d{4}|\d{4}))", re.I)
B=re.compile(r"(?:in|during)\s+the\s+(first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(?:year\s+)?(\d{4})[^.;]{0,120}?adopt(?:ed)?\s+(?:ASU\s*)?(?:No\.\s*)?2016\s*-?\s*16", re.I)
C=re.compile(r"(?:effective|as\s+of|on)\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})[^.;]{0,120}?adopt(?:ed)?\s+(?:ASU\s*)?(?:No\.\s*)?2016\s*-?\s*16", re.I)
ZIPS=['10-X_C_2016-2020.zip','10-X_C_2021.zip']
rows=[]
for zq in ZIPS:
    try: z=zipfile.ZipFile(os.path.join(BASE,zq))
    except Exception as e: print("skip",zq,e); continue
    for n in z.namelist():
        if not n.endswith('.txt'): continue
        mm=re.search(r'edgar_data_(\d+)_',n)
        if not mm or mm.group(1) not in cm: continue
        base=os.path.basename(n); date=base[:8]; form=base.split('_')[1]
        if form not in ('10-K','10-Q'): continue
        if not re.match(r'^(2018|2019|2020|2021)',date): continue
        t=re.sub(r'\s+',' ',z.read(n).decode('utf-8','replace'))
        for pat,lab in ((A,'A'),(B,'B'),(C,'C')):
            for g in pat.finditer(t):
                rows.append(dict(tick=cm[mm.group(1)],form=form,date=date,pat=lab,
                                 stmt=" ".join(g.group(0).split())[:260]))
o=pd.DataFrame(rows)
o=o.drop_duplicates(['tick','stmt']).groupby('tick',group_keys=False).head(6)
o.to_csv(os.path.join(BASE,'dta_probe','adoption_stmts_Claude.csv'),index=False)
print("firms with an adoption statement:",o.tick.nunique(),"of",len(set(cm.values())))
print("rows",len(o))
