import re
import unicodedata
from typing import Optional

from config import OCR_TEXT_FASTPATH_MIN_CHARS, OCR_GARBLED_MAX_COMBINING_RATIO

def normalize_unicode_text(text: Optional[str]) -> Optional[str]:
    """
    文字列を Unicode NFC で正規化する。
    None や空文字の場合は安全にそのまま返す。
    """
    if not text:
        return text
        
    try:
        return unicodedata.normalize("NFC", text)
    except Exception:
        # 万が一の例外時も処理全体を止めず元テキストを返すよう fallback
        return text

def contains_cid_pattern(text: str) -> bool:
    """'(cid:xxxx)' のような文字化けパターンを含むか判定する"""
    if not text:
        return False
    return bool(re.search(r"\(cid:\d+\)", text))

def contains_replacement_char(text: str) -> bool:
    """Unicode の replacement character '\\ufffd' を含むか判定する"""
    if not text:
        return False
    return "\ufffd" in text

def combining_ratio(text: str) -> float:
    """テキスト全体の文字数に対する結合文字（combining character）の割合を計算する"""
    if not text:
        return 0.0
        
    # strip してから判定（空白のみの文字列などのゼロ除算を防止するため、max(len, 1) を使用）
    stripped = text.strip()
    if not stripped:
        return 0.0
        
    combining_count = sum(1 for ch in stripped if unicodedata.combining(ch))
    ratio = combining_count / max(len(stripped), 1)
    return ratio

def detect_garble_reason(text: str) -> str:
    """
    文字化けや抽出不良の原因を特定する。
    問題がなければ空文字 "" を返す。
    """
    if not text:
        return "too_short"
        
    # NFD結合文字を数えるため正規化前に判定する
    if combining_ratio(text) > OCR_GARBLED_MAX_COMBINING_RATIO:
        return "high_combining_ratio"
        
    normalized = normalize_unicode_text(text)
    
    if len(normalized.strip()) < OCR_TEXT_FASTPATH_MIN_CHARS:
        return "too_short"
        
    if contains_cid_pattern(normalized):
        return "cid_pattern"
        
    if contains_replacement_char(normalized):
        return "replacement_char"
        
    return ""

def is_text_extraction_usable(text: str) -> bool:
    """
    抽出されたテキストが fast path で採用可能（品質が良いか）を判定する。
    """
    reason = detect_garble_reason(text)
    # 理由が空であれば usable
    return not bool(reason)
