from pymongo import MongoClient

MONGO_URI = "mongodb+srv://wjdtndpdy0920:dlwjd09tn20@cluster0.zsdkexf.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)

print(client.list_database_names())  # 여기서 실제 DB 목록이 보여야 함

db = client["university_life"]
print(db.list_collection_names())  # ['college']가 나와야 함

coll = db["college"]
print(coll.find_one())  # 실제 문서 1개 출력
