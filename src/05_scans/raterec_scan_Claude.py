import zipfile, csv, io, sys, re, json, os
csv.field_size_limit(min(sys.maxsize,2**31-1))
# Find the RATE RECONCILIATION region of a tax note, then look for a LINE ITEM whose
# label names a restructuring/reorganisation. Intel's is "Restructuring of certain
# non-U.S. subsidiaries (3.4)". A line item is a label followed by a rate figure.
START=re.compile(r"statutory\s+(?:federal\s+)?(?:income\s+)?tax\s+rate",re.I)
END  =re.compile(r"effective\s+(?:income\s+)?tax\s+rate",re.I)
LINE =re.compile(r"((?:[A-Za-z][\w.\-/']*\s+){0,6}?"
                 r"(?:restructur\w+|reorganiz\w+|realign\w+|legal\s+entit\w+|"
                 r"entity\s+simplif\w+|internal\s+transfer\w*|intra[-\s]?entity|"
                 r"intercompany\s+transfer\w*|transfer\s+of\s+(?:certain\s+)?(?:IP|intangible|intellectual)\w*)"
                 r"(?:\s+[\w.\-/']+){0,6})\s*\(?\-?\d{1,2}\.\d\)?",re.I)
ANCHOR=re.compile(r"intra[-\s]?entity|intercompany\s+(?:transfer|sale)|2016\s*-?\s*16|"
                  r"transfers?\s+of\s+(?:certain\s+)?(?:intellectual|intangible)",re.I)
def scan(q):
    z=zipfile.ZipFile(q); sub={}
    with z.open('sub.tsv') as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh,'utf-8',errors='replace'),delimiter='\t'):
            sub[r['adsh']]=(r.get('cik','').lstrip('0'),r.get('name'),r.get('form'),r.get('period'))
    out={}
    with z.open('txt.tsv') as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh,'utf-8',errors='replace'),delimiter='\t'):
            tag=r.get('tag') or ''
            if 'IncomeTax' not in tag and 'EffectiveIncomeTax' not in tag: continue
            v=r.get('value') or ''
            if not re.search(r"restructur|reorganiz|realign|legal entit|intra|intercompany|transfer",v,re.I): continue
            t=re.sub(r'<[^>]+>',' ',v); t=re.sub(r'&#?\w+;',' ',t); t=re.sub(r'\s+',' ',t)
            s=START.search(t)
            if not s: continue
            e=END.search(t,s.end())
            region=t[s.start(): e.end() if e else min(len(t),s.start()+3000)]
            m=LINE.search(region)
            if not m: continue
            a=out.setdefault(r['adsh'],{'sub':sub.get(r['adsh']),'label':" ".join(m.group(0).split()),
                                        'anchor':bool(ANCHOR.search(t))})
    return out
for q in sys.argv[1:]:
    o=scan(q); k=os.path.basename(q).split('_')[0]
    json.dump(o,open(f"/tmp/rr_{k}.json","w"))
    print(f"{k}: {len(o)} filings name a restructuring-type rate-rec line | with anchor vocab {sum(1 for v in o.values() if v['anchor'])}")
