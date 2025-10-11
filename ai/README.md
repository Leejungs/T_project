# 🧩 운영 아키텍처 변경 요약 (A/B 분리)

### 🏫 학교 전용 챗봇의 RAG **경로를 인덱싱(업데이트)** 과 **서빙(질의)** 로 분리했습니다.  
사용자는 **빠른 응답**, 운영자는 **안전한 업데이트**를 얻습니다.

---

## 📊 아키텍처 한눈에 보기

```
┌──────────────┐     인덱싱(오프라인/배치)      ┌──────────────┐
│   데이터     │  ───────────────────────────▶  │  Chroma DB   │  ← 동일 경로(CHROMA_DIR)
│  (PDF·Mongo) │                                 └──────────────┘
└──────────────┘                                        ▲
         ▲                                              │ 읽기 전용
         │                                              │
         └─(A) Indexer API (관리 포트) ────────────────┘
                     │
                     └─ 주기 실행: /rag/ingest

사용자 요청 ─▶ (B) Serving API (사용자 포트) ─▶ /rag/chat → 즉시 응답
```

---

## 📁 파일별 역할

| 파일/폴더 | 역할 |
|------------|------|
| `ai/rag/config.py` | 환경 변수 로딩 및 설정 관리 |
| `ai/rag/ingest.py` | PDF + Mongo 인덱싱 로직 |
| `ai/rag/retriever.py` | Chroma 벡터 검색기 |
| `ai/rag/router.py` | `/rag/chat`, `/rag/ingest` 라우터 통합 |
| `static/index.html` | 임시 프론트엔드 UI (STT/TTS/RAG 테스트) |
| `.env` | 경로, 모델, Mongo, 캐시 등 공통 설정 |

---

## 🅱️ Serving API (사용자용)

### 🎯 역할
준비된 **벡터 인덱스(Chroma)** 를 읽어서 빠르게 Q&A 제공

### 🔗 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/rag/chat` | RAG 답변 |
| `POST` | `/rag/preview` | 검색된 청크 미리보기(디버깅) |
| `GET / POST` | `/warmup/status`, `/warmup/start` | 웜업 관리 (선택) |
| `/stt`, `/tts`, `/voice-chat` | STT/TTS 기능 그대로 유지 |

### ⚙️ 권장 실행
```bash
uvicorn app:app --port 9000 --reload
```

### 🧾 .env 핵심 설정
```bash
AUTO_INDEX_ON_QUERY=false   # 질문 시 자동 인덱싱 금지 (필수)
CHROMA_DIR=<공유 경로>
WARMUP_ON_STARTUP=true      # 서버 시작 시 웜업 수행 (권장)
HF_HOME, TRANSFORMERS_CACHE 고정 캐시 사용
```

---

## 🅰️ Indexer API (운영/개발자용)

### 🎯 역할
PDF 및 Mongo 데이터를 주기적으로 인덱싱하여 **CHROMA_DIR** 갱신

### 🔗 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/rag/ingest` | PDF + Mongo 통합 인덱싱 (증분 지원) |

### ⚙️ 권장 실행
```bash
uvicorn app:app --port 9100
```

### 🔒 보안
- 내부망 또는 방화벽으로 보호  
- 토큰/리버스 프록시 인증 적용  
- 외부 접근 차단 권장  

### ⏰ 스케줄링 예시
#### ▪ Windows (작업 스케줄러)
매일 새벽 03:00:
```powershell
curl.exe -X POST "http://127.0.0.1:9100/rag/ingest" `
  -H "Content-Type: application/json" `
  -d "{}"
```

#### ▪ Linux/macOS (cron)
```bash
0 3 * * * curl -X POST http://127.0.0.1:9100/rag/ingest   -H 'Content-Type: application/json' -d '{}'
```

---

## ⚙️ 환경 변수 정리 (.env 공통)

> 실제로는 `stt-tts-sample/.env` 하나에서 관리하며  
> `ai/rag/config.py` 등이 이를 읽습니다.

```bash
# === Paths & Cache ===
CHROMA_DIR=C:\path\to\chroma_db
HF_HOME=C:\hf_cache
TRANSFORMERS_CACHE=C:\hf_cache
HF_HUB_DISABLE_SYMLINKS_WARNING=1

# === RAG / Data ===
DATA_DIR=C:\Users\user\Documents\Github\T_project\ai\data\docs
PDF_GLOBS=*.pdf

# === Mongo ===
MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>/
MONGO_DB=depatement_db
MONGO_COLL=*                    # 전체 컬렉션 대상
MONGO_UPDATED_FIELD=updated_at  # 없으면 작성일/oid로 보강

# (옵션) Mongo 타임아웃
MONGO_CONNECT_TIMEOUT_MS=3000
MONGO_SERVER_SELECTION_TIMEOUT_MS=3000
MONGO_SOCKET_TIMEOUT_MS=30000

# === Serving 성능/제한 ===
AUTO_INDEX_ON_QUERY=false
WARMUP_ON_STARTUP=true
RAG_MAX_CHUNKS=4
RAG_MAX_CHARS_PER_CHUNK=900
RAG_MAX_CONTEXT_CHARS=9000
LLM_TIMEOUT_S=12

# === Embedder ===
EMBEDDER_MODEL=intfloat/multilingual-e5-small
EMBED_BATCH=64

# === Mongo 증분 인덱싱 ===
MONGO_INCREMENTAL=true
```

---

## 🚀 실행 가이드

### 1️⃣ Serving API (사용자용, 포트 9000)

```bash
uvicorn app:app --port 9000 --reload
```

- 브라우저 접속: [http://127.0.0.1:9000](http://127.0.0.1:9000)  
  → 임시 UI(`index.html`)로 테스트 가능  

#### 🧩 웜업 상태 확인
```bash
GET  http://127.0.0.1:9000/warmup/status
POST http://127.0.0.1:9000/warmup/start
```

---

### 2️⃣ Indexer API (운영용, 포트 9100)

```bash
uvicorn app:app --port 9100
```

#### 🧾 수동 인덱싱 (Windows PowerShell)
```powershell
(curl.exe -s -X POST "http://127.0.0.1:9100/rag/ingest" `
  -H "Content-Type: application/json" `
  -d "{}") | ConvertFrom-Json | ConvertTo-Json -Depth 8
```

#### 🧾 수동 인덱싱 (mac/Linux)
```bash
curl -X POST http://127.0.0.1:9100/rag/ingest   -H "Content-Type: application/json" -d '{}'
```

---

## 💻 프론트엔드 (임시 UI)

`static/index.html` 내 기능:

- STT / TTS / Voice Chat 테스트  
- RAG 질의: `/rag/chat` 호출 방식

#### 🔍 샘플 요청
```bash
curl -X POST "http://127.0.0.1:9000/rag/chat"   -H "Content-Type: application/json"   -d "{\"query\":\"결혼으로 인한 휴학 시 제출 서류는?\",\"top_k\":6}"
```

---

## ⚡ 운영 팁 (딜레이 최소화)

- Serving은 항상 **켜두거나**, 시작 직후 `/warmup/start` 호출  
- Indexer는 **백그라운드 주기 실행** → `CHROMA_DIR` 갱신  
- 두 프로세스 모두 **같은 CHROMA_DIR** 공유  

#### 🟦 블루-그린 인덱스 (무중단 반영)
```
CHROMA_DIR_A, CHROMA_DIR_B 두 세트를 번갈아 빌드
빌드 완료 후 Serving의 .env(또는 심볼릭 링크)만 스위칭
```

---

## 🧰 트러블슈팅

| 증상 | 원인/대처 |
|------|------------|
| 첫 질문만 느림 | 웜업 미완료 → `WARMUP_ON_STARTUP=true` 또는 `/warmup/start` 호출 |
| `/rag/ingest` 오래 걸림 | 정상(백그라운드). `MONGO_INCREMENTAL=true`, `EMBED_BATCH` 조정 |
| Mongo 메타데이터 타입 에러 | `updated_at` 필드 누락 → 값 존재 여부 확인 |
| 검색 결과 엉뚱/빈약 | `RAG_MAX_CHUNKS`, `top_k` 조정 (4~6), 청크 크기 튜닝 |

---

## 🔒 보안 권장사항

- **Indexer(A)** 는 관리자/내부망 전용  
- **Serving(B)** 은 외부 사용자용  
- `.env` 파일은 절대 커밋 금지  
  (특히 `OPENAI_API_KEY`, `MONGO_URI` 등 민감 정보)

---

## ✅ 체크리스트

- [ ] 두 프로세스 모두 같은 `CHROMA_DIR` 사용  
- [ ] Serving `.env`: `AUTO_INDEX_ON_QUERY=false`, `WARMUP_ON_STARTUP=true`  
- [ ] Indexer 스케줄링 설정 완료 (배치/크론)  
- [ ] `/rag/ingest` 성공 로그 확인 (청크 수 증가)  
- [ ] `/rag/preview` 로 검색 품질 점검  
- [ ] `/warmup/status` 와 서버 로그 확인  
