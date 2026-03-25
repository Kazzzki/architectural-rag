"""
audio_transcriber.py - 音声ファイルの文字起こし + Markdown生成サービス

音声ファイルを10分セグメントに分割し、Geminiで文字起こしした後、
Markdown形式で保存する。meeting_sessions/meeting_chunks にも連携する。

既存の audio_indexer._split_audio() を再利用してセグメント分割を行う。
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from google.genai import types

import config
from audio_indexer import _split_audio, _get_duration
from gemini_client import get_client

logger = logging.getLogger(__name__)

TRANSCRIPTION_PROMPT = (
    "この音声を日本語でそのまま文字起こしてください。\n"
    "会議・ミーティングの録音です。\n"
    "以下のルールに従ってください:\n"
    "- 句読点をつけて自然な日本語にする\n"
    "- 話者が変わったと判断できる場合は改行して「話者A:」「話者B:」のように区別する\n"
    "- 話者が判別できない場合は区別しなくてよい\n"
    "- 余計な説明・補足・翻訳は不要。文字起こし結果のテキストのみ返す\n"
)


@dataclass
class TranscriptionResult:
    """文字起こし処理の結果"""
    md_path: str            # 生成されたMarkdownファイルパス
    full_text: str          # 全文テキスト
    segment_count: int      # 処理したセグメント数
    session_id: Optional[int] = None  # meeting_sessions の ID


def _format_time(seconds: float) -> str:
    """秒数を HH:MM:SS 形式に変換する"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class AudioTranscriber:
    """
    音声ファイルを10分セグメントに分割して文字起こしし、
    Markdown形式で保存するサービス。
    """

    def __init__(self):
        self.segment_sec = config.AUDIO_TRANSCRIPTION_SEGMENT_SEC

    async def transcribe_file(
        self,
        file_path: str,
        source_pdf_hash: str,
        version_id: str,
        project_id: Optional[str] = None,
        original_filename: str = "",
    ) -> TranscriptionResult:
        """
        音声ファイルを文字起こしし、Markdownを生成する。

        1. 10分セグメントに分割
        2. 各セグメントをGeminiで文字起こし
        3. Markdown連結 + frontmatter付きで保存
        4. meeting_sessions / meeting_chunks に保存

        Returns:
            TranscriptionResult
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        orig_name = original_filename or path.name

        logger.info(f"[AudioTranscriber] Starting transcription: {orig_name}")

        # 1. 音声の長さ取得
        duration = await asyncio.to_thread(_get_duration, file_path)
        duration = duration or 0.0

        # 2. セグメント分割（10分単位）
        segments = await asyncio.to_thread(
            _split_audio, file_path, ext, self.segment_sec
        )
        if not segments:
            logger.warning(f"[AudioTranscriber] No segments generated for {orig_name}")
            return TranscriptionResult(md_path="", full_text="", segment_count=0)

        logger.info(
            f"[AudioTranscriber] {orig_name}: {len(segments)} segments "
            f"(duration={duration:.0f}s, segment_sec={self.segment_sec})"
        )

        # 3. 各セグメントを文字起こし
        transcripts: list[tuple[float, float, str]] = []
        for idx, (start_sec, end_sec, chunk_bytes) in enumerate(segments):
            try:
                text = await self._transcribe_segment(chunk_bytes, idx, len(segments))
                transcripts.append((start_sec, end_sec, text))
                logger.info(
                    f"[AudioTranscriber] Segment {idx+1}/{len(segments)} done "
                    f"({_format_time(start_sec)}-{_format_time(end_sec)}): "
                    f"{len(text)} chars"
                )
            except Exception as e:
                logger.error(
                    f"[AudioTranscriber] Segment {idx+1} failed "
                    f"({_format_time(start_sec)}-{_format_time(end_sec)}): {e}"
                )
                transcripts.append((start_sec, end_sec, f"（文字起こしエラー: {e}）"))

        # 4. Markdown生成
        full_text = "\n\n".join(t for _, _, t in transcripts if t)
        md_content = self._build_markdown(
            transcripts=transcripts,
            source_pdf_hash=source_pdf_hash,
            version_id=version_id,
            project_id=project_id,
            original_filename=orig_name,
            duration_sec=duration,
        )

        # 5. Markdownファイル保存
        transcripts_dir = config.TRANSCRIPTS_DIR
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        stem = path.stem
        md_filename = f"{stem}_{version_id[:8]}.md"
        md_path = transcripts_dir / md_filename
        md_path.write_text(md_content, encoding="utf-8")
        logger.info(f"[AudioTranscriber] Markdown saved: {md_path}")

        # 6. meeting_sessions / meeting_chunks に保存
        session_id = await asyncio.to_thread(
            self._save_to_meetings,
            transcripts=transcripts,
            project_id=project_id,
            version_id=version_id,
            source_pdf_hash=source_pdf_hash,
            original_filename=orig_name,
            file_path=file_path,
            full_text=full_text,
        )

        return TranscriptionResult(
            md_path=str(md_path),
            full_text=full_text,
            segment_count=len(transcripts),
            session_id=session_id,
        )

    async def _transcribe_segment(
        self, audio_bytes: bytes, idx: int, total: int
    ) -> str:
        """単一の音声セグメントをGeminiで文字起こしする"""
        client = get_client()

        def _call():
            response = client.models.generate_content(
                model=config.GEMINI_MODEL_TRANSCRIPTION,
                contents=[
                    types.Part(
                        inline_data=types.Blob(
                            mime_type="audio/wav", data=audio_bytes
                        )
                    ),
                    types.Part(text=TRANSCRIPTION_PROMPT),
                ],
            )
            return (response.text or "").strip()

        return await asyncio.to_thread(_call)

    def _build_markdown(
        self,
        transcripts: list[tuple[float, float, str]],
        source_pdf_hash: str,
        version_id: str,
        project_id: Optional[str],
        original_filename: str,
        duration_sec: float,
    ) -> str:
        """YAML frontmatter付きMarkdownを生成する"""
        now_iso = datetime.now(timezone.utc).isoformat()
        lines = [
            "---",
            f"source_pdf_hash: {source_pdf_hash}",
            f"version_id: {version_id}",
            f"project_id: {project_id or ''}",
            f"source_type: audio_transcript",
            f"original_filename: {original_filename}",
            f"duration_sec: {int(duration_sec)}",
            f"transcribed_at: {now_iso}",
            "---",
            "",
            f"# 会議文字起こし: {original_filename}",
            "",
        ]

        for start_sec, end_sec, text in transcripts:
            start_str = _format_time(start_sec)
            end_str = _format_time(end_sec)
            lines.append(f"## [{start_str} - {end_str}]")
            lines.append("")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def _save_to_meetings(
        self,
        transcripts: list[tuple[float, float, str]],
        project_id: Optional[str],
        version_id: str,
        source_pdf_hash: str,
        original_filename: str,
        file_path: str,
        full_text: str,
    ) -> Optional[int]:
        """meeting_sessions / meeting_chunks テーブルに保存する"""
        try:
            from database import get_session
            from sqlalchemy import text

            with get_session() as db:
                now = datetime.now(timezone.utc).isoformat()

                # meeting_session 作成
                result = db.execute(
                    text("""
                        INSERT INTO meeting_sessions
                            (project_name, title, participants, created_at, updated_at,
                             project_id, version_id, source_pdf_hash, audio_file_path)
                        VALUES
                            (:project_name, :title, :participants, :created_at, :updated_at,
                             :project_id, :version_id, :source_pdf_hash, :audio_file_path)
                    """),
                    {
                        "project_name": project_id or "",
                        "title": f"文字起こし: {original_filename}",
                        "participants": "",
                        "created_at": now,
                        "updated_at": now,
                        "project_id": project_id or "",
                        "version_id": version_id,
                        "source_pdf_hash": source_pdf_hash,
                        "audio_file_path": file_path,
                    },
                )
                session_id = result.lastrowid

                # meeting_chunks 保存
                for idx, (start_sec, end_sec, transcript) in enumerate(transcripts):
                    db.execute(
                        text("""
                            INSERT INTO meeting_chunks
                                (session_id, chunk_index, transcript, created_at)
                            VALUES
                                (:session_id, :chunk_index, :transcript, :created_at)
                        """),
                        {
                            "session_id": session_id,
                            "chunk_index": idx,
                            "transcript": transcript,
                            "created_at": now,
                        },
                    )

                db.commit()
                logger.info(
                    f"[AudioTranscriber] Saved meeting session {session_id} "
                    f"with {len(transcripts)} chunks"
                )
                return session_id

        except Exception as e:
            logger.error(f"[AudioTranscriber] Failed to save to meetings: {e}", exc_info=True)
            return None
