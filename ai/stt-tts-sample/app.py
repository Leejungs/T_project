# app.py
# =============================================================================
# STT/TTS 샘플 서버 (FastAPI)
# - STT: faster-whisper (CPU 기본), JSON으로 결과 반환
# - TTS: edge-tts (MS Edge 음성 엔진), MP3를 base64로 JSON 반환
# - LLM: vLLM(OpenAI 호환) 로컬 서버 호출 (기본 http://localhost:8000/v1)
#
# 실행:
#   uvicorn app:app --reload --port 9000
#
# 의존성:
#   pip install fastapi uvicorn[standard] faster-whisper edge-tts openai python-dotenv
#   (Windows) FFmpeg 설치 권장: winget install Gyan.FFmpeg
# =============================================================================

import os
import json
import base64
import asyncio
import traceback
from io import BytesIO
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from faster_whisper import WhisperModel
import edge_tts
from dotenv import load_dotenv
from openai import OpenAI

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# --- (선택) .env 로드 ---------------------------------------------------------
load_dotenv()

# ===== Config =====
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")

# whisper: small/medium 등 가능 (CPU 기본)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
# cpu / cuda / auto(미지원 시 cpu로 폴백)
WHISPER_DEVICE = (os.getenv("WHISPER_DEVICE", "cpu") or "cpu").lower()

# edge-tts 한국어 음성 & 포맷 (MP3 권장)
TTS_VOICE = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")

# ===== FastAPI =====
app = FastAPI(title="STT/TTS Sample", version="0.1.0")

# 정적 파일 폴더 마운트 (static 폴더 생성 예정)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def root():
    # 브라우저에서 열 기본 페이지
    return FileResponse("static/index.html")

# ===== Lazy-loaded STT model =================================================
_whisper_model: Optional[WhisperModel] = None

def _compute_type_for(device: str) -> str:
    """GPU면 float16, 그 외에는 int8로 경량화."""
    return "float16" if device == "cuda" else "int8"

def _normalize_device(device: str) -> str:
    if device in {"cpu", "cuda"}:
        return device
    return "cpu"

def get_stt_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        device = _normalize_device(WHISPER_DEVICE)
        _whisper_model = WhisperModel(
            model_size_or_path=WHISPER_MODEL_SIZE,
            device=device,
            compute_type=_compute_type_for(device),
        )
    return _whisper_model

# ====== OpenAI(vLLM) client (>=1.x) ==========================================
_llm_client: Optional[OpenAI] = None

def get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url=LLM_API_BASE,  # 예: http://localhost:8000/v1
            api_key="EMPTY",
            timeout=30,             # 네트워크/서버 준비 지연 대비
        )
    return _llm_client

# -----------------------------------------------------------------------------
# Request/Response Schemas
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
# Helpers (엔드포인트 내부/외부 공용)
# -----------------------------------------------------------------------------
def stt_transcribe_bytes(audio_bytes: bytes) -> Dict[str, Any]:
    """Bytes → STT → {text, language, segments}"""
    if not audio_bytes:
        raise ValueError("empty audio payload")

    model = get_stt_model()
    segments, info = model.transcribe(BytesIO(audio_bytes), beam_size=1)

    out_segments: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []
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
    """텍스트 → LLM 답변(str)"""
    client = get_llm_client()
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": user_text.strip()}],
        max_tokens=256,
    )
    return (resp.choices[0].message.content or "").strip()

async def tts_synthesize_mp3(text: str, voice: str) -> bytes:
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
        # TTS 단계 에러는 502로 보냄 (외부 서비스/네트워크 성격이라)
        raise HTTPException(status_code=502, detail=f"TTS synth failed: {e}")

# =============================================================================
# Health
# =============================================================================
@app.get("/health")
def health():
    return {"status": "ok", "llm_base": LLM_API_BASE, "model": LLM_MODEL}

# =============================================================================
# STT: 음성 → 텍스트 (JSON 반환)
# =============================================================================
@app.post("/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """
    업로드된 음성 파일을 STT 처리 후 JSON으로 반환:
    {
      "text": "...",
      "language": "ko",
      "segments": [
        {"text": "...", "start": 0.00, "end": 1.23}, ...
      ]
    }
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        audio = await file.read()
        result = stt_transcribe_bytes(audio)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {e}")

# =============================================================================
# Chat: 텍스트 → LLM 응답 (JSON 반환)
# =============================================================================
@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")
    try:
        answer = chat_answer(text)
        return {"answer": answer}
    except Exception as e:
        # vLLM 미기동/포트 불일치/일시적 연결 끊김 등
        raise HTTPException(status_code=502, detail=f"LLM connection/request failed: {e}")

# =============================================================================
# TTS: 텍스트 → 음성(MP3 base64) (JSON 반환)
# =============================================================================
@app.post("/tts")
async def tts_endpoint(req: TTSRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    voice = (req.voice or TTS_VOICE).strip()

    try:
        mp3_bytes = await tts_synthesize_mp3(text, voice)
        audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")
        return {"audio_b64": audio_b64, "mime": "audio/mpeg"}

    except HTTPException as e:
        # ← 추가: 이미 의미 있는 코드(502 등)면 그대로 내보냄
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")


# =============================================================================
# Voice Chat: 음성 → (STT) → (LLM) → (TTS) → JSON
# =============================================================================
@app.post("/voice-chat", response_model=VoiceChatResponse)
async def voice_chat(file: UploadFile = File(...)):
    # --- 1) STT ---
    try:
        audio = await file.read()
        stt = stt_transcribe_bytes(audio)
        user_text = (stt.get("text") or "").strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="STT produced empty text")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"voice-chat STT error: {e}")

    # --- 2) LLM ---
    try:
        assistant_text = chat_answer(user_text) or "죄송해요. 지금은 대답을 생성할 수 없어요."
    except HTTPException as e:
        raise e
    except Exception as e:
        # vLLM 미기동/포트/시간초과 등은 502로
        raise HTTPException(status_code=502, detail=f"voice-chat LLM error: {e}")

    # --- 3) TTS ---
    try:
        mp3_bytes = await tts_synthesize_mp3(assistant_text, TTS_VOICE)
        audio_b64 = base64.b64encode(mp3_bytes).decode("utf-8")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"voice-chat TTS error: {e}")

    return VoiceChatResponse(
        user_text=user_text,
        assistant_text=assistant_text,
        audio_b64=audio_b64,
        audio_mime="audio/mpeg",
    )

