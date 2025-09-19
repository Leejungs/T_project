# 📌 2025/09/20
- **WSL2 + Ubuntu 설치 및 환경 세팅**
- **Docker Desktop + NVIDIA GPU 연동**
- **vLLM 서버 실행 성공**
  - `TinyLlama/TinyLlama-1.1B-Chat-v1.0` 모델 로드
  - API 서버 정상 구동 (`http://localhost:8000/v1`)
- **테스트 코드 작성 (`test_llm.py`)**
  - OpenAI API 호환 방식으로 로컬 LLM 호출 성공
  - 간단한 대화 응답 확인 완료
- **보안 관리**
  - Hugging Face Access Token이 노출되는 문제를 발견
  - `.gitignore`에 `.env` 추가해서 해결

---

## 📂 폴더 & 파일 구조

T_project/
├── ai/
│ └── llama-runtime/
│ ├── docker-compose.yml # vLLM 서버 실행 설정
│ ├── .env # Hugging Face Token 등 환경 변수 (Git에 공유 X)
│ ├── test_llm.py # 로컬 vLLM 서버 테스트 스크립트
│ └── requirements.txt # Python 의존성 (옵션)
├── README.md # 프로젝트 설명 문서
└── .gitignore # Git에 올리지 않을 파일 목록 (.env 포함)

---

## 📝 각 파일 역할

### **docker-compose.yml**
- vLLM 서버 실행 정의
- 사용할 모델, 포트, GPU 메모리 활용 비율 등 설정

### **.env**
- Hugging Face Access Token 저장
- **공유 금지** (보안 이슈 때문에 `.gitignore`에 추가됨)

### **test_llm.py**
- Python에서 vLLM(OpenAI API 호환) 호출 예제
- 로컬 서버 테스트 용도

### **requirements.txt**
- 필요한 Python 패키지 명시 (예: `openai`, `requests`)

### **.gitignore**
- Git에 올리지 않아야 하는 파일 제외  
  - `.env`  
  - `__pycache__/`  
  - `*.pyc`  
