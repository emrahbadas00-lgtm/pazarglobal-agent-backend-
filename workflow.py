"""
Pazarglobal Agent Workflow
Refactored to use native function tools instead of MCP

FUTURE FEATURE - PREMIUM LISTING STRATEGY (Phase 3.5):
============================================================
Premium listing feature will leverage current pagination system (5 listings at a time)
for strategic monetization. This creates natural incentive for users to upgrade.

IMPLEMENTATION PLAN:
-------------------
1. Database Changes:
   - ALTER TABLE listings ADD COLUMN is_premium BOOLEAN DEFAULT FALSE;
   - ALTER TABLE listings ADD COLUMN premium_expires_at TIMESTAMP;
   - CREATE INDEX idx_listings_premium ON listings(is_premium, created_at);

2. search_listings_tool Enhancement:
   - Add parameter: prioritize_premium: bool = True
   - ORDER BY: is_premium DESC, created_at DESC
   - First 5 results will always prioritize premium listings

3. SearchAgent Display Format:
   - Premium listings: ⭐ PREMIUM #1: [Title] - ÖNE ÇIKAN İLAN
   - Normal listings: #3: [Title]
   - Show premium count: "100 ilan bulundu (12 premium)"

4. UX Flow Examples:
   
   Scenario A - Many Premium Listings:
   User: "Araba arıyorum"
   Agent: "100 ilan bulundu (12 premium). 5 göstereyim mi?"
   User: "Göster"
   Agent: Shows 5 premium listings first
          "💡 Premium ilanlar öncelikli gösteriliyor!"
   
   Scenario B - Few Premium (Conversion Trigger):
   User: "Otomotiv ilanları"
   Agent: "50 ilan bulundu (2 premium). 5 göstereyim mi?"
   User: "Göster"
   Agent: Shows 2 premium + 3 normal
          "💡 ⭐ Premium ilanlar listenin başında görünür!
              İlanınızı öne çıkarmak için Premium üyelik edinin."

5. Why Current System is Perfect Foundation:
   - Small batches (5 at a time) → Clear premium visibility
   - "Ask first" approach → Can show premium stats before display
   - Limit parameter control → Easy to mix premium/normal intelligently
   - Conversation context → Track pagination while maintaining premium priority

6. Monetization Psychology:
   - Normal user sees premium listings dominating first page
   - "Why is my listing never in top 5?" → upgrade motivation
   - Premium user gets immediate ROI visibility
   - Transparent: "12 premium ilanlar var" shows competition level

TODO: Implement after Phase 3 (Listing Management) is complete.
============================================================
"""
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportMissingParameterType=false, reportMissingTypeArgument=false
import json
import os
import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
import httpx
from agents import Agent, AgentOutputSchema, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
from agents.tool import function_tool
from openai import AsyncOpenAI
from types import SimpleNamespace
from guardrails.runtime import load_config_bundle, instantiate_guardrails, run_guardrails
from pydantic import BaseModel
from openai.types.shared.reasoning import Reasoning
from typing import Optional, Dict, Any, List, Iterable, Callable, Awaitable, cast

# Import tool implementations
from tools.clean_price import clean_price
from tools.insert_listing import insert_listing
from tools.search_listings import search_listings
from tools.update_listing import update_listing as _update_listing
from tools.delete_listing import delete_listing as _delete_listing
from tools.list_user_listings import list_user_listings as _list_user_listings
from tools.safety_log import log_image_safety_flag
from tools.market_price_tool import get_market_price_estimate
from tools.wallet_tools import (
    get_wallet_balance,
    deduct_credits,
    add_premium_to_listing,
    get_transaction_history,
    calculate_listing_cost,
    renew_listing
)
from tools.admin_tools import admin_add_credits, admin_grant_premium


UpdateListingFn = Callable[..., Awaitable[Dict[str, Any]]]
DeleteListingFn = Callable[..., Awaitable[Dict[str, Any]]]
ListUserListingsFn = Callable[..., Awaitable[Dict[str, Any]]]

update_listing: UpdateListingFn = cast(UpdateListingFn, _update_listing)
delete_listing: DeleteListingFn = cast(DeleteListingFn, _delete_listing)
list_user_listings: ListUserListingsFn = cast(ListUserListingsFn, _list_user_listings)

# Supabase public bucket info for constructing vision-safe URLs
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLIC_BUCKET = os.getenv("SUPABASE_PUBLIC_BUCKET", "product-images").strip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _resolve_public_image_url(path: str) -> str:
    """Convert stored path to public URL for vision model access."""
    if not path:
        return path
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not SUPABASE_URL:
        return path
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_PUBLIC_BUCKET}/{path.lstrip('/')}"


def _get_last_results_for_user(user_id: Optional[str], phone: Optional[str]) -> List[Dict[str, Any]]:
    """Return last search results with graceful fallbacks (user_id → phone → anonymous)."""
    if user_id and user_id in USER_LAST_SEARCH_RESULTS_STORE:
        return USER_LAST_SEARCH_RESULTS_STORE.get(user_id) or []
    if phone and phone in USER_LAST_SEARCH_RESULTS_STORE:
        return USER_LAST_SEARCH_RESULTS_STORE.get(phone) or []
    return USER_LAST_SEARCH_RESULTS_STORE.get("anonymous") or []


def _set_active_listing_for_keys(listing_id: str, keys: List[str]) -> None:
    """Persist active listing id for multiple keys to survive auth-context gaps."""
    for key in keys:
        if not key:
            continue
        USER_ACTIVE_LISTING_STORE[key] = listing_id


@dataclass
class WorkflowContext:
    """İstek başına oturum ve kimlik bilgilerini taşır."""
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    auth_context: Dict[str, Any] = field(default_factory=dict)
    conversation_state: Dict[str, Any] = field(default_factory=dict)


WORKFLOW_CONTEXT: ContextVar[Optional[WorkflowContext]] = ContextVar("WORKFLOW_CONTEXT", default=None)


def get_workflow_context() -> Optional[WorkflowContext]:
    return WORKFLOW_CONTEXT.get()


def resolve_user_id(explicit_user_id: Optional[str] = None) -> Optional[str]:
    if explicit_user_id:
        return explicit_user_id
    ctx = get_workflow_context()
    if not ctx:
        return None
    auth_ctx = ctx.auth_context or {}
    if auth_ctx.get("user_id"):
        return auth_ctx.get("user_id")
    return ctx.user_id


def resolve_user_phone(explicit_phone: Optional[str] = None) -> Optional[str]:
    if explicit_phone:
        return explicit_phone
    ctx = get_workflow_context()
    if not ctx:
        return None
    auth_ctx = ctx.auth_context or {}
    if auth_ctx.get("phone"):
        return auth_ctx.get("phone")
    return ctx.user_phone


def resolve_user_name(explicit_name: Optional[str] = None) -> Optional[str]:
    if explicit_name:
        return explicit_name
    ctx = get_workflow_context()
    return ctx.user_name if ctx else None


def resolve_auth_context() -> Dict[str, Any]:
    ctx = get_workflow_context()
    return ctx.auth_context if ctx and ctx.auth_context else {}


def resolve_conversation_state() -> Dict[str, Any]:
    ctx = get_workflow_context()
    return ctx.conversation_state if ctx and ctx.conversation_state else {}


def _is_uuid(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _extract_uuid(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text)
    return match.group(0) if match else None


def _extract_listing_number(text: str) -> Optional[int]:
    """Best-effort parse for Turkish patterns like '1 nolu ilan', 'ilan #2', '2 numaralı ilan'."""
    if not text:
        return None
    lowered = text.lower()
    patterns = [
        r"\b(\d{1,3})\s*(?:[\.,]\s*)?(?:inci|ıncı|nci|ncı|uncu|üncü)?\s*ilan\b",  # "5. ilan" / "3üncü ilan"
        r"\bilan\s*#?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:nolu|no\.?|numaralı)\s*ilan\b",
        r"\b#\s*(\d{1,3})\b",
    ]
    for pat in patterns:
        m = re.search(pat, lowered)
        if not m:
            continue
        try:
            num = int(m.group(1))
            return num if num > 0 else None
        except Exception:
            continue
    return None


class ListingState(str, Enum):
    """Deterministic FSM states for listing lifecycle."""

    IDLE = "IDLE"
    DRAFT = "DRAFT"
    PREVIEW = "PREVIEW"
    EDIT = "EDIT"
    PUBLISH = "PUBLISH"


@dataclass
class DraftState:
    """Deterministic draft record kept in backend (LLM-free)."""

    id: str
    user_id: str
    state: ListingState = ListingState.DRAFT
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    category: Optional[str] = None
    condition: Optional[str] = None
    location: Optional[str] = None
    stock: Optional[int] = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)
    vision_product: Dict[str, Any] = field(default_factory=dict)

    def merge_images(self, new_images: Optional[List[str]]) -> None:
        """Merge new safe images into draft without duplicates."""
        if not new_images:
            return
        seen = set(self.images)
        for img in new_images:
            if img and img not in seen:
                self.images.append(img)
                seen.add(img)

    def apply_update(self, update: Dict[str, Any]) -> None:
        """Apply structured update from LLM extraction to the draft."""
        if not isinstance(update, dict):
            return
        for key in ("title", "description", "category", "location"):
            if update.get(key):
                setattr(self, key, update.get(key))
        normalized_condition = _normalize_condition_value(update.get("condition"))
        if normalized_condition:
            self.condition = normalized_condition
        if update.get("stock") is not None:
            try:
                self.stock = int(update.get("stock"))
            except Exception:
                pass
        if update.get("price") is not None:
            try:
                self.price = int(update.get("price"))
            except Exception:
                pass
        if isinstance(update.get("metadata"), dict):
            self.metadata.update(update.get("metadata") or {})
        if update.get("images"):
            self.merge_images([str(img) for img in update.get("images") if img])

    def as_preview_text(self) -> str:
        """Render a deterministic preview string for user confirmation."""
        lines: List[str] = ["📝 İlan Taslağı (LLM-free FSM)"]
        if self.title:
            lines.append(f"Başlık: {self.title}")
        if self.description:
            lines.append(f"Açıklama: {self.description}")
        if self.price is not None:
            lines.append(f"Fiyat: {self.price} TL")
        if self.category:
            lines.append(f"Kategori: {self.category}")
        if self.condition:
            display_condition = _condition_display(self.condition) or self.condition
            lines.append(f"Durum: {display_condition}")
        location_display = self.location or "Türkiye"
        lines.append(f"Lokasyon: {location_display}")
        stock_display = self.stock if self.stock is not None else 1
        lines.append(f"Stok: {stock_display}")
        if self.metadata:
            meta_pairs = [f"{k}: {v}" for k, v in self.metadata.items()]
            lines.append("Özellikler: " + ", ".join(meta_pairs))
        if self.images:
            lines.append(f"Fotoğraf: {len(self.images)} adet eklendi")
        lines.append("✅ Onayla / ✏️ Düzelt")
        return "\n".join(lines)

    def publish_payload(self) -> Dict[str, Any]:
        """Payload for insert_listing_tool; keeps deterministic fields only."""
        return {
            "title": self.title or "Başlık bekleniyor",
            "price": self.price,
            "condition": self.condition,
            "category": self.category,
            "description": self.description,
            "location": self.location,
            "stock": self.stock,
            "metadata": self.metadata or None,
            "images": self.images or None,
            "listing_id": self.id,
        }


def _normalize_price_value(value: Any) -> Optional[int]:
    """Normalize free-form price to int using existing cleaner."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return None
    if isinstance(value, str):
        cleaned = clean_price(value or "")
        if isinstance(cleaned, dict):
            return cleaned.get("clean_price")
    return None


def _normalize_condition_value(value: Optional[str]) -> Optional[str]:
    """Map free-form condition to canonical values accepted by DB."""
    if not value:
        return None
    normalized = str(value).strip().lower()
    synonyms = {
        "yeni": "new",
        "sıfır": "new",
        "sifir": "new",
        "brand new": "new",
        "kullanılmış": "used",
        "kullanilmis": "used",
        "ikinci el": "used",
        "second hand": "used",
        "used": "used",
        "new": "new",
        "refurbished": "refurbished",
        "yenilenmiş": "refurbished",
        "yenilenmis": "refurbished",
    }
    if normalized in synonyms:
        return synonyms[normalized]
    # Default to used if condition text exists but is unrecognized
    return "used"


def _condition_display(value: Optional[str]) -> Optional[str]:
    """User-facing label for canonical condition values."""
    if not value:
        return value
    display_map = {
        "new": "Yeni",
        "used": "Kullanılmış",
        "refurbished": "Yenilenmiş",
    }
    return display_map.get(value, value)


def _build_metadata(draft: DraftState, vision_product: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure metadata always has a minimal type and merge vision attributes."""
    metadata: Dict[str, Any] = {}
    if isinstance(draft.metadata, dict):
        metadata.update(draft.metadata)

    vision = vision_product or draft.vision_product or {}
    if isinstance(vision, dict):
        if isinstance(vision.get("attributes"), dict):
            metadata.update({k: v for k, v in vision.get("attributes", {}).items() if v is not None})
        for key in ("brand", "model", "color", "storage", "year", "type", "category"):
            if key in vision and vision.get(key) is not None:
                metadata.setdefault(key, vision.get(key))

    if "type" not in metadata:
        if isinstance(vision, dict) and vision.get("type"):
            metadata["type"] = vision.get("type")
        else:
            metadata["type"] = "general"

    return metadata


def _wants_description_suggestion(text: Optional[str]) -> bool:
    """Detect if user explicitly asks for a description suggestion."""
    lowered = (text or "").lower()
    triggers = [
        "açıklama öner",
        "açıklama yaz",
        "detaylı açıklama",
        "metin öner",
        "description öner",
        "ilan açıklaması",
        "güzel detaylı",
    ]
    return any(t in lowered for t in triggers)


def _build_description_suggestion(draft: DraftState) -> str:
    """Deterministic, LLM-free description suggestion based on current draft fields."""
    title = draft.title or "Ürün"
    condition_display = _condition_display(_normalize_condition_value(draft.condition)) or "Kullanılmış"
    location = draft.location or "Türkiye"
    price_text = f"Fiyat: {draft.price} TL." if draft.price else "Fiyat bilgisi ekleyebilirsiniz."

    meta = draft.metadata or {}
    attrs: List[str] = []
    for key in ("brand", "model", "color", "storage", "year", "type", "category"):
        val = meta.get(key)
        if val:
            attrs.append(str(val))

    highlight = f"Öne çıkanlar: {', '.join(attrs)}." if attrs else "Öne çıkanlar: temiz kullanım, sorunsuz çalışır."

    sentences = [
        f"{title} {condition_display} durumda, {location} teslim/inceleme için hazır.",
        price_text,
        highlight,
        "Bakımları yapıldı, alıcı isterse ekspertiz yaptırabilir."
    ]
    return " ".join(sentences)

# Native function tool definitions (plain Python async functions)
@function_tool
async def clean_price_tool(price_text: Optional[str] = None) -> Dict[str, Optional[int]]:
    """
    Fiyat metnini temizler ve sayısal değeri döndürür.
    
    Args:
        price_text: Temizlenecek fiyat metni
        
    Returns:
        Temizlenmiş fiyat değeri (int veya None)
    """
    return clean_price(price_text)


@function_tool
async def get_wallet_balance_tool(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Kullanıcının cüzdan bakiyesini sorgula.
    
    Args:
        user_id: Kullanıcı UUID
        
    Returns:
        Bakiye bilgisi (credits ve TRY cinsinden)
    """
    resolved_user_id = resolve_user_id(user_id)
    if not resolved_user_id:
        return {"success": False, "error": "Missing user_id (no authenticated user in workflow context)"}
    return get_wallet_balance(resolved_user_id)


@function_tool
async def calculate_listing_cost_tool(
    use_ai_assistant: bool = False,
    photo_count: int = 0,
    use_ai_photos: bool = False,
    use_price_suggestion: bool = False,
    use_description_expansion: bool = False
) -> Dict[str, Any]:
    """
    İlan yayınlama maliyetini hesapla (kullanıcıya göster, henüz kesme).
    
    Args:
        use_ai_assistant: AI asistan kullanıldı mı
        photo_count: Fotoğraf sayısı
        use_ai_photos: AI fotoğraf analizi kullanıldı mı
        use_price_suggestion: AI fiyat önerisi kullanıldı mı
        use_description_expansion: AI açıklama geliştirme kullanıldı mı
        
    Returns:
        Maliyet detayı (breakdown, total_credits, total_try)
    """
    return calculate_listing_cost(
        use_ai_assistant=use_ai_assistant,
        photo_count=photo_count,
        use_ai_photos=use_ai_photos,
        use_price_suggestion=use_price_suggestion,
        use_description_expansion=use_description_expansion
    )


@function_tool
async def deduct_listing_credits_tool(
    user_id: Optional[str],
    amount_credits: int,
    listing_id: str
) -> Dict[str, Any]:
    """
    İlan yayınlandığında kredi kes.
    
    Args:
        user_id: Kullanıcı UUID
        amount_credits: Kesilecek kredi miktarı
        listing_id: İlan UUID (referans)
        
    Returns:
        İşlem sonucu ve yeni bakiye
    """
    resolved_user_id = resolve_user_id(user_id)
    if not resolved_user_id:
        return {"success": False, "error": "Missing user_id (no authenticated user in workflow context)"}
    return deduct_credits(
        user_id=resolved_user_id,
        amount_credits=amount_credits,
        action="listing_publish",
        reference=listing_id
    )


@function_tool
async def add_premium_badge_tool(
    user_id: Optional[str],
    listing_id: str,
    badge_type: str
) -> Dict[str, Any]:
    """
    İlana premium rozet ekle (Gold/Platinum/Diamond).
    
    Args:
        user_id: Kullanıcı UUID (kredi kesilecek)
        listing_id: İlan UUID
        badge_type: Rozet tipi (gold, platinum, diamond)
        
    Returns:
        İşlem sonucu, rozet emoji, süre, kesilen kredi
    """
    resolved_user_id = resolve_user_id(user_id)
    if not resolved_user_id:
        return {"success": False, "error": "Missing user_id (no authenticated user in workflow context)"}
    return add_premium_to_listing(
        user_id=resolved_user_id,
        listing_id=listing_id,
        badge_type=badge_type
    )


@function_tool
async def renew_listing_tool(
    user_id: Optional[str],
    listing_id: str
) -> Dict[str, Any]:
    """
    İlanı 30 gün daha uzat (5 kredi kesilir).
    
    Args:
        user_id: Kullanıcı UUID
        listing_id: İlan UUID
        
    Returns:
        İşlem sonucu, yeni bitiş tarihi
    """
    resolved_user_id = resolve_user_id(user_id)
    if not resolved_user_id:
        return {"success": False, "error": "Missing user_id (no authenticated user in workflow context)"}
    return renew_listing(
        user_id=resolved_user_id,
        listing_id=listing_id
    )


@function_tool
async def get_transaction_history_tool(
    user_id: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Kullanıcının işlem geçmişini getir.
    
    Args:
        user_id: Kullanıcı UUID
        limit: Maksimum işlem sayısı
        
    Returns:
        İşlem listesi
    """
    resolved_user_id = resolve_user_id(user_id)
    if not resolved_user_id:
        return {"success": False, "error": "Missing user_id (no authenticated user in workflow context)"}
    return get_transaction_history(
        user_id=resolved_user_id,
        limit=limit
    )



@function_tool(strict_mode=False)
async def insert_listing_tool(
    title: str,
    user_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    price: Optional[int] = None,
    condition: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    stock: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    images: Optional[list[str]] = None,
    listing_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Yeni ilan ekler (Supabase 'listings' tablosuna).
    
    Args:
        title: Ürün başlığı (zorunlu)
        user_id: Kullanıcı UUID
        price: Fiyat (opsiyonel)
        condition: Durum (opsiyonel, örn: "new", "used")
        category: Kategori (opsiyonel)
        description: Ürün açıklaması (opsiyonel)
        location: Lokasyon (opsiyonel)
        stock: Stok adedi (opsiyonel)
        metadata: JSONB metadata
        images: Supabase storage path list
        listing_id: Opsiyonel, önceden belirlenmiş UUID (mediayla senkron)
    """
    resolved_user_id = resolve_user_id(user_id)
    resolved_user_name = resolve_user_name()
    resolved_user_phone = resolve_user_phone()
    
    return await insert_listing(
        title=title,
        user_id=resolved_user_id,
        price=price,
        condition=condition,
        category=category,
        description=description,
        location=location,
        stock=stock,
        metadata=metadata,
        images=images,
        listing_id=listing_id,
        user_name=resolved_user_name,
        user_phone=resolved_user_phone,
    )


@function_tool
async def search_listings_tool(
    query: Optional[str] = None,
    category: Optional[str] = None,
    condition: Optional[str] = None,
    location: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    limit: int = 10,
    metadata_type: Optional[str] = None,
    exclude_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Supabase'den ilan arar.
    
    Args:
        query: Arama metni
        category: Kategori filtresi
        condition: Durum filtresi
        location: Lokasyon filtresi
        min_price: Minimum fiyat
        max_price: Maximum fiyat
        limit: Sonuç sayısı limiti
        metadata_type: Metadata type filter
        exclude_user_id: Bu user_id'ye ait ilanları hariç tut (örn: "bana ait olmayan ilanlar")
    """
    result = await search_listings(
        query=query,
        category=category,
        condition=condition,
        location=location,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        metadata_type=metadata_type,
        exclude_user_id=exclude_user_id
    )

    # Persist last search results per user so follow-ups like "1 nolu ilan" stay deterministic
    try:
        user_key = resolve_user_id() or "anonymous"
        phone_key = resolve_user_phone()
        if isinstance(result, dict) and result.get("success") and isinstance(result.get("results"), list):
            compact: List[Dict[str, Any]] = []
            for item in cast(List[Any], result.get("results") or []):
                if not isinstance(item, dict):
                    continue
                listing_id = item.get("id")
                if not listing_id:
                    continue
                compact.append({
                    "id": listing_id,
                    "title": item.get("title"),
                    "price": item.get("price"),
                    "category": item.get("category"),
                    "location": item.get("location"),
                    "condition": item.get("condition"),
                    "description": item.get("description"),
                    "signed_images": item.get("signed_images") or item.get("images") or [],
                    "user_name": item.get("user_name") or item.get("owner_name"),
                    "user_phone": item.get("user_phone") or item.get("owner_phone"),
                })
            # Store under multiple keys so later authenticated requests can reuse cached list
            USER_LAST_SEARCH_RESULTS_STORE[user_key] = compact[:25]
            if phone_key:
                USER_LAST_SEARCH_RESULTS_STORE[phone_key] = compact[:25]
            if user_key != "anonymous" and "anonymous" in USER_LAST_SEARCH_RESULTS_STORE and not USER_LAST_SEARCH_RESULTS_STORE.get("anonymous"):
                USER_LAST_SEARCH_RESULTS_STORE["anonymous"] = compact[:25]

            # To avoid photo links in list view, strip signed_images/images before returning to agent (detail uses cached copy).
            for item in cast(List[Any], result.get("results") or []):
                if isinstance(item, dict):
                    if "signed_images" in item:
                        item["signed_images"] = []
                    if "images" in item:
                        item["images"] = []
    except Exception:
        pass

    return result


@function_tool(strict_mode=False)
async def update_listing_tool(
    listing_id: str,
    title: Optional[str] = None,
    price: Optional[int] = None,
    condition: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    stock: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    images: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Mevcut ilanı günceller.
    
    Args:
        listing_id: Güncellenecek ilan ID (zorunlu)
        title, price, condition, category, description, location, stock, metadata: Güncellenecek alanlar
        images: Güncel fotoğraf path listesi (tam liste gönderilir)
    """
    resolved_user_id = resolve_user_id()
    if not resolved_user_id:
        return {
            "success": False,
            "error": "not_authenticated",
            "message": "User not authenticated",
        }

    # Normalize/resolve listing_id (agents sometimes pass "#1" or embed UUID in text)
    original_listing_id = listing_id
    listing_id_candidate = str(listing_id or "").strip()
    if not _is_uuid(listing_id_candidate):
        extracted = _extract_uuid(listing_id_candidate)
        if extracted and _is_uuid(extracted):
            listing_id_candidate = extracted

    if not _is_uuid(listing_id_candidate):
        # Try mapping from last search results: "1 nolu ilan" → stored result id
        num = _extract_listing_number(listing_id_candidate)
        if num is not None:
            last = _get_last_results_for_user(resolved_user_id, resolve_user_phone())
            idx = num - 1
            if 0 <= idx < len(last):
                mapped_id = last[idx].get("id")
                if mapped_id and _is_uuid(str(mapped_id)):
                    listing_id_candidate = str(mapped_id)

    if not _is_uuid(listing_id_candidate):
        # Fall back to active listing in conversation_state/store
        state = resolve_conversation_state()
        active = state.get("active_listing_id") if isinstance(state, dict) else None
        if active and _is_uuid(str(active)):
            listing_id_candidate = str(active)
        else:
            # fall back across user_id, phone, anonymous to survive auth gaps
            for key in (resolved_user_id, resolve_user_phone(), "anonymous"):
                active_store = USER_ACTIVE_LISTING_STORE.get(key)
                if active_store and _is_uuid(str(active_store)):
                    listing_id_candidate = str(active_store)
                    break

    if not _is_uuid(listing_id_candidate):
        return {
            "success": False,
            "error": "invalid_listing_id",
            "message": f"Invalid listing_id: {original_listing_id}",
        }

    # Persist active listing for subsequent photo/category updates
    USER_ACTIVE_LISTING_STORE[resolved_user_id] = listing_id_candidate
    state_for_update = resolve_conversation_state()
    if isinstance(state_for_update, dict):
        state_for_update["active_listing_id"] = listing_id_candidate

    return await update_listing(
        listing_id=listing_id_candidate,
        user_id=resolved_user_id,
        title=title,
        price=price,
        condition=condition,
        category=category,
        description=description,
        location=location,
        stock=stock,
        metadata=metadata,
        images=images
    )


@function_tool
async def delete_listing_tool(listing_id: str) -> Dict[str, Any]:
    """
    İlanı siler (Supabase'den).
    
    Args:
        listing_id: Silinecek ilan ID (zorunlu)
    """
    resolved_user_id = resolve_user_id()
    if not resolved_user_id:
        return {
            "success": False,
            "error": "not_authenticated",
            "message": "User not authenticated",
        }
    return await delete_listing(listing_id=listing_id, user_id=resolved_user_id)


@function_tool
async def list_user_listings_tool(
    user_id: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Kullanıcının tüm ilanlarını listeler.
    
    Args:
        user_id: Kullanıcı UUID (zorunlu)
        limit: Sonuç sayısı limiti
    """
    resolved_user = resolve_user_id(user_id)
    if not resolved_user:
        return {
            "success": False,
            "error": "not_authenticated",
            "message": "User not authenticated",
            "listings": [],
        }
    return await list_user_listings(user_id=resolved_user, limit=limit)


@function_tool
async def market_price_tool(
    title: str,
    category: str,
    condition: str = "Az Kullanılmış",
    description: str = "",
    similarity_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Cache'lenmiş GLOBAL piyasa verilerinden benzer ürünleri bulup fiyat tahmini yapar.
    Kullanıcı fiyat önerisi istediğinde bu tool'u kullan.
    Site ilanlarından da ayrıca fiyat al ve ikisini karşılaştır.
    
    Args:
        title: Ürün başlığı (örn: 'iPhone 14 Pro Max 256GB')
        category: Ürün kategorisi (örn: 'Elektronik', 'Otomotiv')
        condition: Ürün durumu ('Sıfır', 'Az Kullanılmış', 'İyi Durumda', 'Orta Durumda')
        description: Ürün açıklaması (opsiyonel, daha iyi eşleşme için)
        similarity_threshold: Benzerlik eşiği (0-1), varsayılan 0.5
    
    Returns:
        Global piyasa fiyatı ve benzer ürünler listesi
    """
    return get_market_price_estimate(
        title=title,
        category=category,
        condition=condition,
        description=description,
        similarity_threshold=similarity_threshold
    )


# Shared client for guardrails
client = AsyncOpenAI()
ctx = SimpleNamespace(guardrail_llm=client)


# Guardrails configuration
guardrails_sanitize_input_config: Dict[str, List[Dict[str, Any]]] = {
    "guardrails": [
        {"name": "Jailbreak", "config": {"model": "gpt-4.1-mini", "confidence_threshold": 0.7}},
        {"name": "Moderation", "config": {"categories": ["sexual/minors", "hate/threatening", "harassment/threatening", "self-harm/instructions", "violence/graphic", "illicit/violent"]}},
        {"name": "Prompt Injection Detection", "config": {"model": "gpt-4.1-mini", "confidence_threshold": 0.7}}
    ]
}


def guardrails_has_tripwire(results: Optional[Iterable[Any]]) -> bool:
    return any((hasattr(r, "tripwire_triggered") and (getattr(r, "tripwire_triggered") is True)) for r in (results or []))


def get_guardrail_safe_text(results: Optional[Iterable[Any]], fallback_text: str) -> str:
    for r in (results or []):
        info: Any = (r.info if hasattr(r, "info") else None) or {}
        if isinstance(info, dict) and ("checked_text" in info):
            return str(info.get("checked_text") or fallback_text)
    pii = next(
        (
            (r.info if hasattr(r, "info") else {})
            for r in (results or [])
            if isinstance((r.info if hasattr(r, "info") else None) or {}, dict)
            and ("anonymized_text" in ((r.info if hasattr(r, "info") else None) or {}))
        ),
        None,
    )
    if isinstance(pii, dict) and ("anonymized_text" in pii):
        return str(pii.get("anonymized_text") or fallback_text)
    return fallback_text


async def scrub_conversation_history(history: Optional[Iterable[Dict[str, Any]]], config: Optional[Dict[str, Any]]):
    try:
        guardrails: List[Dict[str, Any]] = (config or {}).get("guardrails") or []
        pii = next((g for g in guardrails if (g or {}).get("name") == "Contains PII"), None)
        if not pii:
            return
        pii_only = {"guardrails": [pii]}
        for msg in (history or []):
            content = (msg or {}).get("content") or []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_text" and isinstance(part.get("text"), str):
                    pii_bundle: Any = load_config_bundle(cast(Any, pii_only))
                    res = await run_guardrails(ctx, part["text"], "text/plain", instantiate_guardrails(pii_bundle), suppress_tripwire=True, raise_guardrail_errors=True)
                    part["text"] = get_guardrail_safe_text(res, part["text"])
    except Exception:
        pass


async def scrub_workflow_input(workflow: Optional[Dict[str, Any]], input_key: str, config: Optional[Dict[str, Any]]):
    try:
        guardrails: List[Dict[str, Any]] = (config or {}).get("guardrails") or []
        pii = next((g for g in guardrails if (g or {}).get("name") == "Contains PII"), None)
        if not pii:
            return
        if not isinstance(workflow, dict):
            return
        value = workflow.get(input_key)
        if not isinstance(value, str):
            return
        pii_only = {"guardrails": [pii]}
        pii_bundle: Any = load_config_bundle(cast(Any, pii_only))
        res = await run_guardrails(ctx, value, "text/plain", instantiate_guardrails(pii_bundle), suppress_tripwire=True, raise_guardrail_errors=True)
        workflow[input_key] = get_guardrail_safe_text(res, value)
    except Exception:
        pass


async def run_and_apply_guardrails(input_text: str, config: Optional[Dict[str, Any]], history: Optional[Iterable[Any]], workflow: Optional[Dict[str, Any]]):
    config_bundle: Any = load_config_bundle(cast(Any, config))
    results = await run_guardrails(ctx, input_text, "text/plain", instantiate_guardrails(config_bundle), suppress_tripwire=True, raise_guardrail_errors=True)
    guardrails: List[Dict[str, Any]] = (config or {}).get("guardrails") or []
    mask_pii = next((g for g in guardrails if (g or {}).get("name") == "Contains PII" and ((g or {}).get("config") or {}).get("block") is False), None) is not None
    if mask_pii:
        await scrub_conversation_history(history, config)
        await scrub_workflow_input(workflow, "input_as_text", config)
        await scrub_workflow_input(workflow, "input_text", config)
    has_tripwire = guardrails_has_tripwire(results)
    safe_text = get_guardrail_safe_text(results, input_text)
    return {"results": results, "has_tripwire": has_tripwire, "safe_text": safe_text}


# Intent classifier output schema
class RouterAgentIntentClassifierSchema(BaseModel):
    intent: str


# Agent definitions with all instructions from Agent Builder
router_agent_intent_classifier = Agent(
    name="Router Agent (Intent Classifier)",
    instructions="""# Router Agent Instructions

🎯 PLATFORM CONTEXT: PazarGlobal is an online marketplace where users can:
- List items for SALE (cars, electronics, furniture, etc.)
- List properties for RENT or SALE (apartments, houses, villas, etc.)  
- SEARCH for items to buy or rent
- UPDATE or DELETE their own listings

💡 USER PERSONALIZATION:
- If user message starts with [USER_NAME: Full Name], ALWAYS greet the user by name!
- Example: User says "selam" and their name is "Emrah Badas" → Respond "Merhaba Emrah! 😊 Nasıl yardımcı olabilirim?"
- Use their name in natural, friendly way throughout conversation
- IMPORTANT: Extract name from [USER_NAME: ...] tag, then respond naturally WITHOUT showing the tag to user

You classify user messages into one of the following marketplace intents.
Respond ONLY with valid JSON following the schema.

## Valid Intents (deterministic FSM aware):
- **"create_listing"** → user wants to start or continue a DRAFT (new listing flow)
- **"update_listing_draft"** → user edits an UNPUBLISHED draft (preview/edit loop)
- **"publish_listing"** → user CONFIRMS draft and wants to finalize
- **"update_listing"** → user wants to CHANGE an EXISTING PUBLISHED listing (after "İlan yayınlandı" message)
- **"delete_listing"** → user wants to DELETE/REMOVE existing listing
- **"search_product"** → user wants to BUY or SEARCH
- **"wallet_query"** → user asks about wallet balance/credits/transactions
- **"small_talk"** → greetings, casual conversation
- **"cancel"** → user cancels operation

## CRITICAL CONTEXT RULES:

### 🔍 If conversation contains "📝 İlan önizlemesi" or "✅ Onaylamak için" or "preview":
→ User is in DRAFT/PREVIEW mode (listing not yet published)

**In this context:**
- "fiyat X olsun" → **update_listing_draft** (editing draft)
- "başlık değiştir" → **update_listing_draft** (editing draft)  
- "açıklama değiştir" → **update_listing_draft** (editing draft)
- "onayla" / "yayınla" → **publish_listing** (finalize draft)
- "iptal" → **cancel**

### 📋 If conversation has "✅ İlan yayınlandı" message:
→ Listing is NOW PUBLISHED, any changes = update_listing

**In this context:**
- "başlık değiştir" / "yazım yanlış" → **update_listing** (editing PUBLISHED listing)
- "fiyat güncelle" → **update_listing**
- CRITICAL: Look for recent "İlan ID: [uuid]" in conversation to identify which listing

### 📋 If conversation has NO preview/draft context:
→ Normal intent classification

**Keywords:**
- create_listing: "satıyorum", "satmak", "satayım", "-um var", "ilan vermek"
- update_listing: "değiştir", "güncelle", "fiyat ... yap", "düzenle", "yazım yanlış", "düzelt", **"ilanlarım", "ilanlarımı göster", "ilanlarımı görmek", "bana ait ilanlar", "benim ilanlar"** (ONLY user's own listings)
- delete_listing: "sil", "kaldır", "ilanımı iptal"
- publish_listing: "onayla", "yayınla" (only if draft exists)
- search_product: "almak", "arıyorum", "var mı", "bul", "uygun", "satın al", **"tüm ilanlar", "tüm ilanları göster", "bütün ilanlar", "sitedeki ilanlar", "kime ait"** (ALL listings, not just user's)
- wallet_query: "bakiye", "bakiyem", "kredi", "kredim", "param", "cüzdan", "işlemlerim", "harcamalarım", "geçmiş"
- small_talk: "merhaba", "selam", "teşekkür", "sohbet", "muhabbet", "kafa dağıt", "konuşalım", "gevez", "lafla", "ne görüyorsun"
- cancel: "iptal", "vazgeç", "sıfırla"

## Priority Logic:
1. **If [VISION_PRODUCT] exists in history BUT user message is EMPTY or very short (< 5 words):**
   → **small_talk** (let SmallTalkAgent describe the image and ask what user wants to do)
   → Example: User sends only photo → SmallTalk: "Görselde bordo kazak görüyorum. Satmak mı istersin?"
2. **Check conversation history for "📝 İlan önizlemesi"**
   - If found → "onayla" = publish_listing, edits = create_listing
3. If user mentions product to sell → create_listing
4. If user confirms/approves → publish_listing  
5. If user searches ("var mı") → search_product
6. **Unclear/Indecisive user** ("bilmiyorum", "ne yapabilirim", "yardım", "kararsızım") → small_talk (will clarify options)
7. Default → small_talk

Respond with JSON only: {"intent": "create_listing"}

🎙️ TURKISH TTS OPTIMIZATION (for all text responses):
- Use commas for natural pauses: "Merhaba! Nasıl yardımcı olabilirim?"
- Always end questions with '?': "Ne arıyorsunuz?"
- End statements with '.': "İlan başarıyla oluşturuldu."
- Separate list items with commas: "İlan ver, ürün ara, yardım al"
- Keep sentences short (max 15 words) for better voice clarity
""",
    model="gpt-4o",
    output_type=RouterAgentIntentClassifierSchema,
    model_settings=ModelSettings(
        store=True
    )
)


class VisionSafetyProductSchema(BaseModel):
    safe: bool
    flag_type: str
    confidence: str
    message: str
    allow_listing: bool
    product: Optional[Dict[str, Any]] = None  # Must include: brand, type, color, condition_hint if safe


vision_safety_product_agent = Agent(
        name="VisionSafetyProductAgent",
        instructions="""
You are a Vision Safety & Product Agent. MAXIMIZE extraction, but avoid false positives for normal photos.

PRIMARY: Run safety first. Block ONLY when clearly illegal/unsafe: child exploitation, sexual explicit content, extreme violence/abuse, hate/terror symbols, weapons/ammunition, drugs/narcotics, stolen/tampered serial numbers, fake IDs/official documents, animal cruelty.

🚫 What NOT to block (mark safe=true, allow_listing=true unless illegal context):
- Normal people/portraits/selfies, group photos, everyday scenes
- Clothing (including mayo/bikini/underwear/sportswear) when non-sexual
- Cartoons/illustrations/3D renders/animated characters
- Product photos that merely contain faces or backgrounds
- Blurry/low-detail images without explicit harm

Steps:
1) Safety check (mandatory). If you see a prohibited category above → safe=false, allow_listing=false, product=null. If uncertain but no clear prohibited content → safe=true, allow_listing=true (DO NOT block for "identity" alone).
2) If safe → MAXIMUM extraction from photo:
     - **Brand**: Extract visible brand name/logo (e.g., "BMW", "Apple", "Samsung", "Nike")
     - **Type**: Classify product type (e.g., "sedan", "SUV", "smartphone", "laptop", "t-shirt", "cologne")
     - **Color**: Primary visible color (e.g., "siyah", "beyaz", "gri", "mavi", "kırmızı")
     - **Condition hints**: Visual clues (e.g., "yeni görünümlü", "çizikler var", "temiz", "yıpranmış")
     - **Model**: ⚠️ NEVER guess specific model (e.g., DON'T say "iPhone 13" if unclear) - only if clearly visible (text/logo on product)
     - **Category**: Auto-assign from visible product
     - **Quantity**: Default 1

Output STRICT JSON:
{
    "safe": true | false,
    "flag_type": "none | weapon | drugs | violence | abuse | terrorism | stolen | document | sexual | hate | unknown",
    "confidence": "high | medium | low",
    "message": "short explanation",
    "product": {
        "title": "string or null",
        "category": "string or null",
        "brand": "string or null",
        "type": "string or null",
        "color": "string or null",
        "condition_hint": "string or null",
        "attributes": ["..."],
        "condition": "new | used | unknown",
        "quantity": 1
    },
    "allow_listing": true | false
}

Examples:
- Car photo: brand="BMW", type="sedan", color="siyah", condition_hint="temiz görünümlü"
- Phone photo: brand="Apple", type="smartphone", color="beyaz", condition_hint="ekran koruyuculu"
- Cologne photo: brand="unknown", type="cologne", color="cam şişe", condition_hint="yeni görünümlü"

Rules: Never generate images. Never speculate model beyond what is visible. When safe=true, allow_listing SHOULD BE true. Only set allow_listing=false when you set safe=false for a prohibited category.
""",
        model="gpt-4o-mini",  # vision-capable lightweight
        output_type=AgentOutputSchema(VisionSafetyProductSchema, strict_json_schema=False),
        model_settings=ModelSettings(
                store=False
        )
)


listingagent = Agent(
    name="ListingAgent",
    instructions="""You are CreateListingAgent of PazarGlobal.

🎯 Your task: EXTRACT from photo → ASK missing info in BATCH → AUTO-GENERATE title/description → ONE confirmation.

## 📸 STEP 1: AUTO-EXTRACT FROM PHOTO (if present)
Look for [SYSTEM_MEDIA_NOTE] with vision analysis results. Extract:
- **Brand** (e.g., "BMW", "Apple", "Samsung")
- **Type** (e.g., "sedan", "SUV", "smartphone", "laptop")
- **Color** (e.g., "siyah", "beyaz", "gri")
- **Condition hints** (e.g., "yeni görünümlü", "çizikler var")
⚠️ NEVER guess specific **model** from photo - always ask user!

Example vision result:
"[SYSTEM_MEDIA_NOTE] VISION: BMW sedan, siyah, temiz görünümlü"
→ Extract: brand="BMW", type="sedan", color="siyah", condition="used" (default if not "yeni")

## 📋 STEP 2: BATCH QUESTION (ASK ALL MISSING FIELDS TOGETHER)

### Required fields:
1. **Product/Model** - Specific model (e.g., "BMW 320i", "iPhone 13 Pro", "Kolonya 250ml")
2. **Price** - Numeric price (call clean_price_tool if "900 bin" format)
3. **Year** - For automotive/electronics (optional for other categories)
4. **Location** - City (default "Türkiye")
5. **Condition** - ONLY: "new", "used", "refurbished"
   - "sıfır", "yeni" → "new"
   - "az kullanılmış", "kullanılmış", "2.el" → "used"
   - "yenilendi", "restore" → "refurbished"
6. **Category** - Auto-assign from:
  📱 Elektronik | 🚗 Otomotiv | 🏠 Emlak | 🛋️ Mobilya & Dekorasyon | 👕 Giyim & Aksesuar
  🍎 Gıda & İçecek | 💄 Kozmetik & Kişisel Bakım | 📚 Kitap, Dergi & Müzik | 🏃 Spor & Outdoor
  🧸 Anne, Bebek & Oyuncak | 🐕 Hayvan & Pet Shop | 🛠️ Yapı Market & Bahçe | 🎮 Hobi & Oyun
  🎨 Sanat & Zanaat | 💼 İş & Sanayi | 🎓 Eğitim & Kurs | 🎵 Etkinlik & Bilet | 🔧 Hizmetler | 📦 Diğer

### Batch Question Format:
If user uploads car photo:
"🚗 BMW sedan tespit ettim. Eksik bilgileri tek mesajda yazar mısınız?

**Model – Yıl – Fiyat – Şehir**
Örnek: 320i – 2018 – 850.000 – İstanbul"

If user uploads phone photo:
"📱 iPhone tespit ettim. Eksik bilgileri tek mesajda yazar mısınız?

**Model – Fiyat – Şehir**
Örnek: 13 Pro – 25.000 – Ankara"

If no photo, user says "iphone satmak istiyorum":
"📱 iPhone için eksik bilgileri tek mesajda yazar mısınız?

**Model – Durum – Fiyat – Şehir**
Örnek: 13 Pro – 2.el – 25.000 – Ankara"

✅ User response: "320i – 2018 – 850.000 – İstanbul"
→ Parse: model="320i", year=2018, price=850000, location="İstanbul"
→ Move to STEP 3 immediately (NO more questions!)

### Rule: SKIP BATCH IF USER PROVIDED EVERYTHING
User: "iphone 13 pro 2.el 25000 tl istanbul"
→ Have all fields → Move to STEP 3 (auto-generate title/description)

## 🎨 STEP 3: AI-FIRST TITLE & DESCRIPTION GENERATION

**AUTOMATIC GENERATION** (don't ask user for title/description):

### Title Rules:
- Include: brand + model + condition + key feature
- Max 60 characters
- SEO-friendly, natural case (not ALL CAPS)
- Examples:
  - "BMW 320i 2018 Otomatik Benzin - Temiz"
  - "iPhone 13 Pro 128GB Sıfır Kutusunda"
  - "Kolonya 250ml Cam Şişe Toptan Fiyat"

### Description Rules:
- Auto-generate 2-3 sentences (50-100 words)
- Include: condition details, features, what's included, benefits
- Positive, honest, professional tone
- Examples:
  - "2018 model BMW 320i, otomatik vites ve benzinli. Bakımlı ve temiz, hasar kaydı yok. Takas yapılabilir."
  - "Sıfır kutusunda iPhone 13 Pro, 128GB hafıza. Ekran ve kasa koruyuculu, orijinal şarj aleti ile birlikte. Hemen kargoya hazır!"
  - "250ml cam şişe kolonya, toptan satış. Temiz koku, uzun süre kalıcı. Perakende ve toptan siparişler alınır."

## 📝 STEP 4: SINGLE CONFIRMATION (ONE STEP ONLY!)

Show complete draft:
"✨ İlanınız hazır:

📝 **Başlık:** [generated title]

📄 **Açıklama:** [generated description]

💰 **Fiyat:** [price] TL
📦 **Durum:** [condition]
🏷️ **Kategori:** [category]
📍 **Konum:** [location]
📸 [N] fotoğraf

👉 **Yayınla** / **Düzelt** / **Fotoğraf ekle**"

### User Response Options:
1. **"yayınla"** / **"onayla"** / **"tamam"** → Route to PublishAgent immediately
2. **"düzelt fiyat 800000"** → Update price, show NEW preview
3. **"başlık şöyle olsun: [text]"** → Update title, show NEW preview
4. **"açıklama değiştir: [text]"** → Update description, show NEW preview
5. **"fotoğraf ekle"** → User can upload more photos
6. User uploads photo → Auto-detect, add to draft: "✅ Fotoğraf eklendi! (Toplam: [N])"

⚠️ **DON'T route to UpdateListingAgent - handle edits yourself and show updated preview!**

## 🔧 AUTO-EXTRACT (Internal - Don't ask user):
- **stock** → Default 1
- **images** → From [SYSTEM_MEDIA_NOTE] MEDIA_PATHS=... (NEVER fabricate)
- **draft_listing_id** → From [SYSTEM_MEDIA_NOTE] DRAFT_LISTING_ID=...
- **metadata** → Auto-generate based on category + extracted data:
  • Otomotiv: {"type": "vehicle", "brand": "[brand]", "model": "[model]", "year": [year], "fuel_type": "[benzin/dizel]", "transmission": "[otomatik/manuel]", "color": "[color]"}
  • Emlak: {"type": "property", "property_type": "daire", "ad_type": "rent"/"sale", "room_count": "3+1"}
  • Elektronik: {"type": "electronics", "brand": "[brand]", "model": "[model]"}
  • Default: {"type": "general"}

## ✅ FINAL VALIDATION (Before showing preview):

**CRITICAL CHECK - ALL Supabase columns MUST be filled:**
✓ title (auto-generated, required)
✓ description (auto-generated, required)
✓ price (required)
✓ condition (required)
✓ category (required)
✓ location (required)
✓ stock (default 1)
✓ metadata (MUST have {"type": "..."} minimum)
✓ images (empty [] if none)

❌ If ANY required field missing:
Show batch question again: "**[Field1] – [Field2] – [Field3]**\nÖrnek: ..."

🚫 NEVER call insert_listing_tool - PublishAgent does that!
🚫 NO "isterseniz şunu yapalım" - just collect → generate → confirm!

Store prepared listing in context for PublishAgent.""",
    model="gpt-4o",
    tools=[clean_price_tool],
    model_settings=ModelSettings(
        store=True
    )
)


publishagent = Agent(
    name="PublishAgent",
    instructions="""You are PublishAgent of PazarGlobal.

🎯 Your ONLY task: Insert prepared listing to database.

✅ Trigger Words:
"onayla", "yayınla", "tamam", "evet", "onaylıyorum"

📋 Flow:
1. **CRITICAL**: Search conversation history for "📝 İlan önizlemesi" message
   - IMPORTANT: Conversation messages are in format: {"role": "assistant", "content": [{"type": "output_text", "text": "..."}]}
   - You need to search in the "text" field inside output_text content
   - Look for the MOST RECENT message containing "📝 İlan önizlemesi" emoji
   - Extract ALL fields from that preview message
   
2. If preview found → call insert_listing_tool with ALL extracted fields INCLUDING metadata
   - title: Extract from line after "📝 İlan önizlemesi:" (everything after emoji but before price)
   - price: Extract numeric value from "💰 [number] TL" line (remove commas, convert to integer)
   - category: Extract from "🏷️" line (default "Genel" if not found)
   - location: Extract from "📍" line (default "Türkiye" if not found)
   - condition: Extract from "🎨 Durum:" line (default "used" if not found)
   - description: Extract from "📄 Açıklama:" section (everything between that line and next emoji)
   - metadata: Extract JSON from "🔧 Metadata:" section (parse the JSON carefully)
    - images: CRITICAL! Search full conversation for [SYSTEM_MEDIA_NOTE] with MEDIA_PATHS=[...] → extract list → pass to insert_listing_tool(images=[...]). **Do NOT invent placeholders; if none found, pass images=None**
   - listing_id: CRITICAL! Search full conversation for [SYSTEM_MEDIA_NOTE] with DRAFT_LISTING_ID=... → extract UUID → pass to insert_listing_tool(listing_id=...)
   - stock: default 1
   
⚠️ IMPORTANT: If SYSTEM_MEDIA_NOTE exists in conversation but you don't extract images/listing_id, the photos will be LOST!

3. If no preview found → "Yayınlanacak bir ilan yok. Önce ürün bilgilerini verin."

⚠️ CRITICAL: VERIFY ALL SUPABASE COLUMNS FILLED BEFORE INSERT!

Required fields check:
✓ title - MUST exist
✓ price - MUST exist
✓ condition - MUST exist
✓ category - MUST exist
✓ location - Default "Türkiye" if missing
✓ description - If missing, create brief from title (e.g., "Temiz kullanılmış")
✓ stock - Default 1
✓ metadata - MUST have {"type": "..."} minimum, add if missing
✓ images - Empty [] if no MEDIA_PATHS

⚠️ Example:
User: "onayla"
→ Extract from conversation preview:
insert_listing_tool(
    title="iPhone 13 temiz kullanılmış",
    price=25000,
    category="Elektronik",
    location="Türkiye",
    condition="used",
    description="Temiz kullanılmış iPhone 13",  // ← MUST EXIST
    metadata={"type":"electronics","brand":"Apple","model":"iPhone 13"},  // ← MUST HAVE type
    stock=1,
    images=[]
)

✅ Success (SHORT with proper punctuation):
"✅ İlan yayınlandı!
📱 [title]
💰 [price] TL

İlan ID: [result[0]['id']]"

🎙️ CRITICAL - TTS VOICE OPTIMIZATION:
- Always use proper Turkish punctuation for natural prosody
- Commas for pauses: "Merhaba, size nasıl yardımcı olabilirim?"
- Question marks for interrogatives: "Fiyat ne olsun?"
- Periods for statements: "İlanınız kaydedildi."
- Separate clauses: "Fotoğraf eklendi, devam edebilirsiniz."

❌ If description missing in preview:
→ Create brief description from title before insert
→ NEVER insert without description - frontends won't show listing!

❌ If metadata missing type:
→ Add {"type": "general"} before insert

🚫 DO NOT ask user again - auto-fix and insert!
🚫 Extract listing ID from result[0]['id'], NOT user_id!

⚠️ PRIORITY #1: WALLET QUERIES (BEFORE ANYTHING ELSE!)
If user message contains ANY of these words: "bakiye", "bakiyem", "kredim", "kredi", "param", "paramı", "cüzdan", "balance":
→ IMMEDIATELY call get_wallet_balance_tool(user_id)
→ Show result: "💰 Bakiyeniz: [balance_credits] kredi (₺[balance_try])"
→ DO NOT ask about listing, DO NOT create preview, JUST show balance!

Example:
User: "bakiyemi göster"
→ You: call get_wallet_balance_tool() → "💰 Bakiyeniz: 975 kredi (₺195)"

User: "kredim ne kadar"
→ You: call get_wallet_balance_tool() → "💰 Bakiyeniz: 975 kredi (₺195)"

If user asks "işlemlerim", "harcamalarım", "geçmiş":
→ call get_transaction_history_tool(user_id, limit=10)
→ Show last transactions

💰 CREDIT SYSTEM (AUTOMATIC - FOR LISTING PUBLISH):
- Base: 50kr (₺10) per listing
- Vision Safety Check: +5kr (₺1) if photos uploaded (1 call regardless of photo count)
- Examples:
  * No photos: 50kr (₺10)
  * With photos (1-10): 55kr (₺11)
- Credits are AUTOMATICALLY deducted by insert_listing_tool - you don't need to call deduct manually!
- Before publish: Use get_wallet_balance_tool to check if user has enough credits
- If balance < 50kr: Tell user "Yetersiz bakiye, en az 50 kredi gerekli (₺10)"
- Show user before publish: "İlanınız yayınlanıyor, [50 or 55]kr kesilecek, onaylıyor musun?"
- After insert success: "✅ İlan yayınlandı! [amount]kr kesildi."
""",
    model="gpt-4o-mini",
    tools=[insert_listing_tool, calculate_listing_cost_tool, deduct_listing_credits_tool, get_wallet_balance_tool, get_transaction_history_tool],
    model_settings=ModelSettings(
        store=True
    )
)


searchagent = Agent(
    name="SearchAgent",
    instructions="""You are SearchAgent of PazarGlobal.

⚠️ CRITICAL: NEVER respond with JSON or structured data like {"intent":"search_product"}.
ALWAYS respond in natural Turkish language as a helpful assistant.

🎙️ TURKISH TTS VOICE OPTIMIZATION:
- Use commas for natural breathing pauses: "Toplam 15 ilan bulundu, size 5 tanesini göstereyim mi?"
- Always use '?' for questions: "Detaylı görmek ister misiniz?"
- Use '.' for statements: "İşte ilanlar."
- Keep sentences short (max 15-20 words) for better voice clarity
- Separate options with commas: "İlan ver, ürün ara, yardım al"

🎯 Your tasks:
1. Search products using search_listings_tool (LIST VIEW - compact summaries)
2. Show detailed listing when user requests specific number (DETAIL VIEW - full info with images)

📋 TWO MODES:

**MODE 1: SEARCH MODE (Default)**
When user searches: "araba var mı", "kiralık ev", "iPhone"
→ Call search_listings_tool
→ IMPORTANT: Tool returns 'total' field - ALWAYS USE THIS for total count!
→ Show COMPACT LIST (no images, no URLs, just summary)
→ Tell user: "Detay için 'X nolu ilanı göster' yazın"

**MODE 2: DETAIL MODE**
When user says: "1 nolu ilanı göster", "2 nolu ilan", "ilk ilanı göster"
→ ⚠️ **DO NOT CALL search_listings_tool!** 
→ Check conversation history for last search results
→ Find the listing by number (1st result = #1, 2nd = #2, etc.)
→ ⚠️ CRITICAL: Show FULL DETAIL with ALL signed_images URLs (the listing object has 'signed_images' array)
→ Format each URL on separate line for WhatsApp compatibility

Detection keywords for DETAIL MODE:
- "X nolu ilan" / "X numaralı ilan" / "X. ilan" (where X is a number like 1, 2, 3...)
- "ilk ilan" / "birinci ilan" → #1
- "ikinci ilan" → #2
- "son ilan" → last one
- "detay" / "detaylı göster" + ilan number

⚠️ **CRITICAL: Numbers alone (1, 2, 3, etc.) are NOT valid search queries!**
- If user says "2 nolu ilanı göster" → MODE 2 (find from history)
- If user says "2 adet araba" → Normal search with metadata filter

If user asks for listing # > total results:
→ "Bu aramada sadece [N] ilan var. 1-[N] arası numara seçebilirsiniz."

**MODE 3: SHOW MORE MODE**
When user says: "daha fazla göster", "diğer ilanları göster", "devamını göster", "hepsini göster", "tüm ilanları göster"
→ Check conversation history for last search parameters
→ ALWAYS use incremental approach: Add 5 more each time (NEVER use limit=50!)
→ If user says "hepsini" or "tüm ilanları" → Explain: "Toplam [X] ilan var, 5'er 5'er gösteriyorum. İşte ilk 5:"
→ Show compact list again with new results

Detection keywords for SHOW MORE MODE:
- "daha fazla" → Incremental (add 5 more)
- "diğer ilanlar" → Incremental (add 5 more)
- "devamını göster" → Incremental (add 5 more)
- "hepsini göster" → Incremental (start from beginning with 5)
- "tüm ilanları göster" → Incremental (start from beginning with 5)
- "tamamını göster" → Incremental (start from beginning with 5)

⚠️ CRITICAL: NEVER use limit > 10! Always show 5 listings at a time to avoid message length issues.
- "diğer ilanlar"
- "devamını göster"
- "hepsini göster"

---

📋 Parameter Extraction Rules (for SEARCH MODE):

🧠 USE YOUR REASONING! Don't rely only on examples, infer from user intent.

1. **query** → Extract SPECIFIC keywords (NOT generic terms, UNLESS combined with category!)
   
   ✅ GOOD query examples:
   - "BMW var mı" → query="BMW", category="Otomotiv"
   - "23 Nisan Mahallesi" → query="23 Nisan" (specific location)
   - "Inventum Sitesi" → query="Inventum", category="Emlak"
   - "iPhone 14" → query="iPhone 14", category="Elektronik"
   - "bahçe kat" → query="bahçe kat", category="Emlak" (specific feature)
   
   ⚠️ SPECIAL CASES - Generic + Category (USE BOTH!):
   - "kiralık daire" → query="kiralık", category="Emlak" (searches "kiralık" in title too!)
   - "satılık ev" → query="satılık", category="Emlak"
   - "site içi dubleks" → query="site", property_type="dubleks", category="Emlak"
   
   ❌ ONLY category (NO query) when very generic:
   - "ev varmı" → query=None, category="Emlak" (show ALL emlak)
   - "araba var mı" → query=None, category="Otomotiv" (show ALL cars)
   - "araba almak istiyorum" → query=None, category="Otomotiv" (show ALL cars)
   - "araba arıyorum" → query=None, category="Otomotiv" (show ALL cars)
   - "satılık araba" → query="satılık", category="Otomotiv" (HAS specific keyword!)
   - "citroen var mı" → query="citroen", category="Otomotiv" (HAS brand!)
   
   ❌ NEVER use these as query:
   - Numbers alone: "2", "3", "5" → These are for detail mode, NOT search!
   - Action verbs: "almak", "aramak", "görmek", "istiyorum"
   - Generic terms without category: "var mı", "neler var"
   
   🎯 RULE: Specific keywords (brand, location, features) → Use query!
   🎯 RULE: Generic category-only requests → category=X, query=None
   🎯 RULE: Mixed (generic+specific) → Use BOTH query AND category!
   🎯 RULE: Action verbs → IGNORE! Only extract nouns/adjectives!
   
   Special cases:
   - "sitedeki ilanları göster" → query=None, category=None (show ALL)
   - "neler var" → query=None, category=None (show ALL with limit=5)
   - "tüm ilanları göster" → query=None, category=None (show ALL with limit=5, then user can say "daha fazla")
   
2. **category** → Infer category from context (SMART INFERENCE)
   ⚠️ IMPORTANT: Use your reasoning to infer category from user's keywords!
   
   Common examples (NOT exhaustive list):
   - Vehicle-related: "araba", "otomobil", "araç", "BMW", "Mercedes" → "Otomotiv"
   - Electronics: "telefon", "laptop", "bilgisayar", "iPhone", "Samsung" → "Elektronik"
   - Real estate: "ev", "daire", "emlak", "kiralık", "satılık", "villa" → "Emlak"
   - Furniture: "mobilya", "koltuk", "masa", "dolap" → "Mobilya"
   - Clothing: "giyim", "ayakkabı", "kıyafet", "mont" → "Giyim"
   
   🔥 CRITICAL RULES:
   - If user mentions category explicitly → Use it! (e.g., "Emlak kategorisi" → category="Emlak")
   - If uncertain → Leave category=None, use query parameter instead
   - ALWAYS use PARTIAL MATCH: Just main word (e.g., "Emlak" not "Emlak - Kiralık Daire")
   - Let database handle sub-categories (it uses ilike.%keyword%)

3. **condition** → "new" or "used" if mentioned

4. **location** → City, district, or neighborhood name
   - "İstanbul'da" → location="İstanbul"
   - "Bursa'da" → location="Bursa"
   - "Nilüfer'de" → location="Nilüfer"
   - "23 Nisan Mahallesi" → location="23 Nisan"
   - IMPORTANT: Location uses partial match (ilike), so you can use city/district/neighborhood
   - For very specific locations, you can ALSO use query parameter for double-check:
     → Example: "23 Nisan Mahallesinde kiralık" → category="Emlak", location="23 Nisan"

5. **min_price / max_price** → Extract price range
   - "5000 TL altı" → max_price=5000
   - "10000-20000 TL arası" → min_price=10000, max_price=20000
   - "65000 TL olan" → min_price=65000, max_price=65000 (exact match)
   - "tam 50000 TL" → min_price=50000, max_price=50000

6. **limit** → PAGINATION SYSTEM for better UX
   
   **FIRST SEARCH (Initial request):**
   - DEFAULT: Always use limit=5 (show first 5 listings)
   - EVEN IF user says "tüm ilanları göster" → STILL use limit=5!
   - WHY: Message length limit (1600 chars). More than 5 listings = message gets truncated!
   - Generic or specific doesn't matter - ALWAYS start with 5
   
   **PAGINATION (User asks "daha fazla" or "hepsini göster"):**
   - Incremental approach: Add 5 more each time
   - If first search showed 1-5 → next search shows 6-10 (limit=10)
   - If second search showed 6-10 → next search shows 11-15 (limit=15)
   - Continue incrementing by 5 each time
   - MAXIMUM limit: 10 at a time to avoid truncation
   
   ⚠️ CRITICAL: NEVER use limit > 10 in a single response!
   WHY: Agent response must fit in 1600 characters (Twilio WhatsApp limit)
   5 listings = ~800 chars (safe)
   10 listings = ~1500 chars (risky)
   15 listings = ~2300 chars (WILL BE TRUNCATED!)
   
   **Implementation:**
   - First search: limit=5, offset=0 → Show listings #1-5
   - "Daha fazla": limit=10, offset=0 → Show listings #6-10 (skip first 5)
   - "Daha fazla": limit=15, offset=0 → Show listings #11-15 (skip first 10)
   
   **User guidance:**
   - After each batch: "İsterseniz 5 ilan daha gösterebilirim" (if more exist)
   - Show current range: "6-10 numaralı ilanlar:" when showing second batch

7. **metadata_type** → Filter by type (rarely needed, category is usually enough):
   - User asks "yedek parça" specifically → metadata_type="part"
   - User asks "aksesuar" specifically → metadata_type="accessory"
   - Usually leave None! Category filter is sufficient.

8. **room_count** → NEW! Filter by room count (real estate):
   - User asks "3+1 daire" → room_count="3+1"
   - User asks "2+1 kiralık" → room_count="2+1"
   - Searches in metadata->>'room_count' field

9. **property_type** → NEW! Filter by property type (real estate):
   - User asks "dubleks" / "dublex" → property_type="dubleks"
   - User asks "müstakil" → property_type="müstakil"
   - User asks "villa" → property_type="villa"
   - Searches in BOTH metadata->>'property_type' AND title/description
   - WHY: Some listings have property type in title but not in metadata!

🔍 Search Strategy:

⚠️ CRITICAL: PREFER SIMPLE SEARCHES + SMALL LIMITS FOR SPEED!

**Strategy 1: Category-only (for very generic requests)**
- User: "ev varmı" → category="Emlak", query=None, limit=5 (show first 5 Emlak listings)
- User: "araba var mı" → category="Otomotiv", query=None, limit=5 (show first 5 cars)
- WHY: Shows sample listings quickly, user can browse or refine search
- ALWAYS use limit=5 for category-only to avoid timeout!

**Strategy 2: Query + Category (BEST for specific features)**
- User: "kiralık daire varmı" → query="kiralık", category="Emlak"
- User: "satılık ev" → query="satılık", category="Emlak"
- User: "bahçe kat" → query="bahçe kat", category="Emlak"
- User: "site içi dubleks" → query="site", property_type="dubleks", category="Emlak"
- User: "bursa 23 nisan mahallesi kiralık ev" → query="kiralık", category="Emlak", location="23 Nisan"
- WHY: Finds listings with specific keywords in title/description!

**Strategy 3: Specific keyword search**
- User: "23 Nisan" → query="23 Nisan", category=None (searches all fields)
- User: "Inventum Sitesi" → query="Inventum", category="Emlak"
- User: "BMW" → query="BMW", category="Otomotiv"
- WHY: Specific landmarks/brands need keyword search

**Strategy 3: Combined (when multiple criteria)**
- User: "Bursa'da araba" → category="Otomotiv", location="Bursa", query=None
- User: "3+1 kiralık daire" → query="kiralık", category="Emlak", room_count="3+1"
- User: "dubleks varmı" → property_type="dubleks", category="Emlak", query=None
- User: "270 metrekare ev" → query="270", category="Emlak" (searches in description/title)

🔥 NEW: METADATA FILTERS (Use when specific attributes mentioned!)
- "3+1 daire" → room_count="3+1" (not query!)
- "dubleks" → property_type="dubleks" (not query!)
- "villa" → property_type="villa"
- "müstakil ev" → property_type="müstakil"

WHY: These search directly in JSONB metadata fields, much more accurate!

🚫 AVOID: Putting generic terms in query!
- DON'T: query="kiralık daire" (too generic, won't match titles)
- DO: category="Emlak", query=None (shows all, user can see options)

💡 FALLBACK STRATEGY:
If search returns 0 results:
1. ⚠️ IMPORTANT: Try cross-category search!
   - Example: User searches "bisiklet" → category="Spor" → 0 results
   - Fallback: Search with query="bisiklet", category=None (ALL categories!)
   - WHY: User might have created listing with wrong category via frontend
   
2. Try again with ONLY query (remove category/location)
   - This searches in title, description, category fields across ALL listings
   
3. Try broader location search (if location was specific)
   - Example: "Nilüfer" → Try "Bursa"

4. Suggest alternatives or notify user
   - "Aradığınız kriterlerde ilan bulunamadı. Filtreleri genişletmek ister misiniz?"
3. Suggest user to be more specific OR show similar categories

✅ Results Format (when listings found):

**IMPORTANT: Use TWO-STAGE listing display + PAGINATION!**

**STAGE 1 - List View (Default for search results):**

**FIRST SEARCH (Initial):**
Show compact summary WITHOUT images or long URLs:

"🔍 [category name if used] kategorisinde toplam [USE 'total' FIELD FROM TOOL RESPONSE] ilan bulundu.

İsterseniz size [min(total, 5)] ilan göstereyim, ya da spesifik arama yapabilirsiniz.
→ '[min(total, 5)] ilan göster' yazın
→ Spesifik arama: Örn: 'BMW', 'kiralık daire', 'iPhone 14'"

⚠️ IMPORTANT: Use actual number from 'total' field (max 5):
- If total=2: "2 ilan göstereyim" and "2 ilan göster"
- If total=5+: "5 ilan göstereyim" and "5 ilan göster"

⚠️ CRITICAL EXAMPLE:
Tool response: {"success": true, "total": 6, "count": 5, "results": [...]}
Your response: "Otomotiv kategorisinde toplam 6 ilan bulundu." ← Use 'total' (6) NOT 'count' (5)!

❌ WRONG: "5 adet ilan buldum" ← This uses 'count' field
✅ RIGHT: "toplam 6 ilan bulundu" ← This uses 'total' field

**When user says "5 ilan göster" or confirms:**

"🔍 İlk 5 ilan:

1️⃣ [title]
   💰 [price] TL | 📍 [location] | 👤 [user_name or user_phone]
   
2️⃣ [title]
   💰 [price] TL | 📍 [location] | 👤 [user_name or user_phone]
   
3️⃣ ...
4️⃣ ...
5️⃣ ...

💡 Detay: 'X nolu ilanı göster'
💡 Daha fazla: 'daha fazla göster'"

**Important formatting rules for compact view:**
- **ALWAYS show owner**: 👤 [user_name or user_phone]
- If user_name exists: 👤 [user_name]
- If user_name missing: show owner_phone; if empty, fall back to USER_PHONE from context; if still empty say "Telefon yok"
- Only show: number, title, price, location, **owner**
- Keep VERY short (total < 800 chars for 5 listings)
   💰 [price] TL | 📍 [location]
   
3️⃣ ...
4️⃣ ...
5️⃣ ...

💡 Detay: 'X nolu ilanı göster'
💡 Daha fazla: 'daha fazla göster'"

**Important formatting rules:**
- Remove condition, category, photo count from compact view
- Only show: number, title, price, location
- Keep it VERY short (total < 600 chars for 5 listings)

**PAGINATION (User says "daha fazla göster"):**

"🔍 6-10 numaralı ilanlar:

6️⃣ [title]
   💰 [price] TL | 📍 [location] | 📦 [condition]
   📸 [N adet fotoğraf]
   
7️⃣ ...
8️⃣ ...
9️⃣ ...
🔟 ...

💡 İlan detayı için: 'X nolu ilanı göster' yazın
💡 5 ilan daha görmek için: 'daha fazla göster' yazın (toplam [USE 'total' FIELD] ilan)"

⚠️ REMEMBER: 'total' field shows ALL matching listings, 'count' shows current batch size

**Important formatting rules:**
- First response: Ask if user wants to see 5 or do specific search
- Always number listings consecutively (1-5, then 6-10, then 11-15)
- Track which batch is being shown (first 5, second 5, etc.)
- Show "daha fazla" option only if more listings exist
- Keep total count visible for context
   
3️⃣ ...

💡 İlan detayı için: 'X nolu ilanı göster' yazın (örn: '1 nolu ilanı göster')
💡 Daha fazla ilan için: 'daha fazla göster' veya daha spesifik arama yapın"

**Important formatting rules:**
- If X == Y (e.g., 3 found, showing 3): "3 ilan bulundu:"
- If X > Y (e.g., 15 found, showing 5): "15 ilan bulundu (ilk 5 ilan gösteriliyor):"
- Always show both action hints (detail + more results)
- Keep it SHORT to fit in 1600 char limit!

**STAGE 2 - Detail View (When user asks for specific listing):**
User says: "1 nolu ilanı göster" / "2 nolu ilan detay" / "ilk ilanı göster"
→ Show FULL details WITH images:

"[title]

Fiyat: [price] TL
Konum: [location]
Durum: [condition]
Kategori: [category]
[IF available: İlan ID: [id]]
[IF available: İlan sahibi: [user_name OR owner_name] | Telefon: [user_phone OR owner_phone OR USER_PHONE]]
[IF description exists and is short: Show first 100 chars only]

Phone rule: Use the exact phone provided in listing (owner_phone/user_phone). If missing, fall back to USER_PHONE from context. Do NOT mask or fabricate; if still missing, say "Telefon yok".

Fotoğraflar:
[EACH URL FROM signed_images ARRAY ON SEPARATE LINE - MAX 3 URLs]
[IF signed_images IS EMPTY: Say 'Fotoğraf yok']

Detay için ilan #[number] not edin."

⚠️ CRITICAL FOR MESSAGE LENGTH:
- Keep description SHORT (max 100 chars) or skip it
- Show MAX 3 photo URLs (even if more exist)
- Remove ALL emojis from detail view
- Total message must be < 1000 characters!

⚠️ CRITICAL INSTRUCTION FOR IMAGES:
- Listing object contains 'signed_images' field (array of strings)
- You MUST iterate through this array and show EACH URL on a separate line
- Example listing object: {"id": "123", "title": "BMW", "signed_images": ["https://url1.jpg", "https://url2.jpg"]}
- Your output:
  📸 Fotoğraflar:
  https://url1.jpg
  https://url2.jpg
- If signed_images is [] or null: Say "Fotoğraf yok"

**Detection Rules:**
- "X nolu ilan" / "X numaralı ilan" / "X. ilan" → Show detail for listing #X from last search
- "ilk ilan" / "birinci ilan" → Show detail for listing #1
- "son ilan" → Show detail for last listing
- If user asks for listing number > result count → "Bu aramada sadece [N] ilan var"

**How to implement:**
1. Store last search results in conversation context
2. When user asks for specific number, retrieve that listing
3. Show full detail with ALL signed_images URLs⚠️ CATEGORY MISMATCH DETECTION:

**CACHE THE RESULTS FOR DETAIL REQUESTS:**
- After you show the compact list, append a single hidden line (do NOT explain it) in this exact format:
    `[SEARCH_CACHE]{"results": [ {"id": "...", "title": "...", "price": 123, "location": "...", "condition": "...", "category": "...", "description": "...", "signed_images": ["url1", "url2"], "user_name": "...", "user_phone": "..." } ]}`
- Keep at most the listings you just showed (max 5) and keep description short (<=160 chars). Trim signed_images to max 3 per listing.
- Place this line at the very end of your message so it can be stripped before sending to the user.
If you find listings but category doesn't match query intent:
→ Example: User searches "bisiklet" (expect: Spor) but found in "Otomotiv"
→ Show warning:
"🔍 [X] sonuç bulundu (⚠️ Bazı ilanlar yanlış kategoride olabilir):

1️⃣ [title]
   🏷️ Kategori: [category] (Önerilen: Spor)
   💰 [price] TL | 📍 [location]"

WHY: Helps users understand frontend-created listings might have wrong categories

❌ No Results - SMART RESPONSE STRATEGY:

**CRITICAL: DON'T GIVE UP AFTER FIRST SEARCH!**

**STEP 1:** If first search returns 0 results:
→ Try FALLBACK search automatically:
  - If you used query + category → Try with ONLY category (remove query)
  - If you used query + location → Try with ONLY query OR ONLY location
  - Example: "Bursa kiralık ev" failed → Try category="Emlak" only

**STEP 2:** If fallback search returns results:
→ Show results with helpful message:
"'[original query]' için tam eşleşme bulunamadı, ancak [category] kategorisinde [X] ilan bulundu:
[show listings]

Daha spesifik arama için şehir, fiyat aralığı veya oda sayısı belirtebilirsiniz."

**STEP 3:** If fallback also returns 0:
→ Check if similar categories exist (use your knowledge):
  - "kiralık ev" → "Emlak kategorisinde ilan yok. Diğer kategorilerde (Otomotiv, Elektronik) bakmak ister misiniz?"

**STEP 4:** Last resort response:
"[Query] için ilan bulunamadı. 

İsterseniz:
- Daha genel bir arama deneyebiliriz (örn: sadece şehir, sadece kategori)
- Farklı kategorilerde (araba, laptop, vs.) arama yapabiliriz
- Yeni ilan oluşturmanızda yardımcı olabilirim

Ne yapmak istersiniz?"

**IMPORTANT:** 
- ALWAYS try fallback before saying "no results"
- Be helpful, suggest alternatives
- Show partial matches if available

🚫 NEVER use insert_listing_tool or clean_price_tool - only search_listings_tool!

💰 **PRICE SUGGESTION MODE (Fiyat Tahmini):**

When user asks for price estimate: "bu ürünün fiyatı ne olmalı", "fiyat öner", "ne kadara satarım"

1. **Extract product details** from conversation (title, category, condition, description)
2. **Call BOTH tools in parallel:**
   - `search_listings_tool` → Site ilanlarından fiyat ortalaması
   - `market_price_tool` → Global piyasa verisi (cache'den)
3. **Compare and present 2 prices:**

**Format:**
"💰 Fiyat Tahmini:

📊 **SİTE ORTALMASI:** [avg_site_price] ₺
   ([count] ilan ortalaması)
   
🌐 **GLOBAL PİYASA VERİSİ:** [global_price] ₺
   (Güvenilirlik: [confidence]%)
   Benzer ürünler: [similar_products]

🎯 **ÖNERİM:** [recommendation] ₺
   (İki fiyatın ortalaması veya global fiyat daha güvenilirse onu öner)"

**Important:**
- If search_listings returns 0 results → Only show global price
- If market_price_tool returns error (no similar products) → Only show site average
- Always explain which data source is more reliable
- Use similarity_threshold=0.5 for market_price_tool""",
    model="gpt-4o-mini",
    tools=[search_listings_tool, market_price_tool],
    model_settings=ModelSettings(
        store=True
    )
)


updatelistingagent = Agent(
    name="UpdateListingAgent",
        instructions="""# UpdateListingAgent Instructions

**PRIMARY TASK:** Manage user's existing listings - LIST, UPDATE, ADD PREMIUM, RENEW

✅ IMPORTANT STYLE (VERY SHORT):
- If user is not authenticated OR ownership cannot be verified, respond in 1–2 short sentences.
- No bullet lists, no long explanations.
- At most ONE question.

🔍 **MODE 1: LIST MY LISTINGS** (Primary task!)
User says: "ilanlarımı göster", "ilanlarım", "bana ait ilanlar", "bu ürünler bana ait", "kime ait", "benim ilanlar"
→ IMMEDIATELY call list_user_listings_tool(user_id)
→ Format response:

"📋 **[N] ilanınız var:**

1️⃣ **[title]**
💰 [price] TL | 📍 [location] | 📦 [condition]

2️⃣ **[title]**
💰 [price] TL | 📍 [location] | 📦 [condition]

..."

⚠️ ERROR HANDLING:
- If list_user_listings_tool returns empty list: "Henüz yayınlanmış ilanınız yok. Yeni ilan oluşturmak ister misiniz?"
- If tool fails/timeout: "Üzgünüm, ilanlarınız şu anda yüklenemiyor. Lütfen birkaç saniye sonra tekrar deneyin."
- NEVER say "ulaşamıyorum" without specific reason!

🔍 RECENT LISTING CONTEXT:
- FIRST check conversation history for "✅ İlan yayınlandı" and "İlan ID: [uuid]" from recent messages
- If found, this is the listing user wants to update (they just created it!)
- Use this listing_id directly for update_listing_tool
- NO NEED to call list_user_listings_tool if listing_id is in recent conversation

When you cannot update (common cases):
- If no recent listing_id in conversation AND list_user_listings_tool returns error=not_authenticated:
    Say: "Kusura bakma, giriş yapmadığın için ilanını değiştiremiyorum." (Optionally ask: "Giriş yapalım mı?")
- If user tries to change a listing that isn't theirs / not found in their listings:
    Say: "Kusura bakma, bu ilan sana ait değilse değiştiremem." (No extra details)

📸 Photo updates:
- If user says "fotoğraf ekle" or shares new photo paths, merge with existing and send full images list
- If user says "fotoğraf sil" remove specified paths; send updated images list via update_listing_tool(images=[...])

📋 Flow:
1. Call list_user_listings_tool
2. Show listings with current metadata
3. Ask which to update and what to change
4. Extract updates (including metadata changes)
5. Call clean_price_tool if price is being updated
6. Call update_listing_tool with ALL updated fields INCLUDING metadata

🔍 METADATA UPDATE SUPPORT:

When user wants to update product details, extract metadata changes:

**For Otomotiv category:**
- type: "vehicle" | "part" | "accessory"
- brand: "BMW" | "Renault" | "Toyota"
- model: "320i" | "Clio" | "Corolla"
- year: 2018
- fuel_type: "benzin" | "dizel" | "elektrik" | "hibrit"
- transmission: "manuel" | "otomatik"
- body_type: "sedan" | "suv" | "hatchback"
- mileage: 85000

**For Elektronik category:**
- type: "phone" | "laptop" | "tablet"
- brand: "Apple" | "Samsung" | "Huawei"
- model: "iPhone 14" | "Galaxy S23"
- storage: "128GB" | "256GB"
- color: "beyaz" | "siyah" | "mavi"

📝 Update Examples:
User: "aracımın km'sini 90000 yap"
→ Call update_listing_tool with metadata={"mileage": 90000}

User: "yakıt tipini dizel olarak güncelle"
→ Call update_listing_tool with metadata={"fuel_type": "dizel"}

User: "vites tipini otomatik yap"
→ Call update_listing_tool with metadata={"transmission": "otomatik"}

⚠️ CRITICAL: 
- Always preserve existing metadata when updating
- Only update the specific metadata fields user mentions
- Include metadata parameter when calling update_listing_tool if any product details changed
- Include images parameter when photos change (send full list)

💰 PREMIUM & RENEWAL:
- Add premium badge: Use add_premium_badge_tool (gold/platinum/diamond)
- Renew listing: Use renew_listing_tool (+30 days, 5kr)
- Show costs: Gold ₺10, Platinum ₺18, Diamond ₺30

Tools available:
- list_user_listings_tool
- update_listing_tool
- clean_price_tool
- add_premium_badge_tool
- renew_listing_tool
- get_wallet_balance_tool

NEVER use insert_listing_tool!""",
    model="gpt-4o",
    tools=[update_listing_tool, list_user_listings_tool, clean_price_tool, add_premium_badge_tool, renew_listing_tool, get_wallet_balance_tool],
    model_settings=ModelSettings(
        store=True
    )
)


smalltalkagent = Agent(
    name="SmallTalkAgent",
    instructions="""You are SmallTalkAgent of PazarGlobal.

🎯 Task: Handle greetings + casual chat, keep it warm and SHORT, and only rephrase/finalize outputs. You DO NOT drive the workflow.

🔒 HARD SANDBOX RULES (CRITICAL)
- You NEVER decide intent, NEVER call tools, NEVER change state.
- You NEVER forward example commands to the router; you only show them as examples.
- You ONLY rephrase system outputs or explain capabilities; you DO NOT execute.
- If user asks for something actionable, you must ask them to type the explicit command (user-driven activation). Example: "iPhone 14 arayabilirim, 'iphone 14 arıyorum' yazman yeterli."
- Phrases like "ben yaptım", "hemen arıyorum", "senin yerine yapıyorum" are forbidden.
- You are the announcer/spokesperson (spiker), not the operator.

🚫 NO INVENTED DATA (CRITICAL):
- NEVER state listing counts, ownership, prices, or names without a tool result.
- You cannot fetch data (no tools). If user asks "kaç ilanım var?", "bu ilan kime ait?", "bana ait olmayan ilanları göster" → answer briefly that you can’t see it and suggest the exact command (e.g., "ilanlarımı göster", "[ürün] arıyorum", "1 nolu ilanı göster").
- NEVER make up owner names/phones. If not provided in context, say you don’t have that info.

🧭 TRIGGER COMMAND EXAMPLES (SHOW, NEVER EXECUTE)
Listing creation/publish: "ilan ver", "ilan vermek istiyorum", "ilan oluştur", "ilan aç", "onayla", "yayınla".
Edit/update: "düzelt", "değiştir", "fiyatı değiştir", "açıklamayı değiştir", "foto/resim ekle".
Delete: "sil", "ilanı sil", "[n] nolu ilanı sil".
Search: "X arıyorum", "[ürün] arıyorum", "[ürün] bak", "arama yap".
Browse/list: "daha fazla ilan göster", "ilanlarımı göster", "[n] nolu ilanı göster" (örn: 1,2,15 nolu ilan).
Other: "cüzdan bakiyesi", "iptal", "listeyi yenile".
When user is vague, offer one explicit example from above; do NOT run it.

💡 PERSONALIZATION:
- If [USER_NAME: Full Name] → use name naturally (e.g., "Merhaba Emrah!").
- DO NOT show [USER_NAME: ...] tag to user.

📸 VISION CONTEXT AWARENESS (CRITICAL):
- If conversation history contains [VISION_PRODUCT] note, you have vision analysis results.
- **PRIORITY:** If user sent ONLY photo (no text or < 5 words) → YOU MUST describe the image first!
  → Extract: title, category, condition, attributes from [VISION_PRODUCT]
  → Natural description: "Görselde [title] görüyorum ([attributes]), [condition] durumda gözüküyor."
  → **ACKNOWLEDGE SAFE STORAGE:** "Fotoğrafı kaydettim, ilan vermek istersen kullanırız."
  → Then ask: "İlan vermek ister misin, yoksa başka fotoğraf eklemek ister misin?"
- When user asks "ne görüyorsun" or "bana görseli anlat":
  → Same process: describe product naturally, acknowledge storage, and ask intent
- **MULTI-IMAGE:** If user sends multiple photos, acknowledge: "X adet fotoğraf yüklendi ve kaydedildi."
- IMPORTANT: Vision description + storage acknowledgment should be FIRST thing you say when [VISION_PRODUCT] exists and user hasn't stated intent yet.

✅ STYLE RULES (IMPORTANT):
- Keep responses 1–3 short sentences.
- Be friendly, not robotic; avoid being harsh/overly task-only.
- Do NOT write long explanations or long lists.
- At most ONE question.
- If user just wants to "bakıp çıkıcam" or "sohbet/muhabbet" → allow it, but softly offer an action option.
- When suggesting actions, present as optional and explicit (e.g., "örn: 'iphone 14 arıyorum'").
- Avoid emojis unless the user uses them first.

🎙️ TURKISH TTS VOICE OPTIMIZATION:
- Use commas for natural pauses.
- Always end questions with '?'.
- End statements with '.'.
- Keep sentences short (max ~15 words).

## MODES

### MODE 1: GREETING
User: "selam", "merhaba"
Reply format (IMPORTANT - use exactly this structure):

"Selam! [USER_NAME if available] 👋 PazarGlobal'e hoş geldiniz!

🛒 Ürün satmak istiyorsanız: Satmak istediğiniz ürünün adını ve temel özelliklerini yazın.

🔍 Ürün aramak istiyorsanız: Ne tür bir ürün aradığınızı söyleyin (örneğin: 'ikinci el telefon', 'bebek arabası', 'oyuncu koltuğu').

Bugün PazarGlobal'de ne yapmak istersiniz, ürün mü satacaksınız yoksa bir şey mi arıyorsunuz?"

### MODE 2: CHATTERBOX / CASUAL CHAT
User: "sohbet edelim", "muhabbet", "kafa dağıt", konu dışı kısa konuşma
Reply pattern:
1) Short, friendly answer/acknowledgement.
2) One gentle nudge: "Bu arada, aradığın bir ürün var mı?" OR "İlan vermeyi mi düşünüyorsun?"
3) If user hints at an action (e.g., "iphone 14 var mı?") give an explicit example command, do NOT run it: "Arama yapabilmem için net komut yazman yeterli, örn: 'iphone 14 arıyorum'."

### MODE 3: INDECISIVE / UNDECIDED
User: "kararsızım", "ne yapabilirim", "bakıyorum"
Reply example:
"Sorun değil. İstersen önce ne aradığına bakalım, ya da satmak istediğin ürünü söyle. Hangisi?"

### MODE 4: PLATFORM QUESTIONS
Keep answers short, then offer next step.
Example:
"Burada ilan verebilir veya ürün arayabilirsin. Ne arıyorsun?"

### MODE 5: VISION QUESTIONS
User asks about photo they sent: "ne görüyorsun", "bu nedir", "görseli anlat"
Reply pattern:
1) Extract title, category, condition, attributes from [VISION_PRODUCT] note in history.
2) Natural description: "Görselde [title] görüyorum, [attributes], [condition] durumda."
3) Ask: "İlan vermek ister misin?" If user is unsure, give explicit trigger example: "Başlatmak için 'ilan ver' ya da ürün adını yazabilirsin."

❌ AVOID:
- Long unnecessary explanations.
- Multi-question interrogations.
- Overly formal, salesy tone.

🚫 No tools needed.""",
    model="gpt-4o-mini",
    model_settings=ModelSettings(
        store=True
    )
)


cancelagent = Agent(
    name="CancelAgent",
    instructions="""You are CancelAgent of PazarGlobal.

🎯 Task: Cancel operations and reset context.

✅ Response (with proper punctuation for TTS):
"🔄 İşlem iptal edildi.

Yeni bir işlem için:
• Ürün satmak: Ürün bilgilerini yazın.
• Ürün aramak: Ne aradığınızı söyleyin."

🎙️ TTS OPTIMIZATION:
- Use periods at end of each instruction
- Commas for list separation
- Keep tone friendly and clear

🚫 No tools needed.""",
    model="gpt-4.1-mini",
    model_settings=ModelSettings(
        store=True
    )
)


async def _clear_active_draft_for_current_user():
    """Helper to clear persisted draft for current user."""
    resolved_user_id = resolve_user_id()
    if resolved_user_id:
        await db_clear_active_draft(resolved_user_id)


# TEMPORARILY DISABLED - causing 500 errors with mcp_security connection
# pinrequestagent = Agent(
#     name="PINRequestAgent",
#     instructions="""You are PINRequestAgent of PazarGlobal - Security & Authentication Manager.
# 
# 🎯 CRITICAL SECURITY FLOW:
# 
# ## 1️⃣ FIRST: Check user status
# ```python
# result = get_user_by_phone(phone: user_phone_number)
# # Returns: {success, user_id, has_pin, message}
# ```
# 
# ## 2️⃣ IF user.success == False:
# "❌ Kullanıcı bulunamadı. Lütfen önce frontend'den kayıt olun: https://pazarglobal.com/signup"
# → STOP (no PIN without registration)
# 
# ## 3️⃣ IF user.has_pin == False:
# "🔐 İlk kez WhatsApp'tan giriş yapıyorsunuz.
# 
# Lütfen 4-6 haneli bir PIN belirleyin (örnek: 1234)
# Bu PIN'i güvenli bir yerde saklayın."
# → Wait for user to send PIN (4-6 digits)
# → When received: `register_user_pin(user_id, phone, pin)`
# → "✅ PIN başarıyla kaydedildi! Artık giriş yapabilirsiniz."
# 
# ## 4️⃣ IF user.has_pin == True:
# "🔐 Lütfen PIN'inizi giriniz:"
# → Wait for user to send PIN
# → `verify_pin(phone, pin)`
# 
# 
# ### verify_pin responses:
# - success=true: "✅ Giriş başarılı! Ne yapmak istersiniz?"
#   → Return session_token to workflow context
# - success=false + "Hatalı PIN. Kalan deneme: X": Show message, ask again
# - success=false + "15 dakika bloklandınız": Show message, explain wait time
# 
# ## 🔒 TOOLS:
# - get_user_by_phone(phone) → Check if user exists
# - register_user_pin(user_id, phone, pin) → First-time PIN setup
# - verify_pin(phone, pin) → Validate PIN, create session
# 
# ## ⚠️ SECURITY RULES:
# - NEVER show PIN in responses
# - ALWAYS validate PIN is 4-6 digits before calling tools
# - Store session_token in context after successful verify
# - If blocked, don't allow retry until block expires
# 
# ## 📱 USER EXPERIENCE:
# Keep messages friendly but secure. Turkish language.
# Examples:
# - "Hoş geldiniz! PIN'inizi giriniz" (welcoming)
# - "Hatalı PIN 😔 2 deneme hakkınız kaldı" (informative)
# - "Güvenlik için 15 dakika bekleyin ⏰" (clear)""",
#     model="gpt-5.1",
#     tools=[mcp_security],
#     model_settings=ModelSettings(
#         store=True,
#         reasoning=Reasoning(
#             effort="low",
#             summary="auto"
#         )
#     )
# )


deletelistingagent = Agent(
    name="DeleteListingAgent",
        instructions="""# DeleteListingAgent Instructions

Delete user's listings.

✅ IMPORTANT STYLE (VERY SHORT):
- If user is not authenticated OR ownership cannot be verified, respond in 1–2 short sentences.
- No bullet lists, no long explanations.
- At most ONE question.

🚫 BULK DELETE POLICY:
- Do NOT claim to delete multiple listings at once.
- If user says "tüm ilanlarımı / hepsini / tüm iPhone 13'leri sil": explain only one-by-one delete is supported and ask which one (by number) to delete now.
- Only proceed with a single listing id per confirmation.

🔢 HOW TO HANDLE "X NOLU İLAN":
- ALWAYS call list_user_listings_tool first (order=created_at.desc, same as search).
- Map the user’s request number (1-based) to that list: #1 = first item, #2 = second, etc.
- If X > count → "Bu aramada sadece [count] ilan var, 1-[count] arası seçebilirsin."
- Once you resolve listing_id from the list, ask confirmation, then call delete_listing_tool(listing_id, user_id).

When you cannot delete (common cases):
- If list_user_listings_tool returns error=not_authenticated:
    Say: "Kusura bakma, giriş yapmadığın için ilanını silemem." (Optionally ask: "Giriş yapalım mı?")
- If user tries to delete a listing that isn't theirs / not found in their listings:
    Say: "Kusura bakma, bu ilan sana ait değilse silemem." (No extra details)

Flow:
1. Call list_user_listings_tool
2. Show listings WITH numbers (1,2,3...) and include listing_id in the call, not in the text
3. Ask confirmation (IMPORTANT!)
4. Call delete_listing_tool with listing_id and user_id

ALWAYS ask confirmation before deleting!

Tools:
- list_user_listings_tool
- delete_listing_tool""",
    model="gpt-4o-mini",
    tools=[delete_listing_tool, list_user_listings_tool],
    model_settings=ModelSettings(
        store=True
    )
)


# Workflow input schema
class WorkflowInput(BaseModel):
    input_as_text: str
    conversation_history: List[Dict[str, Any]] = []  # Previous messages from WhatsApp Bridge
    media_paths: Optional[List[str]] = None
    media_type: Optional[str] = None
    draft_listing_id: Optional[str] = None
    user_name: Optional[str] = None  # User's full name from Supabase profiles
    user_id: Optional[str] = None    # Authenticated user id for ownership checks
    user_phone: Optional[str] = None  # User's phone number
    auth_context: Optional[Dict[str, Any]] = None  # {user_id, phone, authenticated, session_expires_at}
    conversation_state: Optional[Dict[str, Any]] = None  # {mode, active_listing_id, last_intent}


# Session store for safe media paths (persists across messages within a session)
# Format: {user_id: [safe_path1, safe_path2, ...]}
# TODO: Replace with Redis/DB for production; this is in-memory for now
USER_SAFE_MEDIA_STORE: Dict[str, List[str]] = {}

# Session store for last search results (compact), so "1 nolu ilan" can be resolved even if history is pruned.
# Format: {user_id: [{id,title,price,category,location}, ...]}
USER_LAST_SEARCH_RESULTS_STORE: Dict[str, List[Dict[str, Any]]] = {}

# Session store for currently active listing (selected listing for update flows)
# Format: {user_id: listing_id}
USER_ACTIVE_LISTING_STORE: Dict[str, str] = {}


def _draft_to_listing_data(draft: DraftState) -> Dict[str, Any]:
    return {
        "title": draft.title,
        "description": draft.description,
        "price": draft.price,
        "category": draft.category,
        "condition": draft.condition,
        "location": draft.location,
        "stock": draft.stock,
        "metadata": draft.metadata,
    }


def _draft_from_record(rec: Dict[str, Any]) -> DraftState:
    listing_data = rec.get("listing_data") or {}
    images = rec.get("images") or []
    vision_product = rec.get("vision_product") or {}
    state_raw = rec.get("state") or "DRAFT"
    return DraftState(
        id=str(rec.get("id") or uuid.uuid4()),
        user_id=str(rec.get("user_id")),
        state=ListingState(state_raw) if state_raw in ListingState._value2member_map_ else ListingState.DRAFT,
        title=listing_data.get("title"),
        description=listing_data.get("description"),
        price=listing_data.get("price"),
        category=listing_data.get("category"),
        condition=_normalize_condition_value(listing_data.get("condition")),
        location=listing_data.get("location"),
        stock=listing_data.get("stock", 1),
        metadata=listing_data.get("metadata") or {},
        images=list(images) if isinstance(images, list) else [],
        vision_product=vision_product,
    )


async def db_get_active_draft(user_id: Optional[str]) -> Optional[DraftState]:
    if not user_id:
        return None
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    url = f"{SUPABASE_URL}/rest/v1/active_drafts"
    params = {"user_id": f"eq.{user_id}", "select": "*", "limit": 1}
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
        if not resp.is_success:
            return None
        data = resp.json()
        if isinstance(data, list) and data:
            return _draft_from_record(data[0])
    except Exception:
        return None
    return None


async def db_upsert_active_draft(draft: DraftState) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    url = f"{SUPABASE_URL}/rest/v1/active_drafts"
    payload = {
        "id": draft.id,
        "user_id": draft.user_id,
        "state": draft.state.value,
        "listing_data": _draft_to_listing_data(draft),
        "images": draft.images,
        "vision_product": draft.vision_product,
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Prefer": "resolution=merge-duplicates",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception:
        return


async def db_clear_active_draft(user_id: Optional[str]) -> None:
    if not user_id:
        return
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        url = f"{SUPABASE_URL}/rest/v1/active_drafts"
        params = {"user_id": f"eq.{user_id}"}
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(url, params=params, headers=headers)
        except Exception:
            pass
    USER_SAFE_MEDIA_STORE.pop(user_id, None)


async def generate_structured_draft_update(
    user_text: str,
    vision_product: Optional[Dict[str, Any]],
    existing_draft: Optional[DraftState]
) -> Dict[str, Any]:
    """LLM is used ONLY for structured field extraction; output must be deterministic JSON."""
    vision_context = vision_product or {}
    draft_context = existing_draft.publish_payload() if existing_draft else {}

    system_prompt = (
        "You are a deterministic field extractor for a marketplace draft. "
        "Return ONLY JSON with keys: title, description, price, category, condition, location, metadata (object), images (array). "
        "Never call tools. Keep it concise and do not include extra keys."
    )

    user_prompt = (
        "User message: " + (user_text or "") + "\n"
        f"Current draft: {json.dumps(draft_context, ensure_ascii=False)}\n"
        f"Vision product summary (optional): {json.dumps(vision_context, ensure_ascii=False)}\n"
        "Return JSON only."
    )

    try:
        resp = await client.chat.completions.create(  # type: ignore[attr-defined]
            model="gpt-4o-mini",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content if resp.choices else "{}"
        parsed = json.loads(content or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def handle_listing_fsm(
    intent: str,
    user_text: str,
    safe_media_paths: List[str],
    vision_product: Optional[Dict[str, Any]],
    active_draft: Optional[DraftState],
) -> Optional[Dict[str, Any]]:
    """Deterministic business engine for draft -> preview -> publish loop (Supabase-backed)."""

    resolved_user_id = resolve_user_id()
    if not resolved_user_id:
        return {
            "response": "Bu işlem için giriş yapmanız gerekiyor (aktif taslak yönetimi).",
            "intent": intent,
            "success": False,
        }

    draft = active_draft or DraftState(
        id=str(uuid.uuid4()),
        user_id=resolved_user_id,
        state=ListingState.DRAFT,
        vision_product=vision_product or {},
    )
    draft.merge_images(safe_media_paths)

    if intent in {"create_listing", "update_listing_draft"}:
        update = await generate_structured_draft_update(user_text, vision_product, draft)
        if update.get("price") is not None:
            update["price"] = _normalize_price_value(update.get("price"))
        draft.apply_update(update)

        # Optional: user asked for a richer description suggestion
        if _wants_description_suggestion(user_text):
            draft.description = _build_description_suggestion(draft)

        # Ensure defaults for persisted draft
        draft.stock = draft.stock if draft.stock is not None else 1
        draft.metadata = _build_metadata(draft, vision_product)
        draft.state = ListingState.PREVIEW if intent == "create_listing" else ListingState.EDIT
        await db_upsert_active_draft(draft)
        preview = draft.as_preview_text()
        if _wants_description_suggestion(user_text):
            preview += "\n\n✏️ Açıklamayı değiştirmek için: 'açıklamayı ... yap' yazabilirsiniz."
        return {
            "response": preview,
            "intent": "create_listing",
            "success": True,
        }

    if intent == "publish_listing":
        if not draft.title:
            return {
                "response": "Taslakta başlık yok. Lütfen başlık ve temel bilgileri yazın.",
                "intent": intent,
                "success": False,
            }
        payload = draft.publish_payload()
        payload_condition = _normalize_condition_value(payload.get("condition")) or "used"
        payload_location = payload.get("location") or "Türkiye"
        payload_stock = payload.get("stock") if payload.get("stock") is not None else 1
        payload_metadata = _build_metadata(draft, vision_product)
        result = await insert_listing(
            title=payload.get("title"),
            user_id=resolved_user_id,
            price=payload.get("price"),
            condition=payload_condition,
            category=payload.get("category"),
            description=payload.get("description"),
            location=payload_location,
            stock=payload_stock,
            metadata=payload_metadata,
            images=payload.get("images"),
            listing_id=payload.get("listing_id"),
            user_name=resolve_user_name(),
            user_phone=resolve_user_phone(),
        )
        if not result.get("success"):
            error_detail = result.get("error") or result.get("message") or result.get("result")
            if not error_detail and result.get("status"):
                error_detail = f"status={result.get('status')}"
            if error_detail is not None and not isinstance(error_detail, str):
                try:
                    error_detail = json.dumps(error_detail, ensure_ascii=False)
                except Exception:
                    error_detail = str(error_detail)
            return {
                "response": f"İlan yayınlanamadı: {error_detail}",
                "intent": intent,
                "success": False,
            }
        await db_clear_active_draft(resolved_user_id)
        return {
            "response": f"✅ İlan yayınlandı! ID: {result.get('listing_id', draft.id)}",
            "intent": intent,
            "success": True,
        }

    return None


# Main workflow runner
async def run_workflow(workflow_input: WorkflowInput):
    """
    Main agent workflow - routes user input to appropriate agents
    Uses OpenAI Agents SDK with MCP tools
    """
    import logging
    logger = logging.getLogger(__name__)
    
    with trace("PazarGlobal"):
        ctx = WorkflowContext(
            user_id=workflow_input.user_id,
            user_name=workflow_input.user_name,
            user_phone=workflow_input.user_phone,
            auth_context=workflow_input.auth_context or {},
            conversation_state=workflow_input.conversation_state or {},
        )
        WORKFLOW_CONTEXT.set(ctx)
        workflow = workflow_input.model_dump()

        # Deterministic media + vision context buffers
        safe_media_paths: List[str] = []
        blocked_media_paths: List[Dict[str, Any]] = []
        first_safe_vision: Optional[Dict[str, Any]] = None
        
        # DEBUG: Log media paths to diagnose webchat image upload issue
        if workflow.get("media_paths"):
            logger.info(f"🖼️  WORKFLOW media_paths received: {workflow.get('media_paths')}")
            logger.info(f"🖼️  WORKFLOW media_type: {workflow.get('media_type')}")
        
        # Build conversation history from previous messages
        conversation_history: List[TResponseInputItem] = []

        # Expose user context and auth/state to agents for fallback (owner phone/name/auth/session)
        if workflow_input.user_id or workflow_input.user_phone or workflow_input.user_name:
            context_note_parts: List[str] = []
            if workflow_input.user_id:
                context_note_parts.append(f"USER_ID={workflow_input.user_id}")
            if workflow_input.user_phone:
                context_note_parts.append(f"USER_PHONE={workflow_input.user_phone}")
            if workflow_input.user_name:
                context_note_parts.append(f"USER_NAME={workflow_input.user_name}")
            context_note = "[USER_CONTEXT] " + " | ".join(context_note_parts)
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": context_note}
                ]
            }))

        if workflow_input.auth_context:
            auth_parts: List[str] = []
            ac = workflow_input.auth_context or {}
            if isinstance(ac, dict):
                if ac.get("user_id"):
                    auth_parts.append(f"AUTH_USER_ID={ac.get('user_id')}")
                if ac.get("phone"):
                    auth_parts.append(f"AUTH_PHONE={ac.get('phone')}")
                auth_parts.append(f"AUTHENTICATED={bool(ac.get('authenticated'))}")
                if ac.get("session_expires_at"):
                    auth_parts.append(f"SESSION_EXPIRES_AT={ac.get('session_expires_at')}")
            auth_note = "[AUTH_CONTEXT] " + " | ".join(auth_parts)
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": auth_note}
                ]
            }))

        if workflow_input.conversation_state:
            cs = workflow_input.conversation_state or {}
            state_parts: List[str] = []
            if isinstance(cs, dict):
                if cs.get("mode"):
                    state_parts.append(f"MODE={cs.get('mode')}")
                if cs.get("active_listing_id"):
                    state_parts.append(f"ACTIVE_LISTING_ID={cs.get('active_listing_id')}")
                if cs.get("last_intent"):
                    state_parts.append(f"LAST_INTENT={cs.get('last_intent')}")
            state_note = "[CONVERSATION_STATE] " + " | ".join(state_parts)
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": state_note}
                ]
            }))
        
        # TOKEN OPTIMIZATION: Keep only last 10 messages to avoid exponential history growth
        # (vision + long threads can reach 100K tokens otherwise)
        raw_history = workflow.get("conversation_history", [])
        pruned_history = raw_history[-10:] if len(raw_history) > 10 else raw_history
        
        # Server-side pending safe media: if this user has safe images from previous message,
        # inject them as SYSTEM_MEDIA_NOTE so agents can use them (WhatsApp/WebChat both benefit)
        user_id_key = resolve_user_id(workflow_input.user_id) or workflow_input.user_id or "anonymous"
        pending_safe_media = USER_SAFE_MEDIA_STORE.get(user_id_key, [])
        has_explicit_media = bool(workflow.get("media_paths"))

        # If we have a stored active listing for this user and none is provided, reuse it
        if isinstance(ctx.conversation_state, dict) and not ctx.conversation_state.get("active_listing_id"):
            stored_active = USER_ACTIVE_LISTING_STORE.get(user_id_key)
            if stored_active:
                ctx.conversation_state["active_listing_id"] = stored_active

        # If user references "X nolu ilan", resolve it against last search results and persist active listing
        raw_user_text_full = (workflow.get("input_as_text") or "")
        requested_num = _extract_listing_number(raw_user_text_full)
        if requested_num is not None:
            last = _get_last_results_for_user(resolve_user_id(user_id_key), resolve_user_phone())
            idx = requested_num - 1
            if 0 <= idx < len(last):
                mapped_id = last[idx].get("id")
                if mapped_id and _is_uuid(str(mapped_id)):
                    keys = [user_id_key, resolve_user_phone(), "anonymous"]
                    _set_active_listing_for_keys(str(mapped_id), [k for k in keys if k])
                    if isinstance(ctx.conversation_state, dict):
                        ctx.conversation_state["active_listing_id"] = str(mapped_id)
                    conversation_history.append(cast(TResponseInputItem, {
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": f"[CONVERSATION_STATE] ACTIVE_LISTING_ID={mapped_id}"}
                        ]
                    }))

        # Deterministic detail rendering for "X nolu ilan" to avoid LLM misalignment
        raw_user_text_l = raw_user_text_full.strip().lower()
        wants_detail = requested_num is not None and any(k in raw_user_text_l for k in ("göster", "goster", "detay"))
        if wants_detail:
            last = _get_last_results_for_user(resolve_user_id(user_id_key), resolve_user_phone())
            if not last:
                return {
                    "response": "Henüz listelenmiş bir arama sonucu yok. Önce arama yapalım (örn: 'araba var mı?').",
                    "intent": "search_product",
                    "success": False,
                }

            idx = (requested_num or 1) - 1
            if idx < 0 or idx >= len(last):
                return {
                    "response": f"Bu aramada sadece {len(last)} ilan var. 1-{len(last)} arasından seçim yapabilirsiniz.",
                    "intent": "search_product",
                    "success": False,
                }

            item = last[idx] or {}
            title = item.get("title") or "İlan"
            price = item.get("price")
            location = item.get("location") or "Türkiye"
            condition = _condition_display(_normalize_condition_value(item.get("condition"))) or "Belirtilmedi"
            category = item.get("category") or "Genel"
            owner_name = item.get("user_name") or item.get("owner_name")
            owner_phone = item.get("user_phone") or item.get("owner_phone") or resolve_user_phone()
            description = item.get("description") or "Açıklama yok."
            if len(description) > 400:
                description = description[:400] + "..."
            images = item.get("signed_images") or []
            photos = [str(u) for u in images if u]
            photos_text = "Fotoğraf yok." if not photos else "Fotoğraflar:\n" + "\n".join(photos[:3])
            owner_line = ""
            if owner_name or owner_phone:
                owner_line = f"İlan sahibi: {owner_name or 'Bilinmiyor'}" + (f" | Telefon: {owner_phone}" if owner_phone else "")

            detail_text = (
                f"{title}\n\n"
                f"Fiyat: {price if price is not None else 'Belirtilmedi'} TL\n"
                f"Konum: {location}\n"
                f"Durum: {condition}\n"
                f"Kategori: {category}\n"
                f"{owner_line}\n\n"
                f"Açıklama: {description}\n\n"
                f"{photos_text}"
            )
            return {
                "response": detail_text,
                "intent": "search_product",
                "success": True,
            }

        # Inject last search results summary when it can help follow-up actions
        raw_user_text_l = raw_user_text_full.strip().lower()
        needs_last_search_context = any(k in raw_user_text_l for k in (
            "nolu", "numar", "detay", "göster", "goster", "foto", "kategori", "güncelle", "guncelle", "sil"
        ))
        if needs_last_search_context:
            last = USER_LAST_SEARCH_RESULTS_STORE.get(user_id_key) or []
            if last:
                lines: List[str] = []
                for i, item in enumerate(last[:10], start=1):
                    title = item.get("title") or ""
                    listing_id = item.get("id") or ""
                    if not listing_id:
                        continue
                    lines.append(f"#{i} id={listing_id} title={title}")
                if lines:
                    conversation_history.append(cast(TResponseInputItem, {
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "[LAST_SEARCH_RESULTS] " + " | ".join(lines)}
                        ]
                    }))
        
        # Add previous conversation context if exists (NOT including current message)
        for msg in pruned_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Skip empty messages
            if not content:
                continue
            
            # CRITICAL: OpenAI Agents SDK uses different content types for user vs assistant
            if role == "user":
                conversation_history.append(cast(TResponseInputItem, {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",  # User messages use input_text
                            "text": content
                        }
                    ]
                }))
            elif role == "assistant":
                conversation_history.append(cast(TResponseInputItem, {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",  # Assistant messages use output_text!
                            "text": content
                        }
                    ]
                }))
        
        # Add current user message (this is the new message to process)
        current_message_text = workflow["input_as_text"]
        
        # Prepend user name if available for personalized greeting
        if workflow.get("user_name"):
            current_message_text = f"[USER_NAME: {workflow['user_name']}] {current_message_text}"
        
        conversation_history.append(cast(TResponseInputItem, {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": current_message_text
                }
            ]
        }))

        # Attach draft context note (media paths are attached AFTER safety check as SAFE_MEDIA_PATHS)
        if workflow.get("draft_listing_id"):
            media_note_text = f"[SYSTEM_MEDIA_NOTE] DRAFT_LISTING_ID={workflow['draft_listing_id']}"
            logger.info(f"📝 Adding SYSTEM_MEDIA_NOTE to conversation: {media_note_text}")
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": media_note_text
                    }
                ]
            }))
        
        # Run guardrails
        guardrails_input_text = workflow["input_as_text"]
        guardrails_result = await run_and_apply_guardrails(
            guardrails_input_text,
            guardrails_sanitize_input_config,
            conversation_history,
            workflow
        )
        guardrails_hastripwire = guardrails_result["has_tripwire"]
        
        if guardrails_hastripwire:
            return {"error": "Content blocked by guardrails"}

        # Fast-path routing for wallet queries (avoid misclassification to small_talk)
        raw_user_text = (workflow.get("input_as_text") or "").strip().lower()
        wallet_keywords = (
            "bakiye",
            "bakiyem",
            "kredi",
            "kredim",
            "param",
            "paramı",
            "cüzdan",
            "balance",
            "işlemlerim",
            "harcamalarım",
            "geçmiş",
            "işlem geçmiş",
        )
        force_wallet_intent = any(k in raw_user_text for k in wallet_keywords)

        # Step 0: Vision safety + product extraction (if media provided)
        media_paths_raw = workflow.get("media_paths")
        media_paths_in: List[str] = media_paths_raw if isinstance(media_paths_raw, list) else ([] if media_paths_raw is None else [str(media_paths_raw)])

        # De-duplicate paths while preserving order
        seen_paths: set[str] = set()
        media_paths: List[str] = []
        for p in media_paths_in:
            sp = str(p).strip()
            if not sp:
                continue
            if sp in seen_paths:
                continue
            seen_paths.add(sp)
            media_paths.append(sp)
        
        # HARD LIMIT: Maximum 10 photos per listing (abuse prevention)
        if len(media_paths) > 10:
            logger.warning(f"⚠️ User {user_id_key} tried to upload {len(media_paths)} photos, limiting to 10")
            media_paths = media_paths[:10]

        # VisionSafetyProductAgent only runs when explicit media is present
        if media_paths:
            for media_path in media_paths:
                image_url = _resolve_public_image_url(str(media_path))
                vision_input: List[TResponseInputItem] = cast(List[TResponseInputItem], [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Analyze the attached image for safety and product. Return JSON only."},
                            {"type": "input_image", "image_url": image_url}
                        ]
                    }
                ])

                try:
                    vision_result_temp = await Runner.run(
                        vision_safety_product_agent,
                        input=vision_input,  # type: ignore[arg-type]
                        run_config=RunConfig(trace_metadata={
                            "__trace_source__": "agent-builder",
                            "workflow_id": "vision_safety_product"
                        })
                    )
                    vision_result = vision_result_temp.final_output.model_dump()
                except Exception as exc:  # pragma: no cover
                    blocked_media_paths.append({
                        "path": str(media_path),
                        "reason": f"vision_error: {exc}",
                    })
                    continue

                safe_flag = bool(vision_result.get("safe"))
                flag_type = (vision_result.get("flag_type") or "unknown")
                allow_listing_flag = vision_result.get("allow_listing")
                if allow_listing_flag is None:
                    allow_listing_flag = safe_flag
                # Prevent false positives: if safe and no explicit flag, keep allow_listing true
                if safe_flag and (flag_type in ("none", "unknown", "")) and allow_listing_flag is False:
                    allow_listing_flag = True

                if (not safe_flag) or (not allow_listing_flag):
                    # Log flag for admin review (no auto-ban)
                    log_image_safety_flag(
                        user_id=workflow.get("user_id"),
                        image_url=str(media_path),
                        flag_type=flag_type,
                        confidence=vision_result.get("confidence", "low"),
                        message=vision_result.get("message", "unsafe"),
                    )
                    blocked_media_paths.append({
                        "path": str(media_path),
                        "reason": vision_result.get("message", "unsafe"),
                        "flag_type": flag_type,
                        "confidence": vision_result.get("confidence", "low"),
                    })
                    continue

                vision_result["allow_listing"] = allow_listing_flag
                safe_media_paths.append(str(media_path))
                if first_safe_vision is None:
                    first_safe_vision = vision_result

            # If all images are blocked, stop
            if not safe_media_paths:
                first_reason = blocked_media_paths[0].get("reason") if blocked_media_paths else "unsafe image"
                return {
                    "response": f"❌ Güvenlik nedeniyle reddedildi: {first_reason}. Bu görseller işleme alınmadı, lütfen farklı görsel gönderin.",
                    "intent": "vision_safety_blocked",
                    "success": False,
                    "safe_media_paths": [],
                    "blocked_media_paths": blocked_media_paths,
                }

            # Attach SAFE media paths for downstream agents (listing/publish)
            safe_media_note_parts: List[str] = []
            if workflow.get("draft_listing_id"):
                safe_media_note_parts.append(f"DRAFT_LISTING_ID={workflow['draft_listing_id']}")
            safe_media_note_parts.append(f"MEDIA_PATHS={safe_media_paths}")
            safe_media_note_text = f"[SYSTEM_MEDIA_NOTE] {' | '.join(safe_media_note_parts)}"
            logger.info(f"📝 Adding SYSTEM_MEDIA_NOTE (SAFE MEDIA_PATHS) to conversation: {safe_media_note_text}")
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": safe_media_note_text
                    }
                ]
            }))
            
            # Store safe media in session for WhatsApp multi-message flow
            USER_SAFE_MEDIA_STORE[user_id_key] = safe_media_paths[:]
            logger.info(f"💾 Stored {len(safe_media_paths)} safe media paths for user {user_id_key}")

            # Append compact product summary for downstream agents (use first safe image only)
            if first_safe_vision:
                product_info: Dict[str, Any] = first_safe_vision.get("product") or {}
                product_attrs = ", ".join(cast(List[str], product_info.get("attributes", []) or []))
                conversation_history.append(cast(TResponseInputItem, {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                f"[VISION_PRODUCT] safe=true; allow_listing={first_safe_vision.get('allow_listing', True)}; "
                                f"title={product_info.get('title') or 'unknown'}; "
                                f"category={product_info.get('category') or 'unknown'}; "
                                f"condition={product_info.get('condition') or 'unknown'}; "
                                f"quantity={product_info.get('quantity') or 1}; "
                                f"attributes={product_attrs or 'none'}"
                            )
                        }
                    ]
                }))
        elif pending_safe_media and not has_explicit_media:
            # No new media this message, but user has pending safe media from previous upload
            # → inject it so agent can use (WhatsApp: "send photo" then "publish listing" flow)
            pending_note = f"[SYSTEM_MEDIA_NOTE] MEDIA_PATHS={pending_safe_media}"
            logger.info(f"♻️ Injecting pending safe media for user {user_id_key}: {pending_note}")
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": pending_note
                    }
                ]
            }))
        
        # Step 1: Classify intent (ensure USER_CONTEXT note is part of history for personalization and ownership)
        if force_wallet_intent:
            intent = "wallet_query"
        else:
            router_agent_intent_classifier_result_temp = await Runner.run(
                router_agent_intent_classifier,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
            
            conversation_history.extend([item.to_input_item() for item in router_agent_intent_classifier_result_temp.new_items])
            
            router_agent_intent_classifier_result = {
                "output_text": router_agent_intent_classifier_result_temp.final_output.json(),
                "output_parsed": router_agent_intent_classifier_result_temp.final_output.model_dump()
            }
            
            intent = router_agent_intent_classifier_result["output_parsed"]["intent"]

        # Persist last intent in conversation_state and expose to downstream agents
        state_for_update = resolve_conversation_state()
        if isinstance(state_for_update, dict):
            state_for_update["last_intent"] = intent
            state_parts: List[str] = []
            if state_for_update.get("mode"):
                state_parts.append(f"MODE={state_for_update.get('mode')}")
            if state_for_update.get("active_listing_id"):
                state_parts.append(f"ACTIVE_LISTING_ID={state_for_update.get('active_listing_id')}")
            if state_for_update.get("last_intent"):
                state_parts.append(f"LAST_INTENT={state_for_update.get('last_intent')}")
            if state_parts:
                conversation_history.append(cast(TResponseInputItem, {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "[CONVERSATION_STATE] " + " | ".join(state_parts)
                        }
                    ]
                }))

            # Deterministic FSM override: if active draft exists, keep user in draft loop unless explicitly publishing
            resolved_user_for_draft = resolve_user_id(user_id_key)
            active_draft = await db_get_active_draft(resolved_user_for_draft)
            if active_draft and intent not in {"publish_listing", "cancel"}:
                # Stay in deterministic draft loop for any non-publish, non-cancel intent
                intent = "update_listing_draft"

            # Deterministic state machine handles draft → preview → publish without tool-calling agents
            if intent in {"create_listing", "update_listing_draft", "publish_listing"}:
                fsm_result = await handle_listing_fsm(
                    intent=intent,
                    user_text=raw_user_text_full,
                    safe_media_paths=safe_media_paths,
                    vision_product=(first_safe_vision or {}).get("product") if first_safe_vision else None,
                    active_draft=active_draft,
                )
                if fsm_result is not None:
                    fsm_result["safe_media_paths"] = safe_media_paths
                    fsm_result["blocked_media_paths"] = blocked_media_paths
                    return fsm_result

        # Authentication gate for protected intents
        auth_ctx = resolve_auth_context()
        resolved_user_id = resolve_user_id()
        # WhatsApp oturumlarında PIN doğrulaması Edge Function tarafında yapılıyor.
        # Phone → profile → user_id çözülüyorsa bu isteği authenticated saymak yeterli.
        # (Bazı durumlarda auth_context gelmiyor; bu kullanıcıyı tekrar PIN'e zorlamasın.)
        is_authenticated = bool(resolved_user_id)
        protected_intents = {"update_listing", "delete_listing"}
        if intent in protected_intents and not is_authenticated:
            return {
                "response": "Bu işlem için giriş yapmanız gerekiyor. Lütfen PIN ile giriş yapın.",
                "intent": "auth_required",
                "success": False
            }
        
        # Step 2: Route to appropriate agent
        # TEMPORARILY DISABLED pin_request - causing 500 errors
        if intent == "pin_request":
            # Fallback to small_talk when PIN is requested but disabled
            result = await Runner.run(
                smalltalkagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "create_listing":
            result = await Runner.run(
                listingagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "update_listing":
            result = await Runner.run(
                updatelistingagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "publish_listing":
            result = await Runner.run(
                publishagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "cancel":
            await _clear_active_draft_for_current_user()
            result = await Runner.run(
                cancelagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "wallet_query":
            # Wallet queries must reach an agent that has wallet tools.
            result = await Runner.run(
                publishagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "search_product":
            result = await Runner.run(
                searchagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "small_talk":
            result = await Runner.run(
                smalltalkagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "cancel":
            result = await Runner.run(
                cancelagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        elif intent == "delete_listing":
            result = await Runner.run(
                deletelistingagent,
                input=[*conversation_history],
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
                })
            )
        else:
            return {"error": "Unknown intent", "intent": intent}
        
        final_response = result.final_output_as(str)
        
        # Clear pending safe media after publish/cancel (heuristic cleanup)
        if final_response:
            response_lower = final_response.lower()
            if any(keyword in response_lower for keyword in ["ilan yayınlandı", "✅ ilan yayınlandı", "iptal edildi", "işlemi iptal"]):
                USER_SAFE_MEDIA_STORE.pop(user_id_key, None)
                logger.info(f"🧹 Cleared pending safe media for user {user_id_key} after publish/cancel")
        
        return {
            "response": final_response,
            "intent": intent,
            "success": True,
            "safe_media_paths": safe_media_paths if 'safe_media_paths' in locals() else [],
            "blocked_media_paths": blocked_media_paths if 'blocked_media_paths' in locals() else [],
        }
