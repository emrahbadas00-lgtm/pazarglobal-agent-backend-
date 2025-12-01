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
- **"pin_request"** → user needs PIN authentication (always check session first!)
- **"create_listing"** → user wants to SELL an item
- **"update_listing"** → user wants to CHANGE existing listing
- **"delete_listing"** → user wants to DELETE/REMOVE existing listing
- **"publish_listing"** → user CONFIRMS listing
- **"search_product"** → user wants to BUY or SEARCH
- **"small_talk"** → greetings, casual conversation
- **"cancel"** → user cancels operation

## Keywords:

pin_request: ONLY if message is PURE 4-6 digits ("1234", "5678") - NO TEXT ALLOWED
create_listing: "satıyorum", "satmak", "satayım", "-um var", "ilan vermek"
update_listing: "değiştir", "güncelle", "fiyat olsun", "fiyatını yap", "düzenle"
delete_listing: "sil", "silebilir", "silmek", "silme", "kaldır", "ilanımı iptal", "ilanını sil"
publish_listing: "onayla", "yayınla", "tamam", "evet", "paylaş"
search_product: "almak", "arıyorum", "var mı", "bul", "uygun", "ucuz", "bisiklet" (DEFAULT for queries)
small_talk: "merhaba", "selam", "teşekkür", "nasılsın", "yardım"
cancel: "iptal", "vazgeç", "sıfırla", "başa dön" (WITHOUT "ilan" word)

## Priority:
1. search_product (DEFAULT - "var mı" ALWAYS goes here)
2. create_listing
3. update_listing
4. delete_listing (if "ilan" + "sil")
5. publish_listing
6. pin_request (ONLY if message is PURE 4-6 digits)
7. cancel (only if "iptal/vazgeç" WITHOUT "ilan")
8. small_talk

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

🎯 Your task: PREPARE listing, DO NOT insert to database yet.

📋 Extract fields:
- title → product title
- price → numeric price (call clean_price_tool if text)
- condition → "new", "used", "refurbished"
- category → infer from product
- description → friendly Turkish
- location → default "Türkiye"
- stock → default 1

💰 Price Flow:
If user gives "54,999 TL" → call clean_price_tool(price_text: "54,999 TL")

📝 When ALL required fields ready:
Show PREVIEW:
"📝 İlan önizlemesi:
📱 [title]
💰 [price] TL
📦 Durum: [condition]
📍 [location]

✅ Onaylamak için 'onayla' yazın
✏️ Değiştirmek için 'fiyat X olsun' gibi komutlar verin"

❌ If missing critical info (title or price):
"[Eksik alan] bilgisi gerekli. Lütfen belirtin."

🚫 NEVER call insert_listing_tool - that's PublishAgent's job!
🚫 DO NOT use search_listings_tool

Store prepared listing in conversation context for PublishAgent.""",
    model="gpt-5.1",
    tools=[mcp],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="medium",
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
1. Check conversation context for prepared listing
2. If found → call insert_listing_tool with ALL fields
3. If not found → ask user to create listing first

✅ Success Response:
"✅ İlanınız başarıyla yayınlandı!
📱 [title]
💰 [price] TL
📍 [location]

İlan ID: [supabase_id]"

❌ If tool returns error:
"❌ İlan kaydedilemedi: [error message]
Lütfen bilgileri kontrol edip tekrar deneyin."

❌ No Pending Listing:
"Yayınlanacak bir ilan yok. Önce ürün bilgilerini verin."

🚫 DO NOT use clean_price_tool or search_listings_tool""",
    model="gpt-5.1",
    tools=[mcp1],
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
1. **query** → Extract product keywords from user message
   - "bisiklet var mı" → query="bisiklet"
   - "iPhone aramak istiyorum" → query="iPhone"
   - "sitedeki ilanları göster" → query=None (show all listings)
   - "neler var" → query=None (show all listings)
   
2. **category** → Infer from context if mentioned
   - "elektronik" / "telefon" / "bilgisayar" etc.

3. **condition** → "new" or "used" if mentioned

4. **location** → City name if mentioned
   - "İstanbul'da" → location="İstanbul"

5. **min_price / max_price** → Extract price range
   - "5000 TL altı" → max_price=5000
   - "10000-20000 TL arası" → min_price=10000, max_price=20000

6. **limit** → Default 10, increase if user asks for more

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

❌ No Results:
"Aramanızla eşleşen ilan bulunamadı. Başka bir arama denemek ister misiniz?"

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

Update user's existing listings.

Flow:
1. Call list_user_listings_tool
2. Show listings
3. Ask which to update
4. Call clean_price_tool if needed
5. Call update_listing_tool

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


# Main workflow runner
async def run_workflow(workflow_input: WorkflowInput):
    """
    Main agent workflow - routes user input to appropriate agents
    Uses OpenAI Agents SDK with MCP tools
    """
    with trace("PazarGlobal"):
        workflow = workflow_input.model_dump()
        conversation_history: list[TResponseInputItem] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": workflow["input_as_text"]
                    }
                ]
            }
        ]
        
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
        # if intent == "pin_request":
        #     result = await Runner.run(
        #         pinrequestagent,
        #         input=[*conversation_history],
        #         run_config=RunConfig(trace_metadata={
        #             "__trace_source__": "agent-builder",
        #             "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
        #         })
        #     )
        if intent == "create_listing":
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
