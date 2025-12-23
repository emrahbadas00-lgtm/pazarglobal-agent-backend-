# tools/search_listings.py

import os
import json
from typing import Any, Dict, Optional, List, Iterable, Tuple

import httpx
from urllib.parse import quote


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
# Accept both env names used across the repo
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET") or os.getenv("SUPABASE_PUBLIC_BUCKET") or "product-images"
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
    # NOTE: We intentionally avoid selecting `metadata` to prevent accidental leakage in agent outputs.
    # Filters can still use metadata->>... even if metadata isn't selected.
    select_fields = ",".join(
        [
            "id",
            "user_id",
            "title",
            "description",
            "category",
            "price",
            "stock",
            "location",
            "status",
            "created_at",
            "updated_at",
            "condition",
            "image_url",
            "images",
            "is_premium",
            "user_name",
            "user_phone",
            "premium_until",
            "premium_badge",
            "expires_at",
        ]
    )

    params: Dict[str, str] = {
        "limit": str(limit),
        "order": "created_at.desc",
        "status": "eq.active",  # Default: Only show active listings
        "select": select_fields,
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

        def _normalize_image_entries(value: Any) -> List[str]:
            """Return best-effort list of storage paths or URLs from a jsonb-like value."""
            if value is None:
                return []
            if isinstance(value, list):
                out: List[str] = []
                for it in value:
                    if isinstance(it, str):
                        s = it.strip()
                        if s:
                            out.append(s)
                    elif isinstance(it, dict):
                        # tolerate formats like {"path": "..."} or {"url": "..."}
                        for key in ("path", "object_path", "storage_path", "url"):
                            v = it.get(key)
                            if isinstance(v, str) and v.strip():
                                out.append(v.strip())
                                break
                return out
            if isinstance(value, dict):
                # Occasionally stored as {paths:[...]} or similar
                for key in ("paths", "images", "value"):
                    inner = value.get(key)
                    if inner is not None:
                        return _normalize_image_entries(inner)
                return []
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return []
                # If it looks like a JSON array, parse it.
                if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
                    try:
                        parsed = json.loads(s)
                        return _normalize_image_entries(parsed)
                    except Exception:
                        # fall back to treating as single path
                        return [s]
                return [s]
            return []

        def _collect_listing_image_refs(item: Dict[str, Any]) -> List[str]:
            refs: List[str] = []
            refs.extend(_normalize_image_entries(item.get("images")))
            img0 = item.get("image_url")
            if isinstance(img0, str) and img0.strip():
                refs.append(img0.strip())
            # Deduplicate while preserving order
            return list(dict.fromkeys(refs))

        # Collect all storage paths to sign in one request (skip already-absolute URLs)
        all_paths: List[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            for ref in _collect_listing_image_refs(item):
                if isinstance(ref, str) and ref and not ref.lower().startswith("http"):
                    all_paths.append(ref)

        signed_map: Dict[str, str] = {}
        if all_paths:
            # Preserve order but remove duplicates
            unique_paths = list(dict.fromkeys(all_paths))
            signed_map = await generate_signed_urls(unique_paths)

        # PERFORMANCE OPTIMIZATION: listings table already has user_name and user_phone (denormalized)
        # No need to fetch from profiles table - use existing fields directly!
        
        # Attach owner info and signed URLs per listing
        for item in data:
            if not isinstance(item, dict):
                continue
            
            # Get user info directly from listings table (denormalized fields)
            owner_name = item.get("user_name")
            owner_phone = item.get("user_phone")
            
            # Set owner_* fields for backward compatibility (both user_* and owner_* exist)
            item["owner_name"] = owner_name
            item["owner_phone"] = owner_phone

            refs = _collect_listing_image_refs(item)
            signed_images: List[str] = []
            for ref in refs:
                if not isinstance(ref, str) or not ref:
                    continue
                if ref.lower().startswith("http"):
                    signed_images.append(ref)
                    continue
                signed = signed_map.get(ref)
                if signed:
                    signed_images.append(signed)
                elif SUPABASE_STORAGE_PUBLIC and SUPABASE_URL:
                    # Best-effort fallback when signing fails but bucket is public
                    signed_images.append(f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{quote(ref)}")
            # Unique, preserve order
            signed_images = list(dict.fromkeys(signed_images))
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


async def get_listing_by_id(listing_id: str) -> Dict[str, Any]:
    """Fetch a single listing by UUID.

    Important:
    - Reads `metadata` to extract user-facing fields (e.g., room_count) but does NOT return raw `metadata`.
    - Produces `signed_images` using `images` and `image_url` fallback.
    """

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {
            "success": False,
            "error": "SUPABASE_URL veya SUPABASE_SERVICE_KEY tanımlı değil",
        }

    listing_id_s = str(listing_id or "").strip()
    if not listing_id_s:
        return {
            "success": False,
            "error": "missing_listing_id",
        }

    url = f"{SUPABASE_URL}/rest/v1/listings"
    select_fields = ",".join(
        [
            "id",
            "user_id",
            "title",
            "description",
            "category",
            "price",
            "stock",
            "location",
            "status",
            "created_at",
            "updated_at",
            "condition",
            "image_url",
            "images",
            "metadata",
            "is_premium",
            "user_name",
            "user_phone",
            "premium_until",
            "premium_badge",
            "expires_at",
        ]
    )

    params: Dict[str, str] = {
        "id": f"eq.{listing_id_s}",
        "limit": "1",
        "select": select_fields,
    }

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }

    def _normalize_image_entries(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            out: List[str] = []
            for it in value:
                if isinstance(it, str):
                    s = it.strip()
                    if s:
                        out.append(s)
                elif isinstance(it, dict):
                    for key in ("path", "object_path", "storage_path", "url"):
                        v = it.get(key)
                        if isinstance(v, str) and v.strip():
                            out.append(v.strip())
                            break
            return out
        if isinstance(value, dict):
            for key in ("paths", "images", "value"):
                inner = value.get(key)
                if inner is not None:
                    return _normalize_image_entries(inner)
            return []
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return []
            if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
                try:
                    parsed = json.loads(s)
                    return _normalize_image_entries(parsed)
                except Exception:
                    return [s]
            return [s]
        return []

    def _collect_listing_image_refs(item: Dict[str, Any]) -> List[str]:
        refs: List[str] = []
        refs.extend(_normalize_image_entries(item.get("images")))
        img0 = item.get("image_url")
        if isinstance(img0, str) and img0.strip():
            refs.append(img0.strip())
        return list(dict.fromkeys(refs))

    def _extract_public_fields_from_metadata(meta: Any) -> Dict[str, Any]:
        if not isinstance(meta, dict):
            return {}
        out: Dict[str, Any] = {}

        # Real estate
        if meta.get("room_count") is not None:
            out["room_count"] = meta.get("room_count")
        if meta.get("property_type") is not None:
            out["property_type"] = meta.get("property_type")

        # Common
        if meta.get("type") is not None:
            out["listing_type"] = meta.get("type")
        for key in ("brand", "model", "year"):
            if meta.get(key) is not None:
                out[key] = meta.get(key)
        return out

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(url, params=params, headers=headers)

        if not resp.is_success:
            return {
                "success": False,
                "status": resp.status_code,
                "error": resp.text,
            }

        data = resp.json() or []
        if not isinstance(data, list) or not data:
            return {
                "success": False,
                "error": "not_found",
            }

        item = data[0] if isinstance(data[0], dict) else None
        if not isinstance(item, dict):
            return {
                "success": False,
                "error": "invalid_result",
            }

        # owner convenience fields
        item["owner_name"] = item.get("user_name")
        item["owner_phone"] = item.get("user_phone")

        # Extract safe public fields from metadata and drop raw metadata
        meta = item.get("metadata")
        extracted = _extract_public_fields_from_metadata(meta)
        if extracted:
            item.update(extracted)
        if "metadata" in item:
            item.pop("metadata", None)

        # Sign images
        refs = _collect_listing_image_refs(item)
        paths_to_sign = [r for r in refs if isinstance(r, str) and r and not r.lower().startswith("http")]
        signed_map: Dict[str, str] = {}
        if paths_to_sign:
            signed_map = await generate_signed_urls(list(dict.fromkeys(paths_to_sign)))

        signed_images: List[str] = []
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                continue
            if ref.lower().startswith("http"):
                signed_images.append(ref)
                continue
            signed = signed_map.get(ref)
            if signed:
                signed_images.append(signed)
            elif SUPABASE_STORAGE_PUBLIC and SUPABASE_URL:
                signed_images.append(f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{quote(ref)}")

        signed_images = list(dict.fromkeys(signed_images))
        item["signed_images"] = signed_images
        item["first_image_signed_url"] = signed_images[0] if signed_images else None

        return {
            "success": True,
            "result": item,
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
