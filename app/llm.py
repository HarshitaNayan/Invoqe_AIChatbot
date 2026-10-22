import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SYSTEM = (
    "You are Hynex, an AI learning assistant. Explain clearly and step by step, "
    "give short examples, and format answers in markdown. "
    "Use the knowledge notes below only when they are relevant."
)


def stream_gemini(history, message, context):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    system = SYSTEM + (f"\n\nKnowledge notes:\n{context}" if context else "")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in history[-10:]
    ]
    contents.append({"role": "user", "parts": [{"text": message}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:streamGenerateContent?alt=sse"
    r = requests.post(
        url,
        headers={"x-goog-api-key": key},
        json={"system_instruction": {"parts": [{"text": system}]}, "contents": contents},
        stream=True,
        timeout=60,
    )
    r.raise_for_status()
    r.encoding = "utf-8"
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            try:
                data = json.loads(line[5:])
            except ValueError:
                continue
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "text" in part:
                    yield part["text"]