# tools/search_listings.py

import os
from typing import Any, Dict, Optional, List

import httpx
from urllib.parse import quote


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "product-images")
SUPABASE_STORAGE_PUBLIC = os.getenv("SUPABASE_STORAGE_PUBLIC", "false").lower() in ("1", "true", "yes")


async def generate_signed_urls(paths: List[str], expires_in: int = 3600) -> Dict[str, str]:
    """
    Generate signed URLs for private storage objects.

    Args:
        paths: List of object paths (e.g., userId/listingId/uuid.jpg)
        expires_in: Expiration in seconds

    Returns:
        Mapping of path -> signed URL (missing or failed paths are skipped)
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}

    # If bucket is public, prefer simple public URLs to avoid long signed tokens
    if SUPABASE_STORAGE_PUBLIC:
        return {p: f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{quote(p)}" for p in paths}

    sign_url = f"{SUPABASE_URL}/storage/v1/object/sign/{SUPABASE_STORAGE_BUCKET}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"paths": paths, "expiresIn": expires_in}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(sign_url, json=payload, headers=headers)
        if not resp.is_success:
            return {}
        data = resp.json() or []
        # Supabase returns list of objects with {signedURL, path}
        signed_map: Dict[str, str] = {}
        for item in data:
            signed_url = item.get("signedURL")
            path = item.get("path")
            if not signed_url or not path:
                continue
            # Use as returned (already URL-safe); prepend base
            signed_map[path] = f"{SUPABASE_URL}{signed_url}"
        return signed_map
    except Exception:
        return {}


async def search_listings(
    query: Optional[str] = None,
    category: Optional[str] = None,
    condition: Optional[str] = None,
    location: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    limit: int = 10,
    metadata_type: Optional[str] = None,
    room_count: Optional[str] = None,  # NEW: Direct metadata filter (e.g., "3+1")
    property_type: Optional[str] = None,  # NEW: Direct metadata filter (e.g., "dubleks")
) -> Dict[str, Any]:
    """
    Supabase'den ilan arama.
    WhatsApp'tan: "iPhone aramak istiyorum" → query="iPhone"
    
    Args:
        query: Arama metni (title, description, category, location içinde ara)
        category: Kategori filtresi
        condition: Durum filtresi ("new", "used")
        location: Lokasyon filtresi
        min_price: Minimum fiyat
        max_price: Maximum fiyat
        limit: Sonuç sayısı (default: 10)
        metadata_type: Metadata type filter ("vehicle", "part", "property")
        room_count: Room count filter (e.g., "3+1") - searches in metadata->>'room_count'
        property_type: Property type filter (e.g., "dubleks") - searches in metadata->>'property_type'
        
    Returns:
        İlan listesi veya hata mesajı
    """

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {
            "success": False,
            "error": "SUPABASE_URL veya SUPABASE_SERVICE_KEY tanımlı değil",
        }

    url = f"{SUPABASE_URL}/rest/v1/listings"
    
    # Supabase query parametreleri
    params: Dict[str, str] = {
        "limit": str(limit),
        "order": "created_at.desc",
        "status": "eq.active",  # Default: Only show active listings
        # Join users table to fetch owner name
        "select": "*,users(name)",
    }
    
    # Filtreler - Supabase PostgREST syntax
    if query:
        # Synonym expansion for generic terms
        query_lower = query.lower()
        
        # SMART SEARCH: Search in multiple fields (title, description, category, location)
        # This makes search more flexible - no need to specify exact category!
        if query_lower in ["araba", "otomobil", "araç", "oto"]:
            # Generic vehicle search: Check category and metadata
            if not category:
                params["or"] = f"(title.ilike.*{query}*,description.ilike.*{query}*,category.ilike.*otom*)"
        elif query_lower in ["ev", "daire", "emlak", "kiralık", "satılık"]:
            # Real estate search: Check multiple fields
            if not category:
                params["or"] = f"(title.ilike.*{query}*,description.ilike.*{query}*,category.ilike.*emlak*,location.ilike.*{query}*)"
        else:
            # Normal search: title, description, category, location (BROADEST SEARCH)
            params["or"] = f"(title.ilike.*{query}*,description.ilike.*{query}*,category.ilike.*{query}*,location.ilike.*{query}*)"
    
    if category:
        # Category normalization - case insensitive partial match
        # Example: "Emlak" matches "Emlak – Kiralık Daire"
        # IMPORTANT: When ONLY category is used (no query, no property_type), this is the ONLY filter!
        # The listing will be found if category matches.
        params["category"] = f"ilike.*{category}*"
    
    if condition:
        params["condition"] = f"eq.{condition}"
    
    if location:
        # Use ilike for partial match (e.g., "Bursa" matches "Bursa / Nilüfer, 23 Nisan...")
        params["location"] = f"ilike.*{location}*"
    
    if min_price is not None:
        params["price"] = f"gte.{min_price}"
    
    if max_price is not None:
        if "price" in params:
            # Hem min hem max varsa
            params["price"] = f"gte.{min_price}&price=lte.{max_price}"
        else:
            params["price"] = f"lte.{max_price}"
    
    if metadata_type:
        # Filter by metadata->type field (JSONB query)
        params["metadata->>type"] = f"eq.{metadata_type}"
    
    if room_count:
        # Filter by metadata->room_count field (e.g., "3+1")
        params["metadata->>room_count"] = f"eq.{room_count}"
    
    if property_type:
        # Search in BOTH metadata AND title/description (some listings have type in title, not metadata)
        # Example: "Dubleks" in title but property_type="daire" in metadata
        if query:
            # If query exists, combine with OR
            params["or"] = f"(title.ilike.*{property_type}*,description.ilike.*{property_type}*,metadata->>property_type.ilike.*{property_type}*)" + "," + params.get("or", "")
        else:
            # No query, just search property_type in title, description, and metadata
            params["or"] = f"(title.ilike.*{property_type}*,description.ilike.*{property_type}*,metadata->>property_type.ilike.*{property_type}*)"

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Prefer": "count=exact",  # Get total count in Content-Range header
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(url, params=params, headers=headers)

        if not resp.is_success:
            return {
                "success": False,
                "status": resp.status_code,
                "error": resp.text,
            }

        data = resp.json()

        # Collect all image paths to sign in one request
        all_paths: List[str] = []
        for item in data:
            imgs = item.get("images") if isinstance(item, dict) else None
            if isinstance(imgs, list):
                for p in imgs:
                    if isinstance(p, str):
                        all_paths.append(p)

        signed_map: Dict[str, str] = {}
        if all_paths:
            # Preserve order but remove duplicates
            unique_paths = list(dict.fromkeys(all_paths))
            signed_map = await generate_signed_urls(unique_paths)

        # Attach signed URLs per listing
        for item in data:
            if not isinstance(item, dict):
                continue
            # Extract owner name from joined users table
            user_obj = item.get("users") if isinstance(item.get("users"), dict) else None
            item["user_name"] = user_obj.get("name") if user_obj else None
            # Clean up nested users object if present (optional)
            if "users" in item:
                del item["users"]
            imgs = item.get("images") if isinstance(item.get("images"), list) else []
            signed_images = [signed_map[p] for p in imgs if isinstance(p, str) and p in signed_map]
            item["signed_images"] = signed_images
            item["first_image_signed_url"] = signed_images[0] if signed_images else None

        # Get total count from Content-Range header if available
        total_count = len(data)
        content_range = resp.headers.get("content-range")
        print(f"🔍 DEBUG - Content-Range header: {content_range}")
        if content_range:
            # Format: "0-4/6" means results 0-4 out of total 6
            parts = content_range.split("/")
            if len(parts) == 2 and parts[1].isdigit():
                total_count = int(parts[1])
                print(f"✅ Total count from header: {total_count}")
            else:
                print(f"⚠️ Could not parse Content-Range: {content_range}")
        else:
            print(f"⚠️ No Content-Range header, using count: {total_count}")
        
        print(f"📊 Returning: count={len(data)}, total={total_count}")
        
        return {
            "success": True,
            "count": len(data),  # Number of results returned in this response
            "total": total_count,  # Total number of matching listings (might be > count)
            "results": data,
        }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timeout - Supabase bağlantısı zaman aşımına uğradı",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Beklenmeyen hata: {str(e)}",
        }
