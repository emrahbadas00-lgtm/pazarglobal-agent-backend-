"""
Admin Tools for PazarGlobal
Admin-only actions: credit management, user moderation, illegal reports

PREMIUM BADGE SYSTEM:
- 🥇 Gold: 50 credits (₺10) - 7 days featured
- 💎 Platinum: 90 credits (₺18) - 14 days featured + search boost
- 💠 Diamond: 150 credits (₺30) - 30 days featured + top 5 guaranteed
"""

import os
from typing import Dict, Any, List
from supabase import create_client, Client
from datetime import datetime


def get_supabase_client() -> Client:
    """Get authenticated Supabase client"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        raise Exception("Supabase credentials not configured")
    
    return create_client(supabase_url, supabase_key)


def admin_add_credits(
    admin_id: str,
    target_user_id: str,
    amount_credits: int,
    reason: str = "Admin adjustment"
) -> Dict[str, Any]:
    """
    Admin adds credits to user wallet
    
    Args:
        admin_id: UUID of admin performing action
        target_user_id: UUID of target user
        amount_credits: Credits to add
        reason: Reason for credit adjustment
        
    Returns:
        Dict with success status
    """
    try:
        supabase = get_supabase_client()
        
        # Check admin privileges (simplified - you should check profiles.role)
        # For now, assume admin check happens before tool call
        
        # Add credits using RPC
        amount_bigint = int(amount_credits * 100)
        supabase.rpc("credit_wallet", {
            "p_user": target_user_id,
            "p_amount_bigint": amount_bigint,
            "p_kind": "admin_adjust",
            "p_reference": admin_id,
            "p_metadata": {"reason": reason}
        }).execute()
        
        # Log admin action
        supabase.table("admin_actions").insert({
            "admin_id": admin_id,
            "action": "add_credits",
            "target_user": target_user_id,
            "details": {
                "amount_credits": amount_credits,
                "reason": reason
            }
        }).execute()
        
        return {
            "success": True,
            "message": f"Added {amount_credits} credits to user",
            "amount_credits": amount_credits,
            "target_user_id": target_user_id
        }
        
    except Exception as e:
        print(f"❌ Admin add credits error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def admin_grant_premium(
    admin_id: str,
    listing_id: str,
    badge_type: str = "gold",
    reason: str = "Admin grant"
) -> Dict[str, Any]:
    """
    Admin grants premium badge to a listing (FREE - for promotions/testing)
    
    Args:
        admin_id: UUID of admin
        listing_id: UUID of listing
        badge_type: Type of badge (gold/platinum/diamond)
        reason: Reason for grant
        
    Returns:
        Dict with success status
    """
    try:
        supabase = get_supabase_client()
        
        # Badge configuration
        BADGE_CONFIG = {
            "gold": {"days": 7, "emoji": "🥇"},
            "platinum": {"days": 14, "emoji": "💎"},
            "diamond": {"days": 30, "emoji": "💠"}
        }
        
        if badge_type not in BADGE_CONFIG:
            return {
                "success": False,
                "error": f"Invalid badge type. Must be: gold, platinum, diamond"
            }
        
        config = BADGE_CONFIG[badge_type]
        
        from datetime import timedelta
        premium_until = datetime.utcnow() + timedelta(days=config["days"])
        
        # Update listing with badge
        supabase.table("listings").update({
            "is_premium": True,
            "premium_until": premium_until.isoformat(),
            "premium_badge": badge_type
        }).eq("id", listing_id).execute()
        
        # Log action
        supabase.table("admin_actions").insert({
            "admin_id": admin_id,
            "action": "grant_premium",
            "target_listing": listing_id,
            "details": {
                "badge_type": badge_type,
                "duration_days": config["days"],
                "reason": reason
            }
        }).execute()
        
        return {
            "success": True,
            "message": f"{config['emoji']} {badge_type.upper()} badge granted for {config['days']} days",
            "listing_id": listing_id,
            "badge_type": badge_type,
            "emoji": config["emoji"],
            "premium_until": premium_until.isoformat()
        }
        
    except Exception as e:
        print(f"❌ Admin grant premium error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def admin_freeze_user(
    admin_id: str,
    target_user_id: str,
    reason: str,
    duration_days: int = None
) -> Dict[str, Any]:
    """
    Admin freezes/bans a user account
    
    Args:
        admin_id: UUID of admin
        target_user_id: UUID of user to freeze
        reason: Reason for freeze
        duration_days: Duration (None = permanent)
        
    Returns:
        Dict with success status
    """
    try:
        supabase = get_supabase_client()
        
        # Update user status (assuming profiles table has is_banned/banned_until)
        update_data: Dict[str, Any] = {
            "is_banned": True,
            "ban_reason": reason
        }
        
        if duration_days:
            from datetime import timedelta
            banned_until = datetime.utcnow() + timedelta(days=duration_days)
            update_data["banned_until"] = banned_until.isoformat()
        
        supabase.table("profiles").update(update_data).eq("id", target_user_id).execute()
        
        # Log action
        supabase.table("admin_actions").insert({
            "admin_id": admin_id,
            "action": "freeze_user",
            "target_user": target_user_id,
            "details": {
                "reason": reason,
                "duration_days": duration_days,
                "permanent": duration_days is None
            }
        }).execute()
        
        return {
            "success": True,
            "message": f"User {'banned permanently' if not duration_days else f'frozen for {duration_days} days'}",
            "target_user_id": target_user_id
        }
        
    except Exception as e:
        print(f"❌ Admin freeze user error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def admin_delete_listing(
    admin_id: str,
    listing_id: str,
    reason: str
) -> Dict[str, Any]:
    """
    Admin deletes a listing
    
    Args:
        admin_id: UUID of admin
        listing_id: UUID of listing to delete
        reason: Reason for deletion
        
    Returns:
        Dict with success status
    """
    try:
        supabase = get_supabase_client()
        
        # Soft delete (set status to deleted)
        supabase.table("listings").update({
            "status": "deleted",
            "deleted_at": datetime.utcnow().isoformat(),
            "deleted_by": admin_id,
            "deleted_reason": reason
        }).eq("id", listing_id).execute()
        
        # Log action
        supabase.table("admin_actions").insert({
            "admin_id": admin_id,
            "action": "delete_listing",
            "target_listing": listing_id,
            "details": {"reason": reason}
        }).execute()
        
        return {
            "success": True,
            "message": "Listing deleted",
            "listing_id": listing_id
        }
        
    except Exception as e:
        print(f"❌ Admin delete listing error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def admin_get_illegal_reports(
    admin_id: str,
    reviewed: bool = False,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get illegal activity reports for admin review
    
    Args:
        admin_id: UUID of admin
        reviewed: Filter by reviewed status
        limit: Max reports to return
        
    Returns:
        Dict with reports list
    """
    try:
        supabase = get_supabase_client()
        
        query = supabase.table("illegal_reports")\
            .select("*, listings(title, user_id), profiles!reporter_user(full_name)")\
            .eq("reviewed", reviewed)\
            .order("created_at", desc=True)\
            .limit(limit)
        
        response = query.execute()
        
        return {
            "success": True,
            "reports": response.data,
            "count": len(response.data)
        }
        
    except Exception as e:
        print(f"❌ Admin get illegal reports error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def admin_review_illegal_report(
    admin_id: str,
    report_id: str,
    action_taken: str
) -> Dict[str, Any]:
    """
    Mark illegal report as reviewed
    
    Args:
        admin_id: UUID of admin
        report_id: UUID of report
        action_taken: Description of action
        
    Returns:
        Dict with success status
    """
    try:
        supabase = get_supabase_client()
        
        # Update report
        supabase.table("illegal_reports").update({
            "reviewed": True,
            "reviewed_by": admin_id,
            "reviewed_at": datetime.utcnow().isoformat()
        }).eq("id", report_id).execute()
        
        # Log action
        supabase.table("admin_actions").insert({
            "admin_id": admin_id,
            "action": "review_illegal_report",
            "details": {
                "report_id": report_id,
                "action_taken": action_taken
            }
        }).execute()
        
        return {
            "success": True,
            "message": "Report reviewed",
            "report_id": report_id
        }
        
    except Exception as e:
        print(f"❌ Admin review report error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# Tool definitions for admin agent
ADMIN_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "admin_add_credits",
            "description": "Admin kullanıcıya manuel kredi ekler",
            "parameters": {
                "type": "object",
                "properties": {
                    "admin_id": {"type": "string"},
                    "target_user_id": {"type": "string"},
                    "amount_credits": {"type": "integer"},
                    "reason": {"type": "string"}
                },
                "required": ["admin_id", "target_user_id", "amount_credits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "admin_freeze_user",
            "description": "Admin kullanıcı hesabını dondurur/banlar",
            "parameters": {
                "type": "object",
                "properties": {
                    "admin_id": {"type": "string"},
                    "target_user_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "duration_days": {"type": "integer", "description": "null = kalıcı ban"}
                },
                "required": ["admin_id", "target_user_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "admin_delete_listing",
            "description": "Admin ilanı siler",
            "parameters": {
                "type": "object",
                "properties": {
                    "admin_id": {"type": "string"},
                    "listing_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["admin_id", "listing_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "admin_get_illegal_reports",
            "description": "İllegal işlem raporlarını gösterir",
            "parameters": {
                "type": "object",
                "properties": {
                    "admin_id": {"type": "string"},
                    "reviewed": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 50}
                },
                "required": ["admin_id"]
            }
        }
    }
]
