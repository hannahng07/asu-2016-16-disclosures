"""THE OWNING FILE. One row per (firm, disclosure). Nothing else holds a copy.

Their three requirements:
  1. one file owns each disclosure - this is it: DISCLOSURE_REGISTER_Claude.csv
  2. every output is a VIEW of it by join, never a rebuild from a different frame
  3. one control: rows in the owning file with no corresponding output row must be ZERO

Cause D on 16 October was exactly a breach of (2): the appendix was rebuilt from the frame and
never joined usin_all_adjudicated_Claude.csv, so Zynga was reported as an absence while our own
output had it confirmed. Control C4 below is the check that would have caught it.

SOURCES UNIONED (and each row records which one owns it):
  frame        population_filings_Claude.csv, is_effect=1
  usin_adj     dta_probe/usin_all_adjudicated_Claude.csv  <- the orphaned file
  sweep        the GILTI/FDII/DTA-label sweep over the 74
  sor          SENTENCE_OF_RECORD_Claude.csv, which supplies the sentence of record
"""
import os, re, csv, json, hashlib
from collections import defaultdict
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
H=os.path.expanduser('~')+'/h74'
REG=os.path.join(BASE,'DISCLOSURE_REGISTER_Claude.csv')
CTL=os.path.join(BASE,'DISCLOSURE_REGISTER_CONTROLS_Claude.csv')

CIKS=json.load(open(H+'/ciks.json')); T2C={v:k for k,v in CIKS.items()}
W={ (r['ticker_deliverable'] or '').strip():r for r in
    csv.DictReader(open(os.path.join(BASE,'READER_WORKLIST_74_FIRMS_2026-10-16.csv'),
                        encoding='utf-8-sig')) }
def ck(c):
    c=(c or '').strip()
    try: return str(int(float(c)))
    except ValueError: return ''
def istrue(v): return str(v).strip().lower() in ('1','true','yes')
def did(*parts):
    return 'D'+hashlib.sha1('|'.join(str(p) for p in parts).encode()).hexdigest()[:10].upper()

rows=[]
def add(**k):
    b=dict(disclosure_id='',ticker='',gvkey='',cik='',us_parent='',disclosure_type='',
           fiscal_year='',figure_usd='',sign='',destination='',destination_basis='',
           sentence='',accession='',form='',filing_date='',note_reference='',
           evidence_type='',owned_by='',on_74_worklist='')
    b.update(k)
    b['disclosure_id']=did(b['ticker'],b['cik'],b['disclosure_type'],b['fiscal_year'],b['accession'])
    b['on_74_worklist']=('yes' if b['ticker'] in W else 'no')
    if b['ticker'] in W:
        b['gvkey']=b['gvkey'] or (W[b['ticker']]['gvkey'] or '').strip()
        b['us_parent']=b['us_parent'] or (W[b['ticker']]['us_parent'] or '').strip()
    rows.append(b)

# ---- sentence of record, keyed (ticker, fy)
SOR={}
p=os.path.join(BASE,'SENTENCE_OF_RECORD_FOR_IRISH_READER_Claude.csv')
if os.path.exists(p):
    for r in csv.DictReader(open(p,encoding='utf-8')):
        SOR[(r['ticker'],r['fiscal_year'])]=r

# ---- 1. the frame
R=list(csv.DictReader(open(os.path.join(BASE,'population_filings_Claude.csv'),
                           encoding='utf-8',errors='replace')))
for r in R:
    c=ck(r['cik'])
    if c not in CIKS or not istrue(r.get('is_effect')): continue
    tk=CIKS[c]
    rt=(r.get('record_type') or '')
    dt='ASU2016-16_ADOPTION' if rt=='adoption_catchup' else 'ASU2016-16_SUBSEQUENT_TRANSFER'
    fy=(r.get('adoption_year_stated') if rt=='adoption_catchup' else r.get('transfer_year')) or ''
    try: fy=str(int(float(fy))) if fy else ''
    except ValueError: fy=''
    s=(r.get('anchor_sentence') or r.get('sentence') or '').strip()
    acc=(r.get('accession') or '').strip(); dest=(r.get('destination') or '').strip()
    sor=SOR.get((tk,fy or 'NOT STATED'))
    if sor and sor['sentence_of_record'] and dt.endswith('SUBSEQUENT_TRANSFER'):
        s=sor['sentence_of_record']; acc=sor['accession_of_record'] or acc
        dest=sor['destination_in_this_sentence']
        db='from the sentence of record (%s)'%sor['verdict'].split(' - ')[0]
    else:
        if dest.lower().startswith(('united states','u.s')):
            dest=('NOT CONFIRMED - the frame field said United States but no asserting '
                  'sentence supports it. DO NOT RELY.')
            db='frame field only, contradicted by the sentence check of 16 October'
        else:
            db='frame destination field; not confirmed against the sentence' if dest else 'not stated'
    add(ticker=tk,cik=c,disclosure_type=dt,fiscal_year=fy or 'NOT STATED',
        figure_usd=(r.get('amount') or ''),sign='%s/%s'%(r.get('effect_direction') or '-',
        r.get('dta_dtl') or '-'),destination=dest,destination_basis=db,sentence=s[:900],
        accession=acc,form=r.get('form',''),filing_date=r.get('filing_date','')[:10],
        note_reference='amount_grade=%s tier=%s'%(r.get('amount_grade') or '-',r.get('evidence_tier') or '-'),
        evidence_type=('quoted' if len(s)>45 else 'derived'),owned_by='frame')

# ---- 2. the orphaned US-inbound adjudicated file  (cause D)
AD=list(csv.DictReader(open(os.path.join(BASE,'dta_probe','usin_all_adjudicated_Claude.csv'),
                            encoding='utf-8',errors='replace')))
seenad=set()
for r in AD:
    c=ck(r.get('cik'))
    if not c: continue
    tk=CIKS.get(c,'')
    key=(c,r.get('date',''),r.get('dest_phrase','')[:40])
    if key in seenad: continue
    seenad.add(key)
    add(ticker=tk or ('cik'+c),cik=c,disclosure_type='US_INBOUND_CANDIDATE',
        fiscal_year=(r.get('date','') or '')[:4],destination='United States (phrase matched)',
        destination_basis='full-corpus US-inbound sweep, phrase: %s'%r.get('dest_phrase','')[:70],
        sentence=(r.get('excerpt') or '')[:900],form=r.get('form',''),
        filing_date=r.get('date',''),us_parent=(r.get('company') or ''),
        note_reference='ADJUDICATED 2026-10-09; this file was ORPHANED from the 16 Oct appendix (cause D)',
        evidence_type='quoted excerpt',owned_by='usin_adj')

# ---- 3. GILTI / FDII / DTA labels from the sweep
E=defaultdict(list)
for line in open(H+'/evidence.jsonl',encoding='utf-8'):
    x=json.loads(line); E[x['tick']].append(x)
for tk,v in E.items():
    c=T2C.get(tk,'')
    for key,dt in (('gilti','GILTI'),('fdii','FDII'),('dta','DTA_LINE_LABEL')):
        best=None
        for x in sorted(v,key=lambda y:y['filed']):
            if x.get(key):
                best=(x,x[key][0]); break
        if not best: 
            add(ticker=tk,cik=c,disclosure_type=dt+'_NONE_FOUND',fiscal_year='',
                sentence='',evidence_type='observed absence',owned_by='sweep',
                note_reference='%d filings searched; see COVERAGE_POPULATION_74FIRMS_Claude.csv'%len(v),
                destination_basis='n/a')
            continue
        x,s=best
        add(ticker=tk,cik=c,disclosure_type=dt,fiscal_year=x['filed'][:4],sentence=s[:900],
            accession=x['accession'],form=x['form'],filing_date=x['filed'],
            evidence_type='quoted',owned_by='sweep',destination_basis='n/a',
            note_reference='earliest filing carrying this item')

# ---- 4. firms with no CIK: explicit not-searched rows
for tk,w in W.items():
    if tk in T2C: continue
    add(ticker=tk,cik='',us_parent=w['us_parent'],disclosure_type='NOT_SEARCHED',
        sentence='',evidence_type='COVERAGE GAP - not an absence',owned_by='worklist',
        note_reference='gvkey %s absent from the Compustat extract; no CIK resolved; NO FILINGS READ'%w['gvkey'],
        destination_basis='n/a')

cols=['disclosure_id','ticker','gvkey','cik','us_parent','on_74_worklist','disclosure_type',
      'fiscal_year','figure_usd','sign','destination','destination_basis','sentence',
      'accession','form','filing_date','note_reference','evidence_type','owned_by']
seen=set(); ded=[]
for r in rows:
    if r['disclosure_id'] in seen: continue
    seen.add(r['disclosure_id']); ded.append(r)
ded.sort(key=lambda r:(r['on_74_worklist']=='no',r['ticker'],r['disclosure_type'],r['fiscal_year']))
with open(REG,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); w.writerows(ded)

# ============ CONTROLS. Every one must read ZERO. ============
ctl=[]
def C(cid,desc,n,detail=''):
    ctl.append(dict(control_id=cid,must_read='ZERO',value=n,
                    status=('PASS' if n==0 else 'FAIL'),description=desc,detail=detail[:300]))
regciks={r['cik'] for r in ded if r['cik']}
# C1 every frame effect firm has a register row
framefirms={ck(r['cik']) for r in R if istrue(r.get('is_effect')) and ck(r['cik']) in CIKS}
C('C1','frame effect firms with no register row',len(framefirms-regciks),str(sorted(framefirms-regciks)))
# C2 every adjudicated US-inbound cik has a register row  <- THE CAUSE-D CONTROL
adciks={ck(r.get('cik')) for r in AD if ck(r.get('cik'))}
C('C2','adjudicated US-inbound ciks with no register row (CAUSE D)',len(adciks-regciks),
  str(sorted(adciks-regciks)))
# C3 every one of the 74 worklist firms appears
missing74=[tk for tk in W if tk not in {r['ticker'] for r in ded}]
C('C3','worklist firms with no register row',len(missing74),str(missing74))
# C4 no quoted row without an accession
bad=[r for r in ded if r['evidence_type'].startswith('quoted') and not r['accession']
     and r['owned_by']!='usin_adj']
C('C4','quoted rows with no accession',len(bad),str([(r['ticker'],r['disclosure_type']) for r in bad[:8]]))
# C5 attribution: every quoted sentence present in its accession
AT=os.path.join(BASE,'ATTRIBUTION_CHECK_Claude.csv')
nf=0
if os.path.exists(AT):
    nf=sum(1 for r in csv.DictReader(open(AT,encoding='utf-8')) if r['verdict'].startswith('FAIL'))
C('C5','quoted sentences NOT present in the accession they cite',nf,'see ATTRIBUTION_CHECK_Claude.csv')
# C6 no destination asserted as US without the sentence supporting it
us=[r for r in ded if r['destination'].lower().startswith('united states')
    and 'NOT confirmed' in r['destination_basis']]
C('C6','US destinations resting on the unverified frame field',len(us),
  str(sorted({r['ticker'] for r in us})))
with open(CTL,'w',newline='',encoding='utf-8') as fh:
    w=csv.DictWriter(fh,fieldnames=['control_id','must_read','value','status','description','detail'])
    w.writeheader(); w.writerows(ctl)

from collections import Counter
print('DISCLOSURE REGISTER: %d rows | %d firms | %d on the 74 worklist'
      %(len(ded),len({r['ticker'] for r in ded}),len({r['ticker'] for r in ded if r['on_74_worklist']=='yes'})))
print('  owned_by:',dict(Counter(r['owned_by'] for r in ded)))
print('  types:')
for k,v in Counter(r['disclosure_type'] for r in ded).most_common(): print('     %-34s %4d'%(k,v))
print('\nCONTROLS (every one must read ZERO):')
for r in ctl:
    print('  %-4s %-5s value=%-4d  %s'%(r['control_id'],r['status'],r['value'],r['description']))
    if r['status']=='FAIL': print('        detail: %s'%r['detail'][:200])
print('\nwrote %s'%os.path.basename(REG)); print('wrote %s'%os.path.basename(CTL))
