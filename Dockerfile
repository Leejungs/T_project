# 1. 베이스 이미지 선택
FROM conda/miniconda3

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 환경 설정 파일 복사 및 Conda 환경 생성
COPY environment.yml .
RUN conda env create -f environment.yml

# 4. 필요한 소스 코드 복사
COPY ai/ ./ai
COPY chromaDB/ ./chromaDB

# 5. 기본 실행 명령어 (RAG 앱 실행)
# docker-compose.yml에서 이 명령을 오버라이드하여 사용합니다.
CMD ["conda", "run", "-n", "rag", "uvicorn", "ai.rag.app:app", "--host", "0.0.0.0", "--port", "8000"]