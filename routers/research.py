"""
routers/research.py

技術リサーチ自動化システムの REST API エンドポイント。
バックグラウンドで run_research_pipeline を実行する。
"""
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from database import (
    create_research_job,
    update_research_job,
    get_research_job,
    list_research_jobs,
    add_research_source,
    get_research_sources,
    delete_research_job,
)

logger = logging.getLogger(__name__)

RESEARCH_VAULT_PATH = os.getenv("RESEARCH_VAULT_PATH", "./research_vault")

router = APIRouter(tags=["Research"])


# ===== Pydantic モデル =====

class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    mode: str = Field(default="auto", pattern="^(auto|manual)$")


# ===== バックグラウンドパイプライン =====

async def run_research_pipeline(research_id: str, question: str, mode: str) -> None:
    """
    リサーチの全フェーズを順次実行する。
    例外が発生した場合は status='error' に更新してプロセスを落とさない。
    """
    from research_engine.planner import generate_plan
    from research_engine.collector import collect_sources
    from research_engine.summarizer import summarize_source
    from research_engine.synthesizer import synthesize_report
    from research_engine.embedder import embed_research

    try:
        # Step 1: ディレクトリ作成
        update_research_job(
            research_id,
            status="phase1_planning",
            phase_current=1,
            phase_name="プランニング",
            progress_percent=5,
        )
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")
        Path(RESEARCH_VAULT_PATH).mkdir(parents=True, exist_ok=True)
        (Path(RESEARCH_VAULT_PATH) / "raw" / month_str / research_id).mkdir(parents=True, exist_ok=True)
        (Path(RESEARCH_VAULT_PATH) / "markdown" / month_str / research_id).mkdir(parents=True, exist_ok=True)

        # Step 2: プラン生成（4人格ディスカッション: Phase1→Phase2→Phase3）
        update_research_job(
            research_id,
            detail="法務・技術・メーカー・施工CM の4人格が個別にリサーチ観点を分析中...",
            progress_percent=8,
        )
        plan = await generate_plan(question)
        update_research_job(research_id, progress_percent=20)

        # Step 3: プランをDB保存
        update_research_job(
            research_id,
            plan_json=json.dumps(plan, ensure_ascii=False),
            progress_percent=25,
        )

        if mode == "manual":
            update_research_job(research_id, status="plan_ready")
            return

        # Step 4: ソース収集
        update_research_job(
            research_id,
            status="phase2_collecting",
            phase_current=2,
            phase_name="ソース収集",
        )

        collected_errors: list[str] = []

        def progress_callback(progress: int, detail: str, sources_found: int) -> None:
            update_research_job(
                research_id,
                progress_percent=progress,
                detail=detail,
                sources_found=sources_found,
            )

        raw_sources = await collect_sources(plan, research_id, progress_callback)

        # Step 5: 各ソースを要約
        sources_with_summary = []
        for s in raw_sources:
            md_path = s.get("markdown_path", "")
            md_content = ""
            if md_path:
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        md_content = f.read()
                except Exception:
                    pass
            summary = await summarize_source(md_content, s.get("category", ""), s.get("url", ""))
            sources_with_summary.append({**s, "summary": summary})

        update_research_job(research_id, progress_percent=65)

        # Step 6: ソースをDBに保存
        for s in sources_with_summary:
            try:
                add_research_source(research_id, s)
            except Exception as e:
                logger.warning(f"add_research_source failed: {e}")
                collected_errors.append(str(e))

        update_research_job(
            research_id,
            progress_percent=70,
            sources_found=len(sources_with_summary),
        )

        # Step 7: 統合レポート生成
        update_research_job(
            research_id,
            status="phase3_synthesis",
            phase_current=3,
            phase_name="レポート生成",
            progress_percent=75,
        )
        report_markdown, summary = await synthesize_report(question, sources_with_summary, plan)

        # Step 8: ChromaDB 格納
        await embed_research(research_id, sources_with_summary, report_markdown, question)
        update_research_job(research_id, progress_percent=90)

        # Step 9: レポートをDB保存
        domain = plan.get("domain", "general")
        update_research_job(
            research_id,
            report_markdown=report_markdown,
            summary=summary,
            domain=domain,
            progress_percent=95,
        )

        # Step 10: 完了
        update_research_job(
            research_id,
            status="completed",
            phase_current=4,
            phase_name="完了",
            progress_percent=100,
            completed_at=datetime.now(timezone.utc),
            errors=json.dumps(collected_errors, ensure_ascii=False),
        )
        logger.info(f"Research pipeline completed: {research_id}")

    except Exception as e:
        logger.exception(f"Research pipeline error [{research_id}]: {e}")
        update_research_job(
            research_id,
            status="error",
            errors=json.dumps([str(e)], ensure_ascii=False),
        )


# ===== エンドポイント =====

@router.post("/api/research", status_code=202)
async def submit_research(body: ResearchRequest, background_tasks: BackgroundTasks):
    """リサーチジョブを投入する（即時 202 返却）"""
    research_id = create_research_job(body.question, body.mode)
    background_tasks.add_task(run_research_pipeline, research_id, body.question, body.mode)
    return {
        "research_id": research_id,
        "status": "accepted",
        "estimated_minutes": 25,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/research")
async def list_research(status: str = "all", limit: int = 20, offset: int = 0):
    """ジョブ一覧を返す"""
    jobs = list_research_jobs(status=status, limit=limit, offset=offset)
    # フロントエンドが research_id を期待しているため id → research_id にマップ
    items = [
        {
            "research_id": j["id"],
            "question": j["question"],
            "mode": j["mode"],
            "status": j["status"],
            "phase_current": j["phase_current"],
            "phase_total": j["phase_total"],
            "phase_name": j["phase_name"],
            "progress_percent": j["progress_percent"],
            "detail": j["detail"],
            "sources_found": j["sources_found"],
            "domain": j["domain"],
            "summary": j["summary"],
            "created_at": j["created_at"],
            "updated_at": j["updated_at"],
            "completed_at": j["completed_at"],
        }
        for j in jobs
    ]
    return {"items": items, "total": len(items)}


@router.get("/api/research/{research_id}/status")
async def get_research_status(research_id: str):
    """ステータスと進捗を返す"""
    job = get_research_job(research_id)
    if job is None:
        raise HTTPException(status_code=404, detail="research job not found")
    plan = None
    if job.get("plan_json"):
        try:
            plan = json.loads(job["plan_json"])
        except Exception:
            plan = None
    return {
        "research_id": job["id"],
        "status": job["status"],
        "phase": {
            "current": job["phase_current"],
            "total": job["phase_total"],
            "name": job["phase_name"],
        },
        "progress_percent": job["progress_percent"],
        "detail": job["detail"],
        "sources_found": job["sources_found"],
        "started_at": job["created_at"],
        "updated_at": job["updated_at"],
        "plan": plan,
    }


@router.get("/api/research/{research_id}/report")
async def get_research_report(research_id: str):
    """完了済みレポートを返す。未完了は 409 Conflict"""
    job = get_research_job(research_id)
    if job is None:
        raise HTTPException(status_code=404, detail="research job not found")
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail={"detail": "report not ready", "status": job["status"]},
        )
    sources = get_research_sources(research_id)
    plan = None
    if job.get("plan_json"):
        try:
            plan = json.loads(job["plan_json"])
        except Exception:
            plan = None
    return {
        "research_id": job["id"],
        "question": job["question"],
        "domain": job["domain"],
        "summary": job["summary"],
        "report_markdown": job["report_markdown"],
        "sources": sources,
        "plan": plan,
        "completed_at": job["completed_at"],
    }


@router.delete("/api/research/{research_id}")
async def remove_research(research_id: str):
    """ジョブとファイルを削除する"""
    job = get_research_job(research_id)
    if job is None:
        raise HTTPException(status_code=404, detail="research job not found")

    # ChromaDB から削除
    try:
        from dense_indexer import get_chroma_client
        chroma = get_chroma_client()
        for col_name in ("research_sources", "research_reports"):
            try:
                col = chroma.get_collection(col_name)
                col.delete(where={"research_id": research_id})
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"ChromaDB delete failed [{research_id}]: {e}")

    # ファイル削除
    month_candidates = list(Path(RESEARCH_VAULT_PATH).glob(f"raw/*/{research_id}"))
    month_candidates += list(Path(RESEARCH_VAULT_PATH).glob(f"markdown/*/{research_id}"))
    for p in month_candidates:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    delete_research_job(research_id)
    return {"deleted": research_id}
