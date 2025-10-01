## 🚀 실행 순서

### 0. 사전 준비
- Docker Desktop 실행

### 1. 가상환경 활성화 (.venv)
```bash
cd C:\Users\user\Documents\Github\T_project\ai\stt-tts-sample
.\.venv\Scripts\Activate
```

### 2. 의존성 설치 (최초 1회 또는 변경 시)
```bash
pip install -r requirements.txt
```

### 3. FFmpeg 확인 (미설치 시 설치)
- 설치 후 PowerShell 재시작하고 아래 명령 수행
- 아래 명령어 실행 시 버전이 출력되면 성공
```bash
ffmpeg -version
```

### 4. STT/TTS FastAPI 서버 실행
- Uvicorn running on http://127.0.0.1:9000 가 보이면 정상
```bash
uvicorn app:app --reload --port 9000
```

### 5. TTS 간단 테스트 (예: 텍스트→오디오)
- 새 터미널에서 가상환경 유지한 상태로 또는 다른 터미널에서 실행
- 같은 폴더에 output.wav 생성 → 재생해서 음성 확인
```bash
curl.exe -X POST "http://127.0.0.1:9000/tts" `
  -H "Content-Type: application/json" `
  -d '{"text": "안녕하세요. 샘플 TTS 입니다."}' `
  --output output.wav
```

### 6. 음성 채팅(STT→LLM→TTS) 통합 테스트 (예시)
```bash
curl.exe -X POST "http://127.0.0.1:9000/voice-chat" `
  -H "Content-Type: application/json" `
  -d "{`"text`": `"내일 일정 알려줘`"}"
```