from typing import Dict, Any, Optional
import json

def get_project_profile(user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    # Retrieve from DB using ProjectProfile table
    from database import get_session, ProjectProfile
    with get_session() as session:
        profile = session.query(ProjectProfile).filter(ProjectProfile.project_id == project_id, ProjectProfile.user_id == user_id).first()
        if not profile:
            return {"phase": "", "order_type": "", "client": "", "objective": "", "key_constraints": "", "current_issues": ""}
        return {
            "phase": profile.phase,
            "order_type": profile.order_type,
            "client": profile.client,
            "objective": profile.objective,
            "key_constraints": profile.key_constraints,
            "current_priority": profile.current_priority,
            "current_issues": profile.current_issues,
            "rag_notes": profile.rag_notes
        }

def get_or_generate_project_core_view(user_id: str, project_id: str, registry_info: Dict[str, Any], profile_info: Dict[str, Any]) -> str:
    parts = []
    if registry_info.get("name"): parts.append(f"【プロジェクト名】: {registry_info['name']}")
    if registry_info.get("building_type"): parts.append(f"【建物用途】: {registry_info['building_type']}")
    if profile_info.get("phase"): parts.append(f"【フェーズ】: {profile_info['phase']}")
    if profile_info.get("order_type"): parts.append(f"【発注方式】: {profile_info['order_type']}")
    if profile_info.get("client"): parts.append(f"【事業主】: {profile_info['client']}")
    if profile_info.get("objective"): parts.append(f"【主目的】: {profile_info['objective']}")
    if profile_info.get("key_constraints"): parts.append(f"【主要制約条件】: {profile_info['key_constraints']}")
    if profile_info.get("current_priority"): parts.append(f"【現在の優先事項】: {profile_info['current_priority']}")
    
    return "\n".join(parts)

def retrieve_project_memories(user_id: str, project_id: str, query: str, limit: int = 6) -> list:
    from database import get_project_memories
    memories = get_project_memories(project_id, limit=20)
    return [
        {
            "id": f"pc_{m.id}",
            "content": m.content,
            "type": m.type,
            "keywords": m.trigger_keywords
        }
        for m in memories
    ]

def compact_project_memories(query: str, memories: list, max_tokens: int = 220) -> str:
    if not memories:
        return ""
        
    from gemini_client import get_client
    from config import GEMINI_MODEL_RAG
    import json
    import logging
    
    client = get_client()
    mem_json = json.dumps(memories, ensure_ascii=False)
    
    prompt = f"""
以下の「プロジェクトに関する過去のコンテキスト」の中から、現在の質問「{query}」に関連するものを抽出し、
LLMへのシステムプロンプトとして役立つような要約を作成してください。

【過去のコンテキスト】
{mem_json}

【ルール】
- 質問に関連しない情報は大胆に削ってください。
- 関連性が高いものはそのまま残すか、箇条書きで簡潔にまとめてください。
- ユーザーに直接話しかけるようなトーンではなく、システム指示の文体（例：「・〇〇に注意すること」など）にしてください。
- 情報量に合わせて{max_tokens}文字程度に収めてください。
- もし関連する情報が全くない場合は「関連プロジェクトコンテキストなし」とだけ出力してください。
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL_RAG, contents=prompt)
        text = response.text.strip()
        if "関連プロジェクトコンテキストなし" in text:
            return ""
        return "【プロジェクト固有の決定事項・知見 (Active)】\n" + text
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Error compacting project memories: {e}")
        # fallback
        parts = [f"・{m['content']}" for m in memories[:5]]
        return "【プロジェクト固有の決定事項・知見 (Active)】\n" + "\n".join(parts)

def retrieve_cross_project_lessons(user_id: str, project_id: str, query: str, limit: int = 2) -> list:
    from database import get_global_lessons
    lessons = get_global_lessons(exclude_project_tag=project_id, limit=limit * 5)
    return [
        {
            "id": f"pc_{m.id}",
            "content": m.content,
            "project_tag": m.project_tag
        }
        for m in lessons
    ]

def compact_cross_project_lessons(query: str, lessons: list, max_tokens: int = 100) -> str:
    if not lessons:
        return ""
        
    from gemini_client import get_client
    from config import GEMINI_MODEL_RAG
    import json
    import logging
    
    client = get_client()
    les_json = json.dumps(lessons, ensure_ascii=False)
    
    prompt = f"""
以下の「別プロジェクトでの教訓」の中から、現在の質問「{query}」に役立つ教訓を1〜2個抽出し、簡潔にまとめてください。

【他プロジェクトの教訓】
{les_json}

【ルール】
- 質問に関連しない教訓は無視してください。
- 役立つものがあれば、「他プロジェクトからの参考教訓」として短く箇条書きで示してください。
- {max_tokens}文字程度に収めてください。
- もし関連する情報が全くない場合は「関連教訓なし」とだけ出力してください。
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL_RAG, contents=prompt)
        text = response.text.strip()
        if "関連教訓なし" in text:
            return ""
        return "【他プロジェクトからの参考教訓 (Cross-project)】\n" + text
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Error compacting lessons: {e}")
        parts = [f"・{m['content']} ({m['project_tag']})" for m in lessons[:2]]
        return "【他プロジェクトからの参考教訓 (Cross-project)】\n" + "\n".join(parts)

def estimate_tokens(text: str) -> int:
    return len(text) // 2

def build_project_context_block(user_id: str, project_id: Optional[str], query: str, max_tokens: int = 400) -> Dict[str, Any]:
    if not project_id:
        return {
            "core_view": "",
            "active_view": "",
            "cross_project_lessons": "",
            "used_memory_ids": [],
            "token_estimate": 0,
        }

    from .scope_resolver import get_project_registry
    registry = get_project_registry(project_id)
    if not registry:
        registry = {"id": project_id, "name": f"Project {project_id}"}
        
    profile = get_project_profile(user_id, project_id) or {}
    core_view = get_or_generate_project_core_view(user_id, project_id, registry, profile)

    related = retrieve_project_memories(user_id, project_id, query, limit=6)
    active_view = compact_project_memories(query, related, max_tokens=220)

    lessons = retrieve_cross_project_lessons(user_id, project_id, query, limit=2)
    cross = compact_cross_project_lessons(query, lessons, max_tokens=150)
    used_ids = [m["id"] for m in related] if related else []
    token_estimate = estimate_tokens(core_view + "\n" + active_view + "\n" + cross)

    return {
        "core_view": core_view,
        "active_view": active_view,
        "cross_project_lessons": cross,
        "used_memory_ids": used_ids,
        "token_estimate": token_estimate,
    }
