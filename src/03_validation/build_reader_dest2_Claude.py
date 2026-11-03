#!/usr/bin/env python3
"""Destination reader, round 2 -- the 245 footnote firms the first run never saw.

WHY THESE 245
-------------
Round 1 read 97 firms. Those 97 are exactly the firms where
`notes_text_Claude.py` had already written a non-empty `dest_excerpt`, i.e.
where its COUNTRY+MOVE matcher had ALREADY found a destination cue. So round 1
could only ever confirm or deny destinations the matcher had already spotted.
It could not find one the matcher missed -- and Brunswick showed the matcher's
misses are real: its corpus sentence names no destination while the footnote as
filed says "from one of our affiliates in Norway to the United States".

These 245 firms have NO dest_excerpt. They are the unfiltered remainder, and
they are where a destination the matcher never saw would be hiding. All 245 are
effect-class somewhere; 26 are Double Irish firms.

WHAT THE READER IS ASKED FOR
----------------------------
Same three fields as round 1, so the two runs concatenate:
    dest_to    destination jurisdiction, "unstated", or "not_a_transfer"
    dest_from  source jurisdiction, or "-"
    asset      IP / fixed_assets / other_assets / "-"

`asset` earns its place because Toro's "intra-entity transfer" turned out to be
FIXED ASSETS, not IP -- in scope for ASU 2016-16, out of scope for an IP study,
and not currently a field anywhere in the frame.

The text handed to the reader is the footnote AS FILED from the SEC Notes data
sets, dollar signs and tables intact -- not the Loughran-McDonald sentence,
which is where the destination gets stripped.
"""
import pandas as pd, sys

N_PER_BATCH = 25
MAX_CHARS   = 1800

n = pd.read_csv('notes_text_blocks_Claude.csv', low_memory=False)
done = set(pd.read_csv('reader_destination_rows_Claude.csv', low_memory=False)['cik'])
f = pd.read_csv('population_filings_Claude.csv', low_memory=False)

todo = n[~n['cik'].isin(done)].copy()
# one block per firm: prefer the block the amount of record came from, then score
todo['_r'] = todo['is_amount_of_record'].fillna(False).astype(bool).astype(int)
todo = todo.sort_values(['cik','_r','score','block_chars'], ascending=[True,False,False,False])
pick = todo.groupby('cik', as_index=False).first()

di = set(f.loc[f['double_irish']==1,'cik'])
cur = (f[f['destination'].notna()].groupby('cik')['destination']
         .apply(lambda s: '; '.join(sorted(set(s.astype(str)))[:3])))
uv  = f.groupby('cik')['us_verdict'].apply(
        lambda x:'yes' if (x=='yes').any() else ('no' if (x=='no').any() else 'not_stated'))

pick['current_destinations'] = pick['cik'].map(cur).fillna('not stated')
pick['us_verdict_firm']      = pick['cik'].map(uv).fillna('not_stated')
pick['double_irish']         = pick['cik'].isin(di).astype(int)
pick['dest_excerpt']         = pick['excerpt'].astype(str).str.slice(0, MAX_CHARS)

cols = ['cik','company','form','filing_date','double_irish','us_verdict_firm',
        'current_destinations','dest_excerpt']
pick[cols].to_csv('reader_dest2_rows_Claude.csv', index=False)

# Double Irish firms first -- goal 2's ground truth reads first if the run is cut short
pick = pick.sort_values(['double_irish','company'], ascending=[False,True]).reset_index(drop=True)

HEAD = """You are reading INCOME TAX FOOTNOTES exactly as filed with the SEC.

For each numbered firm, answer with ONE line:
  <number>|<dest_to>|<dest_from>|<asset>

dest_to    Where the transferred asset ENDED UP. Name the jurisdiction as the
           filing names it (Ireland, United States, Switzerland, Singapore...).
           Write "unstated" if a transfer is described but no destination is given.
           Write "not_a_transfer" if no intra-entity/intercompany transfer of an
           asset is described at all (boilerplate about the standard, rate tables,
           third-party sales to customers).
dest_from  Where it came FROM, or "-" if not stated.
asset      IP | fixed_assets | other_assets | "-" if not stated.

RULES
 - Direction matters. "from subsidiaries in the U.S. to subsidiaries in
   Switzerland" means dest_to=Switzerland, dest_from=United States. Do not
   report a jurisdiction as the destination because it appears near the word
   transfer.
 - A sale of IP to an outside CUSTOMER is not an intra-entity transfer.
   dest_to=not_a_transfer.
 - "U.S. GAAP", "the U.S. statutory rate", "taxable in the U.S." and
   "remitted to the U.S." are NOT destinations.
 - If two destinations are named, write both: "Ireland and United States".
 - Answer only from the text shown. Do not infer from the company's domicile.
 - Output only the answer lines. No prose, no explanation.

"""

batches = [pick.iloc[i:i+N_PER_BATCH] for i in range(0, len(pick), N_PER_BATCH)]
for bi, b in enumerate(batches, 1):
    with open(f'reader_dest2_{bi}.txt', 'w', encoding='utf-8') as fh:
        fh.write(HEAD)
        for j, (_, r) in enumerate(b.iterrows(), 1):
            fh.write(f"{j}|{r['company']}|{r['form']} {r['filing_date']} || "
                     f"FOOTNOTE AS FILED: {' '.join(str(r['dest_excerpt']).split())}\n\n")
print(f"firms: {len(pick)}   batches: {len(batches)}   "
      f"double-irish firms in batch 1-2: {int(pick.head(N_PER_BATCH*2)['double_irish'].sum())}")
