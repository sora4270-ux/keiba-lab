"""Validate manually documented exact-run official jockey profile links.

Do not infer a stable identity from abbreviations, affiliation, or current
profile alone. This module neither downloads pages nor modifies predictions.
"""
from urllib.parse import urlsplit, parse_qs
from datetime import date
import re
import unicodedata

VENUES = {"名古屋":"24","浦和":"18","水沢":"11","盛岡":"10","大井":"20",
          "川崎":"21","船橋":"19","笠松":"23","金沢":"22","園田":"27",
          "姫路":"28","高知":"31","佐賀":"32","門別":"36","帯広ば":"3"}


def norm(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def official_params(url, path):
    u = urlsplit(url)
    if u.scheme != "https" or u.netloc != "www.keiba.go.jp" or u.path != path or u.fragment:
        raise ValueError("invalid official evidence URL")
    return parse_qs(u.query, strict_parsing=True)


def evidence_index(items):
    if not isinstance(items,list):
        raise ValueError("jockey evidence must be a list")
    result = {}
    for r in items:
        day=date.fromisoformat(r["date"])
        venue=r["venue"]
        race,no=r["race_no"],r["no"]
        ident=r["license_no"]
        if (venue not in VENUES or type(race) is not int or not 1<=race<=20
                or type(no) is not int or not 1<=no<=30
                or not isinstance(ident,str) or not re.fullmatch(r"[0-9]{5,8}",ident)
                or not norm(r["abbreviation"]) or not norm(r["affiliation"])):
            raise ValueError("invalid jockey evidence fields")
        q=official_params(r["result_source"],"/KeibaWeb/TodayRaceInfo/RaceMarkTable")
        if (q.get("k_babaCode") != [VENUES[venue]] or q.get("k_raceNo") != [str(race)]
                or q.get("k_raceDate") != [day.strftime("%Y/%m/%d")]):
            raise ValueError("race evidence URL mismatch")
        q=official_params(r["profile_source"],"/KeibaWeb/DataRoom/RiderMark")
        if q.get("k_riderLicenseNo") != [ident]:
            raise ValueError("profile ID mismatch")
        key=(venue,day.strftime("%Y%m%d"),race,no)
        if key in result:
            raise ValueError("duplicate jockey evidence")
        result[key]=r
    return result


def matched_id(index, race_key, no, candidate):
    evidence=index.get((*race_key,no))
    if evidence is None:
        return None
    if not candidate or tuple(map(norm,candidate)) != (norm(evidence["abbreviation"]),norm(evidence["affiliation"])):
        return None
    return evidence["license_no"]
