"""Packets for the label-detector candidates: firms with a transfer-ish label in a
tax table but NO effect row in the frame. Same anchor-free design as round one:
the reader gets the income-tax regions and decides."""
import zipfile, re, os, sys, csv, json, time
import pandas as pd
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
OUT=os.path.join(BASE,'reader_packets_b')
STATE=os.path.join(BASE,'dta_probe','packets_b_state_Claude.json')
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 150.0
T0=time.time()

q=pd.read_csv(os.path.join(BASE,'dta_probe','tablelab_ALL_Claude.csv'),dtype=str)
q['cikn']=pd.to_numeric(q.cik,errors='coerce')
F=pd.read_csv(os.path.join(BASE,'population_filings_Claude.csv'),low_memory=False)
F['eff']=F.is_effect.astype(str).isin(['1','1.0','True'])
eff=set(F[F.eff].cik); nm=F.drop_duplicates('cik').set_index('cik').company.to_dict()
IP=re.compile(r"intellectual\s+propert|intangible\s+(?:propert|asset)|\bip\b",re.I)
XF=re.compile(r"transfer|sale|sold|repatriat|realign|restructur|licen[cs]",re.I)
NO=re.compile(r"inventory|receivable|cost\s+of\s+sale|operating\s+profit|stock\s+sale|derivative|"
              r"\bloan\b|financing|available\s+for\s+sale|dividend|interest|pension|lease",re.I)
q=q[~q.lab_n.str.contains(NO)]
t1=q[q.lab_n.str.contains(IP)&q.lab_n.str.contains(XF)]
t1=t1[~t1.cikn.isin(eff)]
# one packet per (cik, filing_date); prefer 10-K, newest first, max 2 per firm
t1=t1.sort_values(['cikn','form','date'],ascending=[True,True,False])
pick={}
for _,r in t1.iterrows():
    c=int(r.cikn); pick.setdefault(c,[])
    key=(r.date,r.form)
    if key not in pick[c] and len(pick[c])<2: pick[c].append(key)
want={}
for c,ks in pick.items():
    for dt,form in ks: want.setdefault(str(c),set()).add(dt)
labmap={}
for c,g in t1.groupby('cikn'):
    labmap[str(int(c))]=sorted(set(g.lab_n))[:6]
print(f"T1 new firms {len(pick)}  target packets {sum(len(v) for v in pick.values())}",flush=True)

HEAD=re.compile(r"(?:NOTE\s+\d+[.:\s-]{0,4})?(?:INCOME\s+TAXES|Income\s+Taxes|PROVISION\s+FOR\s+INCOME\s+TAXES|TAXES\s+ON\s+INCOME)",re.I)
TAXY=re.compile(r"deferred\s+tax|effective\s+tax\s+rate|statutory",re.I)
def regions(t,maxlen=24000,k=2):
    c=[]
    for m in HEAD.finditer(t):
        seg=t[m.start():m.start()+maxlen]
        c.append((len(TAXY.findall(seg[:9000])),m.start(),seg))
    c.sort(reverse=True); out=[];used=[]
    for sc,pos,seg in c:
        if sc<4: continue
        if any(abs(pos-p)<8000 for p in used): continue
        used.append(pos); out.append(seg)
        if len(out)>=k: break
    return out

ZIPS=['10-X_C_2016-2020.zip','10-X_C_2021.zip','10-X_C_2022.zip','10-X_C_2023.zip','10-X_C_2024.zip']
st=json.load(open(STATE)) if os.path.exists(STATE) else {'done':[]}
done=set(st['done']); idx=[]
for zq in ZIPS:
    if zq in done: continue
    if time.time()-T0>BUDGET: print("budget reached"); break
    try: z=zipfile.ZipFile(os.path.join(BASE,zq))
    except Exception as e: print("skip",zq,e); done.add(zq); continue
    n_w=0
    for n in z.namelist():
        if not n.endswith('.txt'): continue
        base=os.path.basename(n); parts=base.split('_')
        form=parts[1] if len(parts)>1 else ''
        if form not in ('10-K','10-Q'): continue
        m=re.search(r'edgar_data_(\d+)_',n)
        if not m or m.group(1) not in want: continue
        if base[:8] not in want[m.group(1)]: continue
        cik=m.group(1)
        t=re.sub(r'\s+',' ',z.read(n).decode('utf-8','replace'))
        regs=regions(t)
        if not regs: continue
        tick=re.sub(r'[^A-Za-z0-9]','',str(nm.get(int(cik),'CIK'+cik)))[:16] or ('CIK'+cik)
        fn=f"{tick}_{cik}_{base[:8]}.txt"
        hdr=[f"COMPANY: {nm.get(int(cik),'(not in frame)')}   CIK: {cik}   FORM: {form}   FILED: {base[:4]}-{base[4:6]}-{base[6:8]}","",
             "WHY THIS FILING IS HERE: a detector found the following LABEL(S) inside this",
             "firm's tax tables (rate reconciliation or deferred-tax components). The frame",
             "has NO transfer-effect row for this firm, so this is an unadjudicated candidate.",
             "Labels found (normalised, across this firm's filings):"]
        for l in labmap.get(cik,[]): hdr.append(f"   - {l}")
        hdr += ["",
          "The detector is NOT evidence. Labels were extracted by pattern and many are",
          "narrative text (Risk Factors, revenue descriptions, litigation, employment IP",
          "assignments), not table captions. Your job is to decide from the filing text.","",
          "NOTE: this corpus strips tables, so dollar SIGNS are absent and some figures are",
          "missing entirely. A bare number followed by 'million'/'billion' is an amount.","",
          "="*70,"INCOME TAX REGIONS OF THIS FILING","="*70,""]
        open(os.path.join(OUT,fn),'w',encoding='utf-8').write("\n".join(hdr)+"\n\n---- REGION BREAK ----\n\n".join(regs))
        idx.append(dict(cik=cik,company=nm.get(int(cik),''),form=form,filed=base[:8],file=fn)); n_w+=1
    done.add(zq); json.dump({'done':sorted(done)},open(STATE,'w'))
    print(f"  {zq}: wrote {n_w}  (total {len(idx)})  [{time.time()-T0:.0f}s]",flush=True)
if idx:
    f=os.path.join(BASE,'dta_probe','packets_b_index_Claude.csv')
    pd.DataFrame(idx).to_csv(f,mode='a',header=not os.path.exists(f),index=False)
print(f"done zips {len(done)}/{len(ZIPS)}")
