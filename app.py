import io
import os
import edge_tts
from gtts import gTTS
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICES = {
    "en_male": ("en-IN-PrabhatNeural", "en"),
    "en_female": ("en-IN-NeerjaNeural", "en"),
    "hi_male": ("hi-IN-MadhurNeural", "hi"),
    "hi_female": ("hi-IN-SwaraNeural", "hi"),
    "mr_male": ("mr-IN-ManoharNeural", "mr"),
    "mr_female": ("mr-IN-AarohiNeural", "mr"),
}


class TTSBody(BaseModel):
    text: str
    profile_id: str = "en_male"
    rate: float = 0.96
    pitch: float = 1.00
    humanise: bool = True


@app.get("/")
async def home():
    return FileResponse("index.html")


@app.post("/api/tts")
async def make_audio(data: TTSBody):
    text = " ".join(data.text.strip().split())
    if not text:
        return JSONResponse(status_code=400, content={"error": "Enter text first."})

    if data.humanise:
        text = text.replace(",", ", ").replace("...", " ... ").replace("।", "। ")

    voice_name, lang_code = VOICES.get(data.profile_id, ("en-IN-PrabhatNeural", "en"))
    rate_str = f"{int(round((data.rate - 1.0) * 100)):+d}%"
    pitch_str = f"{int(round((data.pitch - 1.0) * 40)):+d}Hz"
    buf = io.BytesIO()

    try:
        comm = edge_tts.Communicate(text=text, voice=voice_name, rate=rate_str, pitch=pitch_str)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        if buf.tell() == 0:
            raise RuntimeError("Empty stream")
    except Exception:
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang_code, tld="co.in", slow=(data.rate < 0.85))
        tts.write_to_fp(buf)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="{data.profile_id}.mp3"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
