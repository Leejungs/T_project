import os
from openai import OpenAI
import chromadb
from sentence_transformers import SentenceTransformer

# 1️⃣ OpenAI GPT-4o-mini 클라이언트
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 2️⃣ ChromaDB 클라이언트 (최신 방식으로 변경)
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# 3️⃣ 임베딩 모델 (sav.py와 동일하게 변경)
embed_model = SentenceTransformer("intfloat/multilingual-e5-small")

# 4️⃣ RAG 검색 함수 (오류 처리 및 로직 개선)
def retrieve_relevant_docs(question, top_k=5):
    try:
        question_embedding = embed_model.encode(question).tolist()
        collections = chroma_client.list_collections()
    except Exception as e:
        print(f"🚨 An error occurred during embedding or listing collections: {e}")
        return []

    best_docs = []
    for collection in collections:
        try:
            results = collection.query(
                query_embeddings=[question_embedding],
                n_results=top_k
            )
            # 결과에 문서가 있는 경우에만 추가
            if results and results['documents'] and results['documents'][0]:
                best_docs.append({
                    "collection": collection.name,
                    "docs": results['documents'][0],
                    "metadatas": results['metadatas'][0] if results['metadatas'] else [{}],
                })
        except Exception as e:
            print(f"🚨 An error occurred querying collection {collection.name}: {e}")
            continue
    
    # 최다 문서 기준 정렬
    best_docs.sort(key=lambda x: len(x['docs']), reverse=True)
    return best_docs

# 5️⃣ GPT-4o-mini로 답변 생성
def generate_answer(question, relevant_docs):
    context_texts = []
    for coll in relevant_docs[:3]:  # 상위 3개 컬렉션만 사용
        for doc in coll['docs']:
            context_texts.append(doc)
    context = "\n".join(context_texts)
    
    prompt = f"질문: {question}\n\n관련 자료:\n{context}\n\n위 자료를 참고하여 정확하고 간결하게 답변해줘."
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    
    return response.choices[0].message.content

# 6️⃣ 실행 예시
question = "대학 내 실험실 안전 규정 알려줘"
relevant_docs = retrieve_relevant_docs(question)
answer = generate_answer(question, relevant_docs)

print("===== 답변 =====")
print(answer)
