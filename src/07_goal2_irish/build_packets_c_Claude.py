"""T2 packets. FIX applied: the label shown in the header is the label found in
THAT filing, never pooled across the firm's filings (28% of round-B packets were
flagged label_absent because of pooling)."""
import zipfile, re, os, sys, json, time
import pandas as pd
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
OUT=os.path.join(BASE,'reader_packets_c')
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 150.0
T0=time.time()
q=pd.read_csv(os.path.join(BASE,'dta_probe','tablelab_ALL_Claude.csv'),dtype=str)
q['cikn']=pd.to_numeric(q.cik,errors='coerce')
F=pd.read_csv(os.path.join(BASE,'population_filings_Claude.csv'),low_memory=False)
F['eff']=F.is_effect.astype(str).isin(['1','1.0','True'])
eff=set(F[F.eff].cik); nm=F.drop_duplicates('cik').set_index('cik').company.to_dict()
IP=re.compile(r"intellectual\s+propert|intangible\s+(?:propert|asset)|\bip\b",re.I)
XF=re.compile(r"transfer|sale|sold|repatriat|realign|restructur|licen[cs]",re.I)
ENT=re.compile(r"intra\s*(?:entity|group|company)|inter\s*company|internal",re.I)
NO=re.compile(r"inventory|receivable|cost\s+of\s+sale|operating\s+profit|stock\s+sale|derivative|"
              r"\bloan\b|financing|available\s+for\s+sale|dividend|interest|pension|lease|"
              r"transfer\s+pricing",re.I)
q=q[~q.lab_n.str.contains(NO)]
t1 = q.lab_n.str.contains(IP) & q.lab_n.str.contains(XF)
t2 = (~t1) & q.lab_n.str.contains(ENT) & q.lab_n.str.contains(XF)
cand=q[t2]
cand=cand[~cand.cikn.isin(eff)]
# one packet per firm: prefer a 10-K, newest; carry only THAT filing's labels
cand=cand.assign(is10k=(cand.form=='10-K').astype(int))
cand=cand.sort_values(['cikn','is10k','date'],ascending=[True,False,False])
chosen={}
for _,r in cand.iterrows():
    c=int(r.cikn)
    if c in chosen: continue
    chosen[c]=(r.date,r.form)
perfiling={}
for _,r in cand.iterrows():
    perfiling.setdefault((r.cik,r.date),set()).add(r.lab_n)
print(f"T2 new firms: {len(chosen)}",flush=True)
want={}
for c,(dt,form) in chosen.items(): want.setdefault(str(c),set()).add(dt)

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
idx=[]
for zq in ZIPS:
    if time.time()-T0>BUDGET: print("budget"); break
    try: z=zipfile.ZipFile(os.path.join(BASE,zq))
    except Exception as e: print("skip",zq,e); continue
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
        labs=sorted(perfiling.get((cik,base[:8]),[]))
        nmm=nm.get(int(cik),'(not in frame)')
        tick=re.sub(r'[^A-Za-z0-9]','',str(nmm))[:16] or ('CIK'+cik)
        fn=f"{tick}_{cik}_{base[:8]}.txt"
        hdr=[f"COMPANY: {nmm}   CIK: {cik}   FORM: {form}   FILED: {base[:4]}-{base[4:6]}-{base[6:8]}","",
             "WHY THIS FILING IS HERE: a detector found the following label(s) inside THIS",
             "FILING's tax tables (rate reconciliation or deferred-tax components). The frame",
             "has NO transfer-effect row for this firm, so this is an unadjudicated candidate.",
             "Label(s) found in this filing:"]
        for l in labs: hdr.append(f"   - {l}")
        hdr += ["",
          "The detector is NOT evidence. Labels are pattern-extracted and some come from",
          "narrative text (Risk Factors, revenue descriptions, litigation, transfer-pricing",
          "audits, acquired-intangible purchase accounting, an individual's IP assignment),",
          "not table captions. Decide from the filing text.","",
          "NOTE: this corpus strips tables, so dollar SIGNS are absent and some figures are",
          "missing entirely. A bare number followed by 'million'/'billion' is an amount.","",
          "="*70,"INCOME TAX REGIONS OF THIS FILING","="*70,""]
        open(os.path.join(OUT,fn),'w',encoding='utf-8').write("\n".join(hdr)+"\n\n---- REGION BREAK ----\n\n".join(regs))
        idx.append(dict(cik=cik,company=nmm,form=form,filed=base[:8],file=fn,labels="; ".join(labs))); n_w+=1
    print(f"  {zq}: wrote {n_w} (total {len(idx)}) [{time.time()-T0:.0f}s]",flush=True)
pd.DataFrame(idx).to_csv(os.path.join(BASE,'dta_probe','packets_c_index_Claude.csv'),index=False)
print(f"packets written: {len(idx)}")
