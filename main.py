"""
Pazarglobal Agent Backend
FastAPI wrapper for Agent Builder workflow using OpenAI Agents SDK
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import json
import asyncio

# Import workflow runner
from workflow import run_workflow, WorkflowInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pazarglobal Agent Backend")

# CORS Configuration for Web Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.vercel.app",
        "https://*.railway.app",
        "*"  # Allow all origins for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://pazarglobal-production.up.railway.app")


class AgentRequest(BaseModel):
    """Request format for agent workflow"""
    user_id: str
    phone: Optional[str] = None  # WhatsApp phone number for user lookup
    message: str
    conversation_history: list = []
    media_paths: Optional[List[str]] = None
    media_type: Optional[str] = None
    draft_listing_id: Optional[str] = None
    session_token: Optional[str] = None
    user_context: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    """Response format from agent workflow"""
    response: str
    intent: str
    success: bool


class SpeechCorrectionRequest(BaseModel):
    """Request for speech text correction"""
    text: str
    user_id: Optional[str] = None


class SpeechCorrectionResponse(BaseModel):
    """Response with corrected speech text"""
    original: str
    corrected: str
    changes_made: bool


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Pazarglobal Agent Backend",
        "version": "2.0.0",
        "api_type": "Agents SDK + MCP",
        "openai_configured": bool(OPENAI_API_KEY),
        "mcp_server": MCP_SERVER_URL
    }


@app.post("/agent/run", response_model=AgentResponse)
async def run_agent_workflow(request: AgentRequest):
    """
    Main agent workflow endpoint
    
    Flow:
    1. RouterAgent classifies intent
    2. Route to specialized agent (via Agents SDK)
    3. Return response
    """
    logger.info(f"🎯 Running agent workflow for user: {request.user_id}")
    logger.info(f"📝 Message: {request.message}")
    
    # Resolve user UUID from phone number (WhatsApp) or use provided user_id (Web)
    resolved_user_id = request.user_id
    user_name = None
    
    # Prefer explicit user_name from user_context
    if request.user_context and request.user_context.get("name"):
        user_name = request.user_context.get("name")

    # If user_id looks like a phone number (starts with + or whatsapp:), resolve to UUID
    if request.phone or (request.user_id and (request.user_id.startswith('+') or request.user_id.startswith('whatsapp:'))):
        try:
            import httpx
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
            
            async with httpx.AsyncClient() as client:
                # Clean phone number (remove 'whatsapp:' prefix if present)
                phone_to_lookup = request.phone or request.user_id
                clean_phone = phone_to_lookup.replace('whatsapp:', '').strip()
                
                # Query profiles table by phone to get UUID
                profile_url = f"{supabase_url}/rest/v1/profiles"
                headers = {
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}"
                }
                params = {"phone": f"eq.{clean_phone}", "select": "id,full_name,phone"}
                
                resp = await client.get(profile_url, headers=headers, params=params)
                if resp.is_success and resp.json():
                    profile = resp.json()[0]
                    resolved_user_id = profile.get("id")  # ← UUID from profiles table
                    user_name = user_name or profile.get("full_name")
                    user_phone = profile.get("phone")  # Store phone for listing
                    logger.info(f"✅ Resolved phone {clean_phone} → UUID: {resolved_user_id}, name: {user_name}")
                else:
                    logger.warning(f"⚠️ No profile found for phone: {clean_phone}")
        except Exception as e:
            logger.error(f"❌ Error resolving user from phone: {str(e)}")
    
    try:
        # Run workflow using Agents SDK
        logger.info(f"📚 Conversation history: {len(request.conversation_history)} messages")
        workflow_input = WorkflowInput(
            input_as_text=request.message,
            conversation_history=request.conversation_history,
            media_paths=request.media_paths,
            media_type=request.media_type,
            draft_listing_id=request.draft_listing_id,
            user_name=user_name,  # Pass user name to workflow
            user_id=resolved_user_id,  # Use resolved UUID, not phone number
            user_phone=user_phone if 'user_phone' in locals() else None,  # Pass user phone
        )
        result = await run_workflow(workflow_input)
        
        if "error" in result:
            logger.error(f"❌ Workflow error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"✅ Workflow completed: intent={result['intent']}")
        
        return AgentResponse(
            response=result["response"],
            intent=result["intent"],
            success=result["success"]
        )
        
    except Exception as e:
        logger.error(f"❌ Agent workflow error: {str(e)}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/web-chat")
async def web_chat_endpoint(request: AgentRequest):
    """
    Web frontend chat endpoint with SSE (Server-Sent Events) streaming
    
    Request body:
    {
        "message": "User message",
        "user_id": "web_user_12345",
        "conversation_history": [],
        "session_id": "optional"
    }
    
    Response: SSE stream
    data: {"type":"text","content":"chunk"}
    data: {"type":"done"}
    """
    logger.info(f"💬 Web chat request from user_id={request.user_id}: {request.message[:100]}")

    # Resolve user profile from Supabase for personalization and authorization
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    profile_full_name = None
    owned_listing_ids: list[str] = []
    user_phone = request.user_context.get("phone") if request.user_context else None

    if supabase_url and supabase_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch profile by user_id
                profile_resp = await client.get(
                    f"{supabase_url}/rest/v1/profiles",
                    params={"id": f"eq.{request.user_id}", "select": "full_name, phone"},
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}"
                    },
                )
                if profile_resp.is_success and profile_resp.json():
                    profile = profile_resp.json()[0]
                    profile_full_name = profile.get("full_name")
                    user_phone = user_phone or profile.get("phone")

                # Fetch owned listings for authorization context
                listings_resp = await client.get(
                    f"{supabase_url}/rest/v1/listings",
                    params={"user_id": f"eq.{request.user_id}", "select": "id", "limit": 200},
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}"
                    },
                )
                if listings_resp.is_success:
                    owned_listing_ids = [item.get("id") for item in listings_resp.json() if item.get("id")]
        except Exception as e:
            logger.error(f"❌ Profile/listings fetch failed: {e}")
    
    try:
        async def generate_sse_stream():
            """Generator function for SSE streaming"""
            try:
                # Run workflow
                logger.info(f"📚 Web conversation history: {len(request.conversation_history)} messages")
                # Build auth context note for the agent
                auth_note_parts = [
                    f"user_id={request.user_id}",
                    f"name={profile_full_name or (request.user_context.get('name') if request.user_context else '')}",
                    f"email={(request.user_context.get('email') if request.user_context else '')}",
                    f"phone={user_phone or (request.user_context.get('phone') if request.user_context else '')}",
                    f"owned_listing_ids={owned_listing_ids}"
                ]
                auth_note = "[AUTH_CONTEXT] " + " | ".join(filter(None, auth_note_parts)) + " | KURAL: Sadece owned_listing_ids listesindeki ilanlar üzerinde güncelle/sil yap. Diğer ilanlara sadece görüntüleme izni var."

                enriched_history = request.conversation_history + [
                    {
                        "role": "assistant",
                        "content": auth_note
                    }
                ]

                workflow_input = WorkflowInput(
                    input_as_text=request.message,
                    conversation_history=enriched_history,
                    media_paths=request.media_paths,
                    media_type=request.media_type,
                    draft_listing_id=request.draft_listing_id,
                    user_name=profile_full_name,
                    user_id=request.user_id,
                    user_phone=user_phone,  # Pass user phone
                )
                result = await run_workflow(workflow_input)
                
                if "error" in result:
                    error_data = {"type": "error", "content": result["error"]}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                
                response_text = result.get("response", "")
                if not response_text:
                    error_data = {"type": "error", "content": "Empty response"}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    return
                
                logger.info(f"✅ Web workflow completed: intent={result['intent']}")
                
                # Stream response word by word for smooth UX
                words = response_text.split()
                for i, word in enumerate(words):
                    chunk = word if i == 0 else f" {word}"
                    data = {"type": "text", "content": chunk}
                    yield f"data: {json.dumps(data)}\n\n"
                    await asyncio.sleep(0.02)  # 20ms delay
                
                # Send completion signal
                done_data = {"type": "done"}
                yield f"data: {json.dumps(done_data)}\n\n"
                
            except Exception as e:
                logger.error(f"❌ SSE stream error: {str(e)}")
                logger.exception(e)
                error_data = {"type": "error", "content": str(e)}
                yield f"data: {json.dumps(error_data)}\n\n"
        
        return StreamingResponse(
            generate_sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Web chat endpoint error: {str(e)}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/correct-speech", response_model=SpeechCorrectionResponse)
async def correct_speech(request: SpeechCorrectionRequest):
    """
    Speech Gateway - Text Correction Endpoint
    
    Takes raw speech-to-text output and corrects:
    - Spelling errors
    - Missing punctuation
    - Grammar issues
    - Filler words (eee, şey, ııı)
    - Contextual errors
    
    Uses GPT-4o-mini for cost-effective, fast correction.
    """
    logger.info(f"🎤 Speech correction request from user: {request.user_id or 'anonymous'}")
    logger.info(f"📝 Original text: {request.text}")
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        correction_prompt = f"""Sen otomatik konuşma tanıma (STT) sisteminden gelen Türkçe metinleri düzelten bir asistansın.

GÖREVIN:
- Yazım hatalarını düzelt
- Noktalama işaretleri ekle
- Bağlama göre yanlış algılanan kelimeleri düzelt
- Dolgu kelimelerini kaldır (eee, şey, ııı, hmm, işte)
- Doğal Türkçe cümle yapısına çevir
- Anlam değiştirme, sadece düzelt

KURALLAR:
- Sayıları rakamlarla yaz (otuz bin → 30000, beşyüz → 500)
- Fiyatları doğru formatla (otuz bin lira → 30000 TL)
- Kısa ve öz tut
- Sadece düzeltilmiş metni döndür, açıklama yapma

MARKA İSİMLERİ (Türkçe telaffuz → Orijinal yazılış):
- sitroen, citron, sitroyen → Citroen
- ayfon, ayfın, ayfone → iPhone
- ayped, aypad → iPad
- samsıng, samsung → Samsung
- huavey, huawei → Huawei
- reno, renault → Renault
- porşe, porş → Porsche
- mersedes, mercedes → Mercedes
- bımvı, bm, bemve → BMW
- foksvagen, volkswagen, wolkswagen → Volkswagen
- fiat, fıat → Fiat
- ford, fort → Ford
- hundai, hyndai → Hyundai
- kia, kıa → Kia
- toyta, toyota → Toyota
- nissan, nisan → Nissan
- honda, handa → Honda
- mazda, masda → Mazda
- suzuki, suzüki → Suzuki
- opel, öpel → Opel
- renaut, renau → Renault
- pejo, pöjö, peugot → Peugeot
- cıtrıon → Citroen
- lenova, lenavo → Lenovo
- ecer, eyser, acer → Acer
- esus, asus → ASUS
- dekl, dell → Dell
- eçpi, hp → HP

HAM METİN:
{request.text}

DÜZELTİLMİŞ METİN:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen hızlı ve doğru metin düzelten bir asistansın. Sadece düzeltilmiş metni döndür."},
                {"role": "user", "content": correction_prompt}
            ],
            max_tokens=150,
            temperature=0.3  # Low temperature for consistent corrections
        )
        
        corrected_text = response.choices[0].message.content.strip()
        changes_made = corrected_text.lower() != request.text.lower()
        
        logger.info(f"✅ Corrected text: {corrected_text}")
        logger.info(f"🔄 Changes made: {changes_made}")
        
        return SpeechCorrectionResponse(
            original=request.text,
            corrected=corrected_text,
            changes_made=changes_made
        )
        
    except Exception as e:
        logger.error(f"❌ Speech correction error: {str(e)}")
        logger.exception(e)
        # Fallback: return original text if correction fails
        return SpeechCorrectionResponse(
            original=request.text,
            corrected=request.text,
            changes_made=False
        )


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "checks": {
            "openai_key": "configured" if OPENAI_API_KEY else "missing",
            "mcp_server": MCP_SERVER_URL
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
