# 모델 연결 테스트 스크립트

import os, requests, json

API_BASE = f"http://localhost:{os.getenv('LLM_API_PORT', '8000')}/v1"
MODEL = os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

def chat(msg):
    url = f"{API_BASE}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role":"system","content":"너는 동양미래대학교 학사 도우미야. 모든 날짜는 YYYY-MM-DD로 말해."},
            {"role":"user","content": msg}
        ],
        "max_tokens": 200,
        "temperature": 0.2
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    chat("안녕! 간단히 자기소개해줘.")
