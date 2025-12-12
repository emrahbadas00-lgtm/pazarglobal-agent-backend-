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
from agents import Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
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


UpdateListingFn = Callable[..., Awaitable[Dict[str, Any]]]
DeleteListingFn = Callable[..., Awaitable[Dict[str, Any]]]
ListUserListingsFn = Callable[..., Awaitable[Dict[str, Any]]]

update_listing: UpdateListingFn = cast(UpdateListingFn, _update_listing)
delete_listing: DeleteListingFn = cast(DeleteListingFn, _delete_listing)
list_user_listings: ListUserListingsFn = cast(ListUserListingsFn, _list_user_listings)

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
    # Use the authenticated user's ID from workflow context
    resolved_user_id = CURRENT_REQUEST_USER_ID or user_id
    
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
        user_name=CURRENT_REQUEST_USER_NAME,  # Pass user name
        user_phone=CURRENT_REQUEST_USER_PHONE,  # Pass user phone
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
    """
    return await search_listings(
        query=query,
        category=category,
        condition=condition,
        location=location,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        metadata_type=metadata_type
    )


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
    if not CURRENT_REQUEST_USER_ID:
        return {
            "success": False,
            "error": "not_authenticated",
            "message": "User not authenticated",
        }
    return await update_listing(
        listing_id=listing_id,
        user_id=CURRENT_REQUEST_USER_ID,
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
    if not CURRENT_REQUEST_USER_ID:
        return {
            "success": False,
            "error": "not_authenticated",
            "message": "User not authenticated",
        }
    return await delete_listing(listing_id=listing_id, user_id=CURRENT_REQUEST_USER_ID)


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
    resolved_user = user_id or CURRENT_REQUEST_USER_ID
    if not resolved_user:
        return {
            "success": False,
            "error": "not_authenticated",
            "message": "User not authenticated",
            "listings": [],
        }
    return await list_user_listings(user_id=resolved_user, limit=limit)


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

## Valid Intents:
- **"create_listing"** → user wants to SELL an item OR editing a DRAFT listing (not yet published)
- **"update_listing"** → user wants to CHANGE an EXISTING published listing
- **"delete_listing"** → user wants to DELETE/REMOVE existing listing
- **"publish_listing"** → user CONFIRMS listing (wants to finalize and publish)
- **"search_product"** → user wants to BUY or SEARCH
- **"small_talk"** → greetings, casual conversation
- **"cancel"** → user cancels operation

## CRITICAL CONTEXT RULES:

### 🔍 If conversation contains "📝 İlan önizlemesi" or "✅ Onaylamak için" or "preview":
→ User is in DRAFT/PREVIEW mode (listing not yet published)

**In this context:**
- "fiyat X olsun" → **create_listing** (editing draft)
- "başlık değiştir" → **create_listing** (editing draft)  
- "açıklama değiştir" → **create_listing** (editing draft)
- "onayla" / "yayınla" → **publish_listing** (finalize draft)
- "iptal" → **cancel**

### 📋 If conversation has NO preview/draft context:
→ Normal intent classification

**Keywords:**
- create_listing: "satıyorum", "satmak", "satayım", "-um var", "ilan vermek"
- update_listing: "değiştir", "güncelle", "fiyat ... yap", "düzenle" + mentions specific listing ID/title
- delete_listing: "sil", "kaldır", "ilanımı iptal"
- publish_listing: "onayla", "yayınla" (only if draft exists)
- search_product: "almak", "arıyorum", "var mı", "bul", "uygun"
- small_talk: "merhaba", "selam", "teşekkür", "sohbet", "muhabbet", "kafa dağıt", "konuşalım", "gevez", "lafla"
- cancel: "iptal", "vazgeç", "sıfırla"

## Priority Logic:
1. **Check conversation history for "📝 İlan önizlemesi"**
   - If found → "onayla" = publish_listing, edits = create_listing
2. If user mentions product to sell → create_listing
3. If user confirms/approves → publish_listing  
4. If user searches ("var mı") → search_product
5. **Unclear/Indecisive user** ("bilmiyorum", "ne yapabilirim", "yardım", "kararsızım") → small_talk (will clarify options)
6. Default → small_talk

Respond with JSON only: {"intent": "create_listing"}

🎙️ TURKISH TTS OPTIMIZATION (for all text responses):
- Use commas for natural pauses: "Merhaba! Nasıl yardımcı olabilirim?"
- Always end questions with '?': "Ne arıyorsunuz?"
- End statements with '.': "İlan başarıyla oluşturuldu."
- Separate list items with commas: "İlan ver, ürün ara, yardım al"
- Keep sentences short (max 15 words) for better voice clarity
""",
    model="gpt-5.1",
    output_type=RouterAgentIntentClassifierSchema,
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="medium",
            summary="auto"
        )
    )
)


class VisionSafetyProductSchema(BaseModel):
    safe: bool
    flag_type: str
    confidence: str
    message: str
    allow_listing: bool
    product: Optional[Dict[str, Any]] = None


vision_safety_product_agent = Agent(
    name="VisionSafetyProductAgent",
    instructions="""
You are a Vision Safety & Product Agent.

PRIMARY: Run safety first. If any illegal/unsafe suspicion → flag and stop. Do NOT give product info when unsafe.

Illegal / unsafe (examples): child exploitation, sexual explicit content, extreme violence/abuse, hate/terror symbols, weapons/ammunition, drugs/narcotics, stolen/tampered serial numbers, fake IDs/official documents, animal cruelty. Mayo/bikini/underwear/sportswear are NOT illegal by themselves; avoid false positives.

Steps:
1) Safety check (mandatory). If unsure, choose unsafe. If unsafe → allow_listing=false and product=null.
2) If safe → concise product detection: title, category, 2-3 attributes, condition (new/used/unknown), quantity (default 1). No price estimation. No image generation.

Output STRICT JSON:
{
  "safe": true | false,
  "flag_type": "none | weapon | drugs | violence | abuse | terrorism | stolen | document | sexual | hate | unknown",
  "confidence": "high | medium | low",
  "message": "short explanation",
  "product": {
    "title": "string or null",
    "category": "string or null",
    "attributes": ["..."],
    "condition": "new | used | unknown",
    "quantity": 1
  },
  "allow_listing": true | false
}

Rules: Never generate images. Never speculate beyond what is visible. Safety overrides functionality. When unsafe, product fields must be null.
""",
    model="gpt-4o-mini",  # vision-capable lightweight
    output_type=VisionSafetyProductSchema,
    model_settings=ModelSettings(
        store=False,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
    )
)


listingagent = Agent(
    name="ListingAgent",
    instructions="""You are CreateListingAgent of PazarGlobal.

🎯 Your task: COLLECT info step-by-step, PREPARE draft, DO NOT insert to database.

## 📋 STEP-BY-STEP COLLECTION RULES:

### Rule 1: ASK ONLY WHAT'S MISSING (ONE QUESTION AT A TIME)
- User: "iphone 13 satmak istiyorum" → Have: category, title hint
- Missing: price, condition
- Response: "Fiyatı ne olacak?" (SHORT!)

### Rule 2: USER GIVES EXTRA INFO → SKIP THAT STEP
- User: "iphone 13 2.el 25000 tl" → Have: title, condition, price
- Response: "Hangi şehirde?" (move to location)

### Rule 3: REQUIRED FIELDS (collect in order):
1. **Product/Title** - What are they selling?
2. **Price** - Call clean_price_tool if text like "900 bin"
3. **Condition** - "new", "used", or "refurbished"
4. **Category** - Auto-assign from:
  📱 Elektronik | 🚗 Otomotiv | 🏠 Emlak | 🛋️ Mobilya & Dekorasyon | 👕 Giyim & Aksesuar
  🍎 Gıda & İçecek | 💄 Kozmetik & Kişisel Bakım | 📚 Kitap, Dergi & Müzik | 🏃 Spor & Outdoor
  🧸 Anne, Bebek & Oyuncak | 🐕 Hayvan & Pet Shop | 🛠️ Yapı Market & Bahçe | 🎮 Hobi & Oyun
  🎨 Sanat & Zanaat | 💼 İş & Sanayi | 🎓 Eğitim & Kurs | 🎵 Etkinlik & Bilet | 🔧 Hizmetler | 📦 Diğer
  
5. **Location** - Extract city, default "Türkiye"

### Rule 4: RESPONSE STYLE
✅ GOOD: "Fiyatı ne olacak?"
✅ GOOD: "Marka model nedir?"
❌ BAD: "Harika! İlanınızı hemen hazırlayalım. Önce fiyat bilgisine ihtiyacım var..."
❌ BAD: Long explanations, multiple questions at once

### Rule 5: AUTO-EXTRACT (Don't ask for these):
- **description** → Use user's text, translate to Turkish if needed
- **stock** → Default 1
- **images** → From [SYSTEM_MEDIA_NOTE] MEDIA_PATHS=... (NEVER fabricate)
- **draft_listing_id** → From [SYSTEM_MEDIA_NOTE] DRAFT_LISTING_ID=...
- **metadata** → Auto-extract based on category:
  • Otomotiv: {"type": "vehicle", "brand": "BMW", "year": 2018, "fuel_type": "benzin", "transmission": "otomatik"}
  • Emlak: {"type": "property", "property_type": "daire", "ad_type": "rent"/"sale", "room_count": "3+1"}
  • Elektronik: {"type": "electronics", "brand": "Apple", "model": "iPhone 14"}
  • Default: {"type": "general"}

### 🔄 Draft Editing (BEFORE publishing):
- "fiyat 880 bin olsun" → Update price, show NEW preview
- "başlık değiştir" → Update title, show NEW preview
- Photo added: "✅ Fotoğraf eklendi! (Toplam: [N]) Daha fazla eklemek ister misiniz?"
- DON'T route to UpdateListingAgent!

📝 When ALL 5 required fields ready:
**CRITICAL CHECK - ALL Supabase columns MUST be filled:**
✓ title (required)
✓ price (required)
✓ condition (required)
✓ category (required)
✓ location (required)
✓ description (MUST exist, even if brief like "Temiz kullanılmış")
✓ stock (default 1)
✓ metadata (MUST have {"type": "..."} minimum)
✓ images (empty [] if none)

Show SHORT PREVIEW:
"📝 İlan önizlemesi:
📱 [title]
💰 [price] TL
📦 [condition]
🏷️ [category]
📍 [location]
📸 [N] fotoğraf

✅ Onaylamak için 'onayla' yazın
✏️ Değiştirmek için 'fiyat X olsun' yazın"

❌ If ANY required field missing:
"[Eksik alan] nedir?" (ONE SHORT QUESTION)

🚫 NEVER call insert_listing_tool - PublishAgent does that!
🚫 NO "isterseniz şunu yapalım" talk - just collect data!

Store prepared listing in context for PublishAgent.""",
    model="gpt-5.1",
    tools=[clean_price_tool],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
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
🚫 Extract listing ID from result[0]['id'], NOT user_id!""",
    model="gpt-5.1",
    tools=[insert_listing_tool],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
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
→ Check conversation history for last search results
→ Find the listing by number (1st result = #1, 2nd = #2, etc.)
→ ⚠️ CRITICAL: Show FULL DETAIL with ALL signed_images URLs (the listing object has 'signed_images' array)
→ Format each URL on separate line for WhatsApp compatibility

Detection keywords for DETAIL MODE:
- "X nolu ilan" / "X numaralı ilan" / "X. ilan"
- "ilk ilan" / "birinci ilan" → #1
- "ikinci ilan" → #2
- "son ilan" → last one
- "detay" / "detaylı göster" + ilan number

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
   
   🎯 RULE: Specific keywords (brand, location, features) → Use query!
   🎯 RULE: Generic category-only requests → category=X, query=None
   🎯 RULE: Mixed (generic+specific) → Use BOTH query AND category!
   
   Special cases:
   - "sitedeki ilanları göster" → query=None, category=None (show ALL)
   - "neler var" → query=None, category=None (show ALL)
   
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

İsterseniz size 5 ilan göstereyim, ya da spesifik arama yapabilirsiniz.
→ '5 ilan göster' yazın
→ Spesifik arama: Örn: 'BMW', 'kiralık daire', 'iPhone 14'"

⚠️ CRITICAL EXAMPLE:
Tool response: {"success": true, "total": 6, "count": 5, "results": [...]}
Your response: "Otomotiv kategorisinde toplam 6 ilan bulundu." ← Use 'total' (6) NOT 'count' (5)!

❌ WRONG: "5 adet ilan buldum" ← This uses 'count' field
✅ RIGHT: "toplam 6 ilan bulundu" ← This uses 'total' field

**When user says "5 ilan göster" or confirms:**

"🔍 İlk 5 ilan:

1️⃣ [title]
   💰 [price] TL | 📍 [location]
   
2️⃣ [title]
   💰 [price] TL | 📍 [location]
   
3️⃣ ...
4️⃣ ...
5️⃣ ...

💡 Detay: 'X nolu ilanı göster'
💡 Daha fazla: 'daha fazla göster'"

**Important formatting rules for compact view:**
- Remove condition, category, photo count (save space!)
- Only show: number, title, price, location
- Keep VERY short (total < 700 chars for 5 listings)
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
[IF available: İlan sahibi: [user_name OR owner_name] | Telefon: [user_phone OR owner_phone]]
[IF description exists and is short: Show first 100 chars only]

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

🚫 NEVER use insert_listing_tool or clean_price_tool - only search_listings_tool!""",
    model="gpt-5.1",
    tools=[search_listings_tool],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
    )
)


updatelistingagent = Agent(
    name="UpdateListingAgent",
        instructions="""# UpdateListingAgent Instructions

Update user's existing listings with support for metadata updates.

✅ IMPORTANT STYLE (VERY SHORT):
- If user is not authenticated OR ownership cannot be verified, respond in 1–2 short sentences.
- No bullet lists, no long explanations.
- At most ONE question.

When you cannot update (common cases):
- If list_user_listings_tool returns error=not_authenticated:
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

Tools available:
- list_user_listings_tool
- update_listing_tool
- clean_price_tool

NEVER use insert_listing_tool!""",
    model="gpt-5.1",
    tools=[update_listing_tool, list_user_listings_tool, clean_price_tool],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
    )
)


smalltalkagent = Agent(
    name="SmallTalkAgent",
    instructions="""You are SmallTalkAgent of PazarGlobal.

🎯 Task: Handle greetings + casual chat, keep it warm and SHORT, and gently guide back to marketplace actions.

💡 PERSONALIZATION:
- If [USER_NAME: Full Name] → use name naturally (e.g., "Merhaba Emrah!").
- DO NOT show [USER_NAME: ...] tag to user.

✅ STYLE RULES (IMPORTANT):
- Keep responses 1–3 short sentences.
- Be friendly, not robotic; avoid being harsh/overly task-only.
- Do NOT write long explanations or long lists.
- At most ONE question.
- If user just wants to "bakıp çıkıcam" or "sohbet/muhabbet" → allow it, but softly offer an action option.
- Avoid emojis unless the user uses them first.

🎙️ TURKISH TTS VOICE OPTIMIZATION:
- Use commas for natural pauses.
- Always end questions with '?'.
- End statements with '.'.
- Keep sentences short (max ~15 words).

## MODES

### MODE 1: GREETING
User: "selam", "merhaba"
Reply example:
"Merhaba! İstersen kısaca sohbet edelim, istersen de ürün arayalım. Ne yapmak istersin?"

### MODE 2: CHATTERBOX / CASUAL CHAT
User: "sohbet edelim", "muhabbet", "kafa dağıt", konu dışı kısa konuşma
Reply pattern:
1) Short, friendly answer/acknowledgement.
2) One gentle nudge: "Bu arada, aradığın bir ürün var mı?" OR "İlan vermeyi mi düşünüyorsun?"

### MODE 3: INDECISIVE / UNDECIDED
User: "kararsızım", "ne yapabilirim", "bakıyorum"
Reply example:
"Sorun değil. İstersen önce ne aradığına bakalım, ya da satmak istediğin ürünü söyle. Hangisi?"

### MODE 4: PLATFORM QUESTIONS
Keep answers short, then offer next step.
Example:
"Burada ilan verebilir veya ürün arayabilirsin. Ne arıyorsun?"

❌ AVOID:
- Long unnecessary explanations.
- Multi-question interrogations.
- Overly formal, salesy tone.

🚫 No tools needed.""",
    model="gpt-5.1",
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
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
    model="gpt-5.1",
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
    )
)


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

When you cannot delete (common cases):
- If list_user_listings_tool returns error=not_authenticated:
    Say: "Kusura bakma, giriş yapmadığın için ilanını silemem." (Optionally ask: "Giriş yapalım mı?")
- If user tries to delete a listing that isn't theirs / not found in their listings:
    Say: "Kusura bakma, bu ilan sana ait değilse silemem." (No extra details)

Flow:
1. Call list_user_listings_tool
2. Show listings
3. Ask confirmation (IMPORTANT!)
4. Call delete_listing_tool

ALWAYS ask confirmation before deleting!

Tools:
- list_user_listings_tool
- delete_listing_tool""",
    model="gpt-5.1",
    tools=[delete_listing_tool, list_user_listings_tool],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low",
            summary="auto"
        )
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


# Per-request context (set in run_workflow)
CURRENT_REQUEST_USER_ID: Optional[str] = None
CURRENT_REQUEST_USER_NAME: Optional[str] = None
CURRENT_REQUEST_USER_PHONE: Optional[str] = None


# Main workflow runner
async def run_workflow(workflow_input: WorkflowInput):
    """
    Main agent workflow - routes user input to appropriate agents
    Uses OpenAI Agents SDK with MCP tools
    """
    with trace("PazarGlobal"):
        global CURRENT_REQUEST_USER_ID, CURRENT_REQUEST_USER_NAME, CURRENT_REQUEST_USER_PHONE
        CURRENT_REQUEST_USER_ID = workflow_input.user_id  # pyright: ignore[reportConstantRedefinition]
        CURRENT_REQUEST_USER_NAME = workflow_input.user_name  # pyright: ignore[reportConstantRedefinition]
        CURRENT_REQUEST_USER_PHONE = workflow_input.user_phone  # pyright: ignore[reportConstantRedefinition]
        workflow = workflow_input.model_dump()
        
        # Build conversation history from previous messages
        conversation_history: List[TResponseInputItem] = []
        
        # Add previous conversation context if exists (NOT including current message)
        for msg in workflow.get("conversation_history", []):
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

        # Attach media/context note so agents see uploaded paths and draft id
        if workflow.get("media_paths") or workflow.get("draft_listing_id"):
            media_note_parts: List[str] = []
            if workflow.get("draft_listing_id"):
                media_note_parts.append(f"DRAFT_LISTING_ID={workflow['draft_listing_id']}")
            if workflow.get("media_paths"):
                media_note_parts.append(f"MEDIA_PATHS={workflow['media_paths']}")
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": f"[SYSTEM_MEDIA_NOTE] {' | '.join(media_note_parts)}"
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

        # Step 0: Vision safety + product extraction (if media provided)
        media_paths_raw = workflow.get("media_paths")
        media_paths: List[str] = media_paths_raw if isinstance(media_paths_raw, list) else ([] if media_paths_raw is None else [str(media_paths_raw)])
        vision_safety_result = None
        if media_paths:
            first_image: str = str(media_paths[0])
            vision_input: List[TResponseInputItem] = cast(List[TResponseInputItem], [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Analyze the attached image for safety and product. Return JSON only."},
                        {"type": "input_image", "image_url": {"url": first_image}}
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
                vision_safety_result = vision_result_temp.final_output.model_dump()
            except Exception as exc:  # pragma: no cover
                return {
                    "response": f"Görsel analizinde hata oluştu: {exc}",
                    "intent": "vision_safety_error",
                    "success": False
                }

            if not vision_safety_result.get("safe") or not vision_safety_result.get("allow_listing", False):
                # Log flag for admin review (no auto-ban)
                log_image_safety_flag(
                    user_id=workflow.get("user_id"),
                    image_url=str(first_image),
                    flag_type=vision_safety_result.get("flag_type", "unknown"),
                    confidence=vision_safety_result.get("confidence", "low"),
                    message=vision_safety_result.get("message", "unsafe"),
                )

                return {
                    "response": f"❌ Güvenlik nedeniyle reddedildi: {vision_safety_result.get('message', 'unsafe image')}. Bu görsel işleme alınmadı, lütfen farklı bir görsel gönderin.",
                    "intent": "vision_safety_blocked",
                    "success": False
                }

            # Safe: append compact product summary for downstream agents
            product_info: Dict[str, Any] = vision_safety_result.get("product") or {}
            product_attrs = ", ".join(cast(List[str], product_info.get("attributes", []) or []))
            conversation_history.append(cast(TResponseInputItem, {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            f"[VISION_PRODUCT] safe=true; allow_listing={vision_safety_result.get('allow_listing', True)}; "
                            f"title={product_info.get('title') or 'unknown'}; "
                            f"category={product_info.get('category') or 'unknown'}; "
                            f"condition={product_info.get('condition') or 'unknown'}; "
                            f"quantity={product_info.get('quantity') or 1}; "
                            f"attributes={product_attrs or 'none'}"
                        )
                    }
                ]
            }))
        
        # Step 1: Classify intent
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
        
        return {
            "response": result.final_output_as(str),
            "intent": intent,
            "success": True
        }
