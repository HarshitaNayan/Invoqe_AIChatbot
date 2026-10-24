from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Request
from app.extensions import router, prepare_context, install_extensions
from app.storage import init_db
from app.google_login import router as google_router, init_google_tables
from app.identity import creator_reply
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.chatbot import Chatbot
from app.llm import stream_gemini

bot: Optional[Chatbot] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot
    init_db()
    init_google_tables()
    bot = Chatbot()  # load knowledge base + fit vectorizer once at startup
    yield


app = FastAPI(title="Hynex", lifespan=lifespan)
install_extensions(app)
app.include_router(router)
app.include_router(google_router)


class Msg(BaseModel):
    role: str
    content: str = Field(max_length=50000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    history: List[Msg] = Field(default_factory=list, max_length=100)
    attachment_ids: List[str] = Field(default_factory=list, max_length=6)


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    identity = creator_reply(req.message)
    if identity:
        return StreamingResponse(iter([identity]), media_type="text/plain; charset=utf-8")
    history = [m.model_dump() for m in req.history]
    enhanced, docs = prepare_context(request, req.message, req.attachment_ids)

    def generate():
        started = False
        try:
            for chunk in stream_gemini(history, req.message, bot.context(req.message) + "\n\n" + enhanced, docs):
                started = True
                yield chunk
        except Exception as e:
            print("LLM ERROR:", type(e).__name__)
            if started:
                yield "\n\n[Connection interrupted. Please retry your question.]"
            if not started:  # no key / API error: fall back to the local TF-IDF bot
                reply, _, _ = bot.get_reply(req.message)
                yield "Offline mode (LLM not connected). " + reply

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")