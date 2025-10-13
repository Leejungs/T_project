# app.py
import os
from pathlib import Path
from datetime import timedelta

from flask import Flask, jsonify, request, send_from_directory, session
from flask import session, render_template_string
from flask_cors import CORS
import mysql.connector
from dotenv import load_dotenv
import bcrypt

# ----------------------------
# 1) .env 로딩
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
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

print("==== ENV CHECK ====")
print("[ENV] PATH_TO_ENV      =", ENV_PATH)
print("[ENV] DB_HOST          =", DB_HOST)
print("[ENV] DB_PORT          =", DB_PORT)
print("[ENV] DB_USER          =", DB_USER)
print("[ENV] DB_PASS          =", "***" if DB_PASS != "" else "<EMPTY>")
print("[ENV] DB_NAME          =", DB_NAME)
print("[ENV] CORS_ORIGINS     =", CORS_ORIGINS)
print("====================")

# ----------------------------
# 2) Flask
# ----------------------------
app = Flask(__name__, static_folder="image", static_url_path="/image")
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(days=7)

CORS(
    app,
    supports_credentials=True,
    resources={r"/api/*": {"origins": CORS_ORIGINS or ["*"]}},
)

# ----------------------------
# 3) DB 연결
# ----------------------------
def get_raw_conn(database=None, autocommit=True):
    cfg = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASS if DB_PASS is not None else "",
        "database": database if database else None,
        "autocommit": autocommit,
        "auth_plugin": "mysql_native_password",
    }
    dbg = cfg.copy()
    dbg["password"] = "***" if DB_PASS is not None and DB_PASS != "" else ("<EMPTY>" if DB_PASS == "" else "<NONE>")
    print("[DB CONFIG]", {k: v for k, v in dbg.items() if k != "database"})
    return mysql.connector.connect(**cfg)

# ----------------------------
# 4) 초기화 (DB + users 테이블)
# ----------------------------
def init_db():
    root = get_raw_conn(database=None)
    cur = root.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4")
    cur.close()
    root.close()

    conn = get_raw_conn(database=DB_NAME)
    cur = conn.cursor()

    # 헬스체크(선택)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS healthcheck (
      id INT PRIMARY KEY AUTO_INCREMENT,
      ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ✅ 회원 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INT UNSIGNED NOT NULL AUTO_INCREMENT,
      uid VARCHAR(64) NOT NULL UNIQUE,
      role VARCHAR(20) NOT NULL,
      name VARCHAR(100) NOT NULL,
      department VARCHAR(100) NOT NULL,
      email VARCHAR(150) NOT NULL,
      password_hash VARCHAR(200) NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_uid (uid)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 헬스체크 한 줄
    cur.execute("INSERT INTO healthcheck () VALUES ()")
    conn.commit()
    cur.close()
    conn.close()
    print("[INIT_DB] OK")

# ----------------------------
# 5) 유틸
# ----------------------------
def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_pw(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

# ----------------------------
# 6) API
# ----------------------------
@app.post("/api/signup")
def api_signup():
    """signup.html이 보내는 JSON을 받아 회원 생성"""
    data = request.get_json(silent=True) or {}
    uid  = (data.get("uid") or "").strip()
    role = (data.get("role") or "").strip()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    pw   = (data.get("password") or "").strip()
    dept = (data.get("dept") or "").strip()   # ← 프론트 키 이름: dept

    if not all([uid, role, name, email, pw, dept]):
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
        cur.close(); conn.close()

@app.post("/api/login")
def api_login():
    # JSON 이든 form 이든 다 받기 + 여러 키 이름 허용
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    uid = (payload.get("uid") or payload.get("id") or payload.get("username") or "").strip()
    pw  = (payload.get("password") or payload.get("pw") or payload.get("pass") or "").strip()

    if not uid or not pw:
        return jsonify(ok=False, msg="아이디/비밀번호 필요"), 400

    conn = get_raw_conn(database=DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT uid, name, role, password_hash FROM users WHERE uid=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()

    # bcrypt 해시 대조
    if not row:
        return jsonify(ok=False, msg="존재하지 않는 계정"), 401
    try:
        ok = bcrypt.checkpw(pw.encode("utf-8"), row["password_hash"].encode("utf-8"))
    except AttributeError:
        # 혹시 컬럼 타입이 BLOB이라 바이트로 읽혔다면 이 분기 처리
        hashed = row["password_hash"]
        if isinstance(hashed, (bytes, bytearray)):
            ok = bcrypt.checkpw(pw.encode("utf-8"), hashed)
        else:
            ok = False

    if not ok:
        return jsonify(ok=False, msg="아이디 또는 비밀번호 오류"), 401

    # 로그인 성공 → 세션 기록
    session["uid"] = row["uid"]
    session["name"] = row["name"]
    session["department"] = row.get("department")
    return jsonify(ok=True, user={"uid": row["uid"], "name": row["name"], "role": row["role"], "department": row.get("department")})

@app.get("/api/me")
def api_me():
    if "uid" not in session:
        return jsonify(ok=False, msg="로그인 필요"), 401

    # 세션에 학과가 없으면 DB에서 한 번 조회해 채워 넣기
    if not session.get("department"):
        conn = get_raw_conn(database=DB_NAME)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT department FROM users WHERE uid=%s", (session["uid"],))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row.get("department"):
            session["department"] = row["department"]

    return jsonify(ok=True, user={
        "uid": session.get("uid"),
        "name": session.get("name"),
        "role": session.get("role"),
        "department": session.get("department"),
    })



@app.route("/api/ping")
def ping():
    return jsonify(ok=True, db=DB_NAME)

# ----------------------------
# 7) 페이지 라우트 (HTML 서빙)
# ----------------------------
@app.get("/")   
def serve_main():
    return send_from_directory("templates", "main.html")

@app.get("/login")
def serve_login():
    return send_from_directory("templates", "login.html")

@app.get("/signup")
def serve_signup():
    return send_from_directory("templates", "signup.html")

@app.get("/feature")
def serve_feature():
    return send_from_directory("templates", "feature.html")

@app.get("/guest")
def serve_guest():
    return send_from_directory("templates", "guest.html")

# .html 별칭
@app.get("/main.html")
def serve_main_html():
    # 세션에서 사용자 정보 가져오기
    user = {
        "uid": session.get("uid"),
        "name": session.get("name"),
        "department": session.get("department"),
        "role": session.get("role"),
    }

    return send_from_directory("templates", "main.html")

@app.get("/login.html")
def serve_login_html():
    return send_from_directory("templates", "login.html")

@app.get("/signup.html")
def serve_signup_html():
    return send_from_directory("templates", "signup.html")

@app.get("/feature.html")
def serve_feature_html():
    return send_from_directory("templates", "feature.html")

@app.get("/guest.html")
def serve_guest_html():
    return send_from_directory("templates", "guest.html")

@app.get("/favicon.ico")
def favicon():
    return ("", 204)


# ----------------------------
# 8) 엔트리포인트
# ----------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT, debug=True)
