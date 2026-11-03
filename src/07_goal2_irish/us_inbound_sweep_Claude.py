"""Tight, high-precision sweep of the 105 tracker firms for IP moving INTO the US.
Goal 2 is the only question here, so the pattern is narrow on purpose: an IP /
intangible / asset-transfer token must sit within a short window of an explicit
US destination phrase."""
import zipfile, re, os, sys, csv, json, time
import pandas as pd
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
T=pd.read_csv(os.path.join(BASE,'tracker_firms_resolved_Claude.csv'))
cm={str(int(c)):t for t,c in zip(T.tick,T.cik) if pd.notna(c)}
BUDGET=float(sys.argv[2]) if len(sys.argv)>2 else 150.0; T0=time.time()

# byte prefilter: must mention a US destination phrase at all
KEYS=[b'to the u.s.',b'to the united states',b'back to the u',b'repatriat',
      b'into the u.s.',b'into the united states',b'to a u.s.',b'to our u.s.',
      b'to the us ',b'to u.s.']
# IP / transfer tokens
TOK=re.compile(r"intellectual\s+propert|intangible(?:s|\s+propert\w*|\s+asset\w*)|\bIP\b|"
               r"intra[-\s]?(?:entity|group|company)|inter[-\s]?company|"
               r"transfer\w*|repatriat\w*|realign\w*|restructur\w*|sold|sale", re.I)
# the destination phrase itself
DEST=re.compile(r"(?:to|into)\s+(?:the\s+|a\s+|our\s+|its\s+)?"
                r"(?:U\.?S\.?|United\s+States)(?:\s+(?:parent|entity|entities|subsidiar\w+|affiliate\w*|company))?\b|"
                r"back\s+to\s+the\s+(?:U\.?S\.?|United\s+States)|"
                r"repatriat\w+(?:\s+\w+){0,4}?\s+(?:to\s+the\s+)?(?:U\.?S\.?|United\s+States)?", re.I)
# reject families
NO=re.compile(r"transfer\s+pricing|withholding|repatriation\s+of\s+(?:cash|earnings|foreign\s+earnings|"
              r"non[-\s]?United\s+States\s+earnings|undistributed)|dividend|is\s+generally\s+no\s+longer\s+taxable|"
              r"available\s+for\s+repatriation|repatriate\s+cash|cash\s+repatriat", re.I)
rows=[]; zq=sys.argv[1]; Y=os.environ.get('YEAR')
z=zipfile.ZipFile(os.path.join(BASE,zq)); nseen=0
for n in z.namelist():
    if not n.endswith('.txt'): continue
    if Y and not n.startswith(Y): continue
    base=os.path.basename(n); parts=base.split('_')
    form=parts[1] if len(parts)>1 else ''
    if form not in ('10-K','10-Q','10-K-A'): continue
    m=re.search(r'edgar_data_(\d+)_',n)
    if not m or m.group(1) not in cm: continue
    try: raw=z.read(n)
    except Exception: continue
    nseen+=1
    low=raw.lower()
    if not any(k in low for k in KEYS): continue
    seen=set()
    for dm in DEST.finditer(raw.decode('utf-8','replace')):
        pass
    t=" ".join(raw.decode('utf-8','replace').split())
    for dm in DEST.finditer(t):
        a=max(0,dm.start()-420); b=min(len(t),dm.end()+320)
        w=t[a:b]
        if NO.search(w): continue
        # require an IP/intangible word AND a transfer verb in the window
        if not re.search(r"intellectual\s+propert|intangible", w, re.I): continue
        if not re.search(r"transfer\w*|repatriat\w*|sold|sale|contribut\w*|assign\w*|licens\w*|realign\w*|restructur\w*", w, re.I): continue
        k=w[380:480]
        if k in seen: continue
        seen.add(k)
        rows.append(dict(tick=cm[m.group(1)],cik=m.group(1),form=form,date=base[:8],
                         dest_phrase=" ".join(dm.group(0).split()), excerpt=w))
tag=(Y or 'all').replace('/','')
out=os.path.join(BASE,'dta_probe',f'usin_{zq[:-4]}_{tag}_Claude.csv')
with open(out,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh,fieldnames=['tick','cik','form','date','dest_phrase','excerpt']); w.writeheader(); w.writerows(rows)
print(f"{zq} {tag}: tracker filings scanned {nseen}, hits {len(rows)}, firms {len({r['tick'] for r in rows})} -> {os.path.basename(out)}")
