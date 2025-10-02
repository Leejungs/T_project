import os
import json
import re
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 프로젝트 루트 경로를 기준으로 app 폴더를 sys.path에 추가
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.config import settings

# --- 1. 평가 지표별 프롬프트 템플릿 정의 ---

FAITHFULNESS_PROMPT = PromptTemplate.from_template(
    """[지시]
    당신은 답변이 주어진 컨텍스트에 완전히 근거하는지 평가하는 AI 심판입니다. 
    답변에 컨텍스트에 없는 내용이 포함되어 있다면 낮은 점수를 주세요. 답변이 컨텍스트의 일부 정보만 사용하더라도, 그 내용이 컨텍스트에 의해 뒷받침된다면 만점을 줄 수 있습니다.

    [컨텍스트]
    {context}

    [답변]
    {answer}

    [평가]
    위 컨텍스트를 고려할 때, 답변이 얼마나 충실하게 근거하고 있습니까? (1-5점 척도) 이유를 간략히 설명하고, 마지막 줄에 "평가 점수: [점수]" 형식으로 점수만 명시해주세요.
    """
)

ANSWER_RELEVANCY_PROMPT = PromptTemplate.from_template(
    """[지시]
    당신은 생성된 답변이 사용자의 질문에 얼마나 관련성이 높은지 평가하는 AI 심판입니다. 답변이 질문의 의도를 정확히 파악하고 유용한 정보를 제공하는지 평가해주세요.

    [질문]
    {question}

    [답변]
    {answer}

    [평가]
    위 질문에 대해, 답변이 얼마나 관련성이 높고 유용합니까? (1-5점 척도) 이유를 간략히 설명하고, 마지막 줄에 "평가 점수: [점수]" 형식으로 점수만 명시해주세요.
    """
)

# --- 2. 헬퍼 함수 정의 ---

def load_evaluation_dataset(path: str) -> list:
    """평가 데이터셋 JSON 파일을 로드합니다."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"오류: 평가 데이터셋을 찾을 수 없습니다. 경로: {path}")
        print("먼저 data/evaluation/dataset.json 파일을 생성해주세요.")
        return None

def get_rag_output(question: str) -> dict:
    """실행 중인 RAG API 서버에 요청을 보내 답변과 출처를 받아옵니다."""
    try:
        response = requests.post("http://localhost:8000/api/v1/chat", json={"query": question})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API 요청 실패: {e}")
        return None

def parse_score(evaluation_text: str) -> int:
    """LLM의 평가 결과 텍스트에서 점수만 파싱합니다."""
    match = re.search(r"평가 점수:.*?(\d+)", evaluation_text)
    if match:
        return int(match.group(1))
    return -1 # 파싱 실패 시

def evaluate_metric(judge_llm, prompt: PromptTemplate, **kwargs) -> int:
    """주어진 지표에 대해 LLM-as-a-Judge를 실행하고 점수를 반환합니다."""
    chain = prompt | judge_llm | StrOutputParser()
    try:
        result_text = chain.invoke(kwargs)
        return parse_score(result_text)
    except Exception as e:
        print(f"메트릭 평가 중 오류 발생: {e}")
        return -1

# --- 3. 메인 평가 로직 ---

import time

def run_evaluation():
    """전체 평가 프로세스를 오케스트레이션합니다."""
    print("--- RAG 시스템 평가 시작 ---")

    # API 서버가 준비될 때까지 대기
    max_retries = 10
    wait_time = 5  # 초
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:8000/api/v1/health")
            if response.status_code == 200:
                print("API 서버가 준비되었습니다.")
                break
        except requests.exceptions.ConnectionError:
            pass
        print(f"API 서버 연결 대기 중... ({i+1}/{max_retries})")
        time.sleep(wait_time)
    else:
        print("API 서버에 연결할 수 없습니다. 평가를 중단합니다.")
        return

    # 설정 로드
    dataset_path = settings.EVAL_DATASET_PATH
    judge_model_name = settings.EVAL_LLM_MODEL_NAME

    # 데이터셋 로드
    eval_dataset = load_evaluation_dataset(dataset_path)
    if not eval_dataset:
        return

    # Judge LLM 초기화
    try:
        judge_llm = ChatOpenAI(model=judge_model_name, temperature=0, api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        print(f"Judge LLM 초기화 실패: {e}")
        return

    results = []
    total_faithfulness = 0
    total_relevancy = 0
    valid_faithfulness_count = 0
    valid_relevancy_count = 0

    # 병렬 처리를 위한 ThreadPoolExecutor 사용
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_item = {}
        for item in tqdm(eval_dataset, desc="RAG 시스템 응답 생성 중"):
            future = executor.submit(get_rag_output, item["question"])
            future_to_item[future] = item

        rag_outputs = []
        for future in tqdm(as_completed(future_to_item), total=len(eval_dataset), desc="결과 수집 중"):
            item = future_to_item[future]
            rag_output = future.result()
            if rag_output:
                rag_outputs.append((item, rag_output))

    # 평가 실행
    for item, rag_output in tqdm(rag_outputs, desc="LLM-as-a-Judge 평가 실행 중"):
        question = item["question"]
        answer = rag_output["answer"]
        retrieved_context = "\n".join([s['content'] for s in rag_output["sources"]])

        # Faithfulness 평가
        faithfulness_score = evaluate_metric(judge_llm, FAITHFULNESS_PROMPT, context=retrieved_context, answer=answer)
        if faithfulness_score != -1:
            total_faithfulness += faithfulness_score
            valid_faithfulness_count += 1

        # Answer Relevancy 평가
        relevancy_score = evaluate_metric(judge_llm, ANSWER_RELEVANCY_PROMPT, question=question, answer=answer)
        if relevancy_score != -1:
            total_relevancy += relevancy_score
            valid_relevancy_count += 1

        results.append({
            "question": question,
            "ground_truth_answer": item.get("ground_truth_answer", "N/A"),
            "generated_answer": answer,
            "sources": rag_output["sources"],
            "faithfulness_score": faithfulness_score,
            "answer_relevancy_score": relevancy_score
        })

    # 최종 결과 계산 및 저장
    summary = {
        "total_items_evaluated": len(results),
        "average_faithfulness": (total_faithfulness / valid_faithfulness_count) if valid_faithfulness_count > 0 else 0,
        "average_answer_relevancy": (total_relevancy / valid_relevancy_count) if valid_relevancy_count > 0 else 0,
    }

    output_data = {"summary": summary, "details": results}
    output_path = "evaluation_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    print("--- RAG 시스템 평가 완료 ---")
    print(json.dumps(summary, indent=4, ensure_ascii=False))
    print(f"상세 결과가 '{output_path}' 파일에 저장되었습니다.")

if __name__ == "__main__":
    # 평가를 실행하기 전에 RAG API 서버가 실행 중인지 확인하세요.
    run_evaluation()