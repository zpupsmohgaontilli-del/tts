import asyncio
import os
import subprocess
import tempfile
import edge_tts
import gradio as gr
from mutagen.mp3 import MP3

VOICE_PROFILES = {
    "en_male": {
        "label": "1. Indian English Male",
        "voice": "en-IN-PrabhatNeural",
        "default_text": "Namaste! Welcome to our platform. Let me walk you through the details in a clear and natural tone.",
    },
    "en_female": {
        "label": "2. Indian English Female",
        "voice": "en-IN-NeerjaNeural",
        "default_text": "Hi there! Everything is set up and ready for you. Just type what you'd like me to say and hit generate.",
    },
    "hi_male": {
        "label": "3. Indian Hindi Male",
        "voice": "hi-IN-MadhurNeural",
        "default_text": "नमस्ते! आज मैं आपकी क्या सहायता कर सकता हूँ? आप यहाँ कोई भी वाक्य लिखकर स्वाभाविक आवाज़ में सुन सकते हैं।",
    },
    "hi_female": {
        "label": "4. Indian Hindi Female",
        "voice": "hi-IN-SwaraNeural",
        "default_text": "नमस्कार! हमारी इस सेवा में आपका स्वागत है। यह आवाज़ बिल्कुल स्वाभाविक और स्पष्ट सुनाई देती है।",
    },
    "mr_male": {
        "label": "5. Indian Marathi Male",
        "voice": "mr-IN-ManoharNeural",
        "default_text": "नमस्कार! तुमचं स्वागत आहे. तुम्हाला हवा असलेला मजकूर येथे टाईप करा आणि नैसर्गिक आवाजात ऐका.",
    },
    "mr_female": {
        "label": "6. Indian Marathi Female",
        "voice": "mr-IN-AarohiNeural",
        "default_text": "नमस्कार! मी तुमची कशी मदत करू शकते? कृपया तुमचा संदेश खालील बॉक्समध्ये लिहा.",
    },
}


def get_audio_duration(file_path: str) -> float:
    return float(MP3(file_path).info.length)


async def _render_edge_tts(text: str, voice: str, rate_str: str, pitch_str: str, out_path: str):
    communicate = edge_tts.Communicate(
        text=text.strip(),
        voice=voice,
        rate=rate_str,
        pitch=pitch_str,
    )
    await communicate.save(out_path)


def build_atempo_filter(tempo: float) -> str:
    """Safely chains ffmpeg atempo filters for any time ratio."""
    filters = []
    remaining = tempo
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)


def fit_mp3_to_custom_time(input_mp3: str, desired_seconds: float, output_mp3: str):
    """Fits speech to any user-defined duration without changing vocal pitch."""
    current_dur = get_audio_duration(input_mp3)
    if current_dur <= 0.05:
        raise gr.Error("Audio generation failed. Please check your text.")

    tempo = current_dur / desired_seconds
    atempo_chain = build_atempo_filter(tempo)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_mp3,
        "-filter:a", atempo_chain,
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        output_mp3,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    async def _process_tts(
    text: str,
    voice: str,
    timing_mode: str,
    custom_seconds: float,
    pitch_hz: int,
) -> tuple[str, str]:
    if not text or not text.strip():
        raise gr.Error("Please enter your script first.")

    pitch_str = f"{'+' if pitch_hz >= 0 else ''}{pitch_hz}Hz"
    raw_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    final_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name

    # Pass 1: Measure natural speaking length
    await _render_edge_tts(text, voice, "+0%", pitch_str, raw_tmp)
    natural_dur = get_audio_duration(raw_tmp)

    if timing_mode == "Natural Pace (Auto)" or not custom_seconds or custom_seconds <= 0:
        os.replace(raw_tmp, final_tmp)
        return final_tmp, f"Natural Duration: {natural_dur:.2f}s (Adjust 'Desired Time' above to stretch/compress)"

    # Pass 2: Adjust neural prosody first so breaths/pauses adapt naturally
    ideal_pct = int(round(((natural_dur / custom_seconds) - 1.0) * 100))
    clamped_pct = max(-30, min(45, ideal_pct))
    smart_rate = f"{'+' if clamped_pct >= 0 else ''}{clamped_pct}%"

    await _render_edge_tts(text, voice, smart_rate, pitch_str, raw_tmp)

    # Fine-tune to exact user-entered seconds without pitch shift
    fit_mp3_to_custom_time(raw_tmp, float(custom_seconds), final_tmp)
    final_dur = get_audio_duration(final_tmp)

    if os.path.exists(raw_tmp):
        os.remove(raw_tmp)

    info = f"Natural speech was {natural_dur:.2f}s → Adjusted MP3 to {final_dur:.2f}s (Your target: {custom_seconds:.2f}s)"
    return final_tmp, info


def run_tts(text, voice_id, timing_mode, custom_seconds, pitch_hz):
    return asyncio.run(_process_tts(text, voice_id, timing_mode, custom_seconds, pitch_hz))


def build_voice_tab(profile: dict):
    with gr.Tab(profile["label"]):
        with gr.Row():
            with gr.Column(scale=3):
                text_input = gr.Textbox(
                    label="Script",
                    value=profile["default_text"],
                    lines=5,
                    placeholder="Type or paste your script here...",
                )

                timing_mode = gr.Radio(
                    choices=["Custom Time (Seconds)", "Natural Pace (Auto)"],
                    value="Custom Time (Seconds)",
                    label="Timing Mode",
                )

                with gr.Row():
                    custom_sec_box = gr.Number(
                        value=60,
                        minimum=1,
                        maximum=3600,
                        step=0.5,
                        label="Desired Output Time (Any Seconds — e.g. 15, 32.5, 60, 120)",
                    )
                    pitch_slider = gr.Slider(
                        minimum=-12,
                        maximum=12,
                        value=0,
                        step=1,
                        label="Vocal Pitch (Hz)",
                    )

                # Quick One-Tap Time Presets (still fully editable to any number)
                with gr.Row():
                    btn_15 = gr.Button("15s", size="sm")
                    btn_30 = gr.Button("30s", size="sm")
                    btn_45 = gr.Button("45s", size="sm")
                    btn_60 = gr.Button("60s", size="sm")
                    btn_90 = gr.Button("90s", size="sm")

                btn_15.click(lambda: 15, outputs=custom_sec_box)
                btn_30.click(lambda: 30, outputs=custom_sec_box)
                btn_45.click(lambda: 45, outputs=custom_sec_box)
                btn_60.click(lambda: 60, outputs=custom_sec_box)
                btn_90.click(lambda: 90, outputs=custom_sec_box)

                generate_btn = gr.Button("Generate & Download MP3", variant="primary")

            with gr.Column(scale=2):
                audio_output = gr.Audio(
                    label="Generated MP3 (Tap ⬇ to Download)",
                    type="filepath",
                    format="mp3",
                    autoplay=True,
                )
                status_box = gr.Textbox(
                    label="Duration Report",
                    value="Enter any seconds in 'Desired Output Time' and click Generate.",
                    interactive=False,
                )

        voice_state = gr.State(value=profile["voice"])

        generate_btn.click(
            fn=run_tts,
            inputs=[text_input, voice_state, timing_mode, custom_sec_box, pitch_slider],
            outputs=[audio_output, status_box],
        )


with gr.Blocks(theme=gr.themes.Soft(), title="Indic Custom-Timed AI Voice Studio") as demo:
    gr.Markdown(
        """
        # Indic Humanised AI Voice Studio
        Type **any desired output duration** in seconds (e.g. `12`, `28.5`, `60`, `145`) or tap a quick preset.
        The voice automatically adjusts its pace to match your exact timing while keeping a natural human pitch.
        """
    )

    with gr.Tabs():
        for key in ["en_male", "en_female", "hi_male", "hi_female", "mr_male", "mr_female"]:
            build_voice_tab(VOICE_PROFILES[key])


if __name__ == "__main__":
    demo.launch()
    
