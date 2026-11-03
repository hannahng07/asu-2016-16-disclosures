#!/usr/bin/env python3
r"""Scan one *_notes.zip for ASU 2016-16 facts. Appends to a single CSV.

Streams rather than loads: num.tsv is 1.2 GB uncompressed and the machine has 3 GB.
The trick is to build the tiny set of dimension hashes that name ASU 2016-16 from
dim.tsv first (~90 MB, seconds), then make a single pass over num.tsv keeping only
rows whose dimh is in that set or whose TAG NAME describes a transfer.

The three passes are NOT equal quality and the `why` column keeps them apart:

    asu_member        the dimension names the standard          -> evidence
    segment_2016_16   some other axis mentions 2016-16          -> usable
    tag_name          the tag's name describes a transfer       -> A LEAD ONLY

The third is noisy. OPK's 28 hits in 2019q1 were
`RevenueFromTransferOfIntellectualProperty` on an 8-K -- licensing revenue, not an
intra-entity transfer. Never pool them.

Usage:  python scan_sec_notes_Claude.py 2018q1_notes.zip [--out FILE]
"""
import argparse,collections,csv,io,re,sys,time,zipfile
from pathlib import Path
csv.field_size_limit(min(sys.maxsize,2**31-1))
MEMBER=re.compile(r"AccountingStandardsUpdate2016-?16",re.I)
ANY1616=re.compile(r"2016-?16")
TAGNAME=re.compile(r"intra[-_]?entity|intraentity|intercompany[a-z]*transfer|"
                   r"transferof(intellectual|intangible|ip)|"
                   r"(intellectual|intangible)[a-z]*transfer|noninventory",re.I)
FIELDS=["quarter","why","cik","company","form","fy","fp","period","filed","adsh",
        "tag","version","ddate","qtrs","uom","value","segments"]

# BRIAN'S IDEA, 17 September: "If we can identify the transfer statement, and then
# also see a large US DTA/DTL, then we can state 'likely US'."
#
# The DIRECT form of that -- a deferred tax fact carrying BOTH the ASU 2016-16
# member and a geography axis -- exists but is vanishingly rare: 7 facts in three
# quarters. So the corroborating form is the one to build, and it needs the
# domestic/foreign split that US GAAP puts on separate ELEMENTS rather than on a
# dimension. These are captured for every filer, and joined to the ASU facts later.
#
# CAUTION that belongs with any inference drawn from these: the adoption window
# overlaps the Tax Cuts and Jobs Act, which remeasured US deferred taxes for
# essentially every US filer in 2018. A large US deferred tax movement in 2018 is
# near-universal and is NOT diagnostic of anything. The signal only gets clean
# after the TCJA remeasurement washes out.
GEOTAX=set("""DeferredFederalIncomeTaxExpenseBenefit
DeferredForeignIncomeTaxExpenseBenefit
DeferredStateAndLocalIncomeTaxExpenseBenefit
CurrentFederalTaxExpenseBenefit
CurrentForeignTaxExpenseBenefit
CurrentStateAndLocalTaxExpenseBenefit
DeferredFederalStateAndLocalTaxExpenseBenefit
IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic
IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign
DeferredTaxAssetsNet DeferredTaxAssetsGross DeferredTaxAssetsNetNoncurrent
DeferredTaxLiabilities DeferredTaxLiabilitiesNoncurrent
DeferredTaxAssetsLiabilitiesNet DeferredTaxAssetsLiabilitiesNetNoncurrent
DeferredIncomeTaxAssetsNet DeferredIncomeTaxLiabilities""".split())
NODIM={"0x00000000","","0x0",None}
GEOAX=re.compile(r"IncomeTaxAuthority|Geographical|StatementGeographical|"
                 r"DomesticCountry|ForeignCountry|Jurisdiction", re.I)
GEOFIELDS=["quarter","cik","company","form","fy","fp","period","filed","adsh",
           "tag","ddate","qtrs","uom","value","segments"]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("zip"); ap.add_argument("--out",default="sec_notes_asu_facts_Claude.csv")
    # num.tsv for the largest quarter is 1.2 GB and one pass runs past the
    # shell's time ceiling, so the pass itself is chunkable by row range.
    ap.add_argument("--skip",type=int,default=0)
    ap.add_argument("--take",type=int,default=0)
    a=ap.parse_args(); t0=time.time()
    q=Path(a.zip).name.split("_")[0]
    z=zipfile.ZipFile(a.zip)
    sub={}
    with z.open("sub.tsv") as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh,encoding="utf-8",errors="replace"),delimiter="\t"):
            sub[r["adsh"]]=r
    asu=set(); anyd={}; geod={}
    with z.open("dim.tsv") as fh:
        rd=csv.DictReader(io.TextIOWrapper(fh,encoding="utf-8",errors="replace"),delimiter="\t")
        hk,sk=rd.fieldnames[0],("segments" if "segments" in rd.fieldnames else rd.fieldnames[1])
        for r in rd:
            seg=r.get(sk,"")
            if ANY1616.search(seg):
                anyd[r[hk]]=seg
                if MEMBER.search(seg): asu.add(r[hk])
            if GEOAX.search(seg): geod[r[hk]]=seg
    print(f"{q}: {len(sub):,} submissions, {len(anyd):,} dims mention 2016-16 ({len(asu):,} on the member)  [{time.time()-t0:.0f}s]")
    rows=[];geo=[];n=0
    with z.open("num.tsv") as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh,encoding="utf-8",errors="replace"),delimiter="\t"):
            n+=1
            if n<=a.skip: continue
            if a.take and n>a.skip+a.take: break
            dh=r.get("dimh","")
            why=("asu_member" if dh in asu else "segment_2016_16" if dh in anyd
                 else "tag_name" if TAGNAME.search(r.get("tag","")) else "")
            if not why:
                t=r.get("tag","")
                # NO-DIMENSION IS A HASH, NOT AN EMPTY STRING. Un-dimensioned
                # facts carry dimh='0x00000000', so testing `not dh` dropped every
                # consolidated federal/foreign line and left only the dimensioned
                # stragglers -- 395 facts where one quarter alone holds thousands.
                if t in GEOTAX and (dh in geod or dh in NODIM):
                    s2=sub.get(r["adsh"],{})
                    geo.append({"quarter":q,"cik":(s2.get("cik") or "").lstrip("0"),
                        "company":s2.get("name",""),"form":s2.get("form",""),
                        "fy":s2.get("fy",""),"fp":s2.get("fp",""),"period":s2.get("period",""),
                        "filed":s2.get("filed",""),"adsh":r["adsh"],"tag":t,
                        "ddate":r.get("ddate",""),"qtrs":r.get("qtrs",""),
                        "uom":r.get("uom",""),"value":r.get("value",""),
                        "segments":geod.get(dh,"")})
                continue
            s=sub.get(r["adsh"],{})
            rows.append({"quarter":q,"why":why,"cik":(s.get("cik") or "").lstrip("0"),
                "company":s.get("name",""),"form":s.get("form",""),"fy":s.get("fy",""),
                "fp":s.get("fp",""),"period":s.get("period",""),"filed":s.get("filed",""),
                "adsh":r["adsh"],"tag":r.get("tag",""),"version":r.get("version",""),
                "ddate":r.get("ddate",""),"qtrs":r.get("qtrs",""),"uom":r.get("uom",""),
                "value":r.get("value",""),"segments":anyd.get(dh,"")})
    out=Path(a.out); new=not out.exists()
    with out.open("a",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=FIELDS)
        if new: w.writeheader()
        w.writerows(rows)
    g=Path(str(out).replace(".csv","_GEOTAX.csv")); gnew=not g.exists()
    with g.open("a",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=GEOFIELDS)
        if gnew: w.writeheader()
        w.writerows(geo)
    print(f"  domestic/foreign tax facts captured: {len(geo):,}")
    print(f"  {n:,} facts scanned in {time.time()-t0:.0f}s; matched {len(rows):,} "
          f"{dict(collections.Counter(x['why'] for x in rows))}")
if __name__=="__main__": main()
