import os
from typing import List

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain_community.callbacks import get_openai_callback
from langchain.schema.document import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableLambda

from app.config import settings

# --- 1. 입출력 데이터 구조 정의 (Pydantic Models) ---

class QueryRequest(BaseModel):
    """API 요청 시 사용될 사용자 질문 모델"""
    query: str = Field(description="사용자의 질문 텍스트")

class Source(BaseModel):
    """답변의 근거가 되는 출처 문서 정보 모델"""
    source_document: str = Field(description="출처 문서명 (파일 경로, URL 등)")
    page_number: int = Field(description="출처 문서의 페이지 번호")
    content: str = Field(description="답변 생성에 사용된 실제 텍스트 내용")

class ChatResponse(BaseModel):
    """API가 반환할 최종 응답 모델"""
    answer: str = Field(description="생성된 답변 텍스트")
    sources: List[Source] = Field(description="답변의 근거가 되는 출처 문서 리스트")

# --- 2. RAGSystem 클래스 아키텍처 ---

class RAGSystem:
    def __init__(self):
        """RAGSystem 초기화 시 모든 핵심 컴포넌트를 로드하고 RAG 체인을 구성합니다."""
        print("RAG 시스템 초기화를 시작합니다...")
        self.embeddings = self._initialize_embeddings()
        self.retriever = self._initialize_retriever()
        self.llm = self._initialize_llm()
        self.chain = self._create_rag_chain()
        print("RAG 시스템 초기화가 완료되었습니다.")

    def _initialize_embeddings(self) -> HuggingFaceEmbeddings:
        """설정에 지정된 임베딩 모델을 로드합니다."""
        model_name = settings.EMBEDDING_MODEL_NAME
        print(f"임베딩 모델 '{model_name}'을 로드합니다.")
        return HuggingFaceEmbeddings(model_name=model_name)

    def _initialize_retriever(self):
        """ChromaDB에서 벡터 저장소를 로드하고 검색기를 생성합니다."""
        print(f"ChromaDB 데이터베이스를 '{settings.VECTOR_DB_PATH}'에서 로드합니다.")
        if not os.path.exists(settings.VECTOR_DB_PATH):
            raise FileNotFoundError(
                f"ChromaDB 경로를 찾을 수 없습니다: {settings.VECTOR_DB_PATH}. "
                f"먼저 'python scripts/ingest.py'를 실행하여 데이터베이스를 생성해주세요."
            )
        
        vector_store = Chroma(
            persist_directory=settings.VECTOR_DB_PATH,
            embedding_function=self.embeddings,
            collection_name="school_info_collection"
        )
        return vector_store.as_retriever(
            search_type="mmr", 
            search_kwargs={'k': 10}
        )

    def _initialize_llm(self):
        """설정에 따라 적절한 LLM을 동적으로 로드합니다."""
        provider = settings.llm.provider
        model_name = settings.llm.model_name
        api_key = settings.llm.api_key

        print(f"LLM 공급자: '{provider}', 모델: '{model_name}'을 로드합니다.")

        if provider == "openai":
            return ChatOpenAI(model=model_name, api_key=api_key, temperature=0)
        
        elif provider == "google":
            return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0, convert_system_message_to_human=True)
        
        else:
            # This part should not be reachable due to Pydantic validation
            raise ValueError(f"지원하지 않는 LLM 공급자입니다: {provider}")

    def _create_query_expansion_chain(self):
        """LCEL을 사용하여 쿼리 확장 체인을 구성합니다."""
        template = """
        You are an AI assistant that helps users to find information. 
        Your task is to generate 3 additional queries that are similar to the original query. 
        The queries should be in Korean.

        Original query: {question}

        Additional queries (one per line):
        """
        prompt = PromptTemplate.from_template(template)
        return (
            prompt
            | self.llm
            | StrOutputParser()
            | RunnableLambda(lambda x: x.split('\n'))  # ✅ 수정된 부분
        )


    def _create_rag_chain(self):
        """LCEL을 사용하여 RAG 체인을 구성합니다. 이 체인은 컨텍스트와 질문을 입력으로 받습니다."""
        template = """
        당신은 주어진 컨텍스트 정보를 바탕으로 질문에 답변하는 AI 어시스턴트입니다.
        컨텍스트를 벗어나는 답변이나 추측성 답변은 하지 마세요. 항상 컨텍스트에 근거하여 명확하고 간결하게 답변하세요.
        만약 컨텍스트에서 답변을 찾을 수 없다면, "제공된 정보만으로는 답변을 찾을 수 없습니다."라고 솔직하게 답변하세요.

        컨텍스트:
        {context}

        질문: {question}

        답변:
        """
        prompt = PromptTemplate.from_template(template)

        return (
            prompt
            | self.llm
            | StrOutputParser()
        )

    async def get_answer(self, request: QueryRequest) -> ChatResponse:
        """사용자 질문에 대한 답변과 출처를 반환합니다."""
        print("[RAG] 1. 쿼리 확장 시작...")
        # 1. 쿼리 확장
        query_expansion_chain = self._create_query_expansion_chain()
        with get_openai_callback() as cb_expansion:
            expanded_queries = await query_expansion_chain.ainvoke({"question": request.query})
            print(f"[OpenAI] 쿼리 확장 비용: ${cb_expansion.total_cost:.6f}, 총 토큰: {cb_expansion.total_tokens}")

        all_queries = [request.query] + expanded_queries
        print(f"[RAG] 확장된 쿼리: {all_queries}")

        # 2. 출처 검색
        print("[RAG] 2. 출처 검색 시작...")
        retrieved_docs_lists = await self.retriever.abatch(all_queries)
        
        unique_docs = {}
        for docs_list in retrieved_docs_lists:
            for doc in docs_list:
                unique_docs[doc.page_content] = doc
        retrieved_docs = list(unique_docs.values())
        print(f"[RAG] 검색된 출처 문서 개수: {len(retrieved_docs)}")
        
        source_documents = [
            Source(
                source_document=doc.metadata.get("source", "알 수 없음"),
                page_number=doc.metadata.get("page_number", -1),
                content=doc.page_content
            ) for doc in retrieved_docs
        ]

        # 4. 답변 생성
        print("[RAG] 3. 답변 생성 시작...")
        context = "\n\n".join(f"[문서 출처: {doc.metadata.get('source', '알 수 없음')}, 페이지: {doc.metadata.get('page_number', '알 수 없음')}]\n{doc.page_content}" for doc in retrieved_docs)
        
        with get_openai_callback() as cb_answer:
            answer = await self.chain.ainvoke({"context": context, "question": request.query})
            print(f"[OpenAI] 답변 생성 비용: ${cb_answer.total_cost:.6f}, 총 토큰: {cb_answer.total_tokens}")

        return ChatResponse(answer=answer, sources=source_documents)

# --- Singleton 인스턴스 생성 ---
# FastAPI 애플리케이션이 시작될 때 한 번만 생성되어 재사용됩니다.
try:
    rag_system = RAGSystem()
except Exception as e:
    print(f"RAG 시스템 초기화 중 오류 발생: {e}")
    rag_system = None
