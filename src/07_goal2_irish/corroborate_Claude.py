import zipfile, re, csv, os, sys, json
import pandas as pd

BASE = os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
J = pd.read_csv(os.path.join(BASE,'dta_probe','dta_jumps_Claude.csv'))
T = pd.read_csv(os.path.join(BASE,'tracker_firms_resolved_Claude.csv'))
cikmap = dict(zip(T['tick'], T['cik'].astype('Int64')))
firms = sorted(set(J.tick))
ciks  = {str(int(cikmap[t])): t for t in firms if t in cikmap and pd.notna(cikmap[t])}

import sys as _s; ZIPS = [_s.argv[1]]

FAM = [
 ('asu',          re.compile(r"(?:ASU|Update)\s*(?:No\.\s*)?2016\s*-?\s*16|Intra[-\s]?Entity\s+Transfers?\s+of\s+Assets", re.I)),
 ('transfer',      re.compile(r"(?:intra[-\s]?entity|intercompany|inter[-\s]?company|internal)\s+(?:\w+\s+){0,3}?(?:transfer|sale|sold|contribut\w+|assign\w+)|"
                              r"transfer(?:red|s|ring)?\s+(?:of\s+)?(?:certain\s+)?(?:intellectual\s+propert\w*|IP\b|intangible)", re.I)),
 ('restructure',   re.compile(r"(?:restructur|reorganiz|realign|simplif|consolidat|streamlin)\w*\s+(?:of\s+)?(?:our|its|the|certain)?\s*"
                              r"(?:corporate|legal|international|global|non[-\s]?U\.?S\.?|foreign)?\s*"
                              r"(?:legal\s+)?(?:entity|entities|structure|subsidiar\w+|organizat\w+)", re.I)),
 ('license_dir',   re.compile(r"(?:licens|own|hold|domicil|locat)\w*\s+(?:\w+\s+){0,6}?(?:intellectual\s+propert\w*|IP\b|intangible\w*)\s+(?:\w+\s+){0,4}?(?:from|to|in)\s+(?:the\s+)?(?:U\.?S\.?|United\s+States|Ireland|Irish|Bermuda|Singapore|Switzerland|Netherlands)|"
                              r"(?:intellectual\s+propert\w*|IP\b|intangible\w*)\s+(?:\w+\s+){0,5}?(?:from|to)\s+(?:the\s+)?(?:U\.?S\.?|United\s+States|Ireland|Bermuda|Singapore|Switzerland)", re.I)),
 ('dta_stepup',    re.compile(r"(?:deferred\s+tax\s+asset\w*|tax\s+basis|step[-\s]?up)\s+(?:\w+\s+){0,10}?(?:transfer|intra[-\s]?entity|intercompany|restructur\w+)|"
                              r"(?:transfer|intra[-\s]?entity|intercompany|restructur\w+)\w*\s+(?:\w+\s+){0,12}?(?:deferred\s+tax\s+asset|step[-\s]?up\s+in\s+(?:the\s+)?tax\s+basis)", re.I)),
]
AMT = re.compile(r"(?:\$\s*)?(\d[\d,]*(?:\.\d+)?)\s*(billion|million)", re.I)

rows=[]
for zq in ZIPS:
    p=os.path.join(BASE,zq)
    try: z=zipfile.ZipFile(p)
    except Exception as e:
        print("skip",zq,e); continue
    names=[n for n in z.namelist() if n.endswith('.txt')]
    pick=[]
    for n in names:
        m=re.search(r'edgar_data_(\d+)_',n)
        if m and m.group(1) in ciks: pick.append((n,ciks[m.group(1)]))
    print(zq,len(pick),"filings", flush=True)
    for n,tick in pick:
        base=os.path.basename(n); date=base[:8]; form=base.split('_')[1]
        if form not in ('10-K','10-Q','10-K-A'): continue
        if len(_s.argv)>2 and not date.startswith(_s.argv[2]): continue
        t=re.sub(r'\s+',' ',z.read(n).decode('utf-8','replace'))
        for fam,pat in FAM:
            seen=set()
            for mm in pat.finditer(t):
                a=max(0,mm.start()-400); b=min(len(t),mm.end()+500)
                exc=t[a:b]
                key=exc[300:420]
                if key in seen: continue
                seen.add(key)
                amts=[f"{g1} {g2}" for g1,g2 in AMT.findall(exc)]
                rows.append(dict(tick=tick,form=form,date=date,family=fam,
                                 match=" ".join(mm.group(0).split())[:160],
                                 amounts="; ".join(amts[:6]),
                                 excerpt=" ".join(exc.split())))
            # cap per family per filing
        
out=pd.DataFrame(rows)
# cap at 6 excerpts per (tick,date,family) keeping first
out=out.groupby(['tick','date','family'],group_keys=False).head(6)
out=out.sort_values(['tick','date','family'])
out.to_csv(os.path.join(BASE,'dta_probe','dta_corr_'+os.path.basename(ZIPS[0]).replace('.zip','')+(('_'+_s.argv[2]) if len(_s.argv)>2 else '')+'_Claude.csv'),index=False)
print("\nrows:",len(out))
print(out.groupby('family').size().to_string())
print("\nfirms x family (10-K only):")
k=out[out.form.str.startswith('10-K')]
print(pd.crosstab(k.tick,k.family).to_string())
