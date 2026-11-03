"""Round 2 of the amount chase: the three firms round 1 left open.

FIVE9 and CLOUDERA produced zero windows in round 1 (the transfer pattern plus the
tax-context requirement was too tight); ANIKA produced a window but the figure in it
was the Italian valuation-allowance release, not the transfer's own tax effect.
Here: drop the tax-context filter, widen the assertion, and print every window.
"""
import zipfile, re, os, csv

BASE = os.path.join(os.path.expanduser('~'), 'mnt', 'Grant and Nguyen')
OUT  = os.path.join(BASE, 'dta_probe', 'amount_chase2_Claude.csv')

TARGETS = {'1288847': 'FIVE9', '1535379': 'CLOUDERA', '898437': 'ANIKA'}

HOOK = re.compile(
    r"intra[-\s]?(?:entity|group|company)|inter[-\s]?company|"
    r"corporate\s+(?:entity\s+)?(?:operating\s+)?structure|"
    r"legal\s+entity\s+(?:restructur|reorganiz)|"
    r"transferr?(?:ed|ing|s)?\s+(?:certain\s+|our\s+|its\s+|the\s+|all\s+)?"
    r"(?:intellectual\s+propert\w*|\bIP\b|intangible)|"
    r"(?:intellectual\s+propert\w*|intangible\s+propert\w*)\s+"
    r"(?:transfer|realignment|restructur\w+|rights?\s+(?:to|from))|"
    r"deferred\s+income\s+tax\s+expense|one[-\s]time\s+tax",
    re.I)

MAG = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
                 r"(million|billion|thousand)\b", re.I)

ZIPS = ['10-X_C_2016-2020.zip', '10-X_C_2021.zip', '10-X_C_2022.zip',
        '10-X_C_2023.zip', '10-X_C_2024.zip']

rows = []
for zq in ZIPS:
    p = os.path.join(BASE, zq)
    if not os.path.exists(p):
        continue
    z = zipfile.ZipFile(p)
    for n in z.namelist():
        if not n.endswith('.txt'):
            continue
        m = re.search(r'edgar_data_(\d+)_', n)
        if not m or m.group(1) not in TARGETS:
            continue
        lab = TARGETS[m.group(1)]
        base = os.path.basename(n)
        parts = base.split('_')
        form = parts[1] if len(parts) > 1 else '?'
        date = base[:8]
        t = re.sub(r'\s+', ' ', z.read(n).decode('utf-8', 'replace'))
        used = []
        for hm in HOOK.finditer(t):
            if any(abs(hm.start() - u) < 600 for u in used):
                continue
            used.append(hm.start())
            a = max(0, hm.start() - 350)
            b = min(len(t), hm.end() + 950)
            w = t[a:b]
            mags = ["%s %s" % (g[0], g[1].lower()) for g in MAG.findall(w)]
            rows.append(dict(firm=lab, cik=m.group(1), form=form, date=date,
                             match=" ".join(hm.group(0).split())[:70],
                             mags="|".join(mags) or "NONE",
                             window=" ".join(w.split())))

with open(OUT, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=['firm', 'cik', 'form', 'date', 'match', 'mags', 'window'])
    w.writeheader()
    w.writerows(rows)

print("windows: %d" % len(rows))
for r in rows:
    if r['mags'] != 'NONE':
        print("  %-9s %-6s %s  %-38s  %s" % (r['firm'], r['form'], r['date'],
                                             r['match'][:38], r['mags'][:80]))
