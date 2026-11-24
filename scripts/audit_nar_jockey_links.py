#!/usr/bin/env python3
"""Bounded, read-only probe of exact race-row jockey profile links."""
import argparse
from collections import Counter, defaultdict
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from nar_jockey_evidence import VENUES, norm, official_params
from update_nar import load_zip_tables, row_key, cell, as_int
from audit_nar_context_history import provisional_jockey_key

BASE = "https://www.keiba.go.jp"
RESULT = "/KeibaWeb/TodayRaceInfo/RaceMarkTable"
PROFILE = "/KeibaWeb/DataRoom/RiderMark"


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tables = []
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append({"rows":[],"row":None,"cell":None})
        if not self.stack:
            return
        t = self.stack[-1]
        if tag == "tr":
            t["row"] = []
        elif tag in ("td","th") and t["row"] is not None:
            t["cell"] = {"text":[],"links":[]}
        elif tag == "a" and t["cell"] is not None:
            href = dict(attrs).get("href")
            if href:
                t["cell"]["links"].append(href)
    def handle_data(self, data):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["text"].append(data)
    def handle_endtag(self, tag):
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ("td","th") and t["cell"] is not None:
            if t["row"] is not None:
                c=t["cell"]
                t["row"].append((norm("".join(c["text"])),c["links"]))
            t["cell"]=None
        elif tag=="tr" and t["row"] is not None:
            t["rows"].append(t["row"])
            t["row"]=None
        elif tag=="table":
            self.tables.append(t["rows"])
            self.stack.pop()


def parse_result(html, url, expected):
    """Require recognizable table, exact horse name/number and exact jockey cell."""
    parser=Rows()
    parser.feed(html)
    found=defaultdict(list)
    diagnostics=Counter()
    for table in parser.tables:
        header=next((i for i,row in enumerate(table)
                     if {"馬番","馬名"}.issubset({c[0] for c in row})
                     and any("騎手" in c[0] for c in row)),None)
        if header is None:
            continue
        diagnostics["recognized_tables"]+=1
        for row in table[header+1:]:
            for i,(name,_) in enumerate(row):
                if i==0 or not row[i-1][0].isdigit():
                    continue
                no=int(row[i-1][0])
                target=expected.get(no)
                if not target or name!=norm(target[0]):
                    continue
                diagnostics["horse_row_matches"]+=1
                jockey, affiliation=map(norm,target[1])
                ids=[]
                for text,links in row:
                    if text not in {jockey+"("+affiliation+")",jockey+affiliation}:
                        continue
                    for href in links:
                        link=urljoin(url,href)
                        try:
                            params=official_params(link,PROFILE)
                        except ValueError:
                            continue
                        values=params.get("k_riderLicenseNo",[])
                        if len(values)==1 and re.fullmatch(r"[0-9]{5,8}",values[0]):
                            ids.append((values[0],link))
                if len(set(ids))==1:
                    found[no].append(ids[0])
                else:
                    diagnostics["unmatched_jockey_cell"]+=1
    return {no:{"license_no":v[0][0],"profile_source":v[0][1]}
            for no,v in found.items() if len(v)==1},dict(diagnostics)


def probe(tables, limit=3):
    if not 1<=limit<=3:
        raise ValueError("limit must be 1–3")
    groups=defaultdict(list)
    for item in tables.get("horselist",[]):
        k=row_key(item,())
        if k and k[0] in VENUES:
            groups[k].append(item)
    keys=sorted(groups,key=lambda k:(k[1],k[0],k[2]),reverse=True)
    # Include the documented reference race if available; no broad crawl.
    anchor=("名古屋","20261124",2)
    if anchor in groups:
        keys.remove(anchor)
        keys.insert(0,anchor)
    results=[]
    for k in keys[:limit]:
        venue,day,race=k
        expected={}
        duplicate=set()
        for raw,fields in groups[k]:
            no=as_int(cell(raw,fields,"馬番",idx=5))
            name=cell(raw,fields,"馬名",idx=6)
            candidate=provisional_jockey_key(raw,fields)
            rank=as_int(cell(raw,fields,"着順",idx=31))
            if no is None or not 1<=no<=30 or not name or not candidate or not rank or not 1<=rank<=30:
                continue
            if no in expected:
                duplicate.add(no)
            expected[no]=(name,candidate)
        for n in duplicate:
            expected.pop(n,None)
        url=BASE+RESULT+"?"+urlencode({"k_babaCode":VENUES[venue],"k_raceDate":day[:4]+"/"+day[4:6]+"/"+day[6:],"k_raceNo":race})
        entry={"venue":venue,"date":day,"race_no":race,"source":url,"expected_rows":len(expected)}
        results.append(entry)
        if not expected:
            entry["status"]="no_completed_rows"
            continue
        time.sleep(1)
        try:
            with urlopen(Request(url,headers={"User-Agent":"KEIBA-LAB/3.3 (bounded result audit)"}),timeout=12) as response:
                # Validate the final URL, including exact race parameters.
                if official_params(response.geturl(),RESULT)!=official_params(url,RESULT):
                    entry["status"]="unexpected_redirect"
                    continue
                raw=response.read(2*1024*1024+1)
                if len(raw)>2*1024*1024:
                    entry["status"]="too_large"
                    continue
                try:
                    html=raw.decode(response.headers.get_content_charset() or "utf-8")
                except UnicodeError:
                    html=raw.decode("cp932")
            matches,diag=parse_result(html,url,expected)
            entry.update(status="matched" if matches else "no_verified_matches",
                         matched_rows=len(matches),diagnostics=diag,
                         reference_row_matches=(matches.get(5,{}).get("license_no")=="31333") if k==anchor else None)
        except HTTPError as exc:
            entry["status"]="http_"+str(exc.code)
            if exc.code in (403,429):
                break
        except (OSError,ValueError,UnicodeError):
            entry["status"]="fetch_or_parse_failed"
    return {"status":"bounded_retrospective_probe","requested_limit":limit,
            "sample":results,"matched_rows":sum(r.get("matched_rows",0) for r in results),
            "notes":["Only a small sample is checked. No IDs are propagated to other races or production data.",
                     "No pre-race identity availability or full-history coverage is established."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("nar-jockey-link-probe.json"))
    a=p.parse_args()
    report=probe(load_zip_tables(a.zip.read_bytes()))
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
