# llm_runtime

학교 전용 챗봇의 **LLM 호출 전용 모듈**입니다.  
FastAPI 서버(예: `stt-tts-sample/app.py`)나 RAG 엔진에서 공통으로 import 해서 사용합니다.

---

## 📂 디렉토리 구조
```bash
ai/llm_runtime/
├─ .env # OpenAI API 키/모델 설정 (git에 올리지 말 것)
├─ config.py # .env 로드 및 설정 객체 제공
├─ llm_client.py # GPT-4o-mini 채팅 함수 (프로덕션에서 import)
└─ test_llm.py # 단독 동작 테스트 스크립트
```

---

## 📄 파일별 역할

### `config.py`
- **역할:** 환경변수 로드 & 설정 객체 제공
- **특징:**
  - 현재 폴더의 `.env` 파일을 **명시 경로로 로드**하여, 작업 디렉토리와 무관하게 동작
  - 다른 모듈에서 `from .config import settings` 로 사용

---

### `llm_client.py`
- **역할:** OpenAI *Chat Completions* API 래퍼
- **제공 함수**
  ```bash
  chat(messages, model=None, temperature=0.7, max_tokens=256) -> str
  ```
  - messages: OpenAI 포맷 (예: {"role": "user", "content": "안녕"})
  - model 미지정 시 .env의 OPENAI_MODEL 사용
  - 반환값: 첫 번째 후보의 텍스트(str)

  ---

### `.env`
- **역할:** API 키 및 모델 설정 보관
- **예시**
  ```bash
  OPENAI_API_KEY=sk-********************************
  OPENAI_MODEL=gpt-4o-mini
  OPENAI_BASE_URL=https://api.openai.com/v1
  ```

  ---

### `test_llm.py`
- **역할:** 단독 실행 테스트 스크립트
- **사용:**: python test_llm.py 로 간단히 LLM 응답 확인