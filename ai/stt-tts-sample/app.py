# =============================================================================
# app.py
# -----------------------------------------------------------------------------
# 🎙️ STT/TTS + GPT-4o-mini 통합 FastAPI 서버
# -----------------------------------------------------------------------------
# - STT: faster-whisper (CPU 기본)
# - TTS: edge-tts (MP3 base64 반환)
# - LLM: GPT-4o-mini (ai/llm_runtime/llm_client.py)
# - Guard: 욕설/PII 자동 필터링 (stt-tts-sample/guard.py)
#
# 실행:
#   uvicorn app:app --reload --port 9000
#
# 의존성:
#   pip install fastapi uvicorn[standard] faster-whisper edge-tts python-dotenv
#   (Windows) FFmpeg 권장: winget install Gyan.FFmpeg
# =============================================================================

import os
import base64
import asyncio
from io import BytesIO
import time
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from faster_whisper import WhisperModel
import edge_tts
from dotenv import load_dotenv

from fastapi.staticfiles import StaticFiles

# ✅ 새 GPT LLM 클라이언트 + Guard 모듈
import sys, os

# add parent folder (ai/) to sys.path so we can import llm_runtime/*
CURRENT_DIR = os.path.dirname(__file__)
PARENT_AI_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_AI_DIR not in sys.path:
    sys.path.insert(0, PARENT_AI_DIR)

from llm_runtime.llm_client import chat
from guard import violates_policy

# -----------------------------------------------------------------------------
# Windows용 이벤트 루프 설정 (asyncio 관련 오류 방지)
# -----------------------------------------------------------------------------
import sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -----------------------------------------------------------------------------
# (선택) .env 로드
# -----------------------------------------------------------------------------
load_dotenv()

# -----------------------------------------------------------------------------
# Config (STT/TTS만 유지)
# -----------------------------------------------------------------------------
# whisper: small/medium 등 가능 (CPU 기본)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
# cpu / cuda / auto(미지원 시 cpu로 폴백)
WHISPER_DEVICE = (os.getenv("WHISPER_DEVICE", "cpu") or "cpu").lower()

# edge-tts 한국어 음성 & 포맷 (MP3 권장)
TTS_VOICE = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")

# -----------------------------------------------------------------------------
# FastAPI 앱 설정
# -----------------------------------------------------------------------------
app = FastAPI(title="STT/TTS + GPT-4o-mini", version="1.2.0")

# 정적 파일 (index.html 등)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def root():
    """브라우저에서 기본 페이지 표시"""
    return FileResponse("static/index.html")

# -----------------------------------------------------------------------------
# 비동기 warmup
# -----------------------------------------------------------------------------
WARMUP_ON_STARTUP = os.getenv("WARMUP_ON_STARTUP", "true").lower() == "true"

warmup_state = {
    "running": False,
    "done": False,
    "started_at": None,
    "finished_at": None,
    "steps": [],   # 각 단계 로그
}

def _step(msg: str):
    warmup_state["steps"].append({"t": time.strftime("%H:%M:%S"), "msg": msg})

# app.py - warmup 내부를 경량화(인덱스 확인 제거)
async def _warmup():
    if warmup_state["running"] or warmup_state["done"]:
        return
    warmup_state.update({"running": True, "done": False, "started_at": time.time(), "steps": []})
    try:
        _step("ensure_index_ready()")
        await asyncio.to_thread(ensure_index_ready, False)

        _step("load embedder()")
        await asyncio.to_thread(embedder)

        _step("retrieve('웜업 질문')")
        await asyncio.to_thread(retrieve, "웜업 질문", 1)

        # 위 1)에서 수정한 LLM 핑 호출
        try:
            _step("LLM ping")
            _ = chat(messages=[{"role": "user", "content": "ping"}], temperature=0.0, max_tokens=1)
            _step("LLM ping ok")
        except Exception as e:
            _step(f"LLM ping failed: {e}")

        _step("all done")
    except Exception as e:
        # ← 예외를 여기서 삼켜주어야 'Task exception was never retrieved'가 안 뜹니다.
        _step(f"warmup error: {type(e).__name__}: {e}")
    finally:
        warmup_state.update({"running": False, "done": True, "finished_at": time.time()})


@app.on_event("startup")
async def on_startup():
    if WARMUP_ON_STARTUP:
        asyncio.create_task(_warmup())

# --- 상태 확인/수동 시작 ---
@app.get("/warmup/status")
def warmup_status():
    s = dict(warmup_state)
    if s["started_at"] is not None:
        s["started_at"] = int(s["started_at"])
    if s["finished_at"] is not None:
        s["finished_at"] = int(s["finished_at"])
    return s

@app.post("/warmup/start")
async def warmup_start():
    asyncio.create_task(_warmup())
    return {"ok": True, "started": True}

# -----------------------------------------------------------------------------
# Lazy-loaded STT 모델
# -----------------------------------------------------------------------------
_whisper_model: Optional[WhisperModel] = None

def _compute_type_for(device: str) -> str:
    """GPU면 float16, 그 외에는 int8로 경량화."""
    return "float16" if device == "cuda" else "int8"

def _normalize_device(device: str) -> str:
    return device if device in {"cpu", "cuda"} else "cpu"

def get_stt_model() -> WhisperModel:
    """Whisper 모델을 전역 싱글톤으로 로드"""
    global _whisper_model
    if _whisper_model is None:
        device = _normalize_device(WHISPER_DEVICE)
        _whisper_model = WhisperModel(
            model_size_or_path=WHISPER_MODEL_SIZE,
            device=device,
            compute_type=_compute_type_for(device),
        )
    return _whisper_model

# -----------------------------------------------------------------------------
# 요청/응답 모델
# -----------------------------------------------------------------------------
class ChatRequest(BaseModel):
    text: str

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None

class VoiceChatResponse(BaseModel):
    user_text: str
    assistant_text: str
    audio_b64: str       # MP3 Base64
    audio_mime: str = "audio/mpeg"

# -----------------------------------------------------------------------------
# Helper 함수들
# -----------------------------------------------------------------------------
def stt_transcribe_bytes(audio_bytes: bytes) -> Dict[str, Any]:
    """Bytes → STT → {text, language, segments}"""
    if not audio_bytes:
        raise ValueError("empty audio payload")

    model = get_stt_model()
    segments, info = model.transcribe(BytesIO(audio_bytes), beam_size=1)

    out_segments, full_text_parts = [], []
    for seg in segments:
        seg_text = (seg.text or "").strip()
        if seg_text:
            full_text_parts.append(seg_text)
            out_segments.append(
                {"text": seg_text, "start": float(seg.start), "end": float(seg.end)}
            )

    text = " ".join(full_text_parts).strip()
    language = info.language or "unknown"
    return {"text": text, "language": language, "segments": out_segments}

def chat_answer(user_text: str) -> str:
    """
    텍스트 → GPT-4o-mini 답변(str)
    (기존 TinyLlama/vLLM 호출을 llm_runtime.llm_client.chat()으로 교체)
    """
    # 🛡️ Guard: 금지어/PII 포함 시 차단 멘트
    if violates_policy(user_text):
        return "⚠️ 부적절하거나 개인정보가 포함된 요청입니다. 다른 질문을 해 주세요."

    messages = [
        {"role": "system", "content": "You are a helpful Korean assistant."},
        {"role": "user", "content": user_text.strip()},
    ]
    return chat(messages)  # <-- GPT-4o-mini 호출

async def tts_synthesize_mp3(text: str, voice: str) -> bytes:
    """텍스트를 음성(MP3)으로 변환"""
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        buf = BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        data = buf.getvalue()
        if not data:
            raise RuntimeError("edge-tts produced empty audio")
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS synth failed: {e}")

# -----------------------------------------------------------------------------
# Health 체크
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm": "gpt-4o-mini-via-llm_runtime",
        "warmup_done": warmup_state["done"],
        "warmup_running": warmup_state["running"],
    }

# -----------------------------------------------------------------------------
# STT 엔드포인트
# -----------------------------------------------------------------------------
@app.post("/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """업로드된 음성 파일을 STT 처리"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        audio = await file.read()
        result = stt_transcribe_bytes(audio)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {e}")

# -----------------------------------------------------------------------------
# Chat 엔드포인트
# -----------------------------------------------------------------------------
@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """텍스트 입력 → GPT-4o-mini 응답 반환"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")
    try:
        answer = chat_answer(text)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

# -----------------------------------------------------------------------------
# TTS 엔드포인트
# -----------------------------------------------------------------------------
@app.post("/tts")
async def tts_endpoint(req: TTSRequest):
    """텍스트를 음성(MP3 base64)으로 변환"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    voice = (req.voice or TTS_VOICE).strip()
    try:
        mp3_bytes = await tts_synthesize_mp3(text, voice)
        audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")
        return {"audio_b64": audio_b64, "mime": "audio/mpeg"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")

# -----------------------------------------------------------------------------
# Voice Chat 엔드포인트
# -----------------------------------------------------------------------------
@app.post("/voice-chat", response_model=VoiceChatResponse)
async def voice_chat(file: UploadFile = File(...)):
    """음성 → STT → GPT-4o-mini → TTS → JSON 반환"""
    # 1) STT
    try:
        audio = await file.read()
        stt = stt_transcribe_bytes(audio)
        user_text = (stt.get("text") or "").strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="STT produced empty text")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"voice-chat STT error: {e}")

    # 2) LLM (GPT-4o-mini)
    try:
        assistant_text = chat_answer(user_text) or "죄송해요. 지금은 대답을 생성할 수 없어요."
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"voice-chat LLM error: {e}")

    # 3) TTS
    try:
        mp3_bytes = await tts_synthesize_mp3(assistant_text, TTS_VOICE)
        audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"voice-chat TTS error: {e}")

    return VoiceChatResponse(
        user_text=user_text,
        assistant_text=assistant_text,
        audio_b64=audio_b64,
        audio_mime="audio/mpeg",
    )

# -----------------------------------------------------------------------------
# RAG APIs
# -----------------------------------------------------------------------------
from typing import Optional, Dict, List
from pydantic import BaseModel
from fastapi import HTTPException
from rag.auto_index import ensure_index_ready
from rag.ingest import ingest_all, embedder
from rag.retriever import retrieve
from rag.qa import answer as rag_answer
from llm_runtime.llm_client import chat as llm_chat

class IngestAllReq(BaseModel):
    pdf_paths: Optional[List[str]] = None
    mongo_query: Optional[Dict] = None

@app.post("/rag/ingest")
def rag_ingest(req: Optional[IngestAllReq] = None):
    try:
        res = ingest_all(pdf_paths=req.pdf_paths if req else None,
                         mongo_query=req.mongo_query if req else None)
        # manifest 갱신을 위해 ensure(force=True) 호출
        auto = ensure_index_ready(force=True)
        return {"status":"ok","ingest":res,"auto_index":auto}
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")

class RagChatReq(BaseModel):
    query: str
    top_k: int = 6
    # dataset 등 필터: {"dataset": ["경영학과","전기공학과"]}
    filters: Optional[Dict[str, List[str]]] = None

@app.post("/rag/chat")
def rag_chat(req: RagChatReq):
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")

    t0 = time.perf_counter()

    # ① 인덱스 최신화 (최초 1회만 의미 있음; 이후엔 빠름)
    #    여기서 오래 걸리면 첫 질문만 느린 원인 → startup 웜업으로 해소 가능
    auto = ensure_index_ready(force=False)

    try:
        # ② 리트리버 파라미터 안전 범위로 클램프 (너무 큰 top_k 방지)
        k = max(1, min(8, req.top_k or 6))

        # ③ 검색 (빠르게 끝나야 정상)
        chunks = retrieve(q, k=k, filters=req.filters)

        # ④ LLM 합성 (rag/qa.py에서 timeout/컨텍스트 제한 적용되어 있어야 함)
        qa = rag_answer(q, chunks)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "answer": qa["answer"],
            "sources": qa["sources"],
            "auto_index": auto,
            "latency_ms": latency_ms,   # 디버깅용 지연 시간
        }

    except TimeoutError:
        # LLM 타임아웃은 504로 명확히
        raise HTTPException(status_code=504, detail="LLM timeout")
    except Exception as e:
        # 나머지는 502로 래핑
        raise HTTPException(status_code=502, detail=f"RAG failed: {e}")

@app.post("/rag/preview")
def rag_preview(req: RagChatReq):
    try:
        auto = ensure_index_ready(force=False)
        chunks = retrieve(req.query, k=req.top_k, filters=req.filters)
        return {"auto_index": auto, "chunks": [
            {"page": c["meta"].get("page"),
             "source_type": c["meta"].get("source_type"),
             "title": c["meta"].get("title"),
             "dataset": c["meta"].get("dataset"),
             "score": round((c.get("score") or 0), 3),
             "text": c["text"][:500]}
        for c in chunks]}
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")

# ---------- Mongo 디버그 ----------
from pymongo import MongoClient
from fastapi import APIRouter

@app.get("/rag/debug/mongo")
def rag_debug_mongo():
    import os, traceback
    from rag.config import MONGO_URI, MONGO_DB, MONGO_COLL, MONGO_UPDATED_FIELD
    out = {"ok": False, "uri": MONGO_URI, "db": MONGO_DB, "coll": MONGO_COLL, "updated_field": MONGO_UPDATED_FIELD}
    try:
        cli = MongoClient(MONGO_URI)
        db  = cli[MONGO_DB]
        colls = [c for c in db.list_collection_names() if not c.startswith("system.")]
        out["collections"] = colls
        samples = {}
        for name in colls[:5]:
            doc = db[name].find_one()
            samples[name] = {k: doc.get(k) for k in ["title","subject","content","body","summary","text","updated_at"]} if doc else None
        out["samples"] = samples
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["trace"] = traceback.format_exc(limit=3)
    return out

# -- 임시 테스트
@app.get("/llm/ping")
def llm_ping():
    try:
        msg = [{"role":"user","content":"ping"}]
        txt = llm_chat(messages=msg, temperature=0.0, max_tokens=4)  # timeout_s 인자 넣지 말 것
        return {"ok": True, "model": "OPENAI_MODEL from llm_runtime/.env", "answer": txt}
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=2)}

@app.get("/rag/debug/count")
def rag_debug_count():
    from rag.store import get_client, get_collection
    from rag.config import CHROMA_DIR, COLLECTION_NAME
    cli = get_client(CHROMA_DIR)
    col = get_collection(cli, name=COLLECTION_NAME)
    return {"chroma_dir": CHROMA_DIR, "collection": COLLECTION_NAME, "count": col.count()}
