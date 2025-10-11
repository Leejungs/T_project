# stt-tts-sample

로컬 FastAPI 서버에서 **STT(음성→텍스트)**, **TTS(텍스트→음성)**, **Voice Chat(STT→LLM→TTS)**, **RAG(문서/DB 기반 QA)** 를 빠르게 테스트하기 위한 샘플 앱입니다.  
LLM 호출은 `ai/llm_runtime` 모듈(예: GPT-4o-mini)을 통해 이뤄지며, **LLM 키/모델 설정은 `ai/llm_runtime/.env`** 에서 관리합니다.

> 운영 권장: **A/B 분리** — A(업데이트 서버)는 인덱싱만 수행, B(서비스 서버)는 인덱스만 읽어 응답.

---

## 📁 디렉토리 구조

```
ai/stt-tts-sample/
├─ app.py                 # FastAPI 메인 서버 (STT/TTS/VoiceChat/RAG API + Warmup)
├─ guard.py               # 간단한 가드(욕설/PII 등) 필터
├─ requirements.txt       # 서버 의존성
├─ .env                   # RAG 및 서버 동작 관련 환경설정(로컬 실행용)
└─ static/
   └─ index.html          # 테스트용 프론트 페이지 (http://127.0.0.1:9000/)
```

> ⚠️ **LLM API 키**는 여기 `.env`가 아니라 **`ai/llm_runtime/.env`** 에 넣습니다.  
> STT/TTS는 키가 없어도 동작하고, LLM은 `llm_runtime`에서 키를 읽습니다.

---

## 🧩 파일별 역할

### `app.py`
- FastAPI 서버 본체.
- 엔드포인트
  - `GET /` : `static/index.html` 반환(테스트 UI)
  - `GET /health` : 헬스체크
  - `POST /stt` : 업로드 음성(STT)
  - `POST /tts` : 텍스트→오디오(MP3, base64)
  - `POST /voice-chat` : 음성→(STT)→(LLM)→(TTS)
  - `POST /rag/ingest` : PDF+Mongo 인덱싱 실행 (**A: 업데이트 서버**에서 주기적으로 호출)
  - `POST /rag/chat` : 질문→검색→답변(+출처) (**POST 전용**)
  - `POST /rag/preview` : 검색된 청크 미리보기 (**POST 전용**)
  - `GET /rag/debug/mongo` : Mongo 연결/샘플 진단
  - `GET /rag/debug/count` : 현재 Chroma 문서 수 확인
  - `GET /warmup/status` / `POST /warmup/start` : 서버 웜업 상태/수동 시작
- 내부적으로 `ai/rag/*`(인덱싱, 검색, QA)과 `ai/llm_runtime/*`(LLM 호출) 사용.

### `guard.py`
- 입력 텍스트에 대한 간단한 규칙 기반 필터(욕설/PII 등).
- `app.py`의 `chat_answer()`에서 호출되어 부적절한 요청 차단.

### `static/index.html`
- 클릭 몇 번으로 **STT**, **TTS**, **Voice Chat**, **RAG** 호출을 테스트할 수 있는 페이지.
- `uvicorn`으로 서버 실행 후 http://127.0.0.1:9000 접속.

### `requirements.txt`
- FastAPI/uvicorn, faster-whisper, edge-tts, python-dotenv 등 서버 실행에 필요한 라이브러리.


---

## ⚙️ `.env` 예시
RAG 및 서버 편의 설정을 넣습니다. 예시:

```env
# === RAG / Data / Mongo ===
DATA_DIR=C:\Users\user\Documents\Github\T_project\ai\data\docs
PDF_GLOBS=*.pdf

MONGO_URI=실제 URI 값
MONGO_DB=depatement_db
MONGO_COLL=*                    # '*'=모든 컬렉션, 또는 쉼표로 제한: 공지,규정
MONGO_UPDATED_FIELD=updated_at

# 웜업/자동인덱스
WARMUP_ON_STARTUP=true          # true면 서버 시작 시 비동기 웜업
AUTO_INDEX_ON_QUERY=false       # true면 첫 질의 때 변경 감지+인덱싱(운영에선 false 권장)

# Mongo 타임아웃 (ms)
MONGO_CONNECT_TIMEOUT_MS=3000
MONGO_SERVER_SELECTION_TIMEOUT_MS=3000
MONGO_SOCKET_TIMEOUT_MS=30000

# 임베딩/컨텍스트 튜닝
RAG_MAX_CHUNKS=4
RAG_MAX_CHARS_PER_CHUNK=900
RAG_MAX_CONTEXT_CHARS=9000
LLM_TIMEOUT_S=12

# HF 캐시(Windows 권장)
HF_HOME=C:\hf_cache
TRANSFORMERS_CACHE=C:\hf_cache
HF_HUB_DISABLE_SYMLINKS_WARNING=1
```

> ✅ LLM 키/모델은 **`ai/llm_runtime/.env`** 에 따로 보관하세요.
> ```env
> OPENAI_API_KEY=sk-...
> OPENAI_MODEL=gpt-4o-mini
> OPENAI_BASE_URL=https://api.openai.com/v1
> ```

---

## 🚀 빠른 시작 (Windows / PowerShell)

1) 가상환경 & 설치
```powershell
cd ai\stt-tts-sample
python -m venv .venv
. .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

2) 환경변수(키/모델)
- `ai/llm_runtime/.env` : OpenAI 키/모델
- `ai/stt-tts-sample/.env` : RAG 및 서버 설정

3) 서버 실행
```powershell
uvicorn app:app --reload --port 9000
```
→ 브라우저에서 `http://127.0.0.1:9000` 접속 후 UI로 바로 테스트.

---

## 🛠️ API 사용 예시

### 1) STT (multipart/form-data)
```powershell
curl.exe -X POST "http://127.0.0.1:9000/stt" -F "file=@sample.wav"
```

### 2) TTS (JSON → MP3 base64)
```powershell
curl.exe -X POST "http://127.0.0.1:9000/tts" `
  -H "Content-Type: application/json" `
  -d '{"text":"안녕하세요. 샘플 TTS 입니다."}'
```

### 3) Voice Chat (음성 → STT → LLM → TTS)
```powershell
curl.exe -X POST "http://127.0.0.1:9000/voice-chat" -F "file=@sample.wav"
```

### 4) RAG 인덱싱 (PDF+Mongo)
```powershell
# 기본(환경설정에 따른 전체 인덱싱)
curl.exe -X POST "http://127.0.0.1:9000/rag/ingest"

# 상세 지정
curl.exe -X POST "http://127.0.0.1:9000/rag/ingest" `
  -H "Content-Type: application/json" `
  -d "{\"pdf_paths\":[\"C:\\\\path\\\\to\\\\file1.pdf\"],\"mongo_query\":{}}"
```

### 5) RAG 미리보기 (POST 전용, filters 지원)
```powershell
# PowerShell 여러 줄 버전
curl.exe -s -X POST http://127.0.0.1:9000/rag/preview `
  -H "Content-Type: application/json" `
  -d '{ "query": "휴학은 최대 몇 학기?", "top_k": 6, "filters": { "dataset": ["규정집"] } }'

# PowerShell 한 줄 버전 (이스케이프 포함)
curl.exe -s -X POST "http://127.0.0.1:9000/rag/preview" -H "Content-Type: application/json" -d "{`"query`":`"휴학은 최대 몇 학기?`",`"top_k`":6,`"filters`":{`"dataset`":[`"규정집`"]}}"
```

### 6) RAG 질문 (POST 전용, filters 지원)
```powershell
curl.exe -X POST "http://127.0.0.1:9000/rag/chat" `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"결혼 시 필요한 증빙서류는?\",\"top_k\":6,\"filters\":{\"dataset\":[\"경영학과\",\"규정집\"]}}"
```

### 7) 인덱스 상태/디버그
```powershell
curl.exe -s "http://127.0.0.1:9000/rag/debug/mongo"
curl.exe -s "http://127.0.0.1:9000/rag/debug/count"
```

### 8) 웜업
```powershell
# 상태
curl.exe "http://127.0.0.1:9000/warmup/status"

# 수동 시작(백그라운드)
curl.exe -X POST "http://127.0.0.1:9000/warmup/start"
```

---

## ⚙️ 동작 개요

- **LLM**: `llm_runtime.llm_client.chat()` 호출로 GPT-4o-mini 사용.  
- **RAG**: PDF/표 + Mongo 문서를 청크로 나눠 Chroma에 임베딩 저장 → 검색 → LLM에 컨텍스트로 전달 → 답변/출처 반환.
- **Warmup**: 서버 시작 시(옵션) 또는 수동으로 임베더/인덱스/LLM을 미리 준비 → 첫 질문 지연 최소화.
- **A/B 분리**: `AUTO_INDEX_ON_QUERY=false`일 때, B(서비스)는 절대 인덱싱을 수행하지 않고 **기존 스냅샷만 사용**.

---

## 🧯 트러블슈팅

- **Windows에서 FFmpeg 필요**  
  - 권장: `winget install Gyan.FFmpeg`

- **Whisper 모델 다운로드 느림/캐시 경고**  
  - `.env`에 HF 캐시 경로(HF_HOME, TRANSFORMERS_CACHE) 지정 권장.

- **Mongo 연결 실패**  
  - `.env`의 `MONGO_URI/MONGO_DB/MONGO_COLL` 확인.
  - 방화벽/네트워크, Compass로 접속 가능 여부 점검.
  - 타임아웃 조정: `MONGO_*_TIMEOUT_MS`

- **RAG 첫 질문 지연**  
  - `WARMUP_ON_STARTUP=true`로 서버 시작 시 미리 준비.
  - 운영 단계에서는 RAG 인덱싱/업데이트 작업을 **A 서버**에서 돌리고, **B 서버**는 Chroma만 사용.

- **LLM 키 미설정**  
  - `ai/llm_runtime/.env`에 OpenAI 키/모델 필수.

- **증분 인덱싱 워터마크 초기화**  
  - 풀 재인덱싱이 필요하면 `MONGO_INCREMENTAL=false`로 실행하거나  
    `ai/rag/chroma_db/mongo_watermarks.json`을 삭제 후 `/rag/ingest` 호출.
