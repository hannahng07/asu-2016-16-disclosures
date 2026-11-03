#!/usr/bin/env python3
r"""The balance-sheet sign as a TRACKED FIELD, with the acquisition confounder flagged.

Not applied to `effect_direction`, and nothing in the population is changed.
This writes a side file that joins on cik + accession.

WHY IT IS TRACKED RATHER THAN APPLIED
-------------------------------------
Tested against known cases the instrument is right 5 of 7, and the two failures
are structural rather than timing: the intangibles deferred-tax line moves for
acquisitions and their subsequent amortisation as well as for transfers, and the
transfer is often not the dominant mover. BMS is the demonstration -- the Celgene
acquisition put a -$7,167m intangibles DTL on the books in 2019, whose annual
amortisation (+$775m in 2020) drowns the $853m transfer charge. Adopting this as
the sign would swap a vocabulary-driven bias for an acquisition-driven one, which
is settled point 5's own warning pointed at the new instrument.

THE ACQUISITION PROXY
---------------------
Built from the intangibles data itself, so it needs no Compustat. A large
NEGATIVE move in the net intangibles deferred-tax position is the signature of
an acquisition: purchase accounting writes the target's intangibles up to fair
value for book while the tax basis carries over, creating a DTL at closing (the
same mechanism as settled point 5's acquired-IP cost case).

    acq_suspect      delta < -$100m AND |delta| > 20% of the prior position
    acq_within_3yr   an acq_suspect year for the same firm in the prior 3 years,
                     because it is the AMORTISATION of that DTL, not the
                     acquisition itself, that contaminates later years

`bs_sign_usable` is the field to filter on: a large move, no recent acquisition.
"""
import pandas as pd, numpy as np

pos=pd.read_csv('intangible_net_position_Claude.csv')
pos['ddate']=pd.to_datetime(pos.ddate)
pos['acq_suspect']=((pos.delta< -100e6)&(pos.delta.abs()>0.20*pos.prev.abs())).astype(int)
pos=pos.sort_values(['cik','ddate'])
def within3(g):
    out=[]
    for i,r in enumerate(g.itertuples()):
        prior=g.iloc[max(0,i-3):i]
        out.append(int(prior.acq_suspect.sum()>0))
    return pd.Series(out,index=g.index)
pos['acq_within_3yr']=pos.groupby('cik',group_keys=False).apply(within3)
pos.to_csv('intangible_net_position_Claude.csv',index=False)

m=pd.read_csv('balance_sheet_sign_Claude.csv',low_memory=False)
k=pos[['cik','ddate','delta','acq_suspect','acq_within_3yr']].rename(columns={'ddate':'ddate_y'})
k['ddate_y']=k.ddate_y.astype(str)
m['ddate_y']=pd.to_datetime(m.ddate_y,errors='coerce').astype(str)
m=m.drop(columns=[c for c in ('acq_suspect','acq_within_3yr') if c in m.columns])
m=m.merge(k.drop(columns=['delta']),on=['cik','ddate_y'],how='left')

MIN=1e6
m['bs_sign']=np.where(m.delta>MIN,'benefit',np.where(m.delta<-MIN,'cost','~flat'))
m['bs_delta']=m.delta
m['vocab_sign']=m.effect_direction.fillna('none')
m['bs_vs_vocab']=np.where(~m.vocab_sign.isin(['benefit','cost'])|(m.bs_sign=='~flat'),'not comparable',
                   np.where(m.bs_sign==m.vocab_sign,'agree','DISAGREE'))
m['bs_sign_usable']=((m.bs_delta.abs()>=5e8)&(m.acq_within_3yr.fillna(0)==0)&
                     (m.acq_suspect.fillna(0)==0)).astype(int)
cols=['cik','company','form','filing_date','amount','vocab_sign','bs_sign','bs_delta',
      'bs_vs_vocab','acq_suspect','acq_within_3yr','bs_sign_usable','sentence']
m[cols].to_csv('bs_sign_tracking_Claude.csv',index=False)

print(f"rows tracked: {len(m):,}   firms: {m.cik.nunique()}")
print("\nbs_vs_vocab:"); print(m.bs_vs_vocab.value_counts().to_string())
print(f"\nfirm-years flagged as a suspected ACQUISITION: {int(m.acq_suspect.fillna(0).sum())}")
print(f"rows within 3 years of one:                    {int(m.acq_within_3yr.fillna(0).sum())}")
print(f"rows where bs_sign_usable = 1:                 {int(m.bs_sign_usable.sum())}  "
      f"({m.cik[m.bs_sign_usable==1].nunique()} firms)")
c=m[m.bs_vs_vocab.isin(['agree','DISAGREE'])]
for lab,s in [("ALL comparable",c),
              ("large move, NO recent acquisition",c[c.bs_sign_usable==1]),
              ("large move, acquisition within 3yr",c[(c.bs_delta.abs()>=5e8)&(c.acq_within_3yr.fillna(0)==1)])]:
    if len(s): print(f"  {lab:38s} n={len(s):4d}  agreement {(s.bs_vs_vocab=='agree').mean():.0%}")
