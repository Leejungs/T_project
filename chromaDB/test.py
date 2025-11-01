from pymongo import MongoClient
import os

print(os.getenv("MONGO_URI"))


MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

for db_name in client.list_database_names():
    db = client[db_name]
    print(f"DB: {db_name}, Collections: {db.list_collection_names()}")

client = MongoClient(MONGO_URI)
db = client["Academic_Information_db"]  # 원하는 DB 선택
collections = db.list_collection_names()
print(collections)

target_dbs = [
    "depatement_db",
    "university_life",
    "depatement_all_db",
    "University_Introduction",
    "Admissions_Office",
    "Academic_Information_db"
]

for db_name in target_dbs:
    try:
        db = client[db_name]
        collections = db.list_collection_names()
        print(f"\nDB: {db_name}, Collections: {collections}")
        for coll_name in collections:
            count = db[coll_name].count_documents({})
            print(f"  {coll_name}: {count} documents")
    except Exception as e:
        print(f"Cannot access DB {db_name}: {e}")

