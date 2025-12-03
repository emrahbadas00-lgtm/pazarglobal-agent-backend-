"""
Delete a listing from Supabase
"""
import os
import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

async def delete_listing(listing_id: str) -> dict:
    """
    Delete a listing from Supabase by listing_id.
    
    Args:
        listing_id: UUID of the listing to delete
    
    Returns:
        dict with:
            - success: bool
            - status_code: int (HTTP status)
            - message: confirmation message (if success)
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
        "Prefer": "return=representation"
    }
    
    url = f"{SUPABASE_URL}/rest/v1/listings"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Supabase delete with filter: DELETE /listings?id=eq.{listing_id}
            response = await client.delete(
                f"{url}?id=eq.{listing_id}",
                headers=headers
            )
            
            if response.status_code in [200, 204]:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "message": f"Listing {listing_id} deleted successfully"
                }
            elif response.status_code == 404:
                return {
                    "success": False,
                    "status_code": 404,
                    "error": f"Listing {listing_id} not found"
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
