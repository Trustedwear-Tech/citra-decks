"""
openai_compat.py — OpenAI-Compatible Chat Completions API

Exposes Citra's LLM models via the standard OpenAI `/v1/chat/completions`
and `/v1/models` endpoints so that OpenClaw (or any OpenAI-compatible client)
can use Citra as an LLM provider.

Model mapping:
  citra-reasoning          → llm_call(model=get_default_model())
  citra-fast               → llm_call(model=get_default_model())
  citra-internet           → llm_call_with_internet()
"""

import time
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Model Registry ───────────────────────────────────────────────────────────

CITRA_MODELS = {
    "citra-reasoning": {
        "id": "citra-reasoning",
        "object": "model",
        "created": 1700000000,
        "owned_by": "citra",
        "description": "LLM reasoning model — best for complex tasks",
        "internal_model": None,
        "handler": "llm_call",
    },
    "citra-fast": {
        "id": "citra-fast",
        "object": "model",
        "created": 1700000000,
        "owned_by": "citra",
        "description": "LLM fast model — optimized for speed",
        "internal_model": None,
        "handler": "llm_call",
    },
    "citra-internet": {
        "id": "citra-internet",
        "object": "model",
        "created": 1700000000,
        "owned_by": "citra",
        "description": "LLM with internet search — for real-time data and current events",
        "internal_model": None,
        "handler": "llm_call_with_internet",
    },
}


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = Field(default=10000)
    temperature: Optional[float] = Field(default=0.7)
    stream: Optional[bool] = Field(default=False)
    # Additional OpenAI params we accept but may ignore
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[List[str]] = None


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: UsageInfo


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/v1/models")
async def list_models():
    """List available Citra models (OpenAI-compatible)."""
    data = [
        ModelInfo(
            id=m["id"],
            object=m["object"],
            created=m["created"],
            owned_by=m["owned_by"],
        )
        for m in CITRA_MODELS.values()
    ]
    return ModelListResponse(object="list", data=data)


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    """
    OpenAI-compatible Chat Completions endpoint.

    Delegates to llm_oss.py functions with credit check and billing.
    Auth is handled by JWTAuthMiddleware — user_id and user_email
    are available on request.state.
    """
    # ── Validate model ───────────────────────────────────────────────────
    model_key = body.model
    # Strip "citra/" prefix if present (OpenClaw sends "citra/citra-reasoning")
    if model_key.startswith("citra/"):
        model_key = model_key[len("citra/"):]

    model_info = CITRA_MODELS.get(model_key)
    if not model_info:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": f"Model '{body.model}' not found. Available: {list(CITRA_MODELS.keys())}",
                    "type": "invalid_request_error",
                    "code": "model_not_found",
                }
            },
        )

    # ── Streaming not supported yet ──────────────────────────────────────
    if body.stream:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Streaming is not yet supported. Set stream=false.",
                    "type": "invalid_request_error",
                    "code": "streaming_not_supported",
                }
            },
        )

    # ── Extract system / user prompts from messages ──────────────────────
    system_parts = []
    user_parts = []
    for msg in body.messages:
        if msg.role == "system":
            system_parts.append(msg.content)
        elif msg.role == "user":
            user_parts.append(msg.content)
        elif msg.role == "assistant":
            # Include assistant messages as context in user prompt
            user_parts.append(f"[Assistant previously said]: {msg.content}")

    system_prompt = "\n\n".join(system_parts) if system_parts else "You are a helpful AI assistant."
    user_prompt = "\n\n".join(user_parts) if user_parts else ""

    if not user_prompt:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "At least one user message is required.",
                    "type": "invalid_request_error",
                    "code": "missing_user_message",
                }
            },
        )

    # ── Resolve authenticated user ───────────────────────────────────────
    user_id = getattr(request.state, "user_id", None)
    user_email = getattr(request.state, "user_email", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Authentication required. Provide a valid Bearer token.",
                    "type": "authentication_error",
                    "code": "invalid_api_key",
                }
            },
        )

    logger.info(f"🤖 [OPENAI_COMPAT] {model_key} request from {user_email} ({len(body.messages)} messages)")

    # ── Call the appropriate llm_oss function ─────────────────────────
    try:
        handler = model_info["handler"]
        internal_model = model_info["internal_model"]

        if handler == "llm_call_with_internet":
            from llm_oss import llm_call_with_internet

            answer = llm_call_with_internet(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=internal_model,
                user_id=user_id,
                user_email=user_email,
                max_tokens=body.max_tokens or 10000,
                temperature=body.temperature or 0.7,
            )
        else:
            from llm_oss import llm_call

            answer = llm_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=internal_model,
                user_id=user_id,
                user_email=user_email,
                max_tokens=body.max_tokens or 10000,
                temperature=body.temperature or 0.7,
            )
    except HTTPException:
        # Re-raise FastAPI HTTPExceptions (402 insufficient credits, etc.)
        raise
    except ImportError as e:
        logger.error(f"❌ [OPENAI_COMPAT] llm_oss import failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": "llm_oss backend is not available. Please try again later.",
                    "type": "server_error",
                    "code": "backend_unavailable",
                }
            },
        )
    except Exception as e:
        logger.error(f"❌ [OPENAI_COMPAT] llm_oss call failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "code": "internal_error",
                }
            },
        )

    # ── Build OpenAI-format response ─────────────────────────────────────
    # Estimate token counts (rough approximation — actual counts are billed
    # internally by llm_oss.py via track_query_usage)
    prompt_tokens = sum(len(m.content.split()) for m in body.messages) * 2
    completion_tokens = len(answer.split()) * 2

    response = ChatCompletionResponse(
        id=f"chatcmpl-citra-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=body.model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=answer),
                finish_reason="stop",
            )
        ],
        usage=UsageInfo(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )

    logger.info(f"✅ [OPENAI_COMPAT] {model_key} response sent to {user_email} (~{completion_tokens} tokens)")
    return response
