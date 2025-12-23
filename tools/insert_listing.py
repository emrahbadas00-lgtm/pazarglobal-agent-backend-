# tools/insert_listing.py

import os
import re
from typing import Any, Dict, Optional, List, cast

import httpx
from .suggest_category import suggest_category
from .wallet_tools import deduct_credits


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def normalize_category_with_metadata(category: Optional[str], metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """Force category to align with detected metadata type for consistency."""
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
        # Keep user-provided category when meta_type is very generic
        if meta_type == "general" and category:
            return category
        return type_to_category[meta_type]
    
    return category


async def insert_listing(
    title: str,
    user_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",  # Default test user for development
    price: Optional[int] = None,
    condition: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    stock: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    images: Optional[List[str]] = None,
    listing_id: Optional[str] = None,
    user_name: Optional[str] = None,  # User's full name
    user_phone: Optional[str] = None,  # User's phone number
) -> Dict[str, Any]:
    """
    Supabase REST API üzerinden 'listings' tablosuna kayıt ekler.
    
    Args:
        title: Ürün başlığı (zorunlu)
        user_id: Kullanıcı UUID (WhatsApp entegrasyonunda otomatik gelecek)
        price: Fiyat (sayısal)
        condition: Durum (örn: "new", "used")
        category: Kategori
        description: Açıklama
        location: Lokasyon
        stock: Stok adedi
        metadata: JSONB metadata (type, brand, model, year, etc.)
        images: Supabase storage path list (userId/listingId/uuid.jpg)
        listing_id: Optional predefined UUID (keeps storage path and DB in sync)
        
    Returns:
        Dict içinde success, status ve result anahtarları
        Örnek: {"success": True, "status": 201, "result": {...}}
    """

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {
            "success": False,
            "status": 500,
            "error": "SUPABASE_URL veya SUPABASE_SERVICE_KEY tanımlı değil",
        }
    
    # Use provided user_id (already resolved from phone number in main.py)
    print(f"✅ Using authenticated user_id: {user_id}")
    print(f"👤 User: {user_name} ({user_phone})")

    # 🤖 AI-POWERED CATEGORY VALIDATION
    # If category is missing or potentially wrong, use AI to suggest correct one
    if not category or category.strip() == "":
        print(f"⚠️ Category missing, using AI inference...")
        suggestion = await suggest_category(title, description)
        if suggestion["success"] and suggestion["suggested_category"]:
            category = suggestion["suggested_category"]
            print(f"✅ AI suggested category: {category} (confidence: {suggestion['confidence']})")
        else:
            # Fallback to generic category
            category = "Genel"
            print(f"⚠️ Could not infer category, using default: {category}")
    else:
        # Validate existing category
        print(f"🔍 Validating category: {category}")
        suggestion = await suggest_category(title, description, category)
        if suggestion["success"] and not suggestion.get("is_correct", True):
            original_category = category
            category = suggestion["suggested_category"]
            print(f"⚠️ Category mismatch detected!")
            print(f"   User selected: {original_category}")
            print(f"   AI suggests: {category} (confidence: {suggestion['confidence']})")
            print(f"   Auto-correcting to: {category}")
            
            # Store original category in metadata for audit
            if metadata is None:
                metadata = {}
            metadata["original_category"] = original_category
            metadata["category_corrected"] = True

    # Align category with metadata (e.g., vehicle => Otomotiv)
    category = normalize_category_with_metadata(category, metadata)

    # Only select id to keep response small but reliable (needed for wallet deduction reference)
    url = f"{SUPABASE_URL}/rest/v1/listings?select=id"

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "title": title,
        "price": price,
        "condition": condition,
        "category": category,
        "description": description,
        "location": location,
        "stock": stock,
        "status": "active",
        "metadata": metadata,
        "user_name": user_name,  # Add user_name to payload
        "user_phone": user_phone,  # Add user_phone to payload
    }

    if listing_id:
        payload["id"] = listing_id

    if images is not None:
        # Persist provided storage paths; DB default handles empty list otherwise
        payload["images"] = images
        # Legacy single image column support
        if images:
            payload["image_url"] = images[0]

    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Prefer": "return=representation",
    }

    try:
        print(f"📡 Attempting POST to: {url}")
        print(f"📦 Payload: {payload}")
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(url, json=payload, headers=headers)
        
        print(f"✅ Response status: {resp.status_code}")

        data = None
        try:
            data = resp.json()
        except Exception:
            data = resp.text

        if not resp.is_success:
            print(f"❌ Insert failed body: {data}")

        # 💰 AUTO-DEDUCT CREDITS ON SUCCESSFUL LISTING
        wallet_deduction: Optional[Dict[str, Any]] = None
        if resp.is_success:
            # Try to resolve listing id from (1) provided listing_id, (2) response JSON, (3) response headers
            listing_id_created: Optional[str] = listing_id
            if not listing_id_created:
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    listing_id_created = cast(Optional[str], data[0].get("id"))
                elif isinstance(data, dict):
                    listing_id_created = cast(Optional[str], data.get("id"))

            if not listing_id_created:
                location = resp.headers.get("content-location") or resp.headers.get("location") or ""
                match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", location)
                if match:
                    listing_id_created = match.group(0)

            if listing_id_created:
                # Calculate actual cost based on usage
                total_cost = 50  # Base listing cost (₺10)
                
                # Vision safety check (1 call regardless of photo count)
                if images and len(images) > 0:
                    total_cost += 5  # Vision safety check (₺1)
                
                print(f"💰 Deducting {total_cost} credits for listing (base 50kr + {' vision 5kr' if images else 'no photos'})...")
                deduct_result = deduct_credits(
                    user_id=user_id,
                    amount_credits=total_cost,
                    action="listing_publish",
                    reference=listing_id_created
                )
                wallet_deduction = {
                    "attempted": True,
                    "amount_credits": total_cost,
                    "listing_id": listing_id_created,
                    "result": deduct_result,
                }
                
                if deduct_result["success"]:
                    print(f"✅ Credits deducted! New balance: {deduct_result['new_balance_credits']}kr (₺{deduct_result['new_balance_credits'] * 0.20})")
                else:
                    print(f"⚠️ Credit deduction failed: {deduct_result.get('error')}")
                    # Still return success for listing (credit issue shouldn't block listing)
            else:
                print("⚠️ Could not resolve listing_id from insert response; skipping wallet deduction.")
                wallet_deduction = {"attempted": False, "error": "missing_listing_id"}

        return {
            "success": resp.is_success,
            "status": resp.status_code,
            "result": data,
            "wallet_deduction": wallet_deduction,
        }
    except httpx.TimeoutException as e:
        print(f"⏱️ Timeout error: {str(e)}")
        return {
            "success": False,
            "status": 408,
            "error": f"Request timeout - Supabase bağlantısı zaman aşımına uğradı: {str(e)}",
        }
    except httpx.ConnectError as e:
        print(f"🔌 Connection error: {str(e)}")
        return {
            "success": False,
            "status": 503,
            "error": f"Supabase bağlantısı kurulamadı: {str(e)}",
        }
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "status": 500,
            "error": f"Beklenmeyen hata ({type(e).__name__}): {str(e)}",
        }
