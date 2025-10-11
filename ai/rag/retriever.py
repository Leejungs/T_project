# ai/rag/retriever.py
# ================================================================
# 🔎 역할: 질문 임베딩 → Chroma에서 top-k 검색
#   - Chroma v0.5+ 에서는 include에 "ids"를 넣으면 에러가 납니다.
#   - 그래서 include=["documents","metadatas","distances"]만 요청하고,
#     반환값에 ids가 있으면 사용, 없으면 메타데이터로 대체 ID 생성합니다.
# ================================================================

# 🔎 쿼리 임베딩 → 검색(+간단 쿼리 확장)
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from .config import CHROMA_DIR, TOP_K, FINAL_K, COLLECTION_NAME
from .store import get_client, get_collection

_model = None
def embedder():
    global _model
    if _model is None:
        _model = SentenceTransformer("intfloat/multilingual-e5-base")
    return _model

SYNONYMS = {
    "병결": ["본인의 질병", "질병으로 결석", "의료기관 진단서", "진료확인서", "출석 인정", "결석 사유"],
    "서류": ["증빙서류", "증빙 자료", "제출 서류", "필요 서류"],
    "결혼": ["본인의 결혼", "청첩장", "출석 인정 7일"],
    "사망": ["부모·배우자 사망", "사망 진단서", "가족관계증명서"],
}

def expand_query(q: str) -> str:
    expanded = [q]
    for k, syns in SYNONYMS.items():
        if k in q:
            expanded.extend(syns)
    return " ; ".join(expanded)

def retrieve(query: str, k: int = TOP_K,
             filters: Optional[Dict] = None) -> List[Dict]:
    """
    filters 예시:
      {"source_type": ["pdf"], "dataset": ["규정집","공지"]}
    """
    model = embedder()
    q = expand_query(query)
    qvec = model.encode([f"query: {q}"], convert_to_numpy=True, normalize_embeddings=True)[0]

    client = get_client(CHROMA_DIR)
    col = get_collection(client, name=COLLECTION_NAME)

    include = ["documents", "metadatas", "distances"]
    where = None
    if filters:
        # Chroma where 필터: {"$and":[{"source_type":{"$in":["pdf"]}},{"dataset":{"$in":["규정집"]}}]}
        clauses = []
        for key, vals in filters.items():
            clauses.append({key: {"$in": vals}})
        where = {"$and": clauses} if clauses else None

    res = col.query(query_embeddings=[qvec.tolist()], n_results=k, include=include, where=where)

    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    ids_list = (res.get("ids", [[]])[0]
                if "ids" in res and len(res["ids"]) > 0
                else [f"{m.get('source_type','?')}::{i}" for i, m in enumerate(metas)])

    items = []
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        sim = 1.0 - float(dists[i]) if i < len(dists) else 0.0
        items.append({"id": ids_list[i], "text": doc, "meta": meta, "score": sim})

    return sorted(items, key=lambda x: x["score"], reverse=True)[:FINAL_K]
