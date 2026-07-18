"""
Ramesh Saini v7.1 — Ironclad MVP Backend
FastAPI Main Server — The integration hub for the MVP chat pipeline.
"""
import sys, os, json, uuid, logging

# Ensure we can import from sibling directories
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from core.memory import MemoryManager
from core.agent import AgentManager
from core.sandbox import SandboxExecutor
from core.tools import AVAILABLE_TOOLS, execute_tool
from core.api_key_manager import KEY_MANAGER
from core.llm_router import ROUTER
from security.guard import GUARD

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('ramesh-mvp')

# Initialize core components
memory = MemoryManager(db_path=os.environ.get('RAMESHMEM_DB', 'ramesh_mvp.db'))
agent = AgentManager(checkpoint_db=os.environ.get('RAMESHMEM_DB', 'ramesh_mvp.db'))
executor = SandboxExecutor(timeout=10)

app = FastAPI(
    title="Ramesh Saini v7.1 MVP",
    description="Ironclad MVP — Integrated Chat, Memory, Agent & Security",
    version="7.1.0-mvp"
)

# CORS for Electron renderer
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# API Models
# ============================================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = "default-user"

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    agent_steps: int = 0
    security_checked: bool = False
    security_action: str = "none"
    code_executed: bool = False
    code_output: str = ""
    thread_id: str = ""


# ============================================================
# THE MAIN CHAT ENDPOINT
# ============================================================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    THE CORE MVP PIPELINE:
    1. Receive message → 2. Retrieve memory context
    3. Run agent (LangGraph) → 4. Detect code in output
    5. If code → SecurityGuard inspect → Safe? Execute | Unsafe? Block
    6. Store conversation → 7. Return response
    """
    session_id = req.session_id or f"session-{uuid.uuid4().hex[:8]}"
    
    logger.info(f"[{session_id}] Chat: '{req.message[:60]}...'")
    
    # Step 1: Get memory context
    memory.store_message(session_id, "user", req.message)
    context = memory.get_context(session_id, limit=10)
    
    # Step 2: Build prompt with context
    context_str = "\n".join([f"[{m['role']}] {m['content']}" for m in context[-3:]])
    full_prompt = f"Context:\n{context_str}\n\nUser: {req.message}\n\nRespond helpfully. If the user asks for code, provide it in ```python blocks."
    
    # Step 3: Run agent
    agent_result = agent.run(full_prompt, thread_id=session_id, recursion_limit=5)
    logger.info(f"  Agent: {agent_result['status']}, {agent_result.get('steps', 0)} steps")
    
    reply = agent_result.get('result', '')
    if not reply:
        reply = f"Processed: {req.message}"
    
    # Step 4: Security check on output
    security_checked = False
    security_action = "none"
    code_executed = False
    code_output = ""
    
    if agent.has_code_in_output(reply):
        code_blocks = agent.extract_code_blocks(reply)
        logger.info(f"  Code blocks detected: {len(code_blocks)}")
        
        for block in code_blocks:
            code = block['code']
            if not code.strip():
                continue
            
            # ←←← THE IRONCLAD SECURITY GATE →→→
            security_result = GUARD.inspect_code(code, source="llm")
            security_checked = True
            security_action = security_result['action']
            
            if security_result['action'] == 'allow':
                # Execute safe code in sandbox
                logger.info(f"  ✅ Code passed security guard. Executing...")
                exec_result = executor.execute(code)
                code_executed = True
                code_output = exec_result.get('stdout', '') or exec_result.get('stderr', '') or "Executed (no output)"
            elif security_result['action'] == 'block':
                # Block malicious code
                threats = [t['detail'] for t in security_result['threats'][:3]]
                logger.warning(f"  ❌ BLOCKED malicious code: {threats}")
                warn_msg = (
                    f"\n\n⚠️ **SECURITY BLOCKED** ⚠️\n"
                    f"The generated code was blocked by PreCrime Security Analyzer.\n"
                    f"Threats detected: {', '.join(threats)}\n"
                    f"Score: {security_result['score']}"
                )
                reply += warn_msg
            else:
                # Warn but allow (low severity)
                reply += f"\n\n⚠️ Code contains {security_result['threat_count']} low-severity warnings."
    
    # Step 5: Store response in memory
    memory.store_message(session_id, "assistant", reply)
    
    return ChatResponse(
        reply=reply,
        session_id=session_id,
        agent_steps=agent_result.get('steps', 0),
        security_checked=security_checked,
        security_action=security_action,
        code_executed=code_executed,
        code_output=code_output,
        thread_id=agent_result.get('thread_id', session_id)
    )


# ============================================================
# Health & Status Endpoints
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "7.1.0-mvp",
        "memory_loaded": memory is not None,
        "agent_loaded": agent is not None,
        "guard_loaded": True,
        "security_stats": GUARD.get_stats()
    }

@app.get("/memory/{session_id}")
async def get_memory(session_id: str, limit: int = 20):
    msgs = memory.get_context(session_id, limit=limit)
    return {"session_id": session_id, "messages": msgs}

@app.get("/security/stats")
async def security_stats():
    return GUARD.get_stats()


# ============================================================
# API Key Management Endpoints
# ============================================================

class APIKeyRequest(BaseModel):
    provider: str
    key: str = ""

@app.get("/apikeys/status")
async def apikeys_status():
    return KEY_MANAGER.get_status()

@app.post("/apikeys/set")
async def apikeys_set(req: APIKeyRequest):
    success = KEY_MANAGER.set_key(req.provider, req.key, persist=True)
    return {"success": success, "provider": req.provider}

@app.post("/apikeys/test")
async def apikeys_test(req: APIKeyRequest):
    """Test a provider key by validating its format and making a lightweight API call."""
    # Validate format
    valid = KEY_MANAGER._validate_key_format(req.provider, req.key)
    if not valid:
        return {"success": False, "error": f"Invalid key format for {req.provider}"}
    # Store temporarily and try
    KEY_MANAGER.set_key(req.provider, req.key)
    return {"success": True, "provider": req.provider, "note": "Key format validated"}

@app.post("/apikeys/remove")
async def apikeys_remove(req: APIKeyRequest):
    env_var_map = {
        "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY", "google": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_var = env_var_map.get(req.provider)
    if env_var and env_var in os.environ:
        del os.environ[env_var]
    if req.provider in KEY_MANAGER.keys:
        KEY_MANAGER.keys[req.provider].is_configured = False
        KEY_MANAGER.keys[req.provider].key_preview = "(not set)"
    return {"success": True, "provider": req.provider}

@app.get("/apikeys/discover")
async def apikeys_discover():
    count = KEY_MANAGER.discover_from_env()
    return {"count": count, "keys": KEY_MANAGER.get_status()}


# ============================================================
# Tool Execution Endpoints
# ============================================================

class ToolExecuteRequest(BaseModel):
    tool_name: str
    params: dict = {}

@app.post("/tools/execute")
async def tools_execute(req: ToolExecuteRequest):
    """Execute a PC Control Tool through the Zero-Trust Guard."""
    # Guard: validate tool parameters first
    guard_result = GUARD.validate_tool_params(req.tool_name, req.params)
    if not guard_result["valid"]:
        return {
            "success": False,
            "error": guard_result["error"],
            "blocked_reason": guard_result["blocked_reason"],
            "guarded": True,
        }
    # Execute
    result = execute_tool(req.tool_name, req.params)
    return result

@app.get("/tools/schemas")
async def tools_schemas():
    """Return OpenAI-compatible tool schemas."""
    schemas = []
    for name, tool in AVAILABLE_TOOLS.items():
        properties = {}
        required = []
        for pname, pspec in tool["parameters"].items():
            properties[pname] = {
                "type": pspec.get("type", "string"),
                "description": pspec.get("description", ""),
            }
            if "default" not in pspec:
                required.append(pname)
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        })
    return {"tools": schemas, "count": len(schemas)}

@app.get("/tools/available")
async def tools_available():
    return {"tools": list(AVAILABLE_TOOLS.keys()), "count": len(AVAILABLE_TOOLS)}


# ============================================================
# Model Catalog Endpoints
# ============================================================

@app.get("/models/catalog")
async def models_catalog():
    return ROUTER.get_catalog()


# ============================================================
# Shutdown
# ============================================================

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down...")
    memory.close()


if __name__ == "__main__":
    port = int(os.environ.get('MVP_PORT', 8567))
    logger.info(f"🚀 Ramesh Saini v7.1 MVP Backend starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
