"""
============================================================
vLLM 로컬 서버 테스트 스크립트
------------------------------------------------------------
실행 방법:
    cd ai/llama-runtime
    python test_llm.py
============================================================
"""

# vLLM(OpenAI 호환) 로컬 서버로 채팅 테스트
from openai import OpenAI

# vLLM 서버 주소/키 설정
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",  # vLLM은 임의 문자열이면 됩니다
)

def chat(prompt: str):
    resp = client.chat.completions.create(
        model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",  # compose와 정확히 동일해야 함
        messages=[{"role": "user", "content": prompt}],
        max_tokens=128,
        temperature=0.7,
    )
    print("Assistant:", resp.choices[0].message.content)

if __name__ == "__main__":
    chat("소개 ㄱ")
