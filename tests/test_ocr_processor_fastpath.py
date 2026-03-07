from unittest.mock import MagicMock, patch
import os
import pytest
from pathlib import Path

from ocr_processor import _split_pdf
from config import TEMP_CHUNK_DIR

@patch("pypdf.PdfReader")
@patch("os.makedirs")
def test_split_pdf_fast_path_and_fallback(mock_makedirs, mock_pdf_reader):
    """
    _split_pdf 関数が fast path (テキスト抽出) と fallback (画像ベースOCR) 
    を正しく切り分けるかテストする
    """
    
    # モックの PDF ページを作成
    # ページ1: 正常なテキスト (抽出可能)
    page1 = MagicMock()
    page1.extract_text.return_value = "正常なテキストです。" * 15  # 長さ確保
    
    # ページ2: 文字化け (CID パターン)
    page2 = MagicMock()
    page2.extract_text.return_value = "文字(cid:1234)化け" * 15
    
    # ページ3: 抽出テキストなし
    page3 = MagicMock()
    page3.extract_text.return_value = ""
    
    # PdfReader のモック設定
    mock_reader_instance = MagicMock()
    mock_reader_instance.pages = [page1, page2, page3]
    mock_pdf_reader.return_value = mock_reader_instance
    
    with patch("pypdf.PdfWriter") as mock_pdf_writer, patch("builtins.open", MagicMock()):
        # writer モックの設定
        mock_writer_instance = MagicMock()
        mock_pdf_writer.return_value = mock_writer_instance
        
        # 実行
        chunks = _split_pdf("dummy.pdf", doc_type="general")
        
        # 検証
        # chunks は元のページを反映する。
        # ページ1(p=0) は fast path なので type="text"
        # ページ2,3(p=1,2) は fast path 外れなのでフォールバックしてPDFチャンクになる。
        # そのため、全体のチャンク数は 2つ （テキスト抽出チャンク x 1 + OCR用フォールバックチャンク x 1） になる
        assert len(chunks) == 2
        
        text_chunk = chunks[0]
        assert text_chunk["type"] == "text"
        assert text_chunk["page_count"] == 1
        assert "正常なテキストです。" in text_chunk["extracted_text"]
        
        # ページ2と3はフォールバックされてPDFチャンクになっていること
        pdf_chunk = chunks[1]
        assert pdf_chunk["type"] == "pdf"
        assert pdf_chunk["page_count"] == 2  # 残りの2ページ分がまとまっている想定
        
        # Writer には add_page が ページ2, 3 のために 2回呼ばれたはず
        assert mock_writer_instance.add_page.call_count == 2
