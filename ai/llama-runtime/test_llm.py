import openai

# vLLM 서버 설정
openai.api_base = "http://localhost:8000/v1"
openai.api_key = "EMPTY"   # 로컬 vLLM은 API 키 필요 없음

def chat(prompt: str):
    response = openai.ChatCompletion.create(
        model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",   # 실행 중인 모델 이름
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    print("Assistant:", response["choices"][0]["message"]["content"])

if __name__ == "__main__":
    chat("자기소개 ㄱ")


r'''
cd C:\Users\user\Documents\Github\T_project\ai\llama-runtime
python test_llm.py
'''