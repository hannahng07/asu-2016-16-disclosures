#!/usr/bin/env python3
r"""PREVIEW ONLY. What changes if the amount of record prefers the EVENT over the ADOPTION.

THE CURRENT RULE AND WHY IT WAS CHOSEN
--------------------------------------
`build_deliverable_xlsx_Claude.py` defines the firm's amount of record as
"the earliest filing that states one", because 69 firms disclose before they
quantify and for 23 of them a figure only appears later. That reasoning is
sound and this proposal does NOT reverse it.

THE DEFECT
----------
Adoption always comes first chronologically. A firm that adopts ASU 2016-16 in
2018 (stating a small cumulative-effect catch-up) and transfers IP in 2019
(stating a large benefit) has its amount of record set to the ADOPTION figure.
Twitter: $29.5m adoption against a $1.21bn transfer.

THE PROPOSED RULE
-----------------
Still the EARLIEST filing that states a figure -- but among filings whose
sentence is NOT purely an adoption/cumulative-effect statement, when at least
one such filing exists. If a firm only ever states an adoption figure, nothing
changes for it. The adoption figure moves to `adoption_amount` rather than being
discarded.

This is NOT "take the maximum". The max column is contaminated: Liberty
Broadband's max is $2.017 TRILLION and Coca-Cola's $75bn, both table furniture.
Picking the max would import that junk into the headline for every firm.

Writes a comparison file. CHANGES NOTHING.
"""
import pandas as pd, re, numpy as np

ADOPT=re.compile(r"upon\s+adoption|cumulative[-\s]effect|we\s+adopted|the\s+adoption\s+of\s+(?:this|the|ASU)|"
                 r"adopted\s+(?:this|the|ASU)|opening\s+balance|beginning\s+(?:balance\s+of\s+)?retained\s+earnings",re.I)
# an EVENT sentence names a transfer that happened, not the standard's adoption
EVENT=re.compile(r"(?:completed|recorded|recognized|recognised|resulted\s+in|we\s+transferred|"
                 r"transfer\s+of|sale\s+of|sold)[^.]{0,120}(?:intellectual\s+propert|intangible|IP\b|"
                 r"intra[-\s]?entity|intra[-\s]?group|intercompany)",re.I)

f=pd.read_csv('population_filings_Claude.csv',low_memory=False)
e=f[(f.is_effect.astype(str).isin(['1','True']))&(f.amount.notna())].copy()
e['txt']=e.sentence.fillna('')+' '+e.amount_sentence.fillna('')
e['is_adopt']=e.txt.str.contains(ADOPT)&~e.txt.str.contains(EVENT)
e=e.sort_values(['cik','filing_date'])

cur=e.drop_duplicates('cik').set_index('cik')
ev =e[~e.is_adopt].drop_duplicates('cik').set_index('cik')
ad =e[e.is_adopt].drop_duplicates('cik').set_index('cik')

rows=[]
for cik,r in cur.iterrows():
    new = ev.loc[cik] if cik in ev.index else r
    rows.append(dict(cik=cik,company=r.company,
        current_amount=r.amount,current_date=str(r.filing_date)[:10],current_form=r.form,
        current_is_adoption=bool(r.is_adopt),
        proposed_amount=new.amount,proposed_date=str(new.filing_date)[:10],proposed_form=new.form,
        adoption_amount=(ad.loc[cik,'amount'] if cik in ad.index else np.nan),
        current_sentence=" ".join(str(r.sentence).split())[:160],
        proposed_sentence=" ".join(str(new.sentence).split())[:160]))
d=pd.DataFrame(rows)
d['changes']=d.current_amount!=d.proposed_amount
d['ratio']=d.proposed_amount/d.current_amount
d.to_csv('amount_of_record_preview_Claude.csv',index=False)

N=len(d); C=int(d.changes.sum())
print(f"firms with an amount of record : {N}")
print(f"firms whose amount would CHANGE: {C}  ({C/N:.1%})")
print(f"  of those, the current pick is an adoption sentence: {int(d[d.changes].current_is_adoption.sum())}")
print(f"  median change factor: {d.loc[d.changes,'ratio'].median():.1f}x\n")
print(d[d.changes].sort_values('ratio',ascending=False)
      [['company','current_amount','proposed_amount','ratio','current_date','proposed_date']]
      .head(25).to_string(index=False))
print("\n--- would any firm's amount go DOWN (a sign the rule is picking worse)? ---")
dn=d[d.changes&(d.ratio<1)]
print(f"{len(dn)} firms" if len(dn) else "none")
if len(dn): print(dn[['company','current_amount','proposed_amount','proposed_sentence']].to_string(index=False))
