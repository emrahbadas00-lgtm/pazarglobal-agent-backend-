"""
Update an existing listing in Supabase
"""
import os
import httpx
from typing import Optional, List
from .suggest_category import suggest_category


def normalize_category_with_metadata(category: Optional[str], metadata: Optional[dict]) -> Optional[str]:
    """Ensure category matches metadata type (e.g., vehicle => Otomotiv)."""
    meta_type = (metadata or {}).get("type") if isinstance(metadata, dict) else None
    
    # Map metadata types to categories
    type_to_category = {
        "vehicle": "Otomotiv",
        "property": "Emlak",
        "electronics": "Elektronik",
        "phone": "Elektronik",
        "computer": "Elektronik",
        "appliance": "Ev & Yaşam",
        "furniture": "Ev & Yaşam",
        "clothing": "Moda & Giyim",
        "general": "Genel"
    }
    
    if meta_type and meta_type in type_to_category:
        return type_to_category[meta_type]
    
    return category


def normalize_metadata_type_with_category(metadata: Optional[dict], category: Optional[str]) -> Optional[dict]:
    """If user explicitly changes category, keep metadata->type aligned (best-effort)."""
    if not isinstance(metadata, dict):
        return metadata
    if not category:
        return metadata

    cat = str(category).lower()
    if "emlak" in cat:
        metadata["type"] = "property"
    elif "otomotiv" in cat:
        metadata["type"] = "vehicle"
    elif "elektr" in cat:
        metadata["type"] = "electronics"
    elif "moda" in cat or "giyim" in cat:
        metadata["type"] = "clothing"
    else:
        metadata.setdefault("type", "general")
    return metadata

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

async def update_listing(
    listing_id: str,
    user_id: Optional[str] = None,
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

    if not user_id:
        return {
            "success": False,
            "status_code": 401,
            "error": "Kullanıcı doğrulanmadı; güncelleme için user_id gerekli"
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
        if images:
            payload["image_url"] = images[0]
    
    if not payload:
        return {
            "success": False,
            "status_code": 400,
            "error": "No fields provided to update"
        }
    
    # NOTE: Category updates must respect the user's explicit request.
    # We may still record an AI suggestion for observability, but we do NOT override `category`.
    if category is not None:
        try:
            validation_title = title
            validation_description = description

            if validation_title is None or validation_description is None:
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

            if validation_title:
                suggestion = await suggest_category(validation_title, validation_description, category)
                if suggestion.get("success") and not suggestion.get("is_correct", True):
                    payload["metadata"] = normalize_metadata_type_with_category(payload.get("metadata") or {}, category)
                    payload["metadata"]["category_suggestion"] = {
                        "requested": category,
                        "suggested": suggestion.get("suggested_category"),
                        "confidence": suggestion.get("confidence"),
                    }
        except Exception:
            pass
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    url = f"{SUPABASE_URL}/rest/v1/listings"
    
    try:
        # Ownership check: ensure listing belongs to user_id
        async with httpx.AsyncClient(timeout=10.0) as client:
            ownership_resp = await client.get(
                f"{url}?id=eq.{listing_id}&select=id,user_id",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            if ownership_resp.is_success and ownership_resp.json():
                owner = ownership_resp.json()[0].get("user_id")
                if owner and owner != user_id:
                    return {
                        "success": False,
                        "status_code": 403,
                        "error": "Bu ilan size ait değil. Başkasının ilanını güncelleyemezsiniz."
                    }
            else:
                return {
                    "success": False,
                    "status_code": ownership_resp.status_code,
                    "error": "İlan bulunamadı veya erişim hatası"
                }

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
