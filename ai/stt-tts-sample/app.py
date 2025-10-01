# FastAPI 서버 (STT, TTS, voice-chat)

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from pydub import AudioSegment
from io import BytesIO
import asyncio
import edge_tts
import os
import httpx

from faster_whisper import WhisperModel
from date_utils import normalize_relative_dates_ko
from guard import violates_policy

# ===== Config =====
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")  # small/medium
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")  # cpu/cuda/auto
TTS_VOICE = os.getenv("TTS_VOICE", "ko-KR-SunHiNeural")  # Edge TTS 한국어 예시

app = FastAPI(title="STT/TTS Sample")

# 템플릿
templates = Jinja2Templates(directory="templates")

# ===== STT 엔진 준비 (lazy load) =====
_whisper_model = None
def get_stt_model():
    global _whisper_model
    if _whisper_model is None:
        # compute_type="float16" (GPU) / "int8" (CPU 경량)
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE, 
            device=WHISPER_DEVICE, 
            compute_type="int8")
    return _whisper_model

# ===== 라우팅 =====
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    # 1) 업로드 파일을 wav으로 변환(Whisper는 wav 선호)
    audio_bytes = await file.read()
    audio = AudioSegment.from_file(BytesIO(audio_bytes))
    wav_buf = BytesIO()
    audio.export(wav_buf, format="wav")
    wav_buf.seek(0)

    # 2) STT 실행
    model = get_stt_model()
    segments, info = model.transcribe(wav_buf, language="ko", vad_filter=True)

    text = "".join([seg.text for seg in segments]).strip()

    # 3) 간단 후처리
    text = normalize_relative_dates_ko(text)

    return JSONResponse({"text": text})

@app.post("/tts")
async def tts(text: str = Form(...)):
    # 가드레일 (욕설/PII 등)
    if violates_policy(text):
        text = "죄송해요. 요청하신 내용은 음성으로 안내해 드릴 수 없어요."

    # Edge TTS로 mp3 생성
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate="+0%")  # 속도/볼륨 튜닝 가능
    mp3_buf = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_buf.write(chunk["data"])
    mp3_buf.seek(0)

    return StreamingResponse(mp3_buf, media_type="audio/mpeg")

@app.post("/voice-chat")
async def voice_chat(file: UploadFile = File(...)):
    # 1) STT
    stt_resp = await stt(file)
    user_text = (await stt_resp.body())  # bytes
    import json
    user_text = json.loads(user_text.decode("utf-8"))["text"]

    # 2) 가드레일(입력)
    if violates_policy(user_text):
        user_text = "죄송해요. 부적절한 요청입니다. 다른 내용으로 도와드릴게요."

    # 3) LLM 호출 (OpenAI ChatCompletions 호환)
    prompt_msgs = [
        {"role": "system", "content": "너는 동양미래대학교 학사정보 도우미야. 짧고 명확하게 한국어로 답해."},
        {"role": "user", "content": user_text}
    ]
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{LLM_API_BASE}/chat/completions",
            json={"model": LLM_MODEL, "messages": prompt_msgs, "max_tokens": 200}
        )
        r.raise_for_status()
        out = r.json()
        answer = out["choices"][0]["message"]["content"]

    # 4) TTS (짧은 답변 우선: 1~2문장 잘라내기)
    short_answer = answer.split("다.")  # 아주 러프하게 한글 문장 분리 예시
    short_answer = "다.".join(short_answer[:2]).strip() + ("다." if not answer.strip().endswith("다.") else "")

    # 5) 음성 생성 후 반환
    communicate = edge_tts.Communicate(short_answer, TTS_VOICE)
    mp3_buf = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_buf.write(chunk["data"])
    mp3_buf.seek(0)

    return StreamingResponse(mp3_buf, media_type="audio/mpeg")
