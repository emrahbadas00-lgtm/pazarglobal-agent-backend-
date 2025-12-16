# tools/insert_listing.py

import os
from typing import Any, Dict, Optional, List

import httpx
from .suggest_category import suggest_category
from .wallet_tools import deduct_credits


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def normalize_category_with_metadata(category: Optional[str], metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    """Force category to align with detected metadata type for consistency."""
    meta_type = (metadata or {}).get("type") if isinstance(metadata, dict) else None
    if meta_type == "vehicle":
        return "Otomotiv"
    if meta_type == "property":
        return "Emlak"
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

    url = f"{SUPABASE_URL}/rest/v1/listings"

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

        # 💰 AUTO-DEDUCT CREDITS ON SUCCESSFUL LISTING
        if resp.is_success and data:
            listing_id_created = None
            if isinstance(data, list) and len(data) > 0:
                listing_id_created = data[0].get("id")
            elif isinstance(data, dict):
                listing_id_created = data.get("id")
            
            if listing_id_created:
                # Calculate actual cost based on usage
                total_cost = 25  # Base listing cost (₺5)
                
                # AI Assistant (WhatsApp conversation = always used)
                total_cost += 10  # ₺2
                
                # Photo analysis (if photos uploaded)
                if images and len(images) > 0:
                    total_cost += 5 * len(images)  # ₺1 per photo
                
                print(f"💰 Deducting {total_cost} credits for listing (base 25kr + AI 10kr + {len(images) if images else 0} photos)...")
                deduct_result = deduct_credits(
                    user_id=user_id,
                    amount_credits=total_cost,
                    action="listing_publish",
                    reference=listing_id_created
                )
                
                if deduct_result["success"]:
                    print(f"✅ Credits deducted! New balance: {deduct_result['new_balance_credits']}kr (₺{deduct_result['new_balance_credits'] * 0.20})")
                else:
                    print(f"⚠️ Credit deduction failed: {deduct_result.get('error')}")
                    # Still return success for listing (credit issue shouldn't block listing)

        return {
            "success": resp.is_success,
            "status": resp.status_code,
            "result": data,
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
