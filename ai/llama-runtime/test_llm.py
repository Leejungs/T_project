"""
============================================================
vLLM 로컬 서버 테스트 스크립트
------------------------------------------------------------
실행 방법:
    cd ai/llama-runtime
    python test_llm.py
============================================================
"""

import openai

# vLLM 서버 설정
openai.api_base = "http://localhost:8000/v1"   # 로컬 vLLM 서버 주소
openai.api_key = "EMPTY"   # 로컬 vLLM은 API 키 필요 없음

def chat(prompt: str):
    """사용자 입력(prompt)을 vLLM 서버에 전달하고 응답 출력"""
    response = openai.ChatCompletion.create(
        model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",   # 실행 중인 모델 이름
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    print("Assistant:", response["choices"][0]["message"]["content"])

if __name__ == "__main__":
    chat("자기소개 ㄱ")
