"""Conservative official result-page status extraction for retrospective audits."""
from html.parser import HTMLParser
import re
import time
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

VENUES = {"帯広ば":3, "帯広":3, "門別":36, "盛岡":10, "水沢":11, "浦和":18,
          "船橋":19, "大井":20, "川崎":21, "金沢":22, "笠松":23, "名古屋":24,
          "園田":27, "姫路":28, "高知":31, "佐賀":32}
STATUS = {"取消":"withdrawn","出走取消":"withdrawn","除外":"excluded",
          "競走除外":"excluded","中止":"did_not_finish","競走中止":"did_not_finish"}


def norm(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tables = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append({"rows":[], "row":None, "cell":None})
        if not self.stack:
            return
        t = self.stack[-1]
        if tag == "tr":
            t["row"] = []
        elif tag in ("td","th") and t["row"] is not None:
            t["cell"] = []

    def handle_data(self, data):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"].append(data)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ("td","th") and t["cell"] is not None:
            if t["row"] is not None:
                t["row"].append(norm("".join(t["cell"])))
            t["cell"] = None
        elif tag == "tr" and t["row"] is not None:
            t["rows"].append(t["row"])
            t["row"] = None
        elif tag == "table":
            self.tables.append(t["rows"])
            self.stack.pop()


def parse_statuses(html, wanted):
    """Only rows of a recognizable results table; reject conflicting labels."""
    p = Tables()
    p.feed(html)
    found = {}
    conflicts = set()
    for table in p.tables:
        header = next((row for row in table if len(row) >= 4 and
                       row[:4] == ["着順","枠番","馬番","馬名"]), None)
        if header is None:
            continue
        for row in table[table.index(header)+1:]:
            if len(row) < 4 or not row[2].isdigit():
                continue
            no = int(row[2])
            if no not in wanted:
                continue
            # Some pages display a non-finisher in the time cell, with blank rank.
            label = STATUS.get(row[0])
            if not label and not row[0]:
                labels = {STATUS[c] for c in row[4:] if c in STATUS}
                if len(labels) == 1:
                    label = labels.pop()
            if not label:
                continue
            if no in found and found[no] != label:
                conflicts.add(no)
            found[no] = label
    return {n:v for n,v in found.items() if n not in conflicts}


class OfficialStatusLookup:
    def __init__(self, limit=12):
        self.remaining = limit
        self.blocked = False
        self.cache = {}

    def __call__(self, venue, day, race_no, wanted):
        code = VENUES.get(venue)
        if not code or type(race_no) is not int or not 1 <= race_no <= 20:
            return {}, "unsupported_race"
        url = "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?" + urlencode(
            {"k_babaCode":code, "k_raceDate":day.replace("-","/"), "k_raceNo":race_no})
        if url not in self.cache:
            if self.blocked or self.remaining <= 0:
                return {}, "request_limit_or_blocked"
            self.remaining -= 1
            time.sleep(1)
            try:
                with urlopen(Request(url, headers={"User-Agent":"KEIBA-LAB/3.3 (personal results audit)"}), timeout=12) as r:
                    if r.geturl().split("?")[0] != url.split("?")[0]:
                        return {}, "unexpected_redirect"
                    data = r.read(2*1024*1024+1)
                    if len(data) > 2*1024*1024:
                        return {}, "response_too_large"
                    encoding = r.headers.get_content_charset() or "utf-8"
                    try:
                        html = data.decode(encoding)
                    except UnicodeError:
                        html = data.decode("cp932")
                self.cache[url] = html
            except HTTPError as exc:
                if exc.code in (403,429):
                    self.blocked = True
                return {}, "http_" + str(exc.code)
            except (OSError, ValueError, UnicodeError):
                return {}, "fetch_failed"
        parsed = parse_statuses(self.cache[url], wanted)
        return {n:{"status":v,"source":url} for n,v in parsed.items()}, (
            "matched" if parsed else "no_explicit_status")
