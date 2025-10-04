# ================================================================
# store.py
# ------------------------------------------------
# 💾 역할:
#   - Chroma 벡터DB 초기화 및 Collection 관리
#   - 문서 삽입/검색용 기본 인터페이스 제공
# ================================================================

import chromadb
from chromadb.config import Settings

def get_client(persist_dir: str):
    """Chroma 클라이언트 생성"""
    return chromadb.Client(Settings(persist_directory=persist_dir, anonymized_telemetry=False))

def get_collection(client, name="school_rules"):
    """컬렉션 가져오기 (없으면 새로 생성)"""
    try:
        return client.get_collection(name=name)
    except:
        return client.create_collection(name=name, metadata={"hnsw:space": "cosine"})
