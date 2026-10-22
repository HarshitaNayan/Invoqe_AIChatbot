from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.chatbot import Chatbot
from app.llm import stream_gemini

bot: Optional[Chatbot] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot
    bot = Chatbot()  # load knowledge base + fit vectorizer once at startup
    yield


app = FastAPI(title="Hynex", lifespan=lifespan)


class Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Msg] = []


@app.post("/chat")
def chat(req: ChatRequest):
    history = [m.dict() for m in req.history]

    def generate():
        started = False
        try:
            for chunk in stream_gemini(history, req.message, bot.context(req.message)):
                started = True
                yield chunk
        except Exception as e:
            print("LLM ERROR:", repr(e))
            if not started:  # no key / API error: fall back to the local TF-IDF bot
                reply, _, _ = bot.get_reply(req.message)
                yield "Offline mode (LLM not connected). " + reply

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")