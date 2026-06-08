import os
import time
import httpx
from collections import defaultdict
from typing import List, Optional, Union, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import get_current_user
from db import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/ai", tags=["AI"])

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"   # supports vision


_rate_store: dict = defaultdict(list)
RATE_LIMIT = 20
RATE_WINDOW = 60

def _check_rate_limit(user_id: int):
    now = time.time()
    timestamps = _rate_store[user_id]

    _rate_store[user_id] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_rate_store[user_id]) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много запросов к ИИ. Подождите немного и попробуйте снова.",
        )
    _rate_store[user_id].append(now)


class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Any]]


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    max_tokens: int = 2000
    temperature: float = 0.7
    class_id: Optional[int] = None
    lecture_context: Optional[str] = None


class ChatResponse(BaseModel):
    content: str


def _serialize_message(m: ChatMessage) -> dict:

    if isinstance(m.content, str):
        return {"role": m.role, "content": m.content}

    return {"role": m.role, "content": m.content}


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    body: ChatRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please set OPENAI_API_KEY on the server.",
        )

    _check_rate_limit(current_user.id)

    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    max_tokens = min(body.max_tokens, 4000)


    has_vision = any(
        isinstance(m.content, list) for m in body.messages
    )
    model = OPENAI_MODEL

    payload = {
        "model": model,
        "messages": [_serialize_message(m) for m in body.messages],
        "max_tokens": max_tokens,
        "temperature": body.temperature,
    }

    if body.lecture_context:
        payload["messages"].insert(0, {
            "role": "system",
            "content": f"Материалы класса (отвечай опираясь на них):\n{body.lecture_context[:8000]}",
        })

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                OPENAI_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timed out")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"AI service unreachable: {e}")

    if not resp.is_success:
        try:
            err = resp.json()
            msg = err.get("error", {}).get("message", f"OpenAI error {resp.status_code}")
        except Exception:
            msg = f"OpenAI error {resp.status_code}"
        raise HTTPException(status_code=502, detail=msg)

    data = resp.json()
    content = data["choices"][0]["message"]["content"]


    try:
        usage = data.get("usage", {})
        from models import AiUsageLog
        log = AiUsageLog(
            user_id=current_user.id,
            class_id=body.class_id,
            endpoint="chat_vision" if has_vision else "chat",
            org_type=current_user.org_type,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        db.add(log)
        db.commit()
    except Exception:
        pass

    return ChatResponse(content=content)
