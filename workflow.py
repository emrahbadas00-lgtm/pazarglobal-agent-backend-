"""
Pazarglobal Agent Workflow
Direct port of Agent Builder SDK Python export
Uses OpenAI Agents SDK with HostedMCP tools
"""
from agents import HostedMCPTool, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
from openai import AsyncOpenAI
from types import SimpleNamespace
from guardrails.runtime import load_config_bundle, instantiate_guardrails, run_guardrails
from pydantic import BaseModel
from openai.types.shared.reasoning import Reasoning


# MCP Tool definitions - connects to Railway MCP server
mcp = HostedMCPTool(tool_config={
    "type": "mcp",
    "server_label": "pazarglobal",
    "allowed_tools": [
        "clean_price_tool",
        "insert_listing_tool"
    ],
    "require_approval": "never",
    "server_description": "pazarglobal",
    "server_url": "https://pazarglobal-production.up.railway.app/sse"
})

mcp1 = HostedMCPTool(tool_config={
    "type": "mcp",
    "server_label": "pazarglobal",
    "allowed_tools": [
        "update_listing_tool",
        "list_user_listings_tool"
    ],
    "require_approval": "never",
    "server_description": "pazarglobal",
    "server_url": "https://pazarglobal-production.up.railway.app/sse"
})

mcp2 = HostedMCPTool(tool_config={
    "type": "mcp",
    "server_label": "pazarglobal",
    "allowed_tools": [
        "search_listings_tool"
    ],
    "require_approval": "never",
    "server_description": "pazarglobal",
    "server_url": "https://pazarglobal-production.up.railway.app/sse"
})

mcp3 = HostedMCPTool(tool_config={
    "type": "mcp",
    "server_label": "pazarglobal",
    "allowed_tools": [
        "clean_price_tool",
        "update_listing_tool",
        "list_user_listings_tool"
    ],
    "require_approval": "never",
    "server_description": "pzarglobal",
    "server_url": "https://pazarglobal-production.up.railway.app/sse"
})

mcp4 = HostedMCPTool(tool_config={
    "type": "mcp",
    "server_label": "pazarglobal",
    "allowed_tools": [
        "delete_listing_tool",
        "list_user_listings_tool"
    ],
    "require_approval": "always",
    "server_description": "pazarglobal",
    "server_url": "https://pazarglobal-production.up.railway.app/sse"
})

# TEMPORARILY DISABLED - causing 500 errors
# mcp_security = HostedMCPTool(tool_config={
#     "type": "mcp",
#     "server_label": "pazarglobal_security",
#     "allowed_tools": [
#         "verify_pin",
#         "check_session",
#         "get_user_by_phone",
#         "register_user_pin"
#     ],
#     "require_approval": "never",
#     "server_description": "Security tools for PIN authentication and session management",
#     "server_url": "https://pazarglobal-production.up.railway.app/sse"
# })


# Shared client for guardrails
client = AsyncOpenAI()
ctx = SimpleNamespace(guardrail_llm=client)


# Guardrails configuration
guardrails_sanitize_input_config = {
    "guardrails": [
        {"name": "Jailbreak", "config": {"model": "gpt-4.1-mini", "confidence_threshold": 0.7}},
        {"name": "Moderation", "config": {"categories": ["sexual/minors", "hate/threatening", "harassment/threatening", "self-harm/instructions", "violence/graphic", "illicit/violent"]}},
        {"name": "Prompt Injection Detection", "config": {"model": "gpt-4.1-mini", "confidence_threshold": 0.7}}
    ]
}


def guardrails_has_tripwire(results):
    return any((hasattr(r, "tripwire_triggered") and (r.tripwire_triggered is True)) for r in (results or []))


def get_guardrail_safe_text(results, fallback_text):
    for r in (results or []):
        info = (r.info if hasattr(r, "info") else None) or {}
        if isinstance(info, dict) and ("checked_text" in info):
            return info.get("checked_text") or fallback_text
    pii = next(((r.info if hasattr(r, "info") else {}) for r in (results or []) if isinstance((r.info if hasattr(r, "info") else None) or {}, dict) and ("anonymized_text" in ((r.info if hasattr(r, "info") else None) or {}))), None)
    if isinstance(pii, dict) and ("anonymized_text" in pii):
        return pii.get("anonymized_text") or fallback_text
    return fallback_text


async def scrub_conversation_history(history, config):
    try:
        guardrails = (config or {}).get("guardrails") or []
        pii = next((g for g in guardrails if (g or {}).get("name") == "Contains PII"), None)
        if not pii:
            return
        pii_only = {"guardrails": [pii]}
        for msg in (history or []):
            content = (msg or {}).get("content") or []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_text" and isinstance(part.get("text"), str):
                    res = await run_guardrails(ctx, part["text"], "text/plain", instantiate_guardrails(load_config_bundle(pii_only)), suppress_tripwire=True, raise_guardrail_errors=True)
                    part["text"] = get_guardrail_safe_text(res, part["text"])
    except Exception:
        pass


async def scrub_workflow_input(workflow, input_key, config):
    try:
        guardrails = (config or {}).get("guardrails") or []
        pii = next((g for g in guardrails if (g or {}).get("name") == "Contains PII"), None)
        if not pii:
            return
        if not isinstance(workflow, dict):
            return
        value = workflow.get(input_key)
        if not isinstance(value, str):
            return
        pii_only = {"guardrails": [pii]}
        res = await run_guardrails(ctx, value, "text/plain", instantiate_guardrails(load_config_bundle(pii_only)), suppress_tripwire=True, raise_guardrail_errors=True)
        workflow[input_key] = get_guardrail_safe_text(res, value)
    except Exception:
        pass


async def run_and_apply_guardrails(input_text, config, history, workflow):
    results = await run_guardrails(ctx, input_text, "text/plain", instantiate_guardrails(load_config_bundle(config)), suppress_tripwire=True, raise_guardrail_errors=True)
    guardrails = (config or {}).get("guardrails") or []
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
- small_talk: "merhaba", "selam", "teşekkür"
- cancel: "iptal", "vazgeç", "sıfırla"

## Priority Logic:
1. **Check conversation history for "📝 İlan önizlemesi"**
   - If found → "onayla" = publish_listing, edits = create_listing
2. If user mentions product to sell → create_listing
3. If user confirms/approves → publish_listing  
4. If user searches ("var mı") → search_product
5. Default → small_talk

Respond with JSON only: {"intent": "create_listing"}
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


listingagent = Agent(
    name="ListingAgent",
    instructions="""You are CreateListingAgent of PazarGlobal.

🎯 Your task: PREPARE listing draft, DO NOT insert to database yet.

## 📋 WORKFLOW:

### Initial Listing Creation:
Extract fields from user message:
- title → brief product/property title (e.g., "3+1 Dublex Bahçe Katı Daire" for real estate)
- price → numeric price (call clean_price_tool if text like "900 bin" or "65000 tl")
- condition → "new", "used", "refurbished" (for real estate, default "used")
- category → infer: "Otomotiv", "Elektronik", "Emlak" (for houses/apartments), "Mobilya", "Genel"
- description → keep user's detailed text, translate to friendly Turkish if needed
- location → extract city if mentioned (e.g., "Bursa" → location="Bursa"), default "Türkiye"
- stock → default 1
- **metadata** → Extract structured data (see rules below - keep it SIMPLE!)

### 🔄 Draft Editing (User changes price/title/etc BEFORE publishing):
If conversation already contains "📝 İlan önizlemesi" (preview):
- User says: "fiyat 880 bin olsun" → Update price field, generate NEW preview
- User says: "başlık değiştir" → Update title, generate NEW preview
- User says: "açıklama değiştir" → Update description, generate NEW preview
- ALWAYS show updated preview after changes
- DON'T route to UpdateListingAgent - handle edits yourself!

🔍 METADATA EXTRACTION RULES:

**For Otomotiv (vehicles):**
```json
{
  "type": "vehicle",
  "brand": "BMW" | "Renault" (if mentioned),
  "year": 2018 (if mentioned),
  "fuel_type": "benzin" | "dizel" (if mentioned),
  "transmission": "manuel" | "otomatik" (if mentioned)
}
```

**For Emlak (real estate):**
```json
{
  "type": "property",
  "property_type": "kiralık" | "satılık",
  "room_count": "3+1" | "2+1" (if mentioned),
  "square_meters": 270 (if mentioned),
  "floor": "bahçe katı" | "giriş katı" (if mentioned)
}
```

**For Elektronik:**
```json
{
  "type": "electronics",
  "brand": "Apple" | "Samsung" (if mentioned),
  "model": "iPhone 14" (if mentioned)
}
```

**Default (if unclear):**
```json
{"type": "general"}
```

⚠️ IMPORTANT: Keep metadata SIMPLE! Only add fields you can clearly extract. Don't spend too much time analyzing.

💰 Price Flow:
If user gives "54,999 TL" → call clean_price_tool(price_text: "54,999 TL")

📝 When ALL required fields ready (including metadata):
Show PREVIEW:
"📝 İlan önizlemesi:
📱 [title]
💰 [price] TL
📦 Durum: [condition]
🏷️ Kategori: [category]
📍 [location]
🔧 Metadata: [type, brand if vehicle]

✅ Onaylamak için 'onayla' yazın
✏️ Değiştirmek için 'fiyat X olsun' gibi komutlar verin"

❌ If missing critical info (title or price):
"[Eksik alan] bilgisi gerekli. Lütfen belirtin."

🚫 NEVER call insert_listing_tool - that's PublishAgent's job!
🚫 DO NOT use search_listings_tool

Store prepared listing (with metadata!) in conversation context for PublishAgent.""",
    model="gpt-5.1",
    tools=[mcp],
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
   - stock: default 1
   
3. If no preview found → "Yayınlanacak bir ilan yok. Önce ürün bilgilerini verin."

⚠️ CRITICAL EXAMPLE:
User sees: "📝 İlan önizlemesi: 📱 2020 Renault Clio benzinli manuel 💰 900000 TL ... 🔧 Metadata: {"type":"vehicle","brand":"Renault"...}"
User says: "onayla"
→ You MUST extract all fields from the preview and call:
insert_listing_tool(
    title="2020 Renault Clio benzinli manuel",
    price=900000,
    category="Otomotiv",
    location="İstanbul",
    condition="used",
    description="...",
    metadata={"type":"vehicle","brand":"Renault","model":"Clio","year":2020,"fuel_type":"benzin","transmission":"manuel"},
    stock=1
)

✅ Success Response:
"✅ İlanınız başarıyla yayınlandı!
📱 [title]
💰 [price] TL
📍 [location]
🏷️ [category]

İlan ID: [EXTRACT FROM TOOL RESPONSE result[0]['id']]"

⚠️ CRITICAL: Extract listing ID from tool response:
- Tool returns: {"success": true, "result": [{"id": "uuid-here", ...}]}
- YOU MUST extract result[0]["id"] and show it to user
- DO NOT show user_id, show the ACTUAL listing ID from database

❌ If tool returns error:
"❌ İlan kaydedilemedi: [error message]
Lütfen bilgileri kontrol edip tekrar deneyin."

❌ If tool returns success=false or empty result:
"❌ İlan veritabanına kaydedilemedi. Lütfen daha sonra tekrar deneyin."

❌ No Preview Found:
"Yayınlanacak bir ilan yok. Önce ürün bilgilerini verin.

Örnek: '2020 Renault Clio satıyorum, 900 bin TL'"

🚫 DO NOT use clean_price_tool or search_listings_tool
🚫 DO NOT ask user for fields again - extract from conversation history!
🚫 DO NOT return user_id as listing ID - extract from tool response!""",
    model="gpt-5.1",
    tools=[mcp],  # FIXED: Use mcp (has insert_listing_tool), not mcp1
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

🎯 Your ONLY task: Search products using search_listings_tool.

📋 Parameter Extraction Rules:

🧠 USE YOUR REASONING! Don't rely only on examples, infer from user intent.

1. **query** → Extract product keywords from user message
   - "bisiklet var mı" → query="bisiklet"
   - "iPhone aramak istiyorum" → query="iPhone"
   - "23 Nisan Mahallesi" → query="23 Nisan" (search in location too!)
   - "sitedeki ilanları göster" → query=None (show all listings)
   - "neler var" → query=None (show all listings)
   
   🔄 STRATEGY: Generic terms like "araba"/"ev"
   - OPTION 1: Use query="araba" (tool will search title + category + description)
   - OPTION 2: Use category="Otomotiv" + leave query empty
   - Choose based on context! If user asks "araba var mı" → category works better
   - If user asks "23 Nisan'da araba" → query="23 Nisan araba" works better
   
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

3. **metadata_type** → Filter by listing type (NEW!)
   - "araba" / "araç" / "otomobil" → metadata_type="vehicle"
   - "yedek parça" / "aksesuar" → metadata_type="part"
   - Leave empty for all types

3. **condition** → "new" or "used" if mentioned

4. **location** → City name if mentioned
   - "İstanbul'da" → location="İstanbul"
   - IMPORTANT: For specific neighborhoods/districts (e.g., "23 Nisan Mahallesi", "Nilüfer"):
     → Use query parameter instead! (location field contains only city)
     → Example: "23 Nisan ile ilgili ilan" → query="23 Nisan", category="Emlak"

5. **min_price / max_price** → Extract price range
   - "5000 TL altı" → max_price=5000
   - "10000-20000 TL arası" → min_price=10000, max_price=20000
   - "65000 TL olan" → min_price=65000, max_price=65000 (exact match)
   - "tam 50000 TL" → min_price=50000, max_price=50000

6. **limit** → Default 10, increase if user asks for more

7. **metadata_type** → NEW! Filter by type:
   - User asks "araba" / "araç" → metadata_type="vehicle"
   - User asks "yedek parça" / "parça" → metadata_type="part"
   - User asks "aksesuar" → metadata_type="accessory"
   - Leave None for general searches

🔍 Search Strategy:
- If user mentions specific product → Set query parameter
- If user asks "what's available" / "show listings" → Leave query empty (None)
- Always call search_listings_tool with extracted parameters

✅ Results Format (when listings found):
"🔍 [X] sonuç bulundu:

1️⃣ [title]
   💰 [price] TL | 📍 [location] | [condition]

2️⃣ [title]
   💰 [price] TL | 📍 [location] | [condition]
..."

❌ No Results - SMART RESPONSE STRATEGY:

**STEP 1:** If user asked generic term or specific category:
→ Examples: "araba", "kiralık ev", "Emlak - Kiralık Daire"
→ Try searching with BROAD category only (e.g., "Emlak" not "Emlak - Kiralık Daire")
→ Fallback: Remove query parameter, use category only

**STEP 2:** If category search returns results:
→ For vehicles: Extract brand names (e.g., "BMW", "Clio")
→ For real estate: Extract property types from results
→ RESPONSE: "[X] ilan bulundu. Filtrelemeye yardımcı olabilmem için:
- Hangi marka/tür ilginizi çekiyor?
- Bütçeniz nedir?
- Hangi şehirde arıyorsunuz?"

**STEP 3:** If category search also returns 0:
→ "Aramanızla eşleşen ilan bulunamadı. 
İsterseniz daha spesifik bir arama deneyebiliriz (şehir, fiyat aralığı, oda sayısı vs.)"

**CRITICAL FIX FOR EXACT CATEGORY SEARCH:**
- User: "Emlak - Kiralık Daire kategorisindeki ilanları göster"
- YOU MUST: Use category="Emlak" (not exact string "Emlak - Kiralık Daire")
- Reason: Database uses ilike.%Emlak%, so partial match works!

**IMPORTANT:** 
- Always try BROAD category fallback (just main word: "Emlak", "Otomotiv", "Elektronik")
- Extract popular options from results and suggest them
- Make conversation helpful, not dead-end

🚫 NEVER use insert_listing_tool or clean_price_tool - only search_listings_tool!""",
    model="gpt-5.1",
    tools=[mcp2],
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

Tools available:
- list_user_listings_tool
- update_listing_tool
- clean_price_tool

NEVER use insert_listing_tool!""",
    model="gpt-5.1",
    tools=[mcp3],
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

🎯 Task: Handle greetings, guide users to marketplace.

Example:
User: "Merhaba"
→ "Merhaba! 👋 PazarGlobal'e hoş geldiniz!
   
   🛒 Ürün satmak için: Ürün bilgilerini yazın
   🔍 Ürün aramak için: Ne aradığınızı söyleyin"

Always end with question to guide back to marketplace actions.
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

✅ Response:
"🔄 İşlem iptal edildi.

Yeni bir işlem için:
• Ürün satmak: Ürün bilgilerini yazın
• Ürün aramak: Ne aradığınızı söyleyin"

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
    tools=[mcp4],
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
    conversation_history: list = []  # Previous messages from WhatsApp Bridge


# Main workflow runner
async def run_workflow(workflow_input: WorkflowInput):
    """
    Main agent workflow - routes user input to appropriate agents
    Uses OpenAI Agents SDK with MCP tools
    """
    with trace("PazarGlobal"):
        workflow = workflow_input.model_dump()
        
        # Build conversation history from previous messages
        conversation_history: list[TResponseInputItem] = []
        
        # Add previous conversation context if exists (NOT including current message)
        for msg in workflow.get("conversation_history", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Skip empty messages
            if not content:
                continue
            
            # CRITICAL: OpenAI Agents SDK uses different content types for user vs assistant
            if role == "user":
                conversation_history.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",  # User messages use input_text
                            "text": content
                        }
                    ]
                })
            elif role == "assistant":
                conversation_history.append({
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",  # Assistant messages use output_text!
                            "text": content
                        }
                    ]
                })
        
        # Add current user message (this is the new message to process)
        conversation_history.append({
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": workflow["input_as_text"]
                }
            ]
        })
        
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
