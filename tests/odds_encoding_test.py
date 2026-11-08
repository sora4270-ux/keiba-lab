"""Regression: NAR official UTF-8 CSV cut mid-character at 4096 bytes."""
import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from odds_encoding import detect_odds_csv_encoding
from update_nar import odds_market_index
from trio_strategy import trio_odds_index


def make_archive():
    header = "競馬場,競走年月日,レース番号,賭式,番号1,番号2,番号3,オッズ,オッズ（最大）,人気,備考\n"
    first = "佐賀,20261108,1,単勝,2,,,3.4,,1,"
    prefix = ("\ufeff" + header + first).encode("utf-8")
    padding = 4095 - len(prefix)
    assert padding >= 0
    data = prefix + b"X" * padding + "あ\n佐賀,20261108,1,３連複,1,2,3,18.2,,4,\n".encode("utf-8")
    assert data[4095] == 0xE3 and data[4096] == 0x81
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("20261108_odds.csv", data)
    return output.getvalue(), data


class OddsEncodingTest(unittest.TestCase):
    def test_utf8_sample_ends_inside_character(self):
        _, data = make_archive()
        with self.assertRaises(UnicodeDecodeError):
            data[:4096].decode("utf-8-sig")
        self.assertEqual(detect_odds_csv_encoding(data[:4096]), "utf-8-sig")

    def test_legacy_cp932_remains_supported(self):
        self.assertEqual(detect_odds_csv_encoding("競馬場,賭式".encode("cp932")), "cp932")

    def test_win_and_trio_read_4096_byte_split(self):
        archive, _ = make_archive()
        win = odds_market_index(archive)
        self.assertEqual(win[("佐賀", "20261108", 1)][2]["odds"], 3.4)
        trio = trio_odds_index(archive)
        self.assertEqual(trio[("佐賀", "20261108", 1)][(1, 2, 3)], 18.2)


if __name__ == "__main__":
    unittest.main()
