"""
Wallet Management Tools for PazarGlobal Agent
Handles credit balance, transactions, and premium features

PRICING MODEL (1 credit = ₺0.20):
- Base listing: 25kr (₺5) - 30 days active
- AI assistant: +10kr (₺2)
- AI photo analysis: +5kr per photo (₺1)
- AI price suggestion: +3kr (₺0.60)
- AI description expansion: +2kr (₺0.40)
- Manual edit: +2kr (₺0.40)
- AI edit: +5kr (₺1)
- Renewal: +5kr (₺1) - extends 30 days

PREMIUM BADGES (added after listing creation):
- Gold: +50kr (₺10) - 7 days featured
- Platinum: +90kr (₺18) - 14 days featured + search boost
- Diamond: +150kr (₺30) - 30 days featured + top 5 guaranteed
"""

import os
from typing import Dict, Any
from supabase import create_client, Client
from datetime import datetime, timedelta


def get_supabase_client() -> Client:
    """Get authenticated Supabase client"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        raise Exception("Supabase credentials not configured")
    
    return create_client(supabase_url, supabase_key)


def get_wallet_balance(user_id: str) -> Dict[str, Any]:
    """
    Get user's current wallet balance
    
    Args:
        user_id: UUID of the user
        
    Returns:
        Dict with balance_credits, balance_try, currency
    """
    try:
        supabase = get_supabase_client()
        
        # Get wallet or create if not exists
        response = supabase.table("wallets").select("*").eq("user_id", user_id).execute()
        
        if not response.data:
            # Create wallet for new user
            supabase.table("wallets").insert({
                "user_id": user_id,
                "balance_bigint": 0,
                "currency": "TRY"
            }).execute()
            
            return {
                "success": True,
                "balance_credits": 0,
                "balance_try": 0.0,
                "currency": "TRY"
            }
        
        wallet = response.data[0]
        balance_bigint = wallet.get("balance_bigint", 0)
        
        # Convert bigint (1 credit = 100 units) to credits
        balance_credits = balance_bigint / 100
        balance_try = balance_credits * 0.20  # 1 credit = ₺0.20
        
        return {
            "success": True,
            "balance_credits": balance_credits,
            "balance_try": balance_try,
            "currency": wallet.get("currency", "TRY"),
            "updated_at": wallet.get("updated_at")
        }
        
    except Exception as e:
        print(f"❌ Error getting wallet balance: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def deduct_credits(
    user_id: str,
    amount_credits: int,
    action: str,
    reference: str = None
) -> Dict[str, Any]:
    """
    Deduct credits from user wallet
    
    Args:
        user_id: UUID of the user
        amount_credits: Number of credits to deduct
        action: Action type (e.g., 'listing_publish', 'premium_upgrade')
        reference: Optional reference ID (listing_id, etc.)
        
    Returns:
        Dict with success status and new balance
    """
    try:
        supabase = get_supabase_client()
        
        # Get current balance
        balance_result = get_wallet_balance(user_id)
        if not balance_result["success"]:
            return balance_result
        
        current_credits = balance_result["balance_credits"]
        
        # Check sufficient balance
        if current_credits < amount_credits:
            return {
                "success": False,
                "error": f"Insufficient credits. Need {amount_credits}, have {current_credits}",
                "required_credits": amount_credits,
                "available_credits": current_credits
            }
        
        # Deduct credits (convert to bigint: negative for deduction)
        amount_bigint = -1 * int(amount_credits * 100)
        
        # Use RPC function for atomic transaction
        supabase.rpc("credit_wallet", {
            "p_user": user_id,
            "p_amount_bigint": amount_bigint,
            "p_kind": "purchase",
            "p_reference": reference,
            "p_metadata": {"action": action}
        }).execute()
        
        # Get new balance
        new_balance = get_wallet_balance(user_id)
        
        return {
            "success": True,
            "message": f"Deducted {amount_credits} credits for {action}",
            "amount_credits": amount_credits,
            "new_balance_credits": new_balance["balance_credits"],
            "action": action
        }
        
    except Exception as e:
        print(f"❌ Error deducting credits: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def add_premium_to_listing(
    user_id: str,
    listing_id: str,
    badge_type: str = "gold"
) -> Dict[str, Any]:
    """
    Add premium badge to a listing (deducts credits from user wallet)
    
    Args:
        user_id: UUID of the user (for credit deduction)
        listing_id: UUID of the listing
        badge_type: Premium badge type ('gold', 'platinum', 'diamond')
        
    Returns:
        Dict with success status
    """
    # Define badge configurations
    BADGE_CONFIG = {
        "gold": {"credits": 50, "days": 7, "emoji": "🥇"},
        "platinum": {"credits": 90, "days": 14, "emoji": "💎"},
        "diamond": {"credits": 150, "days": 30, "emoji": "💠"}
    }
    
    try:
        if badge_type not in BADGE_CONFIG:
            return {
                "success": False,
                "error": f"Invalid badge type. Must be: gold, platinum, or diamond"
            }
        
        config = BADGE_CONFIG[badge_type]
        
        # Deduct credits first
        deduct_result = deduct_credits(
            user_id=user_id,
            amount_credits=config["credits"],
            action=f"premium_{badge_type}",
            reference=listing_id
        )
        
        if not deduct_result["success"]:
            return deduct_result
        
        supabase = get_supabase_client()
        
        # Calculate premium expiry
        premium_until = datetime.utcnow() + timedelta(days=config["days"])
        
        # Update listing with badge
        response = supabase.table("listings").update({
            "is_premium": True,
            "premium_until": premium_until.isoformat(),
            "premium_badge": badge_type
        }).eq("id", listing_id).execute()
        
        if not response.data:
            return {
                "success": False,
                "error": "Listing not found or update failed"
            }
        
        return {
            "success": True,
            "message": f"{config['emoji']} {badge_type.upper()} Premium activated for {config['days']} days",
            "listing_id": listing_id,
            "badge_type": badge_type,
            "premium_until": premium_until.isoformat(),
            "credits_deducted": config["credits"],
            "new_balance_credits": deduct_result["new_balance_credits"]
        }
        
    except Exception as e:
        print(f"❌ Error adding premium: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def get_transaction_history(
    user_id: str,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Get user's wallet transaction history
    
    Args:
        user_id: UUID of the user
        limit: Max number of transactions to return
        
    Returns:
        Dict with transaction list
    """
    try:
        supabase = get_supabase_client()
        
        response = supabase.table("wallet_transactions")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        transactions = []
        for tx in response.data:
            amount_bigint = tx.get("amount_bigint", 0)
            amount_credits = amount_bigint / 100
            
            transactions.append({
                "id": tx.get("id"),
                "amount_credits": amount_credits,
                "amount_try": amount_credits * 0.20,
                "kind": tx.get("kind"),
                "reference": tx.get("reference"),
                "metadata": tx.get("metadata"),
                "created_at": tx.get("created_at")
            })
        
        return {
            "success": True,
            "transactions": transactions,
            "count": len(transactions)
        }
        
    except Exception as e:
        print(f"❌ Error getting transaction history: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def calculate_listing_cost(
    use_ai_assistant: bool = False,
    photo_count: int = 0,
    use_ai_photos: bool = False,
    use_price_suggestion: bool = False,
    use_description_expansion: bool = False
) -> Dict[str, Any]:
    """
    Calculate total credits needed to publish a listing
    
    Args:
        use_ai_assistant: Whether AI assistant is used (WhatsApp/Chat)
        photo_count: Number of photos
        use_ai_photos: Whether AI photo analysis is used
        use_price_suggestion: Whether AI price suggestion is used
        use_description_expansion: Whether AI description expansion is used
        
    Returns:
        Dict with cost breakdown
    """
    # Base cost (mandatory)
    base_cost = 25  # ₺5
    
    # Optional services
    ai_assistant = 10 if use_ai_assistant else 0  # ₺2
    photo_analysis = (5 * photo_count) if (use_ai_photos and photo_count > 0) else 0  # ₺1/photo
    price_suggestion = 3 if use_price_suggestion else 0  # ₺0.60
    description_expansion = 2 if use_description_expansion else 0  # ₺0.40
    
    total_credits = base_cost + ai_assistant + photo_analysis + price_suggestion + description_expansion
    total_try = total_credits * 0.20
    
    return {
        "success": True,
        "breakdown": {
            "base": base_cost,
            "ai_assistant": ai_assistant,
            "photo_analysis": photo_analysis,
            "price_suggestion": price_suggestion,
            "description_expansion": description_expansion
        },
        "total_credits": total_credits,
        "total_try": total_try,
        "listing_duration_days": 30
    }


def renew_listing(
    user_id: str,
    listing_id: str
) -> Dict[str, Any]:
    """
    Renew a listing for 30 more days (costs 5 credits)
    
    Args:
        user_id: UUID of the user
        listing_id: UUID of the listing to renew
        
    Returns:
        Dict with success status
    """
    try:
        # Deduct renewal cost
        deduct_result = deduct_credits(
            user_id=user_id,
            amount_credits=5,  # ₺1
            action="listing_renewal",
            reference=listing_id
        )
        
        if not deduct_result["success"]:
            return deduct_result
        
        supabase = get_supabase_client()
        
        # Get current expiry
        listing = supabase.table("listings").select("expires_at").eq("id", listing_id).execute()
        
        if not listing.data:
            return {
                "success": False,
                "error": "Listing not found"
            }
        
        current_expires = listing.data[0].get("expires_at")
        
        # Extend by 30 days from current expiry or now
        if current_expires:
            from dateutil import parser
            base_date = parser.parse(current_expires)
        else:
            base_date = datetime.utcnow()
        
        new_expires = base_date + timedelta(days=30)
        
        # Update listing
        response = supabase.table("listings").update({
            "expires_at": new_expires.isoformat()
        }).eq("id", listing_id).execute()
        
        return {
            "success": True,
            "message": "Listing renewed for 30 more days",
            "listing_id": listing_id,
            "expires_at": new_expires.isoformat(),
            "credits_deducted": 5,
            "new_balance_credits": deduct_result["new_balance_credits"]
        }
        
    except Exception as e:
        print(f"❌ Error renewing listing: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# Tool definition for agent
WALLET_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_wallet_balance",
            "description": "Kullanıcının cüzdan bakiyesini gösterir (kredi ve TL cinsinden)",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Kullanıcının UUID'si"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction_history",
            "description": "Kullanıcının cüzdan işlem geçmişini gösterir",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Kullanıcının UUID'si"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maksimum işlem sayısı (varsayılan 20)",
                        "default": 20
                    }
                },
                "required": ["user_id"]
            }
        }
    }
]
