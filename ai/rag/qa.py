# ================================================================
# qa.py
# ------------------------------------------------
# 💬 역할:
#   - 검색된 문서(Context)를 GPT-4o-mini로 전달하여 답변 생성
#   - 근거 페이지(p.xx) 인용 포함 / 컨텍스트 없을 때 안전 처리
# ================================================================

from typing import List, Dict
import os
from llm_runtime.llm_client import chat

# 전체 컨텍스트 길이 상한(과도한 프롬프트로 인한 속도 저하 방지)
MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "9000"))

SYSTEM_PROMPT = (
    "You are a strict assistant for Dongyang Mirae University rules.\n"
    "Answer ONLY from the provided CONTEXT in Korean.\n"
    "If the answer is missing, say you cannot find it and DO NOT guess.\n"
    "Always append citations like [p.페이지번호]. Keep the answer concise."
)

def _safe_page(meta: Dict) -> str:
    try:
        p = meta.get("page")
        # page가 None/0/음수일 수 있으니 표기만 안전하게 처리
        return str(p) if p not in (None, "") else "?"
    except Exception:
        return "?"

def build_context(chunks: List[Dict]) -> str:
    """
    검색된 청크들을 컨텍스트 문자열로 빌드.
    - 각 줄에 [p.xx] 접두 + 본문
    - 너무 길어지면 MAX_CONTEXT_CHARS 내에서 자름
    """
    lines: List[str] = []
    total = 0
    for c in chunks:
        meta = c.get("meta", {}) or {}
        page = _safe_page(meta)
        text = (c.get("text") or "").strip()
        if not text:
            continue
        line = f"[p.{page}] {text}"
        # 길이 초과 방지
        if total + len(line) + 2 > MAX_CONTEXT_CHARS:
            # 남은 공간만큼 잘라 붙이기
            remain = max(0, MAX_CONTEXT_CHARS - total - 2)
            if remain > 0:
                lines.append(line[:remain])
                total += remain
            break
        lines.append(line)
        total += len(line) + 2
    return "\n\n".join(lines)

def answer(query: str, chunks: List[Dict]) -> Dict:
    """
    질문 + 컨텍스트로 LLM 호출 → 답변/소스 반환
    - 컨텍스트가 비었으면 즉시 안내 메시지 반환
    - source에는 id/page/title/dataset/uri/score 등 부가정보 포함
    """
    # 컨텍스트 비었으면 안전하게 반환
    if not chunks:
        return {
            "answer": "답변을 드릴 수 있는 CONTEXT가 없습니다. 정보를 찾을 수 없습니다.",
            "sources": []
        }

    ctx = build_context(chunks)
    if not ctx.strip():
        return {
            "answer": "답변을 드릴 수 있는 CONTEXT가 없습니다. 정보를 찾을 수 없습니다.",
            "sources": []
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"질문:\n{query}\n\n"
                "지침:\n"
                "1) 아래 CONTEXT에서만 답변.\n"
                "2) 필요한 경우 bullet로 요약.\n"
                "3) 각 근거 뒤에 [p.xx] 인용.\n\n"
                f"CONTEXT:\n{ctx}"
            ),
        },
    ]

    # llm_runtime.llm_client.chat 시그니처에 맞춰 최소 인자만 사용
    text = chat(messages, temperature=0.1, max_tokens=600)

    # 소스 정보는 방어적으로 .get 사용
    sources = []
    for c in chunks:
        m = c.get("meta", {}) or {}
        sources.append({
            "id": c.get("id"),
            "page": m.get("page"),
            "title": m.get("title"),
            "dataset": m.get("dataset"),
            "uri": m.get("uri"),
            "score": c.get("score"),
            "source_type": m.get("source_type"),
        })

    return {"answer": text, "sources": sources}
