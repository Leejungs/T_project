### **[Phase 3 실행 계획 제안: 프로덕션급 API 서버 구축 (`app/main.py`)]**

**To: Project Lead**
**From: Gemini Pro (AI Senior Engineer)**
**Subject: Proposal for Phase 3 - Production-Grade API Server**

Phase 2에서 구현된 `RAGSystem`을 외부에서 안전하고 효율적으로 사용할 수 있도록, FastAPI를 사용한 프로덕션급 API 서버(`app/main.py`)의 구축 계획을 제안합니다. 이 계획은 안정적인 서비스 운영을 위한 로깅, 예외 처리, 명확한 API 명세에 중점을 둡니다.

#### **1. FastAPI 애플리케이션 구조**

`app/main.py` 파일은 FastAPI 애플리케이션의 진입점(entrypoint) 역할을 합니다. 애플리케이션이 시작될 때 필요한 설정을 구성하고, API 라우터를 정의합니다.

- **의존성 주입(Dependency Injection)**: Phase 2에서 `app/rag_core.py` 말미에 생성한 `rag_system` 싱글턴(Singleton) 인스턴스를 직접 `import`하여 사용합니다. 이 방식은 애플리케이션의 생명주기 동안 RAG 시스템의 무거운 모델들이 단 한 번만 로드되도록 보장하여, 메모리와 시작 시간을 효율적으로 관리합니다. 별도의 복잡한 DI 프레임워크 없이도 FastAPI의 권장 패턴을 따르는 효과적인 방법입니다.

#### **2. API 엔드포인트 정의**

API의 기능을 명확히 나타내는 두 개의 엔드포인트를 정의합니다.

1.  **`POST /api/v1/chat` (챗봇 응답 생성)**
    - **목적**: 사용자의 질문을 받아 RAG 시스템을 통해 답변과 근거를 생성합니다.
    - **요청 본문(Request Body)**: `app.rag_core`에 정의된 `QueryRequest` Pydantic 모델을 사용합니다. (`{"query": "..."}`)
    - **성공 응답(Success Response)**: `app.rag_core`에 정의된 `ChatResponse` Pydantic 모델을 반환합니다. (HTTP 200 OK)
    - **동작**: 요청이 들어오면, `rag_system.get_answer()` 메서드를 호출하고 그 결과를 클라이언트에게 반환합니다.

2.  **`GET /api/v1/health` (헬스 체크)**
    - **목적**: API 서버가 정상적으로 실행 중인지 외부 모니터링 시스템(로드 밸런서, 쿠버네티스 등)이 확인할 수 있는 경로를 제공합니다.
    - **요청 본문**: 없음
    - **성공 응답**: `{"status": "ok"}` 형태의 간단한 JSON을 반환합니다. (HTTP 200 OK)
    - **동작**: 서버가 떠 있기만 하면 항상 성공 응답을 반환합니다.

#### **3. 구조화된 로깅 (Structured Logging) 계획**

운영 환경에서 로그를 효과적으로 검색하고 분석하기 위해, 모든 로그를 **JSON 형식**으로 출력하도록 설정합니다. 이를 위해 Python의 내장 `logging` 모듈을 커스터마이징합니다.

1.  **`JsonFormatter` 클래스 정의**: `logging.Formatter`를 상속받아 로그 레코드를 JSON 객체로 변환하는 커스텀 포매터를 `app/main.py` 내에 구현합니다.
2.  **로거 설정 함수**: FastAPI의 `lifespan` 이벤트를 사용하여, 애플리케이션 시작 시 로거를 설정하는 함수를 구현합니다. 이 함수는 기본 로거의 핸들러를 제거하고, `JsonFormatter`를 사용하는 새로운 `StreamHandler`를 추가합니다.
3.  **로그 내용**: 모든 로그 메시지는 `timestamp`, `level`, `message` 필드를 기본으로 포함하며, 필요에 따라 추가적인 컨텍스트 정보(예: 요청 ID, 사용자 질문)를 담을 수 있습니다.

    *예시 로그 출력:*
    `{"timestamp": "2025-09-30T14:30:00.123Z", "level": "INFO", "message": "Chat request received", "query": "장학금 신청 방법"}`

#### **4. 전역 예외 처리 (Global Exception Handling)**

서버가 예상치 못한 오류로 인해 다운되는 것을 방지하고, 사용자에게 일관된 오류 메시지를 제공하기 위해 전역 예외 처리기를 도입합니다.

- **`@app.exception_handler(Exception)`**: FastAPI의 데코레이터를 사용하여 모든 `Exception`을 처리하는 핸들러 함수를 등록합니다.
- **동작**: 서버 코드 실행 중 예외가 발생하면, 이 핸들러가 가로채어 다음을 수행합니다.
    1.  예외의 상세 내용(traceback)을 JSON 형식으로 **로깅**합니다.
    2.  클라이언트에게는 상세 구현을 노출하지 않는 안전하고 표준화된 오류 메시지(예: `{"detail": "Internal Server Error"}`)와 함께 **HTTP 500 상태 코드**를 반환합니다.

#### **5. 논리적 실행 흐름**

1.  `uvicorn app.main:app` 명령어로 서버가 시작됩니다.
2.  FastAPI `lifespan` 이벤트가 트리거되어, 애플리케이션 시작과 함께 구조화된 로깅 설정이 적용됩니다.
3.  `app/main.py`는 `app/rag_core.py`의 `rag_system` 인스턴스를 임포트합니다. (이 시점에 RAG 모델들이 메모리에 로드됩니다.)
4.  사용자가 `POST /api/v1/chat`으로 요청을 보냅니다.
5.  엔드포인트 함수는 요청 본문을 `QueryRequest` 모델로 검증하고, `rag_system.get_answer()`를 호출합니다.
6.  `get_answer`의 반환값(`ChatResponse` 모델)은 FastAPI에 의해 자동으로 JSON으로 직렬화되어 클라이언트에게 응답됩니다.
7.  만약 처리 중 예외가 발생하면, 전역 예외 처리기가 이를 잡아 로깅하고 표준 오류 응답을 보냅니다.

이 계획은 안정적이고 관측 가능한(observable) API 서버를 구축하기 위한 핵심 요소들을 포함하고 있습니다.

---

위 계획에 대한 검토를 부탁드립니다. 계획이 승인되면, 이 설계에 따라 `app/main.py`의 전체 코드를 생성하겠습니다.
