"""
List all listings for a specific user
"""
import os
import httpx
from typing import Optional

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

async def list_user_listings(
    user_id: str,
    status: Optional[str] = None,
    limit: int = 50
) -> dict:
    """
    List all listings belonging to a specific user.
    
    Args:
        user_id: User identifier (phone number or UUID)
        status: Optional filter by status: 'draft', 'active', 'sold', 'inactive'
        limit: Maximum number of listings to return (default: 50)
    
    Returns:
        dict with:
            - success: bool
            - status_code: int
            - listings: list of listing objects (if success)
            - count: number of listings found
            - error: error message (if failed)
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {
            "success": False,
            "status_code": 500,
            "error": "SUPABASE_URL or SUPABASE_SERVICE_KEY not configured"
        }
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    
    url = f"{SUPABASE_URL}/rest/v1/listings"
    
    # Build query params
    params = {
        "user_id": f"eq.{user_id}",
        "limit": limit,
        "order": "created_at.desc"
    }
    
    if status:
        params["status"] = f"eq.{status}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                listings = response.json()
                return {
                    "success": True,
                    "status_code": 200,
                    "listings": listings,
                    "count": len(listings)
                }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": f"Supabase error: {response.text}"
                }
                
    except httpx.ConnectError as e:
        return {
            "success": False,
            "status_code": 503,
            "error": f"Connection error: {str(e)}"
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "status_code": 504,
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "status_code": 500,
            "error": f"Unexpected error: {str(e)}"
        }
