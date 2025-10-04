# ai/rag/ingest.py
# ================================================================
# 📥 PDF → 텍스트/테이블 → 청크 → 임베딩 저장
#   - PyMuPDF: 일반 텍스트 추출 품질 향상
#   - pdfplumber: 표를 행 단위로 구조화해 "결석사유: X | 출석인정일수: Y | 증빙서류: Z"
# ================================================================

import os, re
from typing import List
try:
    import fitz  # PyMuPDF
    USE_FITZ = True
except ImportError:
    from pypdf import PdfReader
    USE_FITZ = False

import pdfplumber
from sentence_transformers import SentenceTransformer
from .config import DOC_PATH, CHROMA_DIR, CHUNK_SIZE, CHUNK_OVERLAP
from .store import get_client, get_collection

def clean(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_text_pages(path: str) -> List[str]:
    pages = []
    if USE_FITZ:
        with fitz.open(path) as doc:
            for p in doc:
                pages.append(clean(p.get_text("text")))
    else:
        reader = PdfReader(path)
        for p in reader.pages:
            pages.append(clean(p.extract_text() or ""))
    return pages

def extract_tables_as_lines(path: str) -> List[str]:
    """각 페이지의 표를 '결석사유: X | 출석인정일수: Y | 증빙서류: Z' 라인으로 변환."""
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rows = []
            tables = page.extract_tables() or []
            for tbl in tables:
                header = None
                if tbl and any(tbl[0]):              # 1행을 헤더로 가정
                    header = [(c or "").strip() for c in tbl[0]]
                for i, row in enumerate(tbl):
                    if i == 0:                       # 헤더 스킵
                        continue
                    cells = [(c or "").strip() for c in row]
                    if not any(cells):
                        continue
                    if header and len(header) == len(cells):
                        kv = [f"{header[j]}: {cells[j]}" for j in range(len(cells))]
                        rows.append(" | ".join(kv))
                    else:
                        rows.append(" | ".join(cells))
            out.append("\n".join(rows))
    return out

def split_paragraphs(text: str) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras if paras else [text]

def to_chunks(paras: List[str], size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> List[str]:
    buf, chunks = "", []
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = (buf + "\n" + p).strip()
        else:
            if buf: chunks.append(buf)
            buf = p
    if buf: chunks.append(buf)
    if overlap > 0 and len(chunks) > 1:
        with_overlap = []
        for i, c in enumerate(chunks):
            prefix = chunks[i-1][-overlap:] if i > 0 else ""
            with_overlap.append((prefix + "\n" + c).strip() if prefix else c)
        chunks = with_overlap
    return chunks

def ingest_pdf(path: str = DOC_PATH):
    text_pages  = extract_text_pages(path)
    table_pages = extract_tables_as_lines(path)

    # 🔧 zip 사용 금지! 길이가 다르면 뒤 페이지가 날아감
    n = max(len(text_pages), len(table_pages))

    docs, metas, ids = [], [], []
    for idx_page in range(n):
        t_text  = text_pages[idx_page]  if idx_page < len(text_pages)  else ""
        t_table = table_pages[idx_page] if idx_page < len(table_pages) else ""
        merged_text = "\n\n".join([t_text, t_table]).strip()
        if not merged_text:
            continue
        for idx, chunk in enumerate(to_chunks(split_paragraphs(merged_text))):
            docs.append(chunk)
            metas.append({"source": os.path.basename(path), "page": idx_page + 1})
            ids.append(f"{idx_page+1}-{idx}")

    # ✅ 한국어 멀티링구얼 임베딩(E5) + 포맷 권장
    model = SentenceTransformer("intfloat/multilingual-e5-base")
    embeds = model.encode([f"passage: {d}" for d in docs],
                          convert_to_numpy=True, normalize_embeddings=True)

    client = get_client(CHROMA_DIR)
    col = get_collection(client)
    try: col.delete(ids=ids)
    except: pass
    col.add(documents=docs, embeddings=embeds.tolist(), metadatas=metas, ids=ids)

    # 디버그: 키워드가 몇 건 들어갔는지 반환
    kw = ("결석사유", "증빙서류", "출석인정일수", "질병", "결혼")
    hit = sum(any(k in d for k in kw) for d in docs)
    return {"documents": len(docs), "pages": n, "keyword_hits": hit}
