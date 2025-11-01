import os
from dotenv import load_dotenv
from openai import OpenAI
from openai import APIError, AuthenticationError, APIConnectionError

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=api_key)

print("🔍 OpenAI API 호출 테스트 중...")

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 가장 저렴하고 가벼운 모델
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=5
    )
    print("✅ 정상 응답 받음 — 한도 초과 아님 (정상 사용 가능)")
    print("💬 응답:", response.choices[0].message.content)

except AuthenticationError:
    print("❌ 인증 실패 — 키가 잘못되었거나 만료됨")

except APIError as e:
    # HTTP 429 등 일반적인 OpenAI 오류 처리
    if hasattr(e, "status_code") and e.status_code == 429:
        print("❌ 한도 초과 (quota exceeded) — 결제/크레딧 소진됨")
    else:
        print(f"⚠️ OpenAI API 오류 ({e.status_code if hasattr(e, 'status_code') else 'unknown'}): {e}")
        if "insufficient_quota" in str(e):
            print("❌ 한도 초과 — 사용량 제한에 걸렸습니다.")

except APIConnectionError:
    print("⚠️ 네트워크 연결 오류 — 인터넷 또는 프록시 확인 필요")

except Exception as e:
    print(f"⚠️ 예상치 못한 오류: {type(e).__name__} → {e}")
