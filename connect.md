# MongoDB 및 PDF 데이터 연결 가이드

이 가이드는 챗봇 시스템이 MongoDB와 PDF 파일에서 데이터를 성공적으로 인덱싱하고 활용할 수 있도록 돕습니다.

## 1. MongoDB 설정

### 1.1 MongoDB 서버 실행 확인
MongoDB 서버가 로컬 또는 원격에서 실행 중인지 확인하세요. 로컬에서 실행하는 경우, 일반적으로 `mongod` 명령으로 시작합니다.

### 1.2 데이터베이스 및 컬렉션 준비
인덱싱하려는 데이터가 포함된 데이터베이스와 컬렉션이 MongoDB에 준비되어 있어야 합니다.
예시: `dmu` 데이터베이스에 `notices`, `regulations` 등의 컬렉션이 있다고 가정합니다.

### 1.3 `.env` 파일 설정 (`ai/stt-tts-sample/.env`)
`ai/stt-tts-sample/.env` 파일에 MongoDB 연결 정보를 정확히 입력해야 합니다.

```ini
# === Mongo ===
MONGO_URI=mongodb://localhost:27017  # MongoDB 연결 URI (원격인 경우 IP/도메인 및 포트)
MONGO_DB=dmu                         # 사용할 데이터베이스 이름
MONGO_COLL=*                         # 인덱싱할 컬렉션 이름 (모든 컬렉션은 '*', 특정 컬렉션은 쉼표로 구분: 'notices,regulations')
MONGO_UPDATED_FIELD=updated_at       # 문서의 최종 업데이트 시간을 나타내는 필드 (증분 인덱싱에 사용)
```
*   `MONGO_URI`: MongoDB 서버의 주소입니다. 로컬에서 실행 중이라면 `mongodb://localhost:27017`을 사용합니다.
*   `MONGO_DB`: 인덱싱할 데이터가 있는 데이터베이스 이름입니다.
*   `MONGO_COLL`: 인덱싱할 컬렉션 이름을 지정합니다. `*`로 설정하면 `system.`으로 시작하는 컬렉션을 제외한 모든 컬렉션을 인덱싱합니다. 특정 컬렉션만 인덱싱하려면 쉼표로 구분하여 나열합니다 (예: `notices,regulations`).
*   `MONGO_UPDATED_FIELD`: MongoDB 문서 내에서 해당 문서가 마지막으로 업데이트된 시간을 나타내는 필드 이름입니다. 증분 인덱싱(변경된 문서만 업데이트)에 사용됩니다.

## 2. PDF 파일 준비

### 2.1 PDF 파일 배치
인덱싱하려는 PDF 파일들을 `ai/data/docs` 디렉토리 안에 넣어주세요.
예시:
```
ai/
└── data/
    └── docs/
        ├── school_rules_학칙.pdf
        └── school_rules.pdf
```

### 2.2 `.env` 파일 설정 (`ai/stt-tts-sample/.env`)
`ai/stt-tts-sample/.env` 파일에 PDF 데이터 디렉토리와 파일 패턴을 설정합니다.

```ini
# === RAG / Data ===
DATA_DIR=/Users/chaseongjun/Desktop/code/T_project/ai/data/docs # PDF 파일이 있는 절대 경로
PDF_GLOBS=*.pdf                                                 # 인덱싱할 PDF 파일 패턴 (예: '*.pdf', 'rules/*.pdf')
```
*   `DATA_DIR`: PDF 파일이 저장된 디렉토리의 **절대 경로**를 지정합니다.
*   `PDF_GLOBS`: 인덱싱할 PDF 파일의 패턴을 지정합니다. `*.pdf`는 모든 PDF 파일을 의미합니다.

## 3. OpenAI API 키 설정

LLM (GPT-4o-mini) 및 임베딩 (OpenAIEmbeddings)을 사용하기 위해 OpenAI API 키가 필요합니다.

### `.env` 파일 설정 (`ai/llm_runtime/.env`)
`ai/llm_runtime/.env` 파일에 OpenAI API 키를 입력합니다.

```ini
OPENAI_API_KEY=sk-YOUR_OPENAI_API_KEY_HERE
OPENAI_MODEL=gpt-4o-mini
```
*   `OPENAI_API_KEY`: 발급받은 OpenAI API 키를 입력합니다.

## 4. 데이터 인덱싱 실행

모든 설정이 완료되면, FastAPI 서버를 실행한 후 인덱싱 명령을 호출합니다.

1.  **FastAPI 서버 실행:**
    `ai/stt-tts-sample` 디렉토리에서 다음 명령을 실행합니다.
    ```bash
    cd /Users/chaseongjun/Desktop/code/T_project/ai/stt-tts-sample
    uvicorn app:app --reload --port 9000
    ```

2.  **인덱싱 명령 호출:**
    새로운 터미널을 열고 다음 `curl` 명령을 실행하여 인덱싱을 시작합니다.
    ```bash
    curl -X POST "http://127.0.0.1:9000/rag/ingest" -H "Content-Type: application/json" -d "{}"
    ```
    이 명령은 `DATA_DIR`의 모든 PDF 파일과 `MONGO_DB`의 `MONGO_COLL`에 지정된 MongoDB 컬렉션의 모든 문서를 인덱싱합니다.

인덱싱이 성공적으로 완료되면, 챗봇이 MongoDB 및 PDF 데이터에 기반하여 질문에 답변할 수 있게 됩니다.
