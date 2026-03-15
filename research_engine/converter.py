"""
research_engine/converter.py

PDF → Markdown、HTML → Markdown の変換モジュール。
変換失敗時は例外をraiseせず False を返す。
"""
import logging
import os

logger = logging.getLogger(__name__)


def convert_pdf(raw_path: str, output_path: str) -> bool:
    """
    marker-pdf を使ってPDFをMarkdownに変換する。
    失敗時は False を返す（例外をraiseしない）。
    """
    try:
        from marker.convert import convert_single_pdf
        from marker.models import load_all_models

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        model_lst = load_all_models()
        full_text, _, _ = convert_single_pdf(raw_path, model_lst)
        if not full_text:
            return False
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        return True
    except Exception as e:
        logger.warning(f"convert_pdf failed [{raw_path}]: {e}")
        return False


def convert_html(html_content: str, output_path: str, url: str = "") -> bool:
    """
    trafilatura を使ってHTMLをMarkdownに変換する。
    変換結果が空の場合も False を返す。
    """
    try:
        import trafilatura

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result = trafilatura.extract(
            html_content,
            include_tables=True,
            include_links=False,
            output_format="markdown",
            url=url or None,
        )
        if not result:
            return False
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
        return True
    except Exception as e:
        logger.warning(f"convert_html failed [{url}]: {e}")
        return False
