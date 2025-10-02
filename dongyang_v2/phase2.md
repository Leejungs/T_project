### **[Phase 2 실행 계획 제안: RAG 핵심 로직 추상화 (`app/rag_core.py`)]**

**To: Project Lead**
**From: Gemini Pro (AI Senior Engineer)**
**Subject: Proposal for Phase 2 - RAG Core Logic Abstraction**

Phase 1에서 구축한 데이터 파이프라인을 기반으로, 검색(Retrieval)과 생성(Generation)을 담당하는 핵심 RAG 시스템을 `app/rag_core.py`에 추상화된 클래스로 설계하는 계획을 제안합니다. 이 설계는 **모듈성**, **구성 용이성**, **명확한 데이터 계약** 원칙을 중심으로 합니다.

#### **1. 입출력 데이터 구조 정의 (Pydantic Models)**

시스템의 모든 입출력은 Pydantic 모델을 사용하여 데이터의 형태와 유효성을 강제합니다. 이는 API의 안정성을 높이고 예측 가능한 동작을 보장합니다.

```python
# In app/rag_core.py

from pydantic import BaseModel, Field
from typing import List

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
```

#### **2. `RAGSystem` 클래스 아키텍처**

RAG의 핵심 로직을 `RAGSystem` 클래스로 캡슐화하여, 검색기와 생성기를 포함한 모든 관련 컴포넌트를 관리합니다.

```python
# In app/rag_core.py

class RAGSystem:
    def __init__(self):
        # 1. 설정 로드
        # 2. 임베딩 모델 초기화
        # 3. 리트리버 (검색기) 초기화
        # 4. LLM (생성기) 초기화
        # 5. RAG 체인 구성
        pass

    def _initialize_embeddings(self):
        # settings.EMBEDDING_MODEL_NAME을 사용하여 HuggingFaceEmbeddings 로드
        pass

    def _initialize_retriever(self):
        # ChromaDB 클라이언트를 로드하고, 컬렉션을 가져와 as_retriever()로 검색기 생성
        pass

    def _initialize_llm(self):
        # settings.LLM_PROVIDER에 따라 OpenAI 또는 Google LLM을 동적으로 로드
        pass

    def get_answer(self, request: QueryRequest) -> ChatResponse:
        # RAG 체인을 실행하고, 결과를 ChatResponse 모델로 변환하여 반환
        pass
```

- **`__init__`**: 시스템 시작 시 단 한 번 호출되어, 필요한 모든 컴포넌트(임베딩, 리트리버, LLM)를 초기화하고 메모리에 로드합니다.
- **`_initialize_*` 메서드**: 각 컴포넌트의 초기화 로직을 명확하게 분리하여 모듈성을 확보합니다. 특히 `_initialize_llm`은 `app.config`의 `LLM_PROVIDER` 값을 확인하여 `ChatOpenAI` 또는 `ChatGoogleGenerativeAI` 인스턴스를 조건부로 생성하는 로직을 포함합니다.
- **`get_answer`**: 외부에 노출되는 유일한 public 메서드입니다. Pydantic 모델 `QueryRequest`를 입력받아 `ChatResponse`를 반환함으로써 명확한 인터페이스를 제공합니다.

#### **3. LangChain Expression Language (LCEL) 체인 설계**

검색과 생성 과정을 파이프라인으로 연결하기 위해 최신 LangChain 표준인 LCEL을 사용합니다. 이는 코드의 가독성과 디버깅 용이성을 크게 향상시킵니다.

**LCEL 체인 구조:**

1.  **`retriever`**: 사용자의 질문을 받아 관련 문서를 검색합니다.
2.  **`format_docs` 함수**: 검색된 문서 리스트(`List[Document]`)를 프롬프트에 삽입하기 용이한 단일 문자열로 포맷합니다.
3.  **`RunnablePassthrough`**: 질문 텍스트를 체인의 후반부로 그대로 전달하는 역할을 합니다.
4.  **`PromptTemplate`**: 아래와 같이 컨텍스트와 질문을 받아 LLM에게 역할을 지시하는 프롬프트를 구성합니다.

    ```
    당신은 주어진 컨텍스트 정보를 바탕으로 질문에 답변하는 AI 어시스턴트입니다.
    컨텍스트를 벗어나는 답변이나 추측성 답변은 하지 마세요. 항상 컨텍스트에 근거하여 명확하고 간결하게 답변하세요.
    만약 컨텍스트에서 답변을 찾을 수 없다면, "제공된 정보만으로는 답변을 찾을 수 없습니다."라고 솔직하게 답변하세요.

    컨텍스트:
    {context}

    질문: {question}

    답변:
    ```

5.  **`llm`**: 프롬프트가 주입된 LLM 모델입니다.
6.  **`StrOutputParser`**: LLM의 출력(AIMessage)에서 답변 텍스트만 추출합니다.

**전체 체인 의사코드:**

```python
chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt_template
    | llm
    | StrOutputParser()
)
```

#### **4. 논리적 실행 흐름**

1.  FastAPI 서버(`app/main.py`)가 시작될 때, `RAGSystem` 클래스의 인스턴스를 단 하나 생성하여 전역적으로 사용합니다 (Singleton 패턴).
2.  사용자가 API 엔드포인트(`POST /api/v1/chat`)로 요청을 보내면, 요청 바디는 `QueryRequest` 모델로 파싱 및 검증됩니다.
3.  `RAGSystem` 인스턴스의 `get_answer` 메서드가 호출됩니다.
4.  `get_answer` 내부에서는 먼저 `retriever`를 호출하여 관련 문서를 검색합니다.
5.  그 후, 위에서 설계된 LCEL 체인을 `invoke`하여 LLM으로부터 답변을 생성합니다.
6.  검색된 문서와 생성된 답변을 `ChatResponse` Pydantic 모델에 담아 반환합니다.
7.  FastAPI는 이 `ChatResponse` 객체를 JSON 형식으로 직렬화하여 사용자에게 최종 응답합니다.

이 계획은 **Phase 3 (API 서버 구축)**와의 자연스러운 연결을 고려하였으며, 각 컴포넌트가 명확히 분리되어 있어 향후 유지보수 및 성능 개선에 용이한 구조입니다.

---

위 계획에 대한 검토를 부탁드립니다. 계획이 승인되면, 이 설계에 따라 `app/rag_core.py`의 전체 코드를 생성하겠습니다.
