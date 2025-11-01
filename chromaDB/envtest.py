from dotenv import load_dotenv
import os

load_dotenv()  # 현재 디렉토리의 .env 파일 로드

from pymongo import MongoClient


MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
print(client.list_database_names())  # 실제 Atlas DB가 보이는지 확인
print(MONGO_URI)
if not MONGO_URI:
    raise ValueError("❌ MONGO_URI 환경변수가 설정되어 있지 않습니다.")
