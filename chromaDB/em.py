import os
from pymongo import MongoClient
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import chromadb

# -----------------------
# 환경변수
# -----------------------
MONGO_URI = os.getenv("MONGO_URI")  # MongoDB URI
client = MongoClient(MONGO_URI)

# -----------------------
# 임베딩 모델
# -----------------------
EMBEDDING_MODEL = "intfloat/e5-small-v2"
device = "cpu"  # M1이면 'mps' 가능
model = SentenceTransformer(EMBEDDING_MODEL, device=device)

def embed_text(texts):
    """SentenceTransformer로 벡터 생성"""
    return model.encode(texts, show_progress_bar=False, convert_to_numpy=True).tolist()

# -----------------------
# ChromaDB 최신 API 클라이언트
# -----------------------
chroma_client = chromadb.Client()

def sanitize_collection_name(name: str):
    """Chroma collection 이름 규칙 맞추기"""
    valid_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    sanitized = "".join([c if c in valid_chars else "_" for c in name])
    return sanitized[:63]

# -----------------------
# 실제 DB 처리
# -----------------------
def process_and_store(db_name, collection_name):
    db = client[db_name]
    coll = db[collection_name]
    docs = list(coll.find({}))

    if not docs:
        print(f"⚠️  No documents in {db_name}.{collection_name}")
        return 0

    # Chroma collection 생성 or 가져오기
    collection_id = sanitize_collection_name(f"{db_name}_{collection_name}")
    try:
        chroma_collection = chroma_client.get_collection(name=collection_id)
    except:
        chroma_collection = chroma_client.create_collection(name=collection_id)

    # 문서 텍스트와 메타데이터 준비
    texts = [" ".join([str(v) for k,v in doc.items() if k != "_id"]) for doc in docs]
    ids = [str(doc["_id"]) for doc in docs]
    metadatas = [{"db": db_name, "collection": collection_name, "_id": str(doc["_id"])} for doc in docs]

    # 임베딩 생성
    embeddings = embed_text(texts)

    # ChromaDB에 추가
    chroma_collection.add(documents=texts, embeddings=embeddings, metadatas=metadatas, ids=ids)
    return len(docs)

# -----------------------
# 메인 루프
# -----------------------
def main():
    # 실제 존재하는 DB만
    target_dbs = [
        "Academic_Information_db",
        "Admissions_Office",
        "University_Introduction",
        "depatement_all_db",
        "depatement_db",
        "university_life"
    ]
    total = 0
    for db_name in target_dbs:
        try:
            db = client[db_name]
            collections = db.list_collection_names()
        except Exception as e:
            print(f"⚠️  Cannot access DB {db_name}: {e}")
            continue

        if not collections:
            print(f"⚠️  No collections in {db_name}")
            continue

        for coll_name in collections:
            count = process_and_store(db_name, coll_name)
            print(f"✅ Stored {count} docs from {db_name}.{coll_name}")
            total += count

    print(f"\n🎉 Done! Total stored documents: {total}")

if __name__ == "__main__":
    main()
