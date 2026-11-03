"""PHASE B FOR GOAL 2: the US-inbound sweep opened to the WHOLE corpus.

The narrow filter was calibrated on the 105 tracker firms, where it went from 1,362
raw hits to 32 by two fixes: a CASE-SENSITIVE US destination token (re.I made
"(?:U\\.?S\\.?)" match the ordinary word "us", so "licensed to us" / "available to us"
produced ~360 false hits from Risk Factors alone) and excluding TCJA deemed
repatriation. Those 32 yielded 16 confirmed US-inbound events. This runs the same
filter against every 10-K / 10-Q / 10-K-A in the corpus.

Resumable: a time budget per invocation, progress in a JSON state file, hits appended
to the output CSV. Run repeatedly until it reports done.

Two tiers:
  A - an IP / intangible word sits in the window (Goal 2 proper)
  B - no IP word, but an intra-entity / intercompany / legal-entity token does
      (the "certain assets" disclosure form, which 17 of 19 events use)
"""
import zipfile, re, os, sys, csv, json, time

BASE  = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
PROBE = os.path.join(BASE, 'dta_probe')
STATE = os.path.join(PROBE, 'usin_all_state_Claude.json')
OUT   = os.path.join(PROBE, 'usin_all_hits_Claude.csv')
IDX   = os.path.join(PROBE, 'usin_all_index_Claude.json')

ZIPS = ['10-X_C_2016-2020.zip', '10-X_C_2021.zip', '10-X_C_2022.zip',
        '10-X_C_2023.zip', '10-X_C_2024.zip']
BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
T0 = time.time()

# ---- byte prefilter. CASE-SENSITIVE on purpose: the lowercase "to us" is the
# ---- single biggest false-positive family in this corpus.
BKEYS = [b'to the U.S', b'to the United States', b'into the U.S',
         b'into the United States', b'to a U.S', b'to our U.S', b'to its U.S',
         b'back to the U', b'to the US ', b'to US ', b'epatriat']

USD = r"(?:U\.S\.?|US|United States)"            # NOT case-insensitive
DEST = re.compile(
    r"(?:transferr?(?:ed|ing|s)?|sold|sells|sale\s+of|contribut\w+|assign\w+|"
    r"repatriat\w+|realign\w+|moving|moved|relocat\w+|migrat\w+)"
    r"[^.;]{0,140}?(?:to|into)\s+(?:the\s+|a\s+|our\s+|its\s+|certain\s+)?" + USD + r"\b")
BACK = re.compile(r"back\s+to\s+(?:the\s+)?" + USD + r"\b")

# TCJA deemed repatriation and cash movement: the dominant reject family
BADREP = re.compile(
    r"deemed\s+repatriation|repatriation\s+of\s+(?:cash|post-1986|undistributed|foreign|"
    r"accumulated|non[-\s]?U\.?S\.?)|one[-\s]time\s+(?:deemed\s+)?(?:mandatory\s+)?"
    r"(?:transition|repatriation)|transition\s+tax|repatriate\s+(?:cash|funds|earnings)|"
    r"cash\s+repatriat|transfer\s+pricing|withholding\s+tax\s+on\s+(?:the\s+)?"
    r"(?:repatriat|dividend)|dividends?\s+(?:received|paid|from)", re.I)

IPWORD   = re.compile(r"intellectual\s+propert|intangible(?:s\b|\s+propert|\s+asset)|"
                      r"\bIP\b|patent|trademark|technolog", re.I)
INTRAWORD = re.compile(r"intra[-\s]?(?:entity|group|company)|inter[-\s]?company|"
                       r"legal\s+entit|wholly[-\s]?owned\s+(?:subsidiar|legal)|"
                       r"affiliated\s+compan|related\s+part", re.I)
TAXWORD   = re.compile(r"deferred\s+tax|income\s+tax|tax\s+(?:benefit|expense|provision|effect|"
                       r"charge|basis)|effective\s+tax\s+rate|valuation\s+allowance", re.I)

FORMS = ('10-K', '10-Q', '10-K-A', '10-Q-A')

# ---------------- index ----------------
if not os.path.exists(IDX):
    idx = []
    for zq in ZIPS:
        p = os.path.join(BASE, zq)
        if not os.path.exists(p):
            continue
        z = zipfile.ZipFile(p)
        for n in z.namelist():
            if not n.endswith('.txt'):
                continue
            parts = os.path.basename(n).split('_')
            if len(parts) < 2 or parts[1] not in FORMS:
                continue
            idx.append([zq, n])
    json.dump(idx, open(IDX, 'w'))
    print('index built: %d filings' % len(idx))
else:
    idx = json.load(open(IDX))

st = json.load(open(STATE)) if os.path.exists(STATE) else {'i': 0, 'hits': 0, 'scanned': 0}
i = st['i']
if i >= len(idx):
    print('DONE  scanned=%d hits=%d' % (st['scanned'], st['hits']))
    sys.exit(0)

FIELDS = ['tier', 'cik', 'company', 'form', 'date', 'dest_phrase', 'excerpt']
new = not os.path.exists(OUT)
fh = open(OUT, 'a', newline='', encoding='utf-8')
w = csv.DictWriter(fh, fieldnames=FIELDS)
if new:
    w.writeheader()

zcache = {}
rows_this_run = 0
while i < len(idx) and (time.time() - T0) < BUDGET:
    zq, n = idx[i]
    i += 1
    st['scanned'] += 1
    if zq not in zcache:
        zcache = {zq: zipfile.ZipFile(os.path.join(BASE, zq))}   # one handle at a time
    try:
        raw = zcache[zq].read(n)
    except Exception:
        continue
    if not any(k in raw for k in BKEYS):
        continue
    base = os.path.basename(n)
    parts = base.split('_')
    form = parts[1]
    date = base[:8]
    m = re.search(r'edgar_data_(\d+)_', n)
    cik = m.group(1) if m else ''
    comp = parts[2] if len(parts) > 2 else ''
    t = " ".join(raw.decode('utf-8', 'replace').split())
    seen = set()
    for pat in (DEST, BACK):
        for dm in pat.finditer(t):
            a = max(0, dm.start() - 420)
            b = min(len(t), dm.end() + 340)
            win = t[a:b]
            if BADREP.search(win):
                continue
            if not TAXWORD.search(win):
                continue
            if IPWORD.search(win):
                tier = 'A'
            elif INTRAWORD.search(win):
                tier = 'B'
            else:
                continue
            k = win[400:500]
            if k in seen:
                continue
            seen.add(k)
            w.writerow(dict(tier=tier, cik=cik, company=comp, form=form, date=date,
                            dest_phrase=" ".join(dm.group(0).split())[:90],
                            excerpt=win))
            st['hits'] += 1
            rows_this_run += 1

fh.close()
st['i'] = i
json.dump(st, open(STATE, 'w'))
pct = 100.0 * i / len(idx)
print('progress %d/%d (%.1f%%)  scanned=%d  hits_total=%d  hits_this_run=%d  %s'
      % (i, len(idx), pct, st['scanned'], st['hits'], rows_this_run,
         'DONE' if i >= len(idx) else 'more to go'))
