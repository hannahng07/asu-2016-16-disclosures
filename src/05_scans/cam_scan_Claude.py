#!/usr/bin/env python3
r"""Critical Audit Matters about intra-entity IP transfers.

WHY A CAM IS WORTH ITS OWN SWEEP
--------------------------------
A CAM exists because the AUDITOR judged the matter material and subjective. That
is a materiality filter the project otherwise has to infer. And the CAM wording
is unusually complete -- it names the transaction type, states the figure, says
what the figure IS, and often names the destination:

  Boston Scientific  "recognized a deferred tax asset and related income tax
                      benefit of $4.1 billion based upon the tax basis step-up to
                      the intellectual property's current fair value"
  MACOM              "completed an intra-entity transfer of a license for
                      intellectual property TO A HIGHER TAX JURISDICTION ...
                      deferred tax asset and related income tax benefit of $39.8
                      million based upon the tax basis step-up"
  Arista             "in exchange for a non-interest-bearing note of $3.4 billion
                      ... tax basis in the IP transferred equaled the fair market
                      value ... recognition of a deferred tax asset of $429.1
                      million ... offset by a deferred tax liability of $343.3
                      million"

Note the two figure KINDS sitting in the same vocabulary. Boston Scientific's and
MACOM's numbers are TAX EFFECTS. Arista's $3.4bn is the IP VALUE, and its tax
effect is $429.1m DTA less $343.3m DTL = $85.8m net -- which reconciles exactly
to its rate-rec line, "Intra-Entity Sale (9.95)" on $862.3m of pre-tax income.
`figure_kind` below keeps them apart; conflating them is settled point 1.

COVERAGE
--------
CAMs are required for large accelerated filers with fiscal years ending on or
after 30 June 2019, and for other filers from 15 December 2020. So this sweep
starts at 2019 and only reads 10-Ks -- the CAM is in the auditor's report, which
10-Qs do not carry.

RESUME
------
`device_bash` is capped at 180s per call, so this processes `--limit` files per
run and records progress in cam_scan_state_Claude.json. Re-run until done.
"""
import zipfile, re, json, sys, csv, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT   = HERE/"cam_hits_Claude.csv"
STATE = HERE/"cam_scan_state_Claude.json"
ZIPS  = ["10-X_C_2016-2020.zip","10-X_C_2021.zip","10-X_C_2022.zip",
         "10-X_C_2023.zip","10-X_C_2024.zip"]

CAM   = re.compile(r"critical\s+audit\s+matter",re.I)
TOPIC = re.compile(r"intra[-\s]?entity|intra[-\s]?group|intercompany\s+(?:transfer|sale)|"
                   r"transfer\s+of\s+(?:a\s+license\s+for\s+)?(?:certain\s+)?"
                   r"(?:intellectual\s+propert|intangible)",re.I)
MONEY = re.compile(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(billion|million|thousand)\b",re.I)
HIGHER= re.compile(r"to\s+a\s+higher\s+tax\s+jurisdiction|higher\s+tax\s+jurisdiction",re.I)
LOWER = re.compile(r"to\s+a\s+lower\s+tax\s+jurisdiction|lower\s+tax\s+jurisdiction",re.I)
# what the number IS
EFFECT= re.compile(r"deferred\s+tax\s+asset\s+and\s+related\s+income\s+tax\s+benefit\s+of|"
                   r"income\s+tax\s+benefit\s+of|deferred\s+tax\s+(?:asset|liability)\s+of|"
                   r"tax\s+benefit\s+of|tax\s+charge\s+of|tax\s+expense\s+of",re.I)
VALUE = re.compile(r"note\s+of|fair\s+market\s+value|in\s+exchange\s+for|"
                   r"fair\s+value\s+of\s+the\s+(?:transferred\s+)?(?:IP|intellectual)",re.I)

def mult(u): return {'billion':1e9,'million':1e6,'thousand':1e3}[u.lower()]

def main():
    limit=int(sys.argv[1]) if len(sys.argv)>1 else 4000
    st=json.load(open(STATE)) if STATE.exists() else {"done":{},"n":0}
    rows=[]; processed=0
    for zn in ZIPS:
        if not (HERE/zn).exists(): continue
        z=zipfile.ZipFile(HERE/zn)
        names=st["done"].get(zn+"_names")
        if names is None:
            names=[n for n in z.namelist()
                   if n.endswith('.txt') and '_10-K' in n
                   and re.search(r"/(2019|2020|2021|2022|2023|2024)/",'/'+n)]
            st["done"][zn+"_names"]=names
        i=st["done"].get(zn,0)
        if i>=len(names): continue
        while i<len(names) and processed<limit:
            n=names[i]; i+=1; processed+=1
            try: raw=z.read(n).decode('utf-8','replace')
            except Exception: continue
            if not CAM.search(raw): continue
            t=re.sub(r'\s+',' ',raw)
            for m in CAM.finditer(t):
                blk=t[max(0,m.start()-2500):m.start()+3500]
                if not TOPIC.search(blk): continue
                em=EFFECT.search(blk); vm=VALUE.search(blk)
                fig=None;kind=''
                src=blk[em.end():em.end()+60] if em else ''
                mm=MONEY.search(src)
                if mm: fig=float(mm.group(1).replace(',',''))*mult(mm.group(2)); kind='tax_effect'
                else:
                    mm=MONEY.search(blk)
                    if mm:
                        fig=float(mm.group(1).replace(',',''))*mult(mm.group(2))
                        kind='ip_value_or_unclear' if vm else 'unclear'
                base=os.path.basename(n)
                p=base.split('_')
                rows.append(dict(zipfile=zn,file=base,date=p[0],form=p[1],
                    cik=p[4] if len(p)>4 else '', accession=p[5].replace('.txt','') if len(p)>5 else '',
                    figure=fig, figure_kind=kind,
                    dest_hint=('higher_tax' if HIGHER.search(blk) else
                               'lower_tax' if LOWER.search(blk) else ''),
                    excerpt=" ".join(blk[max(0,m.start()-(m.start()-max(0,m.start()-2500))):][:1400].split())))
                break
        st["done"][zn]=i
        if processed>=limit: break
    st["n"]=st.get("n",0)+processed
    hdr=not OUT.exists()
    if rows:
        with open(OUT,'a',newline='',encoding='utf-8') as fh:
            w=csv.DictWriter(fh,fieldnames=list(rows[0].keys()))
            if hdr: w.writeheader()
            w.writerows(rows)
    json.dump(st,open(STATE,'w'))
    tot=sum(v for k,v in st["done"].items() if not k.endswith("_names"))
    allf=sum(len(v) for k,v in st["done"].items() if k.endswith("_names"))
    print(f"this run: {processed} files, {len(rows)} CAM hits | cumulative {tot}/{allf} 10-Ks scanned")
main()
