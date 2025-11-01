# save.py
import os
from pymongo import MongoClient
import chromadb
from chromadb.config import Settings
from langchain_huggingface import HuggingFaceEmbeddings
from chromadb import Documents, EmbeddingFunction, Embeddings

# -------------------------------
# ChromaDB Embedding Function Wrapper
# -------------------------------
class ChromaHuggingFaceEmbeddingFunction(EmbeddingFunction):
    def __init__(self, embeddings: HuggingFaceEmbeddings):
        self._embeddings = embeddings

    def __call__(self, input: Documents) -> Embeddings:
        # ChromaDB expects a list of strings for input
        # HuggingFaceEmbeddings.embed_documents expects a list of strings
        return self._embeddings.embed_documents(list(input))

# -------------------------------
# MongoDB 연결 설정
# -------------------------------
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://wjdtndpdy0920:dlwjd09tn20@cluster0.zsdkexf.mongodb.net/"
)
mongo_client = MongoClient(MONGO_URI)

# -------------------------------
# ChromaDB 최신 구조 클라이언트
# -------------------------------
# NEW
chroma_client = chromadb.PersistentClient(path="/app/chroma_db")

# -------------------------------
# Embedding Function
# -------------------------------
# Use the same embedding function as in the RAG application
hf_embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-small")
chroma_embedding_function = ChromaHuggingFaceEmbeddingFunction(hf_embeddings)

# -------------------------------
# MongoDB 데이터 가져와서 Chroma에 저장
# -------------------------------
def process_and_store(db_name, collection_name):
    db = mongo_client[db_name]
    collection = db[collection_name]

    # 문서가 없으면 건너뛰기
    docs = list(collection.find())
    if not docs:
        print(f"⚠️ No documents in {db_name}.{collection_name}")
        return 0

    # Chroma Collection 생성
    chroma_collection_name = f"{db_name}_{collection_name}"
    chroma_coll = chroma_client.get_or_create_collection(
        name=chroma_collection_name,
        embedding_function=chroma_embedding_function
    )

    # _id, content 추출
    ids = [str(doc.get("_id", idx)) for idx, doc in enumerate(docs)]
    contents = [str(doc) for doc in docs]

    chroma_coll.add(
        ids=ids,
        documents=contents
    )
    print(f"✅ Stored {len(docs)} docs from {db_name}.{collection_name}")
    return len(docs)

# -------------------------------
# 모든 DB & Collection 처리
# -------------------------------
def main():
    db_names = ["Academic_Information_db", "Admissions_Office", "University_Introduction",
                "depatement_all_db", "depatement_db", "university_life"]

    total_docs = 0
    for db_name in db_names:
        db = mongo_client[db_name]
        collection_names = db.list_collection_names()
        if not collection_names:
            print(f"⚠️ No collections in {db_name}")
            continue
        for coll_name in collection_names:
            total_docs += process_and_store(db_name, coll_name)

    print(f"\n🎉 Done! Total stored documents: {total_docs}")

if __name__ == "__main__":
    main()
