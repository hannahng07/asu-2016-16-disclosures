#!/usr/bin/env python3
r"""Firms that explicitly disclose the VALUE of the transferred IP.

WHY THIS IS ITS OWN FIELD
-------------------------
Settled point 1: the 10-K amount is a TAX EFFECT, never the IP value, and the two
are never reconciled. That is right, and it has always implied the IP value is
simply absent from the 10-K -- the Irish statutory accounts were the only source
(Salesforce's $24bn).

A few firms disclose it anyway. Arista: "in exchange for a non-interest-bearing
note of $3.4 billion ... tax basis in the IP transferred equaled the fair market
value". That is an IP VALUE in a 10-K, and its tax effect is a separate $85.8m
net. Where both appear, the pair is a directly observed basis-to-tax-effect
ratio -- something the project has never had.

THE FORMS IT TAKES
------------------
  note        "in exchange for a non-interest-bearing note of $3.4 billion"
  fmv         "tax basis ... equaled the fair market value of the qualifying IP"
  basis_stepup "a step-up in the tax deductible basis of $X"   (basis = FMV)
  fair_value  "the fair value of the IP which serves as the tax basis"
  consideration "transferred ... for consideration of $X"

`basis_stepup` counts as an IP value because under these transactions the new
tax basis IS the fair value -- the firms say so explicitly.

WHAT IT IS NOT
--------------
"deferred tax asset and related income tax benefit of $X BASED UPON the tax
basis step-up" is a TAX EFFECT (Boston Scientific $4.1bn, MACOM $39.8m). The
preposition is the tell, not the magnitude. Those are excluded here.
"""
import pandas as pd, re, csv, sys
csv.field_size_limit(min(sys.maxsize,2**31-1))

MONEY=r"\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(billion|million|thousand)\b"
FORMS=[("note",           rf"(?:non-?interest-?bearing\s+)?(?:intercompany\s+|promissory\s+)?note\s+(?:of|totaling|in\s+the\s+(?:amount|principal)\s+of)\s+{MONEY}"),
       ("note",           rf"in\s+exchange\s+for\s+[^.]{{0,60}}?{MONEY}"),
       ("fmv",            rf"fair\s+market\s+value\s+of\s+[^.]{{0,80}}?{MONEY}"),
       ("fair_value",     rf"fair\s+value\s+of\s+the\s+(?:transferred\s+)?(?:IP|intellectual\s+propert\w*|intangible\w*)[^.]{{0,80}}?{MONEY}"),
       ("basis_stepup",   rf"(?:step[-\s]?up\s+in\s+(?:the\s+)?(?:tax(?:\s+deductible)?\s+)?basis|tax\s+basis\s+step[-\s]?up)[^.]{{0,80}}?{MONEY}"),
       ("basis_stepup",   rf"(?:incremental|new|additional)\s+tax\s+basis\s+of\s+{MONEY}"),
       ("consideration",  rf"consideration\s+of\s+{MONEY}"),
      ]
FORMS=[(k,re.compile(v,re.I)) for k,v in FORMS]
# A TAX EFFECT, NOT A VALUE. This guard is the whole precision of the scan.
#
# Firms almost always describe the step-up QUALITATIVELY and then quantify only
# its TAX consequence: "a step-up in the tax basis ... resulting in a deferred
# tax asset of $586 million" (Yum), "... and a correlated $135.5 million increase
# in foreign deferred tax assets" (Twilio), "a step-up in tax basis driven by the
# fair value of the transferred IP rights, resulting in a one-time net deferred
# benefit of $77 million" (Motorola). The basis LANGUAGE is nearly always there;
# the basis NUMBER almost never is. A first cut of this scan collected all three
# as IP values and was wrong on 10 of 11 rows.
#
# So the test is not "is there effect language somewhere nearby" but "does effect
# language sit BETWEEN the basis phrase and the number". If it does, the number
# belongs to the effect.
EFFECT=re.compile(r"deferred\s+tax\s+(?:asset|liabilit)|income\s+tax\s+benefit|tax\s+benefit|"
                  r"tax\s+charge|tax\s+expense|deferred\s+benefit|net\s+deferred|"
                  r"increase\s+in\s+(?:foreign\s+)?deferred|one-?time",re.I)
TOPIC=re.compile(r"intra[-\s]?entity|intra[-\s]?group|intercompany\s+(?:transfer|sale)|"
                 r"transfer\s+of\s+(?:a\s+license\s+for\s+)?(?:certain\s+)?(?:intellectual|intangible)|"
                 r"transferred\s+(?:certain\s+)?(?:intellectual|intangible)",re.I)
M={'billion':1e9,'million':1e6,'thousand':1e3}

def harvest(text, src, meta, out):
    t=" ".join(str(text).split())
    if not TOPIC.search(t): return
    for kind,rx in FORMS:
        for m in rx.finditer(t):
            # Effect language can sit on EITHER side of the figure:
            #   before -- "step-up ... resulting in a deferred tax asset of $586m"
            #   after  -- "a correlated $135.5 million INCREASE IN foreign
            #              deferred tax assets"
            # so both are checked. Twilio is the reason for the second one.
            span=t[m.start():m.start(1)] + " " + t[m.end():m.end()+70]
            if EFFECT.search(span): continue
            try: val=float(m.group(1).replace(',',''))*M[m.group(2).lower()]
            except Exception: continue
            out.append({**meta,'source':src,'form_of_words':kind,'ip_value':val,
                        'quote':t[max(0,m.start()-260):m.end()+200]})
            return

out=[]
try:
    cam=pd.read_csv('cam_hits_Claude.csv')
    for _,r in cam.iterrows():
        harvest(r['excerpt'],'critical_audit_matter',
                {'company':r.get('company',''),'cik':str(r['cik']).lstrip('0'),
                 'date':r['date'],'form':r['form']},out)
except Exception as e: print("cam:",e)
try:
    n=pd.read_csv('notes_text_blocks_Claude.csv',low_memory=False)
    for _,r in n.iterrows():
        harvest(r.get('excerpt',''),'footnote_as_filed',
                {'company':r['company'],'cik':str(r['cik']).lstrip('0'),
                 'date':str(r['filing_date'])[:10],'form':r['form']},out)
except Exception as e: print("notes:",e)
try:
    c=pd.read_csv('asu_v2_candidates_Claude.csv',low_memory=False)
    for _,r in c.iterrows():
        harvest(r.get('candidate_text',''),'candidate_text',
                {'company':r['company'],'cik':str(r['cik']).lstrip('0'),
                 'date':str(r['filing_date'])[:10],'form':r['form']},out)
except Exception as e: print("cand:",e)

d=pd.DataFrame(out)
if len(d):
    d=d.sort_values('ip_value',ascending=False).drop_duplicates(['cik','date','ip_value'])
    d.to_csv('ip_value_disclosures_Claude.csv',index=False)
    print(f"rows {len(d)}  firms {d.cik.nunique()}")
    print("\nEXPECT THIS TO BE NEARLY EMPTY. An explicit IP value in a 10-K is rare;")
    print("if this starts returning many rows, suspect the guard before believing it.")
    print(d.form_of_words.value_counts().to_string())
    print(d.source.value_counts().to_string())
else: print("none found")
