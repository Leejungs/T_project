# 🏫 학교 정보 RAG 챗봇 시스템 v1.1

이 프로젝트는 검색 증강 생성(RAG) 기술과 사용자 인증을 통합하여, 동양미래대학교의 다양한 비정형 데이터(PDF 학칙, 공지사항 등)로부터 사용자의 질문에 대해 신뢰도 높은 답변을 제공하는 완성형 웹 애플리케이션입니다.

기존의 분리된 백엔드(FastAPI, Flask) 구조를 단일 FastAPI 애플리케이션으로 통합하여 아키텍처를 단순화하고, JWT 기반의 현대적인 인증 방식을 도입하여 보안을 강화했습니다.

## ✨ 주요 기능

- **통합 백엔드:** FastAPI를 사용하여 RAG 챗봇 API와 사용자 인증(회원가입, 로그인) API를 모두 제공합니다.
- **보안 인증:** JWT(JSON Web Token)를 사용한 상태 비저장 인증으로 챗봇 API를 보호합니다.
- **LLM 유연성:** OpenAI, Google 등 다양한 LLM을 설정 파일을 통해 쉽게 교체할 수 있습니다.
- **데이터 처리:** PDF 문서에서 텍스트를 추출하고, 의미 단위로 청킹하여 ChromaDB 벡터 데이터베이스에 저장합니다.
- **RAG:** 사용자의 질문에 대해 관련성 높은 문서를 검색하고, 설정된 LLM을 활용하여 답변을 생성합니다.
- **완성형 UI:** 로그인, 회원가입, 실시간 채팅이 가능한 웹 UI를 제공합니다.

## 🚀 기술 스택

- **언어/프레임워크:** Python 3.11+, FastAPI
- **인증:** `python-jose` (JWT), `bcrypt` (비밀번호 해싱)
- **데이터베이스:** `MySQL` (사용자 정보), `ChromaDB` (벡터 저장소)
- **RAG Core:**
    - **LLM:** `langchain-openai`, `langchain-google-genai`
    - **Embedding:** `sentence-transformers` (한국어 모델)
- **데이터 처리:** `unstructured` (PDF 파싱), `langchain` (텍스트 분할)
- **도구:** `python-dotenv`, `uvicorn`, `mysql-connector-python`

## 📂 프로젝트 구조

```
.env.example
README.md
requirements.txt
app/
├── auth.py           # JWT 인증 및 사용자 관련 유틸리티
├── config.py         # 환경 설정 관리
├── database.py       # MySQL 데이터베이스 연결 및 초기화
├── main.py           # FastAPI 애플리케이션 진입점 및 API 엔드포인트
└── rag_core.py       # RAG 시스템의 핵심 로직 (검색, 생성)
data/
└── chroma_db/        # ChromaDB 데이터가 저장될 디렉토리
pdf/
└── *.pdf             # 원본 PDF 문서들을 저장할 디렉토리
scripts/
├── ingest.py         # PDF 문서를 처리하여 ChromaDB 인덱스를 생성
└── evaluate.py       # RAG 시스템의 성능을 평가
YangdongYi-front/     # 프론트엔드 정적 파일 (HTML/CSS/JS)
├── main.html
├── login.html
└── ...
```

## ⚙️ 설치 및 실행 방법

### 1. 사전 준비: MySQL 데이터베이스

이 애플리케이션은 사용자 정보를 저장하기 위해 MySQL 데이터베이스가 필요합니다. 로컬 환경이나 Docker에 MySQL 서버를 설치하고 실행해주세요.

### 2. 환경 설정

#### Python 가상 환경 설정

Python 3.11 이상이 설치되어 있어야 합니다.

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# .\venv\Scripts\activate # Windows
```

#### 의존성 설치

```bash
pip install -r requirements.txt
```

#### 환경 변수 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성하고, 본인의 환경에 맞게 내용을 수정합니다.

```bash
cp .env.example .env
```

`.env` 파일을 열어 **LLM API 키**, **데이터베이스 정보**, **JWT 비밀 키**를 필수로 입력합니다.

```ini
# .env 파일 예시

# LLM 설정
LLM_PROVIDER="openai"
LLM_MODEL_NAME="gpt-4o-mini"
OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# MySQL 데이터베이스 정보
DB_HOST="127.0.0.1"
DB_PORT=3306
DB_USER="root"
DB_PASS="your_db_password"
DB_NAME="dongyang_rag_db"

# JWT 비밀 키 (반드시 길고 복잡한 문자열로 변경하세요)
JWT_SECRET_KEY="a_very_secret_and_long_key_for_jwt_signing"
JWT_ALGORITHM="HS256"
```

### 3. PDF 문서 준비

`pdf/` 디렉토리 안에 챗봇이 답변을 생성할 원본 PDF 문서들을 넣어주세요.

### 4. 데이터 인제스트 (ChromaDB 생성)

PDF 문서를 벡터화하여 ChromaDB에 저장합니다. 이 과정은 PDF 문서가 변경될 때마다 다시 실행해야 합니다.

```bash
python scripts/ingest.py
```

### 5. FastAPI 서버 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

서버가 시작되면 애플리케이션이 자동으로 MySQL 데이터베이스와 `users` 테이블을 생성합니다. 이제 브라우저에서 `http://localhost:8000`으로 접속하여 회원가입 및 로그인을 진행할 수 있습니다.

### 6. API 문서 확인

서버 실행 후 `http://localhost:8000/docs`에서 모든 API의 명세와 테스트 UI를 확인할 수 있습니다.

## 📖 API 엔드포인트

- **인증 API**
  - `POST /api/signup`: 회원가입
  - `POST /api/login`: 로그인 (성공 시 JWT 토큰 발급)
  - `GET /api/me`: (인증 필요) 현재 로그인된 사용자 정보 확인
- **챗봇 API**
  - `POST /api/v1/chat`: (인증 필요) RAG 챗봇 응답 생성
