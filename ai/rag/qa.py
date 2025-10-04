# ================================================================
# qa.py
# ------------------------------------------------
# 💬 역할:
#   - 검색된 문서(Context)를 GPT-4o-mini로 전달하여 답변 생성
#   - 근거 페이지(p.xx) 인용 포함
# ================================================================

from typing import List, Dict
from llm_runtime.llm_client import chat

SYSTEM_PROMPT = (
  "You are a strict assistant for Dongyang Mirae University rules. "
  "Answer ONLY from the provided CONTEXT in Korean. "
  "If the answer is missing, say you cannot find it and DO NOT guess. "
  "Always append citations like [p.페이지번호]. Keep the answer concise."
)

def build_context(chunks: List[Dict]) -> str:
    lines=[]
    for c in chunks:
        p = c["meta"].get("page","?")
        lines.append(f"[p.{p}] {c['text']}")
    return "\n\n".join(lines)

def answer(query: str, chunks: List[Dict]) -> Dict:
    ctx = build_context(chunks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""질문:
{query}

지침:
1) 아래 CONTEXT에서만 답변.
2) 필요한 경우 bullet로 요약.
3) 각 근거 뒤에 [p.xx] 인용.

CONTEXT:
{ctx}"""}
    ]
    text = chat(messages, temperature=0.1, max_tokens=600)
    return {"answer": text, "sources": [{"page":c["meta"]["page"], "id":c["id"]} for c in chunks]}

