# ================================================================
# auto_index.py
# ------------------------------------------------
# 🧩 역할:
#   - 질문이 들어올 때, 벡터 인덱스(Chroma)가 준비돼 있는지 확인
#   - 비어 있거나 PDF가 변경되었으면 즉시 인덱싱 수행
#   - 중복 인덱싱 방지를 위해 프로세스 내 락 사용
# ================================================================

from __future__ import annotations
import os, json, threading
from typing import Optional, Tuple
from .config import DOC_PATH, CHROMA_DIR
from .ingest import ingest_pdf
from .store import get_client, get_collection

_MANIFEST_PATH = os.path.join(CHROMA_DIR, "manifest.json")
_LOCK = threading.Lock()

def _fingerprint(path: str) -> dict:
    """PDF 파일의 식별 정보(경로, 크기, mtime)를 해시 대신 경량 메타로 사용."""
    p = os.path.abspath(path)
    st = os.stat(p)
    return {"path": p, "size": st.st_size, "mtime": int(st.st_mtime)}

def _read_manifest() -> Optional[dict]:
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write_manifest(fp: dict, count: Optional[int]) -> None:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    data = {"fingerprint": fp, "doc_count": count}
    with open(_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _is_populated() -> Tuple[bool, Optional[int]]:
    """Chroma에 문서가 들어있는지 확인."""
    try:
        client = get_client(CHROMA_DIR)
        col = get_collection(client)
        try:
            n = col.count()  # Chroma 0.5+
            return (n and n > 0), n
        except Exception:
            # 일부 버전 호환: count 미지원 시, 에러 없이 get_collection만 돼도 true로 본다.
            return True, None
    except Exception:
        return False, 0

def ensure_index_ready(path: Optional[str] = None, force: bool = False) -> dict:
    """
    - 현재 인덱스가 최신이면 아무 것도 안 함
    - 비었거나 PDF가 바뀌었으면 ingest_pdf() 실행
    - force=True 이면 무조건 재인덱싱
    """
    use_path = os.path.abspath(path or DOC_PATH)
    if not os.path.exists(use_path):
        raise FileNotFoundError(use_path)

    with _LOCK:
        fp = _fingerprint(use_path)
        m = _read_manifest()
        populated, n = _is_populated()
        fresh = (m is not None) and (m.get("fingerprint") == fp) and populated

        if force or not fresh:
            res = ingest_pdf(use_path)
            populated, n = _is_populated()
            _write_manifest(fp, n or res.get("documents"))
            return {
                "indexed": True,
                "reason": "forced" if force else "stale_or_missing",
                "documents": res.get("documents"),
                "pages": res.get("pages"),
                "used_path": use_path,
            }
        else:
            return {
                "indexed": False,
                "reason": "up_to_date",
                "documents": n,
                "used_path": use_path,
            }
