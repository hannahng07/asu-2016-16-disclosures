#!/usr/bin/env python3
r"""The Double Irish deliverable, in the shape of "Example Deliverable ASU 2016-16.docx",
for the DI sample only.

THE ROW SET, AND WHY IT IS 84 AND NOT 72
----------------------------------------
There are three DI firm lists in this folder and they do not agree:

    ex21_irish_subsidiaries_Claude.csv (double_irish_firm flag)   72 firms
    di_firm_years_Claude.txt                                      77 firms
    irish_cik_bridge_Claude.csv (verified Irish transfer dates)    43 firms

The first two overlap in 72; di_firm_years adds ACOM, BTAX, NPSP, SNDK.1, UTIW. The
bridge adds eight more that neither carries -- AON, BMRN, CGNX, CIK0001557939 (Kinetic
Concepts/KCI, which has no ticker), ITG, MNK, NPSP, ORCL. The union is 84.

This builds on the UNION and carries a membership column for each source, so no firm is
silently dropped and any of the three lists can be cut back out with a filter. Which list
is authoritative is Brian's call, not this script's.

ABSENCE IS NOT EVIDENCE OF ABSENCE
-----------------------------------
Settled point 2. Disclosure is required only when material, and REGN, YELP and INSM say
nothing across 28-29 filings each. So every DI firm gets a row whether or not the corpus
found anything, and "Disclosure found" says which of three states it is in:

    effect          the filing states a transfer effect
    mention only    the firm is in the corpus and mentions the standard, no effect stated
    none in corpus  the firm never appears in the 10-K/10-Q corpus at all

A blank amount on this sheet means the firm did not state one, or the corpus stripped the
figure. It NEVER means the transfer did not happen. 20 of the 84 never appear in the
corpus; most were acquired or delisted before the 2016 corpus window opens, which is a
property of the sample frame and not a finding about the firm.

THE GOAL 2 COLUMN
-----------------
"Irish transfer year" and "Irish destination" come from the Irish statutory work and are
read-only here -- nothing is written back. "10-K agrees with Irish year" compares the
verified Irish calendar year against the transfer year read out of the filing, which is
the test goal 2 actually poses. Settled point 3 applies: the adoption date is not the
transfer date, so an adoption catch-up landing years later is not a disagreement.
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
HERE = Path(__file__).resolve().parent
OUT = HERE / "ASU_2016_16_DoubleIrish_deliverable_Claude.xlsx"

FONT="Arial"
HEAD=PatternFill("solid",fgColor="1F3864"); HEADF=Font(name=FONT,bold=True,color="FFFFFF",size=10)
BODY=Font(name=FONT,size=10); NOTEF=Font(name=FONT,size=10,italic=True,color="595959")
TITLE=Font(name=FONT,bold=True,size=13,color="1F3864")
WARN=PatternFill("solid",fgColor="FFF2CC")
BORD=Border(bottom=Side(style="thin",color="D9D9D9"))
MONEY='$#,##0;($#,##0);-'

ITEMS=[("amt_retained_earnings","Retained earnings"),
       ("amt_deferred_tax_asset","Deferred tax asset"),
       ("amt_deferred_tax_liability","Deferred tax liability"),
       ("amt_tax_pl","Tax expense / benefit (P&L)"),
       ("amt_prepaid","Prepaid / deferred charge"),
       ("amt_valuation_allowance","Valuation allowance"),
       ("amt_other_assets","Other assets"),
       ("amt_noncontrolling_interest","Noncontrolling interest")]

def num(x):
    try:
        v=float(x); return None if v!=v else v
    except (TypeError,ValueError): return None

def write(ws,df,money,title,note,widths=None):
    ws.sheet_view.showGridLines=False
    ws["A1"]=title; ws["A1"].font=TITLE
    ws["A2"]=note;  ws["A2"].font=NOTEF
    ws.freeze_panes="A5"
    for j,c in enumerate(df.columns,1):
        cell=ws.cell(row=4,column=j,value=c); cell.fill,cell.font=HEAD,HEADF
        cell.alignment=Alignment(vertical="center",wrap_text=True)
    for i,row in enumerate(df.itertuples(index=False),5):
        for j,v in enumerate(row,1):
            cell=ws.cell(row=i,column=j)
            cell.value=None if v=="" else v          # ws.cell(value=None) is a no-op
            cell.font,cell.border=BODY,BORD
            if df.columns[j-1] in money: cell.number_format=MONEY
    ws.row_dimensions[4].height=32
    for j,c in enumerate(df.columns,1):
        w=(widths or {}).get(c)
        if w is None: w=min(max(11,int(df[c].astype(str).str.len().quantile(.9))+2),34)
        ws.column_dimensions[get_column_letter(j)].width=w
    ws.auto_filter.ref=f"A4:{get_column_letter(len(df.columns))}{4+len(df)}"

def main():
    fil=pd.read_csv(HERE/"population_filings_Claude.csv",dtype=str,low_memory=False)
    ex =pd.read_csv(HERE/"ex21_irish_subsidiaries_Claude.csv",dtype=str,low_memory=False)
    dy =pd.read_csv(HERE/"di_firm_years_Claude.txt",sep="\t",dtype=str)
    br =pd.read_csv(HERE/"irish_cik_bridge_Claude.csv",dtype=str,low_memory=False)
    ir =pd.read_csv(HERE/"IRISH_transfer_dates_for_10K_verification_2026-09-18.csv",
                    dtype=str,low_memory=False)

    exd=ex[ex.double_irish_firm.isin(["1","True","TRUE"])].drop_duplicates("cik")
    P=lambda s: s.astype(str).str.lstrip("0")
    exd["k"]=P(exd.cik); dy["k"]=P(dy.cik)
    br["k"]=P(br.cik_plain if "cik_plain" in br else br.cik)
    fil["k"]=P(fil.cik)

    uni=sorted(set(exd.k)|set(dy.k)|set(br.k))
    m_ex,m_dy,m_br=set(exd.k),set(dy.k),set(br.k)
    tick={**dy.set_index("k").tic.to_dict(),**exd.set_index("k").ticker.to_dict(),
          **br.set_index("k").ticker.to_dict()}
    gvk ={**dy.set_index("k").gvkey.to_dict(),**exd.set_index("k").gvkey.to_dict()}
    name={**exd.set_index("k").company.to_dict(),
          **br.set_index("k").company_in_corpus.dropna().to_dict()}
    cname=fil.drop_duplicates("k").set_index("k").company.to_dict()

    # Irish ground truth, per firm: the verified years and the destination the Irish
    # accounts point at. Read-only -- nothing is written back to that project.
    t2k={v:k for k,v in tick.items() if isinstance(v,str)}
    ir["k"]=ir.ticker.map(t2k)
    irg=(ir.dropna(subset=["k"]).groupby("k")
           .agg(irish_years=("irish_transfer_year",lambda s:"; ".join(sorted(set(s.dropna())))),
                irish_dest =("destination_group",lambda s:"; ".join(sorted(set(s.dropna())))),
                irish_conf =("irish_evidence_confidence",lambda s:"; ".join(sorted(set(s.dropna())))),
                irish_match=("match_status",lambda s:"; ".join(sorted(set(s.dropna()))))))

    eff=fil[fil.is_effect=="1"].copy()
    effs=eff.sort_values(["k","filing_date","form"])
    first=effs.drop_duplicates("k").set_index("k")
    amt1=effs[effs.amount.notna()&(effs.amount!="")].drop_duplicates("k").set_index("k")
    n_all=fil.groupby("k").size().to_dict(); n_eff=eff.groupby("k").size().to_dict()
    uv=fil.groupby("k").us_verdict.apply(
        lambda x:"yes" if (x=="yes").any() else ("no" if (x=="no").any() else "not stated")).to_dict()

    rows=[]
    for k in uni:
        f1=first.loc[k] if k in first.index else None
        a1=amt1.loc[k] if k in amt1.index else None
        state=("effect" if f1 is not None else
               ("mention only" if k in n_all else "none in corpus"))
        g=irg.loc[k] if k in irg.index else None
        r={"Ticker":tick.get(k,""),
           "Company name":name.get(k) or cname.get(k,""),
           "CIK":k,"gvkey":gvk.get(k,""),
           "On ex21 DI list":"yes" if k in m_ex else "",
           "On di_firm_years":"yes" if k in m_dy else "",
           "Has verified Irish date":"yes" if k in m_br else "",
           "Irish transfer year (verified)":(g.irish_years if g is not None else ""),
           "Irish destination (verified)":(g.irish_dest if g is not None else ""),
           "Irish evidence confidence":(g.irish_conf if g is not None else ""),
           "Disclosure found":state,
           "Filings with an anchor hit":n_all.get(k,0),
           "Effect filings":n_eff.get(k,0)}
        if f1 is not None:
            r.update({"FIRST DISCLOSURE DATE":str(f1.filing_date)[:10],
                      "First disclosure form":f1.form,
                      "Fiscal year at first disclosure":f1.fyear or "",
                      "QUOTE FROM 10-K":" ".join(str(f1.sentence).split())[:900],
                      "Headline tax effect":num(a1.amount) if a1 is not None else None,
                      "Amount source":(a1.amount_source if a1 is not None else ""),
                      "Sign":f1.dta_dtl or "","Direction":f1.effect_direction or "",
                      "Destination stated":f1.destination or "",
                      "Transfer year read from filing":f1.transfer_year or "",
                      "Transfer timing":f1.transfer_timing or ""})
            for c,nm in ITEMS: r[nm]=num(f1[c]) if c in f1 else None
            r["Unit check"]=("component unit missing - do not use the item columns"
                             if any(abs(v)<1e4 for v in
                                    (num(f1[c]) for c,_ in ITEMS if c in f1) if v is not None) else "")
        else:
            for _,nm in ITEMS: r[nm]=None
            r["Unit check"]=""
        r["Into the US? (us_verdict)"]=uv.get(k,"not stated")
        # the goal 2 test
        ty=str(r.get("Transfer year read from filing") or "").strip()
        if ty.lower() in ("nan","none"): ty=""
        iy=str(r.get("Irish transfer year (verified)") or "")
        if not iy: r["10-K agrees with Irish year"]="no verified Irish year"
        elif state!="effect": r["10-K agrees with Irish year"]="no disclosure to compare"
        else:
            yrs={int(y) for y in iy.replace(";"," ").split() if y.isdigit()}
            try: tyi=int(float(ty))
            except (TypeError,ValueError): tyi=None
            if tyi is None or not yrs:
                r["10-K agrees with Irish year"]="filing states no transfer year"
            else:
                r["10-K agrees with Irish year"]=("yes" if any(abs(tyi-y)<=1 for y in yrs)
                                                  else "NO - differs by more than a year")
        rows.append(r)

    order=["Ticker","Company name","CIK","gvkey","On ex21 DI list","On di_firm_years",
           "Has verified Irish date","Irish transfer year (verified)",
           "Irish destination (verified)","Irish evidence confidence",
           "Disclosure found","Filings with an anchor hit","Effect filings",
           "FIRST DISCLOSURE DATE","First disclosure form","Fiscal year at first disclosure",
           "QUOTE FROM 10-K","Headline tax effect",*[n for _,n in ITEMS],"Unit check",
           "Amount source","Sign","Direction","Destination stated","Into the US? (us_verdict)",
           "Transfer year read from filing","Transfer timing","10-K agrees with Irish year"]
    firms=pd.DataFrame(rows).reindex(columns=order).fillna("")
    firms=firms.sort_values(["Disclosure found","Company name"])

    # every effect filing for these firms, the example's own shape
    d=eff[eff.k.isin(uni)].sort_values(["company","filing_date"])
    disc=pd.DataFrame({
        "Ticker":d.k.map(tick).fillna(""),"Company name":d.company,
        "Year":d.fyear.fillna(""),"Form":d.form,"Filing date":d.filing_date.str[:10],
        "QUOTE FROM 10-K":d.sentence.astype(str).str.split().str.join(" ").str[:900],
        "Headline tax effect":d.amount.map(num),"Sign":d.dta_dtl.fillna(""),
        "Direction":d.effect_direction.fillna(""),"Amount source":d.amount_source.fillna("")})
    for c,nm in ITEMS: disc[nm]=d[c].map(num) if c in d else None
    disc["Destination stated"]=d.destination.fillna("")
    disc["Into the US?"]=d.us_verdict.fillna("")
    disc["Transfer year"]=d.transfer_year.fillna("")
    disc["Disclosure class"]=d.disclosure_class.fillna("")
    disc["CIK"]=d.k; disc["Accession"]=d.accession
    disc=disc.fillna("")

    missing=firms[firms["Disclosure found"]!="effect"][
        ["Ticker","Company name","CIK","On ex21 DI list","On di_firm_years",
         "Has verified Irish date","Irish transfer year (verified)",
         "Irish destination (verified)","Disclosure found","Filings with an anchor hit"]].copy()
    missing["Why there is no row above"]=missing["Disclosure found"].map({
        "mention only":"in the corpus and mentions the standard, but states no effect",
        "none in corpus":"never appears in the 10-K/10-Q corpus (acquired, delisted, or "
                         "never filed in the window) - the corpus cannot speak to it"})

    gt=ir[["ticker","irish_transfer_year","irish_transfer_date_as_printed","transferor_name",
           "counterparty_as_printed","destination_group","irish_evidence_confidence",
           "match_status","irish_source_cite"]].copy()
    gt.columns=["Ticker","Irish transfer year","Date as printed","Transferor",
                "Counterparty as printed","Destination group","Evidence confidence",
                "Match status","Source cite"]

    # ---- GOAL 2, stated as narrowly as it can be stated.
    # The Irish statutory accounts are the ground truth for where the IP went. These are
    # the DI firms whose Irish accounts point at the UNITED STATES; the question is
    # whether the 10-K route independently confirms it.
    g2=firms[firms["Irish destination (verified)"].astype(str).str.contains("United States")][
        ["Ticker","Company name","CIK","Irish transfer year (verified)",
         "Irish destination (verified)","Irish evidence confidence","Disclosure found",
         "Filings with an anchor hit","FIRST DISCLOSURE DATE","QUOTE FROM 10-K",
         "Headline tax effect","Destination stated","Into the US? (us_verdict)",
         "Transfer year read from filing"]].copy()
    g2["Does the 10-K confirm the US destination?"]=[
        ("YES" if u=="yes" else
         ("NO - the filing route says NOT into the US" if u=="no" else
          ("cannot tell - firm never appears in the corpus" if d=="none in corpus" else
           "cannot tell - the filing states no destination")))
        for u,d in zip(g2["Into the US? (us_verdict)"],g2["Disclosure found"])]

    money={"Headline tax effect",*[n for _,n in ITEMS]}
    wid={"QUOTE FROM 10-K":95,"Company name":30,"Counterparty as printed":40,
         "Transferor":34,"Source cite":46,"Why there is no row above":54,
         "10-K agrees with Irish year":18,"Irish destination (verified)":20}

    with pd.ExcelWriter(OUT,engine="openpyxl") as xw:
        pd.DataFrame({"A":[""]}).to_excel(xw,sheet_name="Read me",index=False)
        for nm,df,t,note in [
          ("DI firms",firms,"Every Double Irish firm, disclosure or not",
           f"{len(firms)} firms: the union of the three DI lists in this folder (ex21 flag 72, "
           f"di_firm_years 77, verified-Irish-date bridge 43). Membership columns let any one "
           f"list be cut back out. {(firms['Disclosure found']=='effect').sum()} state an effect; "
           f"the rest are kept because ABSENCE IN A 10-K IS NEVER EVIDENCE OF ABSENCE."),
          ("Disclosures",disc,"Every effect filing by a Double Irish firm",
           f"{len(disc)} filings, {disc.CIK.nunique()} firms. One row per filing. Every figure "
           f"is a TAX EFFECT, never the value of the IP -- the two are never reconciled."),
          ("No disclosure found",missing,"The DI firms the corpus does not speak for",
           f"{len(missing)} of {len(firms)}. Blank is not a zero. Disclosure is required only "
           f"when material, and a firm absent from the corpus was never searched at all."),
          ("GOAL 2 - into the US",g2,
           "DI firms whose IRISH accounts point at the United States",
           f"{len(g2)} firms. The Irish statutory accounts are the ground truth for the "
           f"destination; this sheet asks whether the 10-K route confirms it independently. "
           f"It confirms {(g2['Does the 10-K confirm the US destination?']=='YES').sum()} of "
           f"{len(g2)}. That is the goal 2 result, and it is a negative one."),
          ("Irish ground truth",gt,"The verified Irish transfer events (read-only)",
           f"{len(gt)} events, {gt.Ticker.nunique()} firms, from the Irish statutory work. "
           f"Nothing is written back to that project. This is the only column set here that "
           f"does not come from the 10-K corpus."),
        ]:
            xw.book.create_sheet(nm); write(xw.book[nm],df,money,t,note,wid)

        ws=xw.book["Read me"]; ws.sheet_view.showGridLines=False
        ws.column_dimensions["A"].width=112
        L=[("ASU 2016-16 - the Double Irish sample",TITLE),
           ("",None),
           ("WHAT THE AMOUNT COLUMNS ARE",Font(name=FONT,bold=True,size=10)),
           ("Every figure is a TAX EFFECT, not the value of the IP. Salesforce carries $24bn of IP "
            "in its Irish accounts against 'a net tax benefit of $2.0 billion'. At 12.5% that is the "
            "right order of magnitude and it is not an identity. The two are never reconciled.",None),
           ("A blank amount means the firm did not state that item, or the corpus stripped the figure. "
            "'Amount source' says which. A blank is never a zero.",None),
           ("",None),
           ("WHY 84 FIRMS AND NOT 72",Font(name=FONT,bold=True,size=10)),
           ("Three DI lists sit in this folder and they disagree: the ex21 double_irish_firm flag has "
            "72, di_firm_years has 77, and the verified-Irish-date bridge has 43. ex21 and di_firm_years "
            "overlap in 72; di_firm_years adds ACOM, BTAX, NPSP, SNDK.1 and UTIW; the bridge adds AON, "
            "BMRN, CGNX, CIK0001557939 (Kinetic Concepts, no ticker), ITG, MNK, NPSP and ORCL. The union "
            "is 84. This workbook carries all 84 with a membership column per list, so nothing is "
            "silently dropped and any single list can be filtered back out. Which list is authoritative "
            "is not this workbook's call.",None),
           ("",None),
           ("ABSENCE IS NOT EVIDENCE OF ABSENCE",Font(name=FONT,bold=True,size=10)),
           ("Disclosure is required only when material. REGN, YELP and INSM say nothing across 28-29 "
            "filings each, and that is not evidence they did not transfer. Every DI firm therefore has "
            "a row whether or not anything was found, and 'Disclosure found' distinguishes an effect "
            "from a mention with no effect from a firm the corpus never contained at all. The 10-K can "
            "confirm a transfer; it can never refute one.",None),
           ("",None),
           ("THE DATES ARE NOT THE SAME DATE",Font(name=FONT,bold=True,size=10)),
           ("The adoption date is not the transfer date. Apple recorded $2.7bn of deferred tax assets "
            "in Q1 2019 for a 2015 transfer. '10-K agrees with Irish year' allows one year either way "
            "and an adoption catch-up landing later is not counted as a disagreement.",None),
           ("",None),
           ("WHAT IS MEASURED, AND WHAT IS NOT",Font(name=FONT,bold=True,size=10)),
           ("Detection - was a filing correctly identified as carrying a transfer disclosure - runs at "
            "81%. Amount extraction is a different measurement and a different number; the two must not "
            "be quoted as one. On the destination question: us_verdict = yes is 59% precise at firm "
            "level (20 of 34 read in full) and caught 6 of 11 US destinations the footnote reader found "
            "(55%), on a favourable subsample. Both halves of that question are weak and the second "
            "number rests on a filtered denominator.",None),
           ("The 'Destination stated' column is NOT reliable and is shown only for provenance: it reads "
            "'United States' on 1,807 filings against 214 for Ireland, because it matches 'U.S. GAAP' "
            "and 'the U.S. statutory rate' in boilerplate. Use 'Into the US? (us_verdict)'.",
            Font(name=FONT,size=10,color="9C0006")),
           ("",None),
           ("KNOWN-WRONG VALUES NOT YET CORRECTED",Font(name=FONT,bold=True,size=10)),
           ("Seagate's $602m is the total of net deferred tax assets EXCLUDING the $2m intra-entity "
            "figure - off by 300x. Intersil's $27.4m is a UTB reserve release, not an ASU 2016-16 "
            "effect. DTS is filed as United States but went outbound. Toro's transfer is of fixed "
            "assets, not IP. None of these are corrected in the underlying data yet.",None)]
        for i,(txt,fnt) in enumerate(L,1):
            c=ws.cell(row=i,column=1,value=txt or None)
            c.font=fnt or BODY; c.alignment=Alignment(wrap_text=True,vertical="top")
            if txt and len(txt)>200: ws.row_dimensions[i].height=int(len(txt)/112*14)+16
    print(f"wrote {OUT.name}")
    print(f"  DI firms {len(firms)}   effect {(firms['Disclosure found']=='effect').sum()}"
          f"   mention only {(firms['Disclosure found']=='mention only').sum()}"
          f"   none in corpus {(firms['Disclosure found']=='none in corpus').sum()}")
    print(f"  disclosures {len(disc)}   irish ground-truth events {len(gt)}")
    print(firms["10-K agrees with Irish year"].value_counts().to_string())
    print("\nGOAL 2 - DI firms whose Irish accounts say United States:")
    print(g2[["Ticker","Does the 10-K confirm the US destination?"]].to_string(index=False))

main()
