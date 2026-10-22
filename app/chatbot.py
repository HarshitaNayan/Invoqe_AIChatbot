import json
import random
from pathlib import Path
from typing import Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.preprocess import clean_text

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "intents.json"
THRESHOLD = 0.25
FALLBACK = "Sorry, I didn't understand that. Could you rephrase your question?"


class Chatbot:
    """TF-IDF + cosine similarity intent matcher."""

    def __init__(self, data_path: Path = DATA_PATH):
        with open(data_path, encoding="utf-8") as f:
            intents = json.load(f)["intents"]

        self.responses = {i["tag"]: i["responses"] for i in intents}
        patterns, self.tags = [], []
        for intent in intents:
            for pattern in intent["patterns"]:
                patterns.append(clean_text(pattern))
                self.tags.append(intent["tag"])

        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(patterns)

    def get_reply(self, message: str) -> Tuple[str, Optional[str], float]:
        cleaned = clean_text(message)
        if not cleaned:
            return FALLBACK, None, 0.0

        scores = cosine_similarity(self.vectorizer.transform([cleaned]), self.matrix)[0]
        best = int(scores.argmax())
        score = float(scores[best])

        if score < THRESHOLD:
            return FALLBACK, None, score

        tag = self.tags[best]
        return random.choice(self.responses[tag]), tag, score

    def context(self, message: str, k: int = 3, min_score: float = 0.1) -> str:
        """Top matching knowledge notes, passed to the LLM as context (RAG)."""
        cleaned = clean_text(message)
        if not cleaned:
            return ""
        scores = cosine_similarity(self.vectorizer.transform([cleaned]), self.matrix)[0]
        notes = []
        for i in scores.argsort()[::-1][:k]:
            if scores[i] >= min_score:
                note = self.responses[self.tags[i]][0]
                if note not in notes:
                    notes.append(note)
        return "\n".join(notes)
