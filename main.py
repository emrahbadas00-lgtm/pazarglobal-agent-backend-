"""
Pazarglobal Agent Backend
FastAPI wrapper for Agent Builder workflow using OpenAI Agents SDK
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
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


class AgentResponse(BaseModel):
    """Response format from agent workflow"""
    response: str
    intent: str
    success: bool


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
    
    # Get user profile from Supabase if phone provided
    user_name = None
    if request.phone:
        try:
            import httpx
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
            
            async with httpx.AsyncClient() as client:
                # Clean phone number (remove 'whatsapp:' prefix if present)
                clean_phone = request.phone.replace('whatsapp:', '').strip()
                
                # Query profiles table by phone
                profile_url = f"{supabase_url}/rest/v1/profiles"
                headers = {
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}"
                }
                params = {"phone": f"eq.{clean_phone}", "select": "full_name"}
                
                resp = await client.get(profile_url, headers=headers, params=params)
                if resp.is_success and resp.json():
                    profile = resp.json()[0]
                    user_name = profile.get("full_name")
                    logger.info(f"👤 User profile found: {user_name}")
                else:
                    logger.warning(f"⚠️ No profile found for phone: {clean_phone}")
        except Exception as e:
            logger.error(f"❌ Error fetching user profile: {str(e)}")
    
    try:
        # Run workflow using Agents SDK
        logger.info(f"📚 Conversation history: {len(request.conversation_history)} messages")
        workflow_input = WorkflowInput(
            input_as_text=request.message,
            conversation_history=request.conversation_history,
            media_paths=request.media_paths,
            media_type=request.media_type,
            draft_listing_id=request.draft_listing_id,
            user_name=user_name  # Pass user name to workflow
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
    
    try:
        async def generate_sse_stream():
            """Generator function for SSE streaming"""
            try:
                # Run workflow
                logger.info(f"📚 Web conversation history: {len(request.conversation_history)} messages")
                workflow_input = WorkflowInput(
                    input_as_text=request.message,
                    conversation_history=request.conversation_history,
                    media_paths=request.media_paths,
                    media_type=request.media_type,
                    draft_listing_id=request.draft_listing_id
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
