import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_jockey_links import parse_result

URL="https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_babaCode=24&k_raceDate=2026%2F11%2F24&k_raceNo=2"
HEADER="<table><tr><th>着順</th><th>馬番</th><th>馬名</th><th>騎手</th></tr>"
ROW='<tr><td>1</td><td>5</td><td>テスト馬</td><td><a href="/KeibaWeb/DataRoom/RiderMark?k_riderLicenseNo=12345">試験騎</a> (愛知)</td></tr>'

class JockeyLinkTests(unittest.TestCase):
    def test_exact_row(self):
        x,d=parse_result(HEADER+ROW+"</table>",URL,{5:("テスト馬",("試験騎","愛知"))})
        self.assertEqual(x[5]["license_no"],"12345")
        self.assertEqual(d["recognized_tables"],1)
    def test_reject_wrong_horse_affiliation_or_domain(self):
        for html,expected in [(HEADER+ROW+"</table>",{5:("別馬",("試験騎","愛知"))}),
                              (HEADER+ROW+"</table>",{5:("テスト馬",("試験騎","浦和"))}),
                              (HEADER+ROW.replace('href="/','href="https://example.com/')+"</table>",{5:("テスト馬",("試験騎","愛知"))}),
                              ("<table>"+ROW+"</table>",{5:("テスト馬",("試験騎","愛知"))})]:
            self.assertEqual(parse_result(html,URL,expected)[0],{})
    def test_duplicate_rows_rejected(self):
        self.assertEqual(parse_result(HEADER+ROW+ROW+"</table>",URL,{5:("テスト馬",("試験騎","愛知"))})[0],{})

if __name__=="__main__":
    unittest.main()
