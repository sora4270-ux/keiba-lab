"""Small, incremental sniff for UTF-8 vs legacy cp932 odds CSVs.

ZIP CSV samples can end in the middle of a multibyte UTF-8 codepoint.
Decoding such a sample with final=True incorrectly treats valid UTF-8 as
broken and falls back to cp932, making all Japanese labels mojibake.
"""
import codecs


def detect_odds_csv_encoding(sample: bytes) -> str:
    if not isinstance(sample, bytes):
        raise TypeError("sample must be bytes")
    decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
    try:
        decoder.decode(sample, final=False)
    except UnicodeDecodeError:
        return "cp932"
    return "utf-8-sig"
