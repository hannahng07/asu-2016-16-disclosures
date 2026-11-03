#!/usr/bin/env python3
r"""The balance-sheet sign: does the intangibles deferred-tax position move
toward ASSET (benefit) or toward LIABILITY (cost)?

net position = sum(DTA intangibles) - sum(DTL intangibles), per firm per ddate.
The YEAR-ON-YEAR CHANGE in that net position around the transfer is the sign.

PepsiCo FY2018 is the worked example: DTA 0 -> 985m and DTL 3,169m -> 0, a
+$4.154bn swing toward asset. Benefit, with no adjective read anywhere.
"""
import pandas as pd, numpy as np
d=pd.read_csv('intangibles_dtaxes_Claude.csv')
d['ddate']=pd.to_datetime(d.ddate,format='%Y%m%d',errors='coerce')
d=d.dropna(subset=['ddate'])
d['signed']=np.where(d.side=='DTA',d.value,-d.value)
# one net position per firm per balance-sheet date (dedupe repeated filings of the same date)
pos=(d.groupby(['cik','ddate','side'],as_index=False).value.max()
       .assign(signed=lambda x: np.where(x.side=='DTA',x.value,-x.value))
       .groupby(['cik','ddate'],as_index=False).signed.sum()
       .rename(columns={'signed':'net_intangible_dtax'}))
pos=pos.sort_values(['cik','ddate'])
pos['prev']=pos.groupby('cik').net_intangible_dtax.shift(1)
pos['prev_date']=pos.groupby('cik').ddate.shift(1)
pos['delta']=pos.net_intangible_dtax-pos.prev
pos['gap_days']=(pos.ddate-pos.prev_date).dt.days
pos=pos[(pos.gap_days>=300)&(pos.gap_days<=430)]          # year-on-year only
pos.to_csv('intangible_net_position_Claude.csv',index=False)
print(f"firm-year changes computed: {len(pos):,}  firms: {pos.cik.nunique():,}")

f=pd.read_csv('population_filings_Claude.csv',low_memory=False)
e=f[f.is_effect.astype(str).isin(['1','True'])].copy()
e['ddate']=pd.to_datetime(e.datadate,errors='coerce')
e=e.dropna(subset=['ddate'])
m=e.merge(pos,on='cik',how='inner')
m['days']=(m.ddate_y-m.ddate_x).dt.days.abs()
m=m[m.days<=200].sort_values('days').drop_duplicates(['cik','accession'])
print(f"effect filings matched to a firm-year balance change: {len(m):,}  firms: {m.cik.nunique()}")

MIN=1_000_000
m['bs_sign']=np.where(m.delta>MIN,'benefit',np.where(m.delta<-MIN,'cost','~flat'))
m['vocab']=m.effect_direction.fillna('none')
cmp=m[m.vocab.isin(['benefit','cost'])&(m.bs_sign!='~flat')]
print(f"\ncomparable rows (both signs present): {len(cmp)}  firms: {cmp.cik.nunique()}")
ct=pd.crosstab(cmp.vocab,cmp.bs_sign)
print("\nvocabulary sign (rows) vs balance-sheet sign (cols):")
print(ct.to_string())
agree=int(np.trace(ct.reindex(index=['benefit','cost'],columns=['benefit','cost']).fillna(0).values))
print(f"\nagree {agree} of {len(cmp)} = {agree/len(cmp):.0%}")
m.to_csv('balance_sheet_sign_Claude.csv',index=False)
