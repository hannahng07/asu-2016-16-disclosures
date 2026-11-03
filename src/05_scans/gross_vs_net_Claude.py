#!/usr/bin/env python3
r"""Do firms disclose the GROSS components (DTA and DTL) or only the NET?

WHY IT MATTERS
--------------
The net conflates two things with different meanings:
  * the DTA from the basis step-up -- economic, comparable across firms
  * the offsetting DTL -- frequently the GILTI liability, which exists only
    because the firm ELECTED the deferred method (J&J states the election
    outright). Two firms with identical transfers and different elections report
    different nets.
So a firm disclosing only the net gives a number that cannot be compared with
another firm's, while a firm disclosing both gives one that can. Gross-vs-net is
therefore a DISCLOSURE-QUALITY variable in its own right, not just a parsing
nuisance.

Read from the UNSTRIPPED footnote (the SEC notes sets), because the corpus
strips dollar signs and this test depends on reading figures next to the right
nouns.
"""
import pandas as pd, re
M=r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:billion|million|thousand)?"
# Firms write these BOTH ways round -- "deferred tax assets of $101 million"
# AND "$101 million of deferred tax assets" -- and a first cut that only handled
# noun-then-figure misclassified Travelport, Marathon and Nasdaq into the "no
# figure" bucket, inflating it. Both orders are matched below, and "expense" and
# "charge" sit beside "benefit" because a net can be either sign.
DTA=re.compile(rf"deferred\s+tax\s+assets?[^.;]{{0,70}}?(?:of|totaling|totalling|equal\s+to)\s+{M}|"
               rf"{M}\s+(?:of|in|to)\s+(?:net\s+|new\s+|additional\s+|foreign\s+)*deferred\s+tax\s+assets?|"
               rf"{M}\s+increase\s+(?:in|to)\s+[^.;]{{0,30}}?deferred\s+tax\s+assets?|"
               rf"recogni[sz]\w+[^.;]{{0,40}}?deferred\s+tax\s+assets?\s+of\s+{M}",re.I)
DTL=re.compile(rf"deferred\s+tax\s+liabilit(?:y|ies)[^.;]{{0,70}}?(?:of|totaling|totalling)\s+{M}|"
               rf"{M}\s+(?:of|in|to)\s+(?:net\s+|new\s+|additional\s+)*deferred\s+tax\s+liabilit|"
               rf"{M}\s+increase\s+(?:in|to)\s+[^.;]{{0,30}}?deferred\s+tax\s+liabilit|"
               rf"offset\s+by[^.;]{{0,70}}?{M}[^.;]{{0,45}}?deferred\s+tax\s+liabilit",re.I)
NET=re.compile(rf"net\s+(?:income\s+)?tax\s+(?:benefit|expense|charge)\s+of\s+{M}|"
               rf"net\s+deferred\s+(?:tax\s+)?(?:benefit|expense|charge)\s+of\s+{M}|"
               rf"one-?time\s+net\s+tax\s+(?:benefit|expense|charge)\s+of\s+{M}|"
               rf"net\s+cumulative[-\s]effect[^.;]{{0,70}}?{M}|"
               rf"cumulative[-\s]effect\s+adjustment[^.;]{{0,90}}?{M}|"
               rf"{M}\s+cumulative[-\s]effect\s+adjustment|"
               rf"{M}\s+net\s+(?:tax\s+)?(?:benefit|expense|charge)",re.I)
TOPIC=re.compile(r"intra[-\s]?entity|intra[-\s]?group|intercompany\s+(?:transfer|sale)|"
                 r"transfer\w*\s+of\s+(?:certain\s+)?(?:intellectual|intangible)|2016-16",re.I)

n=pd.read_csv('notes_text_blocks_Claude.csv',low_memory=False)
f=pd.read_csv('population_filings_Claude.csv',low_memory=False)
eff=set(zip(f.loc[f.is_effect==True,'cik'],f.loc[f.is_effect==True,'accession']))
n['txt']=(n.excerpt.fillna('')+' '+n.dest_excerpt.fillna('')).map(lambda s:' '.join(str(s).split()))
n=n[[ (c,a) in eff for c,a in zip(n.cik,n.accession) ]]
g=n.groupby(['cik','accession']).agg(company=('company','first'),form=('form','first'),
        date=('filing_date','first'),txt=('txt',lambda s:' '.join(s)))
rows=[]
for (cik,acc),r in g.iterrows():
    t=r.txt
    if not TOPIC.search(t): continue
    has_dta,has_dtl,has_net=bool(DTA.search(t)),bool(DTL.search(t)),bool(NET.search(t))
    if   has_dta and has_dtl: k='gross both (DTA and DTL)'
    elif has_dta and has_net: k='gross DTA and a net'
    elif has_dta:             k='gross DTA only'
    elif has_dtl:             k='gross DTL only'
    elif has_net:             k='net only'
    else:                     k='no figure attached to a component'
    rows.append(dict(cik=cik,accession=acc,company=r.company,form=r.form,date=r.date,
                     dta=has_dta,dtl=has_dtl,net=has_net,disclosure_granularity=k))
d=pd.DataFrame(rows); d.to_csv('gross_vs_net_Claude.csv',index=False)
N=len(d); F=d.cik.nunique()
print(f"effect filings with unstripped footnote text: {N}  (firms {F})\n")
v=d.disclosure_granularity.value_counts()
for k,c in v.items(): print(f"  {k:36s} {c:4d}  {c/N:5.1%}")
fr=d.groupby('cik').disclosure_granularity.apply(
    lambda s:'gross both (DTA and DTL)' if (s=='gross both (DTA and DTL)').any() else s.iloc[0])
print(f"\nBY FIRM (best disclosure the firm ever gives), n={len(fr)}:")
for k,c in fr.value_counts().items(): print(f"  {k:36s} {c:4d}  {c/len(fr):5.1%}")
print(f"\nfirms that EVER separate the gross DTA from a DTL: {(fr=='gross both (DTA and DTL)').sum()}"
      f" of {len(fr)} = {(fr=='gross both (DTA and DTL)').mean():.1%}")
