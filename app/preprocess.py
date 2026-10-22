import re
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS


def clean_text(text: str) -> str:
    """Lowercase, strip punctuation and remove stopwords."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = text.split()
    filtered = [t for t in tokens if t not in ENGLISH_STOP_WORDS]
    # if everything was a stopword (e.g. "who are you"), keep the original tokens
    return " ".join(filtered or tokens)
