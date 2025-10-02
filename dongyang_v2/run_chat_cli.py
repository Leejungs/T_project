import asyncio
import dotenv
from typing import List, Dict

# .env 파일을 먼저 로드합니다.
print("환경 변수를 로드합니다...")
dotenv.load_dotenv()

# 환경 변수가 로드된 후 RAG 시스템을 임포트합니다.
# 이 순서가 중요합니다. 그렇지 않으면 설정이 제대로 로드되지 않습니다.
try:
    from app.rag_core_streaming import rag_system, QueryRequest, Source
except (ImportError, FileNotFoundError) as e:
    print(f"오류: RAG 시스템을 임포트하는 데 실패했습니다. ({e})")
    print("스크립트를 프로젝트의 루트 디렉토리에서 실행하고 있는지 확인하세요.")
    exit(1)
except Exception as e:
    print(f"RAG 시스템 초기화 중 예기치 않은 오류 발생: {e}")
    print("환경 변수(.env) 설정이 올바른지 확인하세요. (예: API 키)")
    exit(1)

async def main():
    """
    터미널에서 챗봇과 상호작용하기 위한 메인 비동기 함수입니다.
    """
    if not rag_system:
        print("오류: RAG 시스템이 초기화되지 않았습니다. 프로그램을 종료합니다.")
        return

    print("\n--- 동양미래대학교 AI 챗봇 (CLI 버전) ---")
    print("대화를 시작하세요. 종료하려면 'exit' 또는 'quit'을 입력하세요.")
    print("--------------------------------------------------")

    while True:
        try:
            user_query = input("You: ")
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C 또는 Ctrl+D 입력 시 안전하게 종료
            print("\n프로그램을 종료합니다.")
            break

        if user_query.lower() in ["exit", "quit"]:
            print("챗봇을 종료합니다.")
            break

        if not user_query.strip():
            continue

        request = QueryRequest(query=user_query)
        
        print("AI: ", end="", flush=True)
        
        full_answer = ""
        sources: List[Dict] = []

        try:
            async for chunk in rag_system.stream_answer(request):
                if chunk["type"] == "token":
                    token = chunk["data"]
                    print(token, end="", flush=True)
                    full_answer += token
                elif chunk["type"] == "sources":
                    sources = chunk["data"]
                elif chunk["type"] == "end":
                    break
            
            print() # 답변 후 줄바꿈

            if sources:
                print("\n--- 근거 자료 ---")
                for i, source in enumerate(sources[:3], 1): # 상위 3개만 표시
                    source_doc = source.get('source_document', '알 수 없음')
                    page_num = source.get('page_number', 'N/A')
                    print(f"{i}. {source_doc} (페이지: {page_num})")
                print("--------------------\n")

        except Exception as e:
            print(f"\n오류 발생: 답변을 생성하는 동안 문제가 발생했습니다. ({e})")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램을 강제 종료합니다.")