import asyncio
import logging
import json
import time
import os
import sys
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from agents.orchestrator import Orchestrator

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("agos.servant")

app = FastAPI(title="AGOS A2A Servant")
orchestrator = Orchestrator()

# --- A2A Agent Card (Section 16 Discovery) ---
AGENT_CARD = {
    "schemaVersion": "1.0",
    "humanReadableId": "agos-sovereign-kernel",
    "name": "AGOS Sovereign Servant",
    "description": "Principal-grade OS agent for macOS syscalls and systems orchestration.",
    "capabilities": {
        "a2aVersion": "1.0",
        "streaming": True,
        "security": "mTLS"
    },
    "skills": [
        {"id": "sys_info", "name": "System Profiler"},
        {"id": "macos_control", "name": "macOS Syscall Interface"},
        {"id": "code_gen", "name": "Code Synthesis"}
    ]
}

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return AGENT_CARD

# --- JSON-RPC 2.0 A2A Handlers ---
class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict
    id: Optional[int] = None

@app.post("/a2a")
async def handle_a2a(request: JsonRpcRequest):
    logger.info(f"A2A Request: {request.method}")
    
    if request.method == "submit_task":
        intent = request.params.get("intent")
        agent_uuid = request.params.get("agent_uuid", "unknown")
        
        # Steel-thread: execute immediately for now
        result = await orchestrator.execute(intent, agent_uuid=agent_uuid)
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "success": result.success,
                "output": result.output,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
                "ttft_ms": result.ttft_ms,
                "itl_ms": result.itl_ms,
                "total_latency_ms": result.total_latency_ms,
                "agent_uuid": result.agent_uuid,
                "error": result.error or ""
            },
            "id": request.id
        }
    
    return {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": "Method not found"},
        "id": request.id
    }

# --- SSE Streaming (Server-Sent Events) ---
@app.get("/a2a/stream/{task_id}")
async def stream_task(task_id: str, intent: str):
    async def event_generator():
        yield f"data: {json.dumps({'event': 'started', 'task_id': task_id})}\n\n"
        
        try:
            result = await orchestrator.execute(intent, agent_uuid="a2a-stream")
            payload = {
                'event': 'completed',
                'output': result.output,
                'tokens_used': result.tokens_used
            }
            yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    # Start on 50051 to match the previously planned Go gRPC port
    uvicorn.run(app, host="0.0.0.0", port=50051)
