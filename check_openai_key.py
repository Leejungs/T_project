import os
import requests
import socket
from dotenv import load_dotenv
from datetime import datetime
from openai import OpenAI
from openai import AuthenticationError, APIConnectionError, APIError

# ========== 설정 ==========
DOTENV_PATH = ".env"
TEST_URL = "https://api.openai.com/v1/models"
BILLING_URL = "https://api.openai.com/v1/dashboard/billing/credit_grants"

print("\n===== 🧩 OpenAI 환경 및 사용 한도 종합 점검 =====")
# ========== 1. .env 파일 체크 ==========
print("\n🔍 1. .env 파일 검사")
if os.path.exists(DOTENV_PATH):
    print(f"✅ .env 파일 발견: {os.path.abspath(DOTENV_PATH)}")
else:
    print("❌ .env 파일을 찾을 수 없습니다.")
    print("   → 현재 경로:", os.getcwd())

# 기존 환경 변수 삭제 (충돌 방지)
os.environ.pop("OPENAI_API_KEY", None)

# .env 로드
load_dotenv(dotenv_path=DOTENV_PATH)

# ========== 2. 환경 변수 확인 ==========
print("\n🔍 2. 환경 변수 검사")
api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    print("✅ 환경 변수에서 OPENAI_API_KEY를 찾았습니다.")
    print(f"   (앞 10자만 표시) → {api_key[:10]}********")
else:
    print("❌ OPENAI_API_KEY를 환경 변수에서 찾지 못했습니다.")
    print("   → .env 파일에 `OPENAI_API_KEY=sk-...` 형태로 있는지 확인")
    exit(1)

# ========== 3. 키 문자열 포맷 검사 ==========
print("\n🔍 3. API 키 형식 검사")
api_key_stripped = api_key.strip()
if api_key != api_key_stripped:
    print("⚠️ 공백 또는 줄바꿈 문자가 포함되어 있습니다. 자동으로 제거했습니다.")
    api_key = api_key_stripped

if not api_key.startswith("sk-"):
    print("⚠️ 예상치 못한 키 형식입니다. (보통 'sk-'로 시작해야 함)")
else:
    print("✅ 키 형식 정상 ('sk-' 시작)")

# ========== 4. 네트워크 연결 테스트 ==========
print("\n🔍 4. 네트워크 연결 테스트 (api.openai.com)")
try:
    socket.create_connection(("api.openai.com", 443), timeout=5)
    print("✅ api.openai.com:443 연결 성공")
except OSError as e:
    print(f"❌ OpenAI 서버에 연결 실패: {e}")
    print("   → 인터넷, VPN, 방화벽 설정 확인 필요")

# ========== 5. 실제 인증 테스트 ==========
print("\n🔍 5. 실제 API 인증 테스트")

client = OpenAI(api_key=api_key)

try:
    response = requests.get(TEST_URL, headers={"Authorization": f"Bearer {api_key}"})
    if response.status_code == 200:
        print("✅ 직접 요청 인증 성공 (HTTP 200)")
    elif response.status_code == 401:
        print("❌ 직접 요청 인증 실패 (HTTP 401) — 키가 잘못되었거나 만료됨.")
    else:
        print(f"⚠️ 직접 요청 오류 (HTTP {response.status_code})")
        print(response.text)
except requests.exceptions.RequestException as e:
    print(f"⚠️ 직접 요청 실패: {e}")

# OpenAI SDK 인증 테스트
try:
    models = client.models.list()
    print(f"✅ SDK 인증 성공 — {len(models.data)}개의 모델 접근 가능")
except AuthenticationError:
    print("❌ SDK 인증 실패 — 키가 잘못되었거나 권한 없음.")
except APIConnectionError:
    print("⚠️ SDK 연결 오류 — 네트워크 문제 가능성 있음.")
except APIError as e:
    print(f"⚠️ API 오류: {e}")
except Exception as e:
    print(f"⚠️ 예외 발생: {type(e).__name__} → {e}")

# ========== 6. (선택) 조직 ID 테스트 ==========
org_id = os.getenv("OPENAI_ORG_ID")
print("\n🔍 6. 조직 ID 검사")
if org_id:
    print(f"✅ OPENAI_ORG_ID 발견: {org_id}")
    try:
        client_org = OpenAI(api_key=api_key, organization=org_id)
        models = client_org.models.list()
        print("✅ 조직 지정 후 모델 목록 접근 성공")
    except Exception as e:
        print(f"⚠️ 조직 지정 후 인증 실패: {e}")
else:
    print("ℹ️ 조직 ID가 설정되어 있지 않습니다. (일반 계정이면 괜찮습니다)")

print("\n✅ 모든 점검 완료")

# ========== 6. 사용 한도(크레딧) 조회 ==========
print("\n🔍 6. 남은 크레딧(사용 한도) 검사")
try:
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(BILLING_URL, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        total = data.get("total_granted", 0)
        used = data.get("total_used", 0)
        remain = data.get("total_available", 0)
        expire_info = data.get("grants", {}).get("data", [{}])[0]
        expires = expire_info.get("expires_at")
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d") if expires else "정보 없음"

        print(f"✅ 크레딧 정보 조회 성공")
        print(f"   총 제공: ${total:,.2f}")
        print(f"   사용됨: ${used:,.2f}")
        print(f"   남음: ${remain:,.2f}")
        print(f"   만료일: {exp_date}")

        if remain <= 0.0:
            print("❌ 사용 가능한 크레딧이 없습니다. (한도 초과)")
    elif resp.status_code == 401:
        print("❌ 인증 실패 — 키가 잘못되었거나 접근 권한이 없습니다.")
    elif resp.status_code == 429:
        print("⚠️ 요청 한도 초과 (HTTP 429)")
    else:
        print(f"⚠️ 크레딧 정보 조회 실패 (HTTP {resp.status_code})")
        print(resp.text[:200])
except Exception as e:
    print(f"⚠️ 크레딧 확인 중 오류: {e}")

print("\n===== ✅ 진단 완료 =====")