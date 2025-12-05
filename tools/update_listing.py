"""
Update an existing listing in Supabase
"""
import os
import httpx
from typing import Optional, List
from .suggest_category import suggest_category

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

async def update_listing(
    listing_id: str,
    user_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",  # For RLS validation (future)
    title: Optional[str] = None,
    price: Optional[int] = None,
    condition: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    stock: Optional[int] = None,
    status: Optional[str] = None,
    metadata: Optional[dict] = None,
    images: Optional[List[str]] = None,
) -> dict:
    """
    Update an existing listing in Supabase by listing_id.
    Only provided fields will be updated (partial update).
    
    Args:
        listing_id: UUID of the listing to update
        user_id: Kullanıcı UUID (RLS validation için, WhatsApp phase'de aktif olacak)
        title: Updated title (optional)
        price: Updated price in TL (optional)
        condition: Updated condition: 'yeni', 'sıfır', 'az kullanılmış', 'kullanılmış' (optional)
        category: Updated category: 'elektronik', 'ev', 'moda', 'spor', etc. (optional)
        description: Updated description (optional)
        location: Updated location (optional)
        stock: Updated stock quantity (optional)
        status: Updated status: 'draft', 'active', 'sold', 'inactive' (optional)
        metadata: JSONB metadata (type, brand, model, year, etc.) (optional)
        images: Supabase storage paths list (overwrite with provided list)
    
    Returns:
        dict with:
            - success: bool
            - status_code: int (HTTP status)
            - result: updated listing object (if success)
            - error: error message (if failed)
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {
            "success": False,
            "status_code": 500,
            "error": "SUPABASE_URL or SUPABASE_SERVICE_KEY not configured"
        }
    
    # Build payload with only provided fields
    payload = {}
    if title is not None:
        payload["title"] = title
    if price is not None:
        payload["price"] = price
    if condition is not None:
        payload["condition"] = condition
    if category is not None:
        payload["category"] = category
    if description is not None:
        payload["description"] = description
    if location is not None:
        payload["location"] = location
    if stock is not None:
        payload["stock"] = stock
    if status is not None:
        payload["status"] = status
    if metadata is not None:
        payload["metadata"] = metadata
    if images is not None:
        payload["images"] = images
    
    if not payload:
        return {
            "success": False,
            "status_code": 400,
            "error": "No fields provided to update"
        }
    
    # 🤖 AI-POWERED CATEGORY VALIDATION (if category is being updated)
    if category is not None:
        # Get current listing to validate against title/description
        # If title/description also being updated, use new values
        validation_title = title  # Will be None if not being updated
        validation_description = description  # Will be None if not being updated
        
        # If we're updating category but not title/description, we need to fetch current values
        if validation_title is None or validation_description is None:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    fetch_resp = await client.get(
                        f"{SUPABASE_URL}/rest/v1/listings?id=eq.{listing_id}&select=title,description",
                        headers={
                            "apikey": SUPABASE_KEY,
                            "Authorization": f"Bearer {SUPABASE_KEY}"
                        }
                    )
                    if fetch_resp.is_success and fetch_resp.json():
                        current = fetch_resp.json()[0]
                        validation_title = validation_title or current.get("title")
                        validation_description = validation_description or current.get("description")
            except Exception as e:
                print(f"⚠️ Could not fetch current listing for validation: {e}")
        
        # Validate category
        if validation_title:
            print(f"🔍 Validating category update: {category}")
            suggestion = await suggest_category(validation_title, validation_description, category)
            if suggestion["success"] and not suggestion.get("is_correct", True):
                original_category = category
                category = suggestion["suggested_category"]
                payload["category"] = category
                print(f"⚠️ Category mismatch detected during update!")
                print(f"   User selected: {original_category}")
                print(f"   AI suggests: {category} (confidence: {suggestion['confidence']})")
                print(f"   Auto-correcting to: {category}")
                
                # Store correction info in metadata
                if metadata is None:
                    metadata = payload.get("metadata", {})
                if metadata:
                    metadata["original_category"] = original_category
                    metadata["category_corrected"] = True
                    payload["metadata"] = metadata
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    url = f"{SUPABASE_URL}/rest/v1/listings"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Supabase update with filter: PATCH /listings?id=eq.{listing_id}
            response = await client.patch(
                f"{url}?id=eq.{listing_id}",
                json=payload,
                headers=headers
            )
            
            if response.status_code in [200, 201, 204]:
                result = response.json() if response.text else {"listing_id": listing_id}
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "result": result if result else {"listing_id": listing_id, "updated": True}
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
