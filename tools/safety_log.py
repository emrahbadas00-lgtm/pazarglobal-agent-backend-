"""
Safety logging helper for vision flags (no auto-ban)
"""
from typing import Optional, Dict, Any
import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Lazy client creation to avoid errors if env missing
_supabase: Optional[Client] = None


def _get_client() -> Client:
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase


def log_image_safety_flag(
    *,
    user_id: Optional[str],
    image_url: Optional[str],
    flag_type: str,
    confidence: str,
    message: str,
    status: str = "pending",
    notes: Optional[str] = None,
    reviewer: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert a safety flag row for admin review. Blocking is handled in workflow logic.
    """
    data: Dict[str, Any] = {
        "user_id": user_id,
        "image_url": image_url,
        "flag_type": flag_type,
        "confidence": confidence,
        "message": message,
        "status": status,
        "notes": notes,
        "reviewer": reviewer,
    }
    try:
        client = _get_client()
        result = client.table("image_safety_flags").insert(data).execute()
        return {"success": True, "result": result.data}
    except Exception as exc:  # pragma: no cover
        return {"success": False, "error": str(exc), "data": data}
