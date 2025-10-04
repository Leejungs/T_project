# ================================================================
# config.py
# ------------------------------------------------
# 📚 역할:
#   - RAG 관련 설정(파일 경로, 청크 크기, 검색 수 등)을 관리
# ================================================================

# 📚 RAG 전역 설정
import os
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOC_PATH = os.path.join(BASE_DIR, "data", "docs", "school_rules.pdf")
CHROMA_DIR = os.path.join(BASE_DIR, "rag", "chroma_db")

# 👉 규정류 문서에 더 잘 맞는 청크 파라미터
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

# 👉 초반 검색은 넉넉히, 후처리로 줄임
TOP_K = 6
FINAL_K = 3
