#!/usr/bin/env python3
r"""ip_provenance, dtl_mechanism and gilti_method, read from the footnote as filed.

WHY THESE THREE FIELDS
----------------------
For the investor-information project the partition that matters is whether the
transferred IP was ACQUIRED or INTERNALLY DEVELOPED:

    internally developed -> no valuation of it has ever been public, so the
                            transfer's fair value is NEW information
    acquired             -> the purchase price allocation already published a
                            fair value, so on the asset-value channel there is
                            nothing new

`dta_dtl` is a poor proxy for that split. Of the 51 DTL/both firms, the
determinable mechanisms are overwhelmingly GILTI or outside-basis, not the
acquired-IP inside-basis case. So provenance has to be read directly.

`gilti_method` is captured separately because it is an ACCOUNTING POLICY
ELECTION that decides whether a DTL appears at all -- J&J: "as a result of the
election to record GILTI on the deferred method, the Company recorded a GILTI
deferred tax liability of $1.7 billion". Two firms with identical economics
report different balance sheets. Any specification using the DTL as a regressor
needs this field beside it.

THE HONEST LIMIT, STATED UP FRONT
---------------------------------
"Acquired" is usually SAID. "Internally developed" almost never is -- firms do
not write "this IP was internally developed", they just transfer it. So this
script will NOT code the absence of acquisition language as internal
development. That would be the same error as reading a destination out of
silence, which cost this project a 59%-precision destination field.

The categories are therefore:
    acquired          the firm says the IP was acquired
    acquired_nearby   acquisition language is in the block but not clearly
                      attached to the transferred IP -- needs a reader
    unstated          no acquisition language; provenance genuinely unknown

`unstated` will dominate, and that IS the result: the 10-K does not generally
say, so the internally-developed arm has to come from a reader or from an
external source (a firm with heavy R&D and no material acquisition in the prior
two years). Nothing here should be used as if it were the full partition.

Writes a SEPARATE file. It does not modify the population.
"""
import pandas as pd, re

ACQ_DIRECT = re.compile(
    r"transfer\w*\s+of\s+(?:certain\s+)?acquired\s+(?:intangible|intellectual|IP)|"
    r"acquired\s+(?:intangible\s+assets?|intellectual\s+propert\w+|IP)\s+(?:were\s+|was\s+)?"
    r"(?:transferred|sold|moved)|"
    r"(?:intangible\s+assets?|intellectual\s+propert\w+|IP)[^;]{0,70}?acquired\s+in\s+(?:the\s+)?"
    r"[A-Z][\w-]+\s+(?:acquisition|transaction|merger)|"
    r"transfer\w*[^;]{0,90}?acquired\s+(?:from|in)\s+(?:the\s+)?[A-Z][\w-]+|"
    r"IP\s+(?:rights\s+)?acquired\s+(?:from|in)\b", re.I)
ACQ_NEAR  = re.compile(r"\bacquisition\b|\bacquired\b|business\s+combination|purchase\s+accounting", re.I)
INTERNAL  = re.compile(r"internally[-\s]developed|internally\s+generated|"
                       r"(?:IP|intellectual\s+propert\w+)\s+(?:we|the\s+Company)\s+developed", re.I)

GILTI     = re.compile(r"\bGILTI\b|global\s+intangible\s+low[- ]taxed", re.I)
G_DEFER   = re.compile(r"(?:elect\w*|account\w*)[^.]{0,80}GILTI[^.]{0,80}deferred|"
                       r"GILTI[^.]{0,60}deferred\s+method|deferred\s+method[^.]{0,60}GILTI", re.I)
G_PERIOD  = re.compile(r"GILTI[^.]{0,80}(?:as\s+a\s+)?period\s+cost|period\s+cost[^.]{0,60}GILTI|"
                       r"GILTI[^.]{0,60}in\s+the\s+period\s+incurred", re.I)
OUTSIDE   = re.compile(r"future\s+U\.?S\.?\s+tax\s+on\s+foreign\s+earnings|unremitted|"
                       r"undistributed\s+earnings|permanent(?:ly)?\s+reinvest|outside\s+basis", re.I)

def main():
    n = pd.read_csv('notes_text_blocks_Claude.csv', low_memory=False)
    f = pd.read_csv('population_filings_Claude.csv', low_memory=False)
    # The footnote blocks alone are too narrow: BMS states its provenance
    # ("acquired in the Celgene transaction") in a sentence the population
    # carries but the notes block does not. So pool every text we hold per firm.
    n['txt'] = n.excerpt.fillna('') + ' ' + n.dest_excerpt.fillna('')
    parts = [n[['cik','company','txt']]]
    f0 = pd.read_csv('population_filings_Claude.csv', low_memory=False)
    parts.append(pd.DataFrame({'cik': f0.cik, 'company': f0.company,
                               'txt': f0.sentence.fillna('') + ' ' +
                                      f0.amount_sentence.fillna('') + ' ' +
                                      f0.anchor_sentence.fillna('')}))
    try:
        c0 = pd.read_csv('asu_v2_candidates_Claude.csv', low_memory=False)
        c0['cikp'] = c0.cik.astype(str).str.lstrip('0').astype(int)
        parts.append(pd.DataFrame({'cik': c0.cikp, 'company': c0.company,
                                   'txt': c0.candidate_text.fillna('')}))
    except Exception as e:
        print('candidates:', e)
    try:
        cm = pd.read_csv('cam_hits_Claude.csv')
        cm['cikp'] = cm.cik.astype(str).str.lstrip('0').astype(int)
        parts.append(pd.DataFrame({'cik': cm.cikp, 'company': cm.company.fillna(''),
                                   'txt': cm.excerpt.fillna('')}))
    except Exception as e:
        print('cam:', e)
    allt = pd.concat(parts, ignore_index=True)
    g = allt.groupby('cik').agg(company=('company','first'),
                                txt=('txt', lambda s: ' '.join(s.astype(str))))
    rows=[]
    for cik, r in g.iterrows():
        t = ' '.join(str(r.txt).split())
        if   ACQ_DIRECT.search(t): prov='acquired'
        elif ACQ_NEAR.search(t):   prov='acquired_nearby'
        else:                      prov='unstated'
        if INTERNAL.search(t) and prov!='acquired': prov='internally_developed_stated'
        gm = 'deferred' if G_DEFER.search(t) else ('period' if G_PERIOD.search(t) else
             ('unstated_but_mentions_gilti' if GILTI.search(t) else 'no_gilti_language'))
        if   GILTI.search(t):   mech='gilti'
        elif OUTSIDE.search(t): mech='outside_basis'
        elif prov=='acquired':  mech='acquired_inside_basis'
        else:                   mech='unstated'
        rows.append(dict(cik=cik, company=r.company, ip_provenance=prov,
                         dtl_mechanism=mech, gilti_method=gm))
    d=pd.DataFrame(rows)
    ft=f[f.is_effect==True]
    d['has_dtl']=d.cik.isin(set(ft[ft.dta_dtl.astype(str).str.upper().isin(['DTL','BOTH'])].cik))
    d['double_irish']=d.cik.isin(set(f.loc[f.double_irish==1,'cik']))
    d.to_csv('ip_provenance_Claude.csv', index=False)
    N=len(d)
    print(f"firms read from the footnote: {N}\n")
    print("ip_provenance:");  print((d.ip_provenance.value_counts()).to_string())
    print("\ngilti_method:"); print((d.gilti_method.value_counts()).to_string())
    print("\ndtl_mechanism among firms flagged DTL/both:")
    print(d[d.has_dtl].dtl_mechanism.value_counts().to_string())
    print(f"\nacquired, and flagged DTL: {len(d[(d.ip_provenance=='acquired')&d.has_dtl])}")
    print(f"acquired, Double Irish   : {len(d[(d.ip_provenance=='acquired')&d.double_irish])}")
    print("\nfirms coded 'acquired':")
    print(d[d.ip_provenance=='acquired'][['company','dtl_mechanism','gilti_method']].to_string(index=False))
main()
