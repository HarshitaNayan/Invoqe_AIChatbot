"""Transparent reference-based lexical checks; never presented as factual truth."""
import re
from collections import Counter

def tokens(s):return re.findall(r'\w+',s.lower())
def evaluate(answer,reference=''):
    a=tokens(answer)
    result={'word_count':len(a),'notice':'Lexical overlap measures wording similarity, not factual correctness. Human review is still needed.'}
    if reference.strip():
        r=tokens(reference); common=sum((Counter(a)&Counter(r)).values())
        precision=common/len(a) if a else 0; recall=common/len(r) if r else 0
        result.update(precision=round(precision,3),recall=round(recall,3),token_f1=round(2*precision*recall/(precision+recall),3) if precision+recall else 0)
    return result
