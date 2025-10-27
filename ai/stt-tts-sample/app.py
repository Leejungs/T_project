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

# add project root to sys.path so we can import from frontend/
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from llm_runtime.llm_client import chat
from guard import violates_policy

# -----------------------------------------------------------------------------
# Windows용 이벤트 루프 설정 (asyncio 관련 오류 방지)
# -----------------------------------------------------------------------------
import sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -----------------------------------------------------------------------------
# .env 로드 (경로 명시)
# -----------------------------------------------------------------------------
# LLM 설정과 RAG/서버 설정을 각기 다른 .env 파일에서 명시적으로 로드
LLM_RUNTIME_ENV_PATH = os.path.join(PARENT_AI_DIR, "llm_runtime", ".env")
STT_TTS_ENV_PATH = os.path.join(CURRENT_DIR, ".env")

# .env 파일이 존재하는지 확인하고 로드
if os.path.exists(LLM_RUNTIME_ENV_PATH):
    load_dotenv(dotenv_path=LLM_RUNTIME_ENV_PATH)
    print(f"Loaded .env from: {LLM_RUNTIME_ENV_PATH}")

if os.path.exists(STT_TTS_ENV_PATH):
    load_dotenv(dotenv_path=STT_TTS_ENV_PATH, override=True)
    print(f"Loaded .env from: {STT_TTS_ENV_PATH}")

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

# -----------------------------------------------------------------------------
# ✅ CORS 설정 (프론트 연결용)
# -----------------------------------------------------------------------------
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8001",   # 프론트 주소
        "http://localhost:8001",   # 일부 브라우저용
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# The /static and / routes are now handled by the mounted Flask app.

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
# RAG - Mounted App
# -----------------------------------------------------------------------------
# All RAG logic is now handled by the self-contained FastAPI app in /rag/app.py
# It is mounted under the /rag prefix.
# -----------------------------------------------------------------------------
from rag.app import app as rag_app

app.mount("/rag", rag_app, name="rag")


# -----------------------------------------------------------------------------
# Frontend - Mount Flask App as main UI
# -----------------------------------------------------------------------------
from frontend.app import app as flask_app
from asgiref.wsgi import WsgiToAsgi

# Mount the Flask app at the root. This will handle all UI routes.
app.mount("/", WsgiToAsgi(flask_app), name="frontend")


# -----------------------------------------------------------------------------
# Standalone LLM Ping (for testing)
# -----------------------------------------------------------------------------
from llm_runtime.llm_client import chat as llm_chat

@app.get("/llm/ping")
def llm_ping():
    try:
        msg = [{"role":"user","content":"ping"}]
        txt = llm_chat(messages=msg, temperature=0.0, max_tokens=4)
        return {"ok": True, "model": "OPENAI_MODEL from llm_runtime/.env", "answer": txt}
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=2)}
