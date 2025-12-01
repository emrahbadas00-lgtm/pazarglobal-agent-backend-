"""
Pazarglobal Agent Backend
FastAPI wrapper for Agent Builder workflow using OpenAI Agents SDK
"""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

# Import workflow runner
from workflow import run_workflow, WorkflowInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pazarglobal Agent Backend")

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://pazarglobal-production.up.railway.app")


class AgentRequest(BaseModel):
    """Request format for agent workflow"""
    user_id: str
    message: str
    conversation_history: list = []


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
    
    try:
        # Run workflow using Agents SDK
        logger.info(f"📚 Conversation history: {len(request.conversation_history)} messages")
        workflow_input = WorkflowInput(
            input_as_text=request.message,
            conversation_history=request.conversation_history
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
