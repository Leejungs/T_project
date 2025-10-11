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
    """서버 상태 확인용 엔드포인트"""
    # 키가 없더라도 STT/TTS는 동작하므로 단순 상태만 표기
    return {"status": "ok", "llm": "gpt-4o-mini-via-llm_runtime"}

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
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException

from rag.config import DOC_PATH
from rag.auto_index import ensure_index_ready
from rag.retriever import retrieve
from rag.qa import answer as rag_answer

# 인덱싱 강제 실행(수동): path 없으면 기본 DOC_PATH 사용
class IngestReq(BaseModel):
    path: Optional[str] = None

@app.post("/rag/ingest")
def rag_ingest(req: Optional[IngestReq] = None):
    """학칙 PDF 인덱싱(강제). path가 없으면 기본 DOC_PATH."""
    try:
        use_path = (req.path if req else None) or DOC_PATH
        res = ensure_index_ready(path=use_path, force=True)
        return {"status": "ok", **res}
    except FileNotFoundError as e:
        raise HTTPException(500, f"PDF not found: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")

# 질의 모델: path 제공 시 해당 PDF로 자동 인덱싱 보장 후 질의
class RagChatReq(BaseModel):
    query: str
    top_k: int = 6
    path: Optional[str] = None  # 없으면 기본 DOC_PATH

@app.post("/rag/chat")
def rag_chat(req: RagChatReq):
    """질문 → (자동 인덱싱) → 검색 → 답변(+출처)"""
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(400, "Empty query")
    try:
        # ✅ 핵심: 인덱스가 없거나 PDF가 바뀌었으면 자동 인덱싱
        auto = ensure_index_ready(path=req.path or DOC_PATH, force=False)

        chunks = retrieve(q, k=req.top_k)
        qa = rag_answer(q, chunks)
        return {"answer": qa["answer"], "sources": qa["sources"], "auto_index": auto}
    except FileNotFoundError as e:
        raise HTTPException(500, f"PDF not found: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"RAG failed: {e}")

# 미리보기: 선택된 청크/점수 확인 (+자동 인덱싱)
@app.post("/rag/preview")
def rag_preview(req: RagChatReq):
    try:
        auto = ensure_index_ready(path=req.path or DOC_PATH, force=False)
        chunks = retrieve(req.query, k=req.top_k)
        return {
            "auto_index": auto,
            "chunks": [
                {
                    "page": c["meta"]["page"],
                    "score": round((c.get("score") or 0.0), 3),
                    "text": c["text"][:500],
                }
                for c in chunks
            ],
        }
    except FileNotFoundError as e:
        raise HTTPException(500, f"PDF not found: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")

# 디버그: RAG 상태 확인
@app.get("/rag/info")
def rag_info():
    from rag.config import DOC_PATH, CHROMA_DIR
    import os
    return {
        "doc_path": DOC_PATH,
        "exists": os.path.exists(DOC_PATH),
        "chroma_dir": CHROMA_DIR,
    }
