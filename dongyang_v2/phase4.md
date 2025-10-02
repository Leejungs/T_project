### **[Phase 4 실행 계획 제안: 정량적 평가 프레임워크 구축 (`scripts/evaluate.py`)]**

**To: Project Lead**
**From: Gemini Pro (AI Senior Engineer)**
**Subject: Proposal for Phase 4 - Quantitative Evaluation Framework**

이제 RAG 시스템의 성능을 객관적이고 반복 가능하게 측정하기 위한 정량적 평가 프레임워크(`scripts/evaluate.py`)의 구축 계획을 제안합니다. 이 계획은 **LLM-as-a-Judge** 접근법을 사용하여 RAG의 핵심 품질 지표를 자동으로 평가하는 데 중점을 둡니다.

#### **1. 평가 목표 및 핵심 지표 정의**

우리는 RAG 시스템의 응답 품질을 다각도에서 측정하기 위해 다음 세 가지 핵심 지표를 정의합니다.

1.  **Faithfulness (충실성/근거 기반)**: 생성된 답변이 제공된 컨텍스트(검색된 문서)에 얼마나 충실하게 근거하고 있는가? (즉, 환각(Hallucination)이 없는가?)
2.  **Answer Relevancy (답변 관련성)**: 생성된 답변이 사용자의 원본 질문에 대해 얼마나 관련성이 높고 유용한가?
3.  **Context Precision (컨텍스트 정확성)**: 검색된 컨텍스트가 답변을 생성하는 데 얼마나 정확하고 필요한 정보를 담고 있는가? (Retriever의 성능 측정)

각 지표는 1점(나쁨)부터 5점(좋음)까지의 척도로 측정됩니다.

#### **2. 평가 데이터셋 형식 정의**

평가의 기반이 될 데이터셋은 JSON 파일 형식으로 관리합니다. 각 항목은 질문과 함께, 평가에 필요한 정답 및 이상적인 컨텍스트를 포함합니다.

**파일 경로**: `data/evaluation/dataset.json` (예시)

**구조 예시**:
```json
[
  {
    "question": "장학금 신청은 언제 어디서 하나요?",
    "ground_truth_answer": "장학금 신청은 매년 2월과 8월, 학생회관 2층 장학팀에서 할 수 있습니다.",
    "ground_truth_context": [
      "장학 규칙 제5조 (신청) ① ... 매 학기 개시 전 총장이 정하는 기간(통상 2월, 8월) 내에 신청하여야 한다.",
      "장학 업무는 학생회관 2층에 위치한 장학팀에서 담당한다."
    ]
  },
  {
    "question": "수강 신청을 변경하고 싶으면 어떻게 해야 하나요?",
    "ground_truth_answer": "수강 신청 변경은 개강 첫 주에만 가능하며, 학교 포털 시스템에서 직접 처리해야 합니다.",
    "ground_truth_context": [
      "수강신청 운영규칙 제8조 (변경) ① 수강 신청의 변경은 개강 후 1주 이내에만 허용된다.",
      "모든 수강 신청 관련 업무는 온라인 포털 시스템을 통해 학생 본인이 직접 수행하는 것을 원칙으로 한다."
    ]
  }
]
```

#### **3. 평가 방법론: LLM-as-a-Judge**

각 지표를 평가하기 위해, 강력한 성능의 LLM(`gpt-4-turbo` 등)을 "판단자(Judge)"로 활용합니다. 각 지표별로 특화된 프롬프트를 사용하여 RAG 시스템의 출력을 평가하고 점수를 매기도록 합니다.

**Judge LLM 프롬프트 예시:**

-   **Faithfulness 평가 프롬프트**:
    ```
    [지시]
    당신은 답변이 주어진 컨텍스트에 완전히 근거하는지 평가하는 AI 심판입니다. 답변에 컨텍스트에 없는 내용이 포함되어 있다면 낮은 점수를 주세요.

    [컨텍스트]
    {retrieved_context}

    [답변]
    {answer}

    [평가]
    위 컨텍스트를 고려할 때, 답변이 얼마나 충실하게 근거하고 있습니까? (1-5점 척도) 이유를 간략히 설명하고, 마지막 줄에 "평가 점수: [점수]" 형식으로 점수만 명시해주세요.
    ```

-   **Answer Relevancy 평가 프롬프트**:
    ```
    [지시]
    당신은 생성된 답변이 사용자의 질문에 얼마나 관련성이 높은지 평가하는 AI 심판입니다.

    [질문]
    {question}

    [답변]
    {answer}

    [평가]
    위 질문에 대해, 답변이 얼마나 관련성이 높고 유용합니까? (1-5점 척도) 이유를 간략히 설명하고, 마지막 줄에 "평가 점수: [점수]" 형식으로 점수만 명시해주세요.
    ```

#### **4. `scripts/evaluate.py` 스크립트 구조 및 실행 흐름**

평가 스크립트는 아래와 같은 모듈식 구조로 설계합니다.

1.  **`load_evaluation_dataset()`**: `EVAL_DATASET_PATH` 설정에 따라 평가 데이터셋 JSON 파일을 로드합니다.

2.  **`get_rag_output(question: str)`**: 주어진 질문에 대해 실행 중인 RAG API 서버(`http://localhost:8000/api/v1/chat`)에 요청을 보내 `answer`와 `retrieved_context`를 받아옵니다.

3.  **`evaluate_metric(judge_llm, metric_prompt, **kwargs)`**: Judge LLM과 지표별 프롬프트를 받아, 주어진 인자들로 프롬프트를 완성하고 LLM을 호출하여 점수를 파싱하고 반환합니다.

4.  **`run_evaluation()` (메인 로직)**:
    a.  `app.config`에서 `EVAL_LLM_MODEL_NAME`, `EVAL_DATASET_PATH` 등 설정을 로드합니다.
    b.  `load_evaluation_dataset()`을 호출하여 평가 데이터셋을 로드합니다.
    c.  `ChatOpenAI(model=settings.EVAL_LLM_MODEL_NAME)`를 사용하여 **Judge LLM**을 초기화합니다.
    d.  평가 데이터셋의 각 항목을 순회하며 (`tqdm`으로 진행률 표시):
        i.  `get_rag_output()`을 호출하여 현재 RAG 시스템의 답변과 검색된 컨텍스트를 얻습니다.
        ii. `evaluate_metric()` 함수를 각 지표(Faithfulness, Answer Relevancy 등)에 대해 특화된 프롬프트와 함께 호출하여 점수를 얻습니다.
    e.  모든 항목에 대한 평가 결과를 (질문, 시스템 답변, 출처, 각 지표별 점수 등) 리스트에 저장합니다.
    f.  평가가 완료되면, 전체 항목에 대한 각 지표의 **평균 점수**를 계산합니다.
    g.  상세 결과와 요약 통계를 `evaluation_results.json` 파일로 저장하고, 콘솔에 요약 결과를 출력합니다.

이 계획은 RAG 시스템의 성능을 지속적으로 추적하고 개선의 방향성을 제시할 수 있는 강력하고 자동화된 평가 파이프라인의 기반이 될 것입니다.

---

위 계획에 대한 검토를 부탁드립니다. 계획이 승인되면, 이 설계에 따라 `scripts/evaluate.py`의 전체 코드를 생성하겠습니다.
