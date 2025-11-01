# Docker를 이용한 프로젝트 실행 방법

이 문서는 Docker를 사용하여 프로젝트를 설정하고 실행하는 방법을 안내합니다.

## 사전 요구사항

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

## 설치 및 실행

1.  **저장소 복제:**

    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  **`.env` 파일 생성:**

    프로젝트 루트 디렉토리에 `.env` 파일을 생성하고, `OPENAI_API_KEY`를 추가합니다.

    ```
    OPENAI_API_KEY="your_openai_api_key"
    ```

3.  **Docker 컨테이너 빌드 및 실행:**

    `docker-compose.yml` 파일이 있는 프로젝트 루트 디렉토리에서 다음 명령어를 실행하여 Docker 컨테이너를 빌드하고 실행합니다.

    ```bash
    docker-compose up --build
    ```

4.  **데이터 인제스트 (데이터베이스 채우기):**

    새로운 터미널을 열고, 다음 명령어를 실행하여 ChromaDB에 데이터를 인제스트합니다.

    ```bash
    docker-compose run ingest
    ```

5.  **애플리케이션 접속:**

    `app` 서비스가 실행되면, 웹 브라우저에서 `http://localhost:9000`으로 접속하여 애플리케이션을 사용할 수 있습니다.

## 서비스 설명

-   **`app`:** STT/TTS 및 RAG 기능을 제공하는 메인 애플리케이션입니다.
-   **`ingest`:** `chromaDB/sav.py` 스크립트를 실행하여 MongoDB의 데이터를 ChromaDB로 인제스트하는 서비스입니다.
