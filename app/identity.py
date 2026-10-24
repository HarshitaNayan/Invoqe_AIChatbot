"""Creator identity is answered locally, so it also works without an LLM key."""
import re
CREATOR_REPLY = 'Hynex was created by Harshita Nayan.'
PATTERNS = [
    r'\bwho\s+(?:made|created|built|developed|designed|programmed)\s+(?:you|hynex)\b',
    r'\bwho\s+(?:is|are)\s+(?:your|hynex[’\']?s)\s+(?:creator|creators|developer|developers|maker|makers|founder)\b',
    r'\b(?:your|hynex[’\']?s)\s+(?:creator|developer|maker|founder)(?:[’\']?s)?\s+name\b',
    r'\b(?:who|whom)\s+(?:were|was)\s+(?:you|hynex)\s+(?:made|created|built|developed|designed)\s+by\b',
    r'\b(?:tumhe|tumko|aapko)\s+kisne\s+banaya\b',
    r'(?:तुम्हें|तुमको|आपको)\s*किसने\s*बनाया',
]
def creator_reply(message):
    text=re.sub(r'\s+',' ',message.lower()).strip()
    if any(re.search(pattern,text) for pattern in PATTERNS):return CREATOR_REPLY
    return None
