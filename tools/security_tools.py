"""
Security tools for PIN authentication, session management, and rate limiting
"""
from typing import Dict, Any, Optional
from supabase import create_client, Client
import os
import bcrypt

# Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Service role key (bypasses RLS)

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


async def verify_pin_tool(phone: str, pin: str) -> Dict[str, Any]:
    """
    Verify user PIN and create session
    
    Args:
        phone: WhatsApp phone number (e.g., "+905551234567")
        pin: 4-6 digit PIN code
        
    Returns:
        {
            "success": bool,
            "session_token": str | None,
            "message": str,
            "blocked_until": datetime | None
        }
    """
    try:
        # Call Supabase function
        result = supabase.rpc("verify_pin", {
            "p_phone": phone,
            "p_pin": pin
        }).execute()
        
        if result.data and len(result.data) > 0:
            row = result.data[0]
            return {
                "success": row["success"],
                "session_token": row["session_token"],
                "message": row["message"],
                "blocked_until": None  # TODO: Parse from message if blocked
            }
        
        return {
            "success": False,
            "session_token": None,
            "message": "PIN doğrulama başarısız",
            "blocked_until": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "session_token": None,
            "message": f"Hata: {str(e)}",
            "blocked_until": None
        }


async def check_session_tool(phone: str, session_token: str) -> Dict[str, Any]:
    """
    Check if session is still valid
    
    Args:
        phone: WhatsApp phone number
        session_token: Session token from verify_pin
        
    Returns:
        {
            "valid": bool,
            "expires_at": datetime | None,
            "message": str
        }
    """
    try:
        # Call Supabase function
        result = supabase.rpc("is_session_valid", {
            "p_phone": phone,
            "p_session_token": session_token
        }).execute()
        
        is_valid = result.data if isinstance(result.data, bool) else False
        
        if is_valid:
            # Get expiry time
            security_data = supabase.table("user_security") \
                .select("session_expires_at") \
                .eq("phone", phone) \
                .eq("session_token", session_token) \
                .single() \
                .execute()
            
            return {
                "valid": True,
                "expires_at": security_data.data.get("session_expires_at") if security_data.data else None,
                "message": "Session geçerli"
            }
        else:
            return {
                "valid": False,
                "expires_at": None,
                "message": "Session geçersiz veya süresi dolmuş. Lütfen PIN giriniz."
            }
            
    except Exception as e:
        return {
            "valid": False,
            "expires_at": None,
            "message": f"Session kontrol hatası: {str(e)}"
        }


async def check_rate_limit_tool(
    user_id: str,
    phone: str,
    action: str,
    max_allowed: int
) -> Dict[str, Any]:
    """
    Check and increment rate limit for action
    
    Args:
        user_id: User UUID
        phone: WhatsApp phone number
        action: Action type (e.g., "delete_listing", "insert_listing")
        max_allowed: Maximum allowed per day
        
    Returns:
        {
            "allowed": bool,
            "current_count": int,
            "max_allowed": int,
            "resets_at": datetime,
            "message": str
        }
    """
    try:
        result = supabase.rpc("check_rate_limit", {
            "p_user_id": user_id,
            "p_phone": phone,
            "p_action": action,
            "p_max_allowed": max_allowed
        }).execute()
        
        if result.data and len(result.data) > 0:
            row = result.data[0]
            allowed = row["allowed"]
            current = row["current_count"]
            maximum = row["max_allowed"]
            resets = row["resets_at"]
            
            if allowed:
                message = f"İşlem izni verildi ({current}/{maximum})"
            else:
                message = f"Günlük limit aşıldı ({current}/{maximum}). Limit sıfırlanma: {resets}"
            
            return {
                "allowed": allowed,
                "current_count": current,
                "max_allowed": maximum,
                "resets_at": resets,
                "message": message
            }
        
        return {
            "allowed": False,
            "current_count": 0,
            "max_allowed": max_allowed,
            "resets_at": None,
            "message": "Rate limit kontrolü başarısız"
        }
        
    except Exception as e:
        return {
            "allowed": False,
            "current_count": 0,
            "max_allowed": max_allowed,
            "resets_at": None,
            "message": f"Rate limit hatası: {str(e)}"
        }


async def log_audit_tool(
    user_id: str,
    phone: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    response_status: str = "success",
    error_message: Optional[str] = None,
    request_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Log audit event
    
    Args:
        user_id: User UUID
        phone: WhatsApp phone number
        action: Action type (e.g., "delete_listing")
        resource_type: Resource type (e.g., "listing")
        resource_id: Resource UUID (optional)
        response_status: Status (success, failed, unauthorized, rate_limited)
        error_message: Error details (optional)
        request_data: Request payload (optional)
        
    Returns:
        {
            "success": bool,
            "log_id": str,
            "message": str
        }
    """
    try:
        result = supabase.rpc("log_audit", {
            "p_user_id": user_id,
            "p_phone": phone,
            "p_action": action,
            "p_resource_type": resource_type,
            "p_resource_id": resource_id,
            "p_response_status": response_status,
            "p_error_message": error_message,
            "p_request_data": request_data or {}
        }).execute()
        
        log_id = result.data if result.data else None
        
        return {
            "success": bool(log_id),
            "log_id": str(log_id) if log_id else None,
            "message": "Audit log kaydedildi" if log_id else "Audit log kaydedilemedi"
        }
        
    except Exception as e:
        return {
            "success": False,
            "log_id": None,
            "message": f"Audit log hatası: {str(e)}"
        }


async def register_user_pin_tool(
    user_id: str,
    phone: str,
    pin: str
) -> Dict[str, Any]:
    """
    Register new user with PIN (first-time setup)
    
    Args:
        user_id: User UUID
        phone: WhatsApp phone number
        pin: 4-6 digit PIN code
        
    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        # Validate PIN length
        if not pin.isdigit() or len(pin) < 4 or len(pin) > 6:
            return {
                "success": False,
                "message": "PIN 4-6 haneli rakamlardan oluşmalıdır"
            }
        
        # Hash PIN with bcrypt
        pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
        
        # Insert into user_security
        result = supabase.table("user_security").insert({
            "user_id": user_id,
            "phone": phone,
            "pin_hash": pin_hash
        }).execute()
        
        if result.data:
            return {
                "success": True,
                "message": "PIN başarıyla kaydedildi. Lütfen PIN'inizi güvenli bir yerde saklayın."
            }
        else:
            return {
                "success": False,
                "message": "PIN kaydedilemedi"
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"PIN kayıt hatası: {str(e)}"
        }


async def get_user_by_phone_tool(phone: str) -> Dict[str, Any]:
    """
    Get user by phone number
    
    Args:
        phone: WhatsApp phone number
        
    Returns:
        {
            "success": bool,
            "user_id": str | None,
            "has_pin": bool,
            "message": str
        }
    """
    try:
        # Check if user exists in users table
        user_result = supabase.table("users") \
            .select("id") \
            .eq("phone", phone) \
            .single() \
            .execute()
        
        if not user_result.data:
            return {
                "success": False,
                "user_id": None,
                "has_pin": False,
                "message": "Kullanıcı bulunamadı"
            }
        
        user_id = user_result.data["id"]
        
        # Check if user has PIN in user_security
        security_result = supabase.table("user_security") \
            .select("id") \
            .eq("phone", phone) \
            .single() \
            .execute()
        
        has_pin = bool(security_result.data)
        
        return {
            "success": True,
            "user_id": user_id,
            "has_pin": has_pin,
            "message": "Kullanıcı bulundu" if has_pin else "PIN tanımlı değil"
        }
        
    except Exception as e:
        return {
            "success": False,
            "user_id": None,
            "has_pin": False,
            "message": f"Kullanıcı sorgu hatası: {str(e)}"
        }
