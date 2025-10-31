# ==========================================================
# app.py (Flask + MySQL + FastAPI RAG/STT/TTS 프록시 통합)
# ==========================================================
import os
from pathlib import Path
from datetime import timedelta
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
import mysql.connector
from dotenv import load_dotenv
import bcrypt
import requests

# ----------------------------
# 1) 환경 변수 로드 (.env)
# ----------------------------
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "test")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
PORT = int(os.getenv("PORT", "8001"))
FASTAPI_BASE = os.getenv("FASTAPI_BASE", "http://127.0.0.1:9000")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

print("==== ENV CHECK ====")
print("[ENV] DB_HOST =", DB_HOST)
print("[ENV] DB_NAME =", DB_NAME)
print("[ENV] FASTAPI_BASE =", FASTAPI_BASE)
print("====================")

# ----------------------------
# 2) Flask 초기화
# ----------------------------
app = Flask(__name__, static_folder="image", static_url_path="/image")
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(days=7)

CORS(app, supports_credentials=True, resources={r"/*": {"origins": CORS_ORIGINS or ["*"]}})

# ----------------------------
# 3) MySQL 연결
# ----------------------------
def get_raw_conn(database=None, autocommit=True):
    cfg = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASS or "",
        "database": database or None,
        "autocommit": autocommit,
        "auth_plugin": "mysql_native_password",
    }
    return mysql.connector.connect(**cfg)

def init_db():
    root = get_raw_conn(database=None)
    cur = root.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4")
    cur.close()
    root.close()

    conn = get_raw_conn(database=DB_NAME)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
      uid VARCHAR(64) UNIQUE NOT NULL,
      role VARCHAR(20) NOT NULL,
      name VARCHAR(100) NOT NULL,
      department VARCHAR(100) NOT NULL,
      email VARCHAR(150) NOT NULL,
      password_hash VARCHAR(200) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("[INIT_DB] ✅ OK")

# ----------------------------
# 4) 유틸
# ----------------------------
def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_pw(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

# ----------------------------
# 5) 회원가입 / 로그인 API
# ----------------------------
@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}
    uid, role, name, dept, email, pw = (
        data.get("uid", "").strip(),
        data.get("role", "").strip(),
        data.get("name", "").strip(),
        data.get("dept", "").strip(),
        data.get("email", "").strip(),
        data.get("password", "").strip(),
    )
    if not all([uid, role, name, dept, email, pw]):
        return jsonify(ok=False, msg="필수 항목 누락"), 400

    conn = get_raw_conn(database=DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users(uid, role, name, department, email, password_hash) VALUES(%s,%s,%s,%s,%s,%s)",
            (uid, role, name, dept, email, hash_pw(pw)),
        )
        conn.commit()
        return jsonify(ok=True)
    except mysql.connector.errors.IntegrityError:
        return jsonify(ok=False, msg="이미 존재하는 아이디입니다."), 409
    finally:
        cur.close()
        conn.close()

@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    uid = (payload.get("uid") or payload.get("id") or "").strip()
    pw = (payload.get("password") or "").strip()
    if not uid or not pw:
        return jsonify(ok=False, msg="아이디/비밀번호 필요"), 400

    conn = get_raw_conn(database=DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE uid=%s", (uid,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not check_pw(pw, row["password_hash"]):
        return jsonify(ok=False, msg="아이디 또는 비밀번호 오류"), 401

    session.update(
        uid=row["uid"],
        name=row["name"],
        role=row["role"],
        department=row["department"],
    )
    return jsonify(ok=True, user=row)

@app.get("/api/me")
def me():
    if "uid" not in session:
        return jsonify(ok=False, msg="로그인 필요"), 401
    return jsonify(ok=True, user={
        "uid": session.get("uid"),
        "name": session.get("name"),
        "role": session.get("role"),
        "department": session.get("department")
    })


# ----------------------------
# 6) Flask → FastAPI 프록시
# ----------------------------
@app.post("/chat")
def proxy_chat():
    """main.html → FastAPI RAG 질의응답"""
    payload = request.get_json() or {}
    # ✅ FastAPI가 요구하는 키로 맞춰줌
    if "text" in payload:
        payload = {"query": payload["text"]}
    try:
        res = requests.post(f"{FASTAPI_BASE}/rag/chat", json=payload, timeout=60)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify(ok=False, msg=f"RAG 서버 연결 실패: {e}"), 500

@app.post("/rag/ingest")
def proxy_rag_ingest():
    try:
        res = requests.post(f"{FASTAPI_BASE}/rag/ingest", json={}, timeout=120)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify(ok=False, msg=f"RAG 인덱싱 실패: {e}"), 500

@app.post("/tts")
def proxy_tts():
    payload = request.get_json() or {}
    try:
        res = requests.post(f"{FASTAPI_BASE}/tts", json=payload, timeout=30)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify(ok=False, msg=f"TTS 연결 실패: {e}"), 500

@app.post("/voice-chat")
def proxy_voice():
    try:
        files = {"file": request.files["file"]}
        res = requests.post(f"{FASTAPI_BASE}/voice-chat", files=files, timeout=60)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify(ok=False, msg=f"Voice 연결 실패: {e}"), 500

# ----------------------------
# 7) HTML 페이지 라우팅
# ----------------------------
@app.get("/")
def main_page():
    return send_from_directory("templates", "main.html")

@app.get("/login")
def login_page():
    return send_from_directory("templates", "login.html")

@app.get("/signup")
def signup_page():
    return send_from_directory("templates", "signup.html")

@app.get("/guest")
def guest_page():
    return send_from_directory("templates", "guest.html")

@app.get("/favicon.ico")
def favicon():
    return ("", 204)

# ----------------------------
# 8) 서버 시작
# ----------------------------
if __name__ == "__main__":
    init_db()
    print(f"🚀 Flask + FastAPI 프록시 통합 서버 실행 중: http://127.0.0.1:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
