from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

def get_setting(key: str) -> Optional[str]:
    # TODO: Implement actual settings DB fetch in P2/P3.
    # For P1, we can return None or a mock if needed, but we will wire this up properly later.
    from database import get_db, Settings
    try:
        db = next(get_db())
        setting = db.query(Settings).filter(Settings.key == key).first()
        return setting.value if setting else None
    except Exception as e:
        logger.warning(f"Failed to get setting {key}: {e}")
        return None

def get_project_registry(project_id: str) -> Optional[Dict[str, Any]]:
    # TODO: Fetch from mindmap projects table in P2
    # Mocking for P1
    return {"id": project_id, "name": f"Project {project_id}"}


def infer_project_from_attachments_or_query(question: str, attachments: Optional[List[dict]]) -> Optional[Dict[str, Any]]:
    from database import get_session, ProjectProfile
    try:
        with get_session() as session:
            # P3: Very basic exact-match inference against profiled projects
            profiles = session.query(ProjectProfile).all()
            for p in profiles:
                if p.project_id in question:
                    return {
                        "project_id": p.project_id,
                        "source": "inferred",
                        "confidence": 0.9,
                        "project_name": p.project_id
                    }
    except Exception as e:
        logger.warning(f"Error inferring project: {e}")
    return None

def resolve_scope(user_id: str, question: str, project_id: Optional[str] = None, scope_mode: str = "auto", attachments: Optional[List[dict]] = None) -> Dict[str, Any]:
    """
    Returns the resolved scope for the chat.
    {
      "scope_type": "project" | "global",
      "scope_id": "abc123" | None,
      "project_id": "abc123" | None,
      "source": "explicit" | "attachment" | "inferred" | "active_setting" | "global_fallback",
      "confidence": 0.0,
      "project_name": "..."
    }
    """
    if scope_mode == "global":
        return {
            "scope_type": "global",
            "scope_id": None,
            "project_id": None,
            "source": "global_mode",
            "confidence": 1.0,
            "project_name": None,
        }

    if project_id and scope_mode == "explicit":
        p = get_project_registry(project_id)
        return {
            "scope_type": "project",
            "scope_id": project_id,
            "project_id": project_id,
            "source": "explicit",
            "confidence": 1.0,
            "project_name": p["name"] if p else None,
        }
        
    if project_id and scope_mode == "auto":
        p = get_project_registry(project_id)
        return {
            "scope_type": "project",
            "scope_id": project_id,
            "project_id": project_id,
            "source": "explicit", # Even in auto, if ID is provided, it's explicit for this request
            "confidence": 1.0,
            "project_name": p["name"] if p else None,
        }

    inferred = infer_project_from_attachments_or_query(question, attachments)
    if inferred and inferred.get("confidence", 0) >= 0.85:
        return {
            "scope_type": "project",
            "scope_id": inferred["project_id"],
            "project_id": inferred["project_id"],
            "source": inferred["source"],
            "confidence": inferred["confidence"],
            "project_name": inferred.get("project_name"),
        }

    active_project_id = get_setting("active_project_id")
    if active_project_id:
        p = get_project_registry(active_project_id)
        return {
            "scope_type": "project",
            "scope_id": active_project_id,
            "project_id": active_project_id,
            "source": "active_setting",
            "confidence": 0.60,
            "project_name": p["name"] if p else None,
        }

    return {
        "scope_type": "global",
        "scope_id": None,
        "project_id": None,
        "source": "global_fallback",
        "confidence": 1.0,
        "project_name": None,
    }
