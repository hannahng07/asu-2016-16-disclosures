"""Detector: firm-authored LABELS inside the two tax tables.

  A) rate reconciliation  -> a reconciling line naming the transaction
  B) deferred tax components -> a DTA/DTL component line naming it

Loughran-McDonald strips table FIGURES but leaves table LABELS as text, so a
labelled line survives even when its number does not. Seeded on 17 labels
observed in confirmed cases, then generalised.

Resumable: processes chunks until a time budget, records progress in a state file,
so repeated invocations finish the corpus. Run: python3 -I table_label_scan_Claude.py [seconds]
"""
import zipfile, re, os, sys, csv, json, time
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
OUT=os.path.join(BASE,'dta_probe')
STATE=os.path.join(OUT,'table_label_state_Claude.json')
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 150.0
T0=time.time()

# ---------- byte-level candidate labels (cheap prefilter + locator) ----------
# literal byte keys: substring search is C-speed; a big case-insensitive regex
# over whole documents was the bottleneck (7k filings/quarter x ~1MB each).
KEYS=[b'intra-entity',b'intra entity',b'intraentity',b'intra-group',b'intra group',
      b'intra-company',b'intercompany',b'inter-company',b'intellectual propert',
      b'intangible propert',b'legal entit',b'other than inventory',
      b'repatriation and sale',b'restructuring of certain']
def label_positions(low,cap=80):
    out=[]
    for k in KEYS:
        i=low.find(k)
        while i!=-1 and len(out)<cap:
            out.append(i); i=low.find(k,i+len(k))
        if len(out)>=cap: break
    return sorted(set(out))

# ---------- the label must look like a reconciling / component CAPTION ----------
LABEL_PAT=re.compile(r"""(
    (?:intra[-\s]?entity|intra[-\s]?group|intra[-\s]?company|inter[-\s]?company|internal)
      [\w\s./'()-]{0,45}?
      (?:transfer|transfers|sale|sales|sold|profit|licen[cs]\w*|IP\b|intellectual\s+propert\w*|intangible\w*|asset\w*)
  | (?:intellectual\s+propert\w*|intangible\s+(?:propert\w*|asset\w*))
      [\w\s./'()-]{0,35}?
      (?:transfer\w*|repatriation|sale|sales|realign\w*|restructur\w*|step[-\s]?up)
  | (?:transfer\w*|sale|repatriation|restructur\w*|realign\w*|reorganiz\w*)
      [\w\s./'()-]{0,35}?
      (?:intellectual\s+propert\w*|intangible\s+(?:propert\w*|asset\w*)|IP\b)
  | legal\s+entit(?:y|ies)\s+(?:restructur\w*|realign\w*|reorganiz\w*|simplif\w*)
  | restructuring\s+of\s+certain\s+(?:non[-\s]?U\.?S\.?|foreign)\s+subsidiar\w*
  | (?:excess|difference)\s+of\s+tax\s+basis\s+over\s+book\s+basis\s+of\s+intangible\w*
  | prepaid\s+(?:tax\w*\s+)?on\s+inter[-\s]?company\s+profit
  | assets?\s+other\s+than\s+inventory
)""", re.I|re.X)

# ---------- region tests ----------
RR_A=re.compile(r"statutory\s+(?:federal\s+|U\.?S\.?\s+)?(?:income\s+)?tax\s+rate|federal\s+statutory\s+rate",re.I)
RR_B=re.compile(r"effective\s+(?:income\s+)?tax\s+rate|effective\s+rate",re.I)
DT_A=re.compile(r"deferred\s+tax\s+assets?",re.I)
DT_B=re.compile(r"valuation\s+allowance|deferred\s+tax\s+liabilit",re.I)
# a table region has many short label-like runs and few sentence-enders
def region_kind(w):
    rr = bool(RR_A.search(w)) and bool(RR_B.search(w))
    dt = bool(DT_A.search(w)) and bool(DT_B.search(w))
    if rr and dt: return 'both'
    if rr: return 'rate_rec'
    if dt: return 'deferred_tax_table'
    return ''
# exclude narrative: a label inside a long prose sentence is not a caption
SENT=re.compile(r"[.;]\s")
NOISE=re.compile(r"transfer\s+pricing|non[-\s]?inventory\s+(?:working|purchas|vendor|supplier|asset\s+write)|"
                 r"is\s+(?:currently\s+)?evaluating|removes\s+the\s+prohibition|FASB\s+issued|"
                 r"Accounting\s+Standards\s+Update|prohibits\s+the\s+recognition",re.I)

CHUNKS=[]
for y in ['2016','2017','2018','2019','2020']:
    for q in ['QTR1','QTR2','QTR3','QTR4']:
        CHUNKS.append(('10-X_C_2016-2020.zip', f'{y}/{q}'))
for z in ['10-X_C_2021.zip','10-X_C_2022.zip','10-X_C_2023.zip','10-X_C_2024.zip']:
    CHUNKS.append((z,''))

st=json.load(open(STATE)) if os.path.exists(STATE) else {'done':[]}
done=set(tuple(x) for x in st['done'])
fieldnames=['zip','chunk','cik','form','date','region','label','context']

for zq,pref in CHUNKS:
    if (zq,pref) in done: continue
    if time.time()-T0 > BUDGET:
        print(f"budget reached; {len(CHUNKS)-len(done)} chunks remain"); break
    try: z=zipfile.ZipFile(os.path.join(BASE,zq))
    except Exception as e:
        print("skip",zq,e); done.add((zq,pref)); continue
    rows=[]; nseen=0; ndeep=0
    for n in z.namelist():
        if not n.endswith('.txt'): continue
        if pref and not n.startswith(pref): continue
        base=os.path.basename(n); parts=base.split('_')
        form=parts[1] if len(parts)>1 else ''
        if form not in ('10-K','10-Q','10-K-A'): continue
        cik=re.search(r'edgar_data_(\d+)_',n)
        if not cik: continue
        try: raw=z.read(n)
        except Exception: continue
        nseen+=1
        low=raw.lower()
        pos=label_positions(low)
        if not pos: continue
        ndeep+=1
        seen=set()
        for p in pos:
            w=" ".join(raw[max(0,p-1400):p+1400].decode('utf-8','replace').split())
            kind=region_kind(w)
            if not kind: continue
            if NOISE.search(w[1150:1700]): continue
            # the label itself, taken from a tight window
            tight=" ".join(raw[max(0,p-120):p+180].decode('utf-8','replace').split())
            m=LABEL_PAT.search(tight)
            if not m: continue
            lab=" ".join(m.group(0).split())
            # captions are short and do not sit mid-sentence
            if len(lab)>95: continue
            k=lab.lower()[:55]
            if k in seen: continue
            seen.add(k)
            rows.append(dict(zip=zq,chunk=pref or 'all',cik=cik.group(1),form=form,date=base[:8],
                             region=kind,label=lab,context=w[1150:1700]))
    tag=(pref or 'all').replace('/','')
    f=os.path.join(OUT,f'tablelab_{zq[:-4]}_{tag}_Claude.csv')
    with open(f,'w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=fieldnames); w.writeheader(); w.writerows(rows)
    done.add((zq,pref))
    json.dump({'done':[list(x) for x in done]},open(STATE,'w'))
    print(f"{zq} {pref or 'all'}: filings {nseen}, candidates {ndeep}, labels {len(rows)}, "
          f"firms {len({r['cik'] for r in rows})}  [{time.time()-T0:.0f}s]",flush=True)
print(f"chunks done {len(done)}/{len(CHUNKS)}")
