import pytest
import unicodedata
from text_sanitizer import (
    normalize_unicode_text,
    contains_cid_pattern,
    contains_replacement_char,
    combining_ratio,
    detect_garble_reason,
    is_text_extraction_usable
)

def test_normalize_unicode_text():
    # NFD の "ジ" (シ + 濁点) -> NFC の "ジ"
    nfd_zi = "シ\u3099" 
    nfc_zi = "ジ"
    
    assert nfd_zi != nfc_zi
    
    # NFD が NFC に変換されること
    normalized = normalize_unicode_text(nfd_zi)
    assert normalized == nfc_zi
    assert unicodedata.normalize("NFC", nfd_zi) == normalized

    # "ナレッジベース" (NFD)
    nfd_knowledge = "ナレッシ\u3099ヘ\u3099ース"
    assert normalize_unicode_text(nfd_knowledge) == "ナレッジベース"

    # None や 空文字の処理
    assert normalize_unicode_text(None) is None
    assert normalize_unicode_text("") == ""

def test_contains_cid_pattern():
    assert contains_cid_pattern("テスト(cid:7743)文字列") is True
    assert contains_cid_pattern("進(cid:7743)を status_manager に都度報告") is True
    assert contains_cid_pattern("テスト(cid:)文字列") is False
    assert contains_cid_pattern("テストcid:1234文字列") is False
    assert contains_cid_pattern("正常な文字列") is False
    assert contains_cid_pattern(None) is False

def test_contains_replacement_char():
    assert contains_replacement_char("これは\ufffdです") is True
    assert contains_replacement_char("正常な文字列") is False
    assert contains_replacement_char(None) is False

def test_combining_ratio():
    # 正常な文字列
    normal_text = "これは正常な文字列です"
    assert combining_ratio(normal_text) == 0.0
    
    # 結合文字を含む文字列
    combining_text = "ア\u3099イ\u309Aウ"
    # len("ア\u3099イ\u309Aウ") は文字数評価により結合文字も1文字としてカウントされるため 5文字
    # 結合文字は 2 つあるため ratio は 2 / 5 = 0.4
    assert combining_ratio(combining_text) == 0.4
    
    # 空白文字列
    assert combining_ratio("   ") == 0.0

def test_detect_garble_reason_and_usable():
    # 1. 正常な日本語テキスト (閾値 80 文字以上にしてテスト)
    normal_text = "これは正常なPDF本文です。構造設計の基本事項を示します。" * 10
    assert detect_garble_reason(normal_text) == ""
    assert is_text_extraction_usable(normal_text) is True
    
    # 2. 短すぎるテキスト
    short_text = "文字数が足りない"
    assert detect_garble_reason(short_text) == "too_short"
    assert is_text_extraction_usable(short_text) is False
    
    # 3. CID を含む
    cid_text = normal_text + "(cid:1234)"
    assert detect_garble_reason(cid_text) == "cid_pattern"
    assert is_text_extraction_usable(cid_text) is False
    
    # 4. Replacement char を含む
    rep_text = normal_text + "文字化け\ufffd"
    assert detect_garble_reason(rep_text) == "replacement_char"
    assert is_text_extraction_usable(rep_text) is False
    
    # 5. Combining ratio が高すぎる
    # ほぼすべての文字が結合文字という異常な状況を作る
    high_combining = ("a\u0301" * 50) + normal_text
    assert detect_garble_reason(high_combining) == "high_combining_ratio"
    assert is_text_extraction_usable(high_combining) is False
