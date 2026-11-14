import io
import os
import traceback
import edge_tts
from gtts import gTTS
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Indic Humanised AI Voice Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICE_MAP = {
    "en_male": ("en-IN-PrabhatNeural", "en", "co.in"),
    "en_female": ("en-IN-NeerjaNeural", "en", "co.in"),
    "hi_male": ("hi-IN-MadhurNeural", "hi", "co.in"),
    "hi_female": ("hi-IN-SwaraNeural", "hi", "co.in"),
    "mr_male": ("mr-IN-ManoharNeural", "mr", "co.in"),
    "mr_female": ("mr-IN-AarohiNeural", "mr", "co.in"),
}


class TTSRequest(BaseModel):
    text: str
    profile_id: str = "en_male"
    rate: float = 0.96
    pitch: float = 1.00
    humanise: bool = True


def shape_human_text(text: str, humanise: bool) -> str:
    cleaned = " ".join(text.strip().split())
    if not humanise:
        return cleaned
    return cleaned.replace(",", ", ").replace("...", " ... ").replace("।", "। ")


def format_prosody(rate: float, pitch: float) -> tuple[str, str]:
    rate_pct = int(round((rate - 1.0) * 100))
    pitch_hz = int(round((pitch - 1.0) * 40))
    return f"{rate_pct:+d}%", f"{pitch_hz:+d}Hz"


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/tts")
async def generate_tts(payload: TTSRequest):
    if not payload.text or not payload.text.strip():
        return JSONResponse(status_code=400, content={"error": "Please enter text first."})

    voice_name, gtts_lang, gtts_tld = VOICE_MAP.get(
        payload.profile_id, ("en-IN-PrabhatNeural", "en", "co.in")
    )
    rate_str, pitch_str = format_prosody(payload.rate, payload.pitch)
    final_text = shape_human_text(payload.text, payload.humanise)
    buffer = io.BytesIO()

    try:
        communicate = edge_tts.Communicate(
            text=final_text,
            voice=voice_name,
            rate=rate_str,
            pitch=pitch_str,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        if buffer.tell() == 0:
            raise RuntimeError("Empty audio stream from edge-tts")
    except Exception as edge_err:
        print("Primary edge-tts failed, switching to gTTS:", repr(edge_err))
        traceback.print_exc()
        try:
            buffer = io.BytesIO()
            tts = gTTS(text=final_text, lang=gtts_lang, tld=gtts_tld, slow=(payload.rate < 0.85))
            tts.write_to_fp(buffer)
        except Exception as fallback_err:
            return JSONResponse(
                status_code=500,
                content={"error": f"TTS failed: {str(fallback_err)}"},
            )

    buffer.seek(0)
    filename = f"{payload.profile_id}-human-voice.mp3"
    return StreamingResponse(
        buffer,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>Indic Humanised AI Voice Studio</title>
  <style>
    :root {
      --bg: #090d16; --surface: #131c2e; --surface-alt: #1e293b;
      --border: #2a3954; --primary: #f97316; --primary-hover: #ea580c;
      --accent: #2563eb; --text: #f8fafc; --muted: #94a3b8; --success: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    html, body { height: 100%; height: 100dvh; width: 100%; overflow: hidden; background: var(--bg); color: var(--text); }
    body { display: flex; justify-content: center; align-items: stretch; }
    .app-shell { width: 100%; max-width: 760px; height: 100%; height: 100dvh; display: flex; flex-direction: column; background: var(--surface); padding: 10px 12px; gap: 8px; overflow: hidden; }
    @media (min-width: 768px) {
      body { padding: 16px; align-items: center; }
      .app-shell { height: min(720px, 94dvh); border: 1px solid var(--border); border-radius: 16px; padding: 16px 20px; gap: 10px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }
    }
    .top-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-shrink: 0; }
    .top-bar h1 { font-size: clamp(0.95rem, 3.8vw, 1.2rem); font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .badge { padding: 3px 9px; border-radius: 999px; font-size: 0.68rem; font-weight: 600; background: rgba(16,185,129,0.18); color: var(--success); white-space: nowrap; flex-shrink: 0; }
    .tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; flex-shrink: 0; }
    .tab-btn { background: var(--bg); color: var(--muted); border: 1px solid var(--border); padding: 6px 4px; border-radius: 8px; cursor: pointer; text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 42px; }
    .tab-btn .t-title { font-size: clamp(0.7rem, 2.6vw, 0.82rem); font-weight: 600; line-height: 1.15; }
    .tab-btn .t-sub { font-size: 0.62rem; opacity: 0.75; margin-top: 2px; }
    .tab-btn.active { background: rgba(249,115,22,0.16); border-color: var(--primary); color: var(--text); }
    .editor-wrap { flex: 1; min-height: 70px; display: flex; }
    textarea { width: 100%; height: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; font-size: clamp(0.92rem, 3.4vw, 1rem); line-height: 1.45; resize: none; outline: none; }
    textarea:focus { border-color: var(--primary); }
    .sliders-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 6px; align-items: stretch; flex-shrink: 0; }
    .mini-box { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 5px 8px; display: flex; flex-direction: column; justify-content: center; }
    .mini-box .lbl { display: flex; justify-content: space-between; font-size: 0.66rem; color: var(--muted); margin-bottom: 2px; }
    .mini-box .lbl strong { color: var(--text); }
    input[type="range"] { width: 100%; height: 16px; accent-color: var(--primary); cursor: pointer; }
    .human-chip { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 0 9px; display: flex; align-items: center; gap: 5px; font-size: 0.72rem; font-weight: 600; cursor: pointer; white-space: nowrap; user-select: none; }
    .human-chip input { accent-color: var(--primary); width: 14px; height: 14px; }
    .actions { display: grid; grid-template-columns: 1.8fr 0.9fr 1.3fr; gap: 6px; flex-shrink: 0; }
    button.btn { padding: 10px 8px; border-radius: 9px; border: none; font-size: clamp(0.8rem, 3vw, 0.9rem); font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; white-space: nowrap; }
    button.btn:disabled { opacity: 0.55; cursor: not-allowed; }
    .btn-play { background: var(--primary); color: #fff; }
    .btn-stop { background: var(--surface-alt); color: var(--text); border: 1px solid var(--border) !important; }
    .btn-dl { background: var(--accent); color: #fff; }
    .status-line { font-size: 0.7rem; color: var(--muted); display: flex; justify-content: space-between; align-items: center; gap: 6px; flex-shrink: 0; }
    .status-line span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  </style>
</head>
<body>
  <div class="app-shell">
    <header class="top-bar">
      <h1>Indic Humanised AI Voice</h1>
      <span class="badge" id="voiceTag">Prabhat Neural</span>
    </header>
    <nav class="tabs" id="tabContainer"></nav>
    <main class="editor-wrap">
      <textarea id="scriptInput" placeholder="Type or paste English, Hindi, or Marathi text here..."></textarea>
    </main>
    <section class="sliders-row">
      <div class="mini-box">
        <div class="lbl"><span>Speed</span><strong id="rateVal">0.96x</strong></div>
        <input type="range" id="rateSlider" min="0.65" max="1.35" step="0.02" value="0.96" />
      </div>
      <div class="mini-box">
        <div class="lbl"><span>Pitch</span><strong id="pitchVal">1.00</strong></div>
        <input type="range" id="pitchSlider" min="0.75" max="1.25" step="0.02" value="1.00" />
      </div>
      <label class="human-chip">
        <input type="checkbox" id="humaniseToggle" checked />
        <span>Humanise</span>
      </label>
    </section>
    <section class="actions">
      <button class="btn btn-play" id="speakBtn" type="button">▶ Speak</button>
      <button class="btn btn-stop" id="stopBtn" type="button">⏹ Stop</button>
      <button class="btn btn-dl" id="downloadBtn" type="button">⬇ MP3</button>
    </section>
    <footer class="status-line">
      <span id="statusText">Ready • Tap Speak or Download MP3</span>
      <span id="langTag">en-IN Male</span>
    </footer>
  </div>

  <script>
    const PROFILES = [
      { id: "en_male", shortTitle: "1. Eng Male", sub: "Indian English", neural: "Prabhat Neural", tag: "en-IN Male", rate: 0.96, pitch: 0.98, sample: "Namaste! Welcome to our platform. Let me walk you through the details in a calm, natural, and conversational tone." },
      { id: "en_female", shortTitle: "2. Eng Female", sub: "Indian English", neural: "Neerja Neural", tag: "en-IN Female", rate: 0.99, pitch: 1.02, sample: "Hi there! Everything is set up and ready for you. Just type what you would like me to say, and listen to the natural flow." },
      { id: "hi_male", shortTitle: "3. Hindi Male", sub: "हिन्दी पुरुष", neural: "Madhur Neural", tag: "hi-IN Male", rate: 0.95, pitch: 0.98, sample: "नमस्ते! आज मैं आपकी क्या सहायता कर सकता हूँ? आप यहाँ कोई भी वाक्य लिखकर बिल्कुल स्वाभाविक और स्पष्ट आवाज़ में सुन सकते हैं।" },
      { id: "hi_female", shortTitle: "4. Hindi Female", sub: "हिन्दी महिला", neural: "Swara Neural", tag: "hi-IN Female", rate: 0.98, pitch: 1.02, sample: "नमस्कार! हमारी इस सेवा में आपका स्वागत है। यह आवाज़ बिल्कुल इंसानों जैसी सहज और स्वाभाविक सुनाई देती है।" },
      { id: "mr_male", shortTitle: "5. Marathi Male", sub: "मराठी पुरुष", neural: "Manohar Neural", tag: "mr-IN Male", rate: 0.95, pitch: 0.98, sample: "नमस्कार! तुमचं मनापासून स्वागत आहे. तुम्हाला हवा असलेला मजकूर येथे टाईप करा आणि नैसर्गिक आवाजात ऐका." },
      { id: "mr_female", shortTitle: "6. Marathi Female", sub: "मराठी महिला", neural: "Aarohi Neural", tag: "mr-IN Female", rate: 0.98, pitch: 1.02, sample: "नमस्कार! मी तुमची कशी मदत करू शकते? कृपया तुमचा संदेश खालील बॉक्समध्ये लिहा आणि प्ले बटण दाबा." }
    ];
    let current = PROFILES[0], audioObj = null, cachedUrl = null;
    const tabContainer = document.getElementById("tabContainer");
    const scriptInput = document.getElementById("scriptInput");
    const rateSlider = document.getElementById("rateSlider");
    const pitchSlider = document.getElementById("pitchSlider");
    const rateVal = document.getElementById("rateVal");
    const pitchVal = document.getElementById("pitchVal");
    const humaniseToggle = document.getElementById("humaniseToggle");
    const speakBtn = document.getElementById("speakBtn");
    const stopBtn = document.getElementById("stopBtn");
    const downloadBtn = document.getElementById("downloadBtn");
    const statusText = document.getElementById("statusText");
    const voiceTag = document.getElementById("voiceTag");
    const langTag = document.getElementById("langTag");

    function renderTabs() {
      tabContainer.innerHTML = "";
      PROFILES.forEach((p) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tab-btn" + (p.id === current.id ? " active" : "");
        btn.innerHTML = `<span class="t-title">${p.shortTitle}</span><span class="t-sub">${p.sub}</span>`;
        btn.onclick = () => selectProfile(p);
        tabContainer.appendChild(btn);
      });
    }

    function stopPlayback() {
      if (audioObj) { audioObj.pause(); audioObj.currentTime = 0; audioObj = null; }
      speakBtn.textContent = "▶ Speak";
    }

    function selectProfile(p) {
      stopPlayback();
      current = p;
      scriptInput.value = p.sample;
      rateSlider.value = p.rate;
      pitchSlider.value = p.pitch;
      rateVal.textContent = p.rate.toFixed(2) + "x";
      pitchVal.textContent = p.pitch.toFixed(2);
      voiceTag.textContent = p.neural;
      langTag.textContent = p.tag;
      renderTabs();
      statusText.textContent = `Selected: ${p.shortTitle} (${p.neural})`;
    }

    async function requestMp3() {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: scriptInput.value.trim(),
          profile_id: current.id,
          rate: parseFloat(rateSlider.value),
          pitch: parseFloat(pitchSlider.value),
          humanise: humaniseToggle.checked
        })
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `Server error ${res.status}`);
      }
      return await res.blob();
    }

    speakBtn.addEventListener("click", async () => {
      if (audioObj) { stopPlayback(); statusText.textContent = "Stopped."; return; }
      const text = scriptInput.value.trim();
      if (!text) { statusText.textContent = "Enter some text first."; return; }
      try {
        speakBtn.disabled = true; speakBtn.textContent = "⏳ Loading...";
        statusText.textContent = `Generating ${current.neural}...`;
        const blob = await requestMp3();
        if (cachedUrl) URL.revokeObjectURL(cachedUrl);
        cachedUrl = URL.createObjectURL(blob);
        audioObj = new Audio(cachedUrl);
        audioObj.onended = () => { audioObj = null; speakBtn.textContent = "▶ Speak"; statusText.textContent = "Finished speaking."; };
        await audioObj.play();
        speakBtn.disabled = false; speakBtn.textContent = "⏸ Stop";
        statusText.textContent = `Playing ${current.neural}...`;
      } catch (err) {
        speakBtn.disabled = false; speakBtn.textContent = "▶ Speak";
        statusText.textContent = err.message;
      }
    });

    stopBtn.addEventListener("click", () => { stopPlayback(); statusText.textContent = "Stopped."; });

    downloadBtn.addEventListener("click", async () => {
      const text = scriptInput.value.trim();
      if (!text) { statusText.textContent = "Enter text before downloading MP3."; return; }
      try {
        downloadBtn.disabled = true; downloadBtn.textContent = "⏳ MP3...";
        statusText.textContent = "Building MP3 file...";
        const blob = await requestMp3();
        if (cachedUrl) URL.revokeObjectURL(cachedUrl);
        cachedUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = cachedUrl;
        a.download = `${current.id}-human-voice.mp3`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        statusText.textContent = `Downloaded ${current.id}-human-voice.mp3`;
      } catch (err) {
        statusText.textContent = err.message;
      } finally {
        downloadBtn.disabled = false; downloadBtn.textContent = "⬇ MP3";
      }
    });

    rateSlider.addEventListener("input", () => { rateVal.textContent = parseFloat(rateSlider.value).toFixed(2) + "x"; });
    pitchSlider.addEventListener("input", () => { pitchVal.textContent = parseFloat(pitchSlider.value).toFixed(2); });
    selectProfile(PROFILES[0]);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return HTML_UI


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    









    









    
