import asyncio
import os
import subprocess
import tempfile
import edge_tts
import gradio as gr
import imageio_ffmpeg
from mutagen.mp3 import MP3

VOICE_PROFILES = {
    "1. Indian English Male": {
        "voice": "en-IN-PrabhatNeural",
        "default_text": "Namaste! Welcome to our channel. Let me walk you through the details in a clear, warm, and conversational tone.",
    },
    "2. Indian English Female": {
        "voice": "en-IN-NeerjaNeural",
        "default_text": "Hi there! Everything is set up and ready for you. Just paste your script, set your desired time, and download your MP3.",
    },
    "3. Indian Hindi Male": {
        "voice": "hi-IN-MadhurNeural",
        "default_text": "नमस्ते! आज मैं आपकी क्या सहायता कर सकता हूँ? आप यहाँ कोई भी स्क्रिप्ट लिखकर स्वाभाविक आवाज़ और सटीक समय में सुन सकते हैं।",
    },
    "4. Indian Hindi Female": {
        "voice": "hi-IN-SwaraNeural",
        "default_text": "नमस्कार! हमारी इस सेवा में आपका स्वागत है। यह आवाज़ बिल्कुल इंसानों जैसी सहज और स्पष्ट सुनाई देती है।",
    },
    "5. Indian Marathi Male": {
        "voice": "mr-IN-ManoharNeural",
        "default_text": "नमस्कार! तुमचं मनापासून स्वागत आहे. तुम्हाला हवा असलेला मजकूर येथे टाईप करा आणि नैसर्गिक आवाजात ऐका.",
    },
    "6. Indian Marathi Female": {
        "voice": "mr-IN-AarohiNeural",
        "default_text": "नमस्कार! मी तुमची कशी मदत करू शकते? कृपया तुमचा संदेश खालील बॉक्समध्ये लिहा आणि ऑडिओ डाउनलोड करा.",
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


def time_fit_mp3(input_mp3: str, target_seconds: float, output_mp3: str):
    current_dur = get_audio_duration(input_mp3)
    if current_dur <= 0.05:
        raise gr.Error("Audio generation failed. Please check your script text.")

    tempo = current_dur / target_seconds
    atempo_chain = build_atempo_filter(tempo)
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    filter_complex = f"{atempo_chain},apad=whole_dur={target_seconds:.3f}"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", input_mp3,
        "-filter:a", filter_complex,
        "-t", f"{target_seconds:.3f}",
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        output_mp3,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def _synthesize_audio(
    text: str,
    profile_label: str,
    use_custom_time: bool,
    target_seconds: float,
    pitch_hz: int,
) -> tuple[str, str]:
    if not text or not text.strip():
        raise gr.Error("Please enter your script first.")

    voice_id = VOICE_PROFILES[profile_label]["voice"]
    pitch_str = f"{'+' if pitch_hz >= 0 else ''}{pitch_hz}Hz"

    raw_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    final_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name

    # Pass 1: Measure natural speaking length
    await _render_edge_tts(text, voice_id, "+0%", pitch_str, raw_tmp)
    natural_dur = get_audio_duration(raw_tmp)

    if not use_custom_time or not target_seconds or target_seconds <= 0:
        os.replace(raw_tmp, final_tmp)
        status = f"Voice: {profile_label} | Mode: Natural Pace | Duration: {natural_dur:.2f}s"
        return final_tmp, status

    # Pass 2: Pre-adjust neural rate so breaths/pauses adapt naturally
    ideal_pct = int(round(((natural_dur / target_seconds) - 1.0) * 100))
    clamped_pct = max(-30, min(45, ideal_pct))
    smart_rate = f"{'+' if clamped_pct >= 0 else ''}{clamped_pct}%"

    await _render_edge_tts(text, voice_id, smart_rate, pitch_str, raw_tmp)
    time_fit_mp3(raw_tmp, float(target_seconds), final_tmp)
    final_dur = get_audio_duration(final_tmp)

    if os.path.exists(raw_tmp):
        os.remove(raw_tmp)

    status = (
        f"Voice: {profile_label} | Natural: {natural_dur:.2f}s → "
        f"Final MP3: {final_dur:.2f}s (Target: {target_seconds:.1f}s)"
    )
    return final_tmp, status


def generate_speech(text, profile_label, use_custom_time, target_seconds, pitch_hz):
    return asyncio.run(
        _synthesize_audio(text, profile_label, use_custom_time, target_seconds, pitch_hz)
    )


with gr.Blocks(title="Indic Humanised AI Voice Studio") as demo:
    gr.Markdown(
        """
        # Indic Humanised AI Voice Studio
        Pick any of the **6 Indian Neural Voice Tabs** or switch to **7. Custom Time MP3** to fit your script into an exact duration (e.g. `60` sec).
        """
    )

    active_profile = gr.State(value="1. Indian English Male")
    tab_objects = []

    with gr.Tabs():
        for label, info in VOICE_PROFILES.items():
            with gr.Tab(label) as tab:
                gr.Markdown(f"**Selected Voice:** `{label}` (`{info['voice']}`)")
                tab_objects.append((label, tab))

        with gr.Tab("7. Custom Time MP3 (Reel Mode)") as custom_time_tab:
            gr.Markdown(
                "**Exact Duration Mode:** Enter your script and set any target seconds (e.g., `60`). "
                "Your script will be converted into an exact **60.00-second MP3**."
            )
            custom_voice_dropdown = gr.Dropdown(
                choices=list(VOICE_PROFILES.keys()),
                value="1. Indian English Male",
                label="Choose Voice for Custom Time MP3",
            )

    with gr.Row():
        with gr.Column(scale=3):
            shared_script = gr.Textbox(
                label="Script / Text",
                value=VOICE_PROFILES["1. Indian English Male"]["default_text"],
                lines=6,
                placeholder="Type or paste your script here...",
            )

            with gr.Row():
                enable_custom_time = gr.Checkbox(
                    value=False,
                    label="Enable Custom Target Time (Exact Seconds MP3)",
                )
                target_seconds_input = gr.Number(
                    value=60,
                    minimum=1,
                    maximum=3600,
                    step=0.5,
                    label="Target Time (Seconds)",
                )
                pitch_slider = gr.Slider(
                    minimum=-12,
                    maximum=12,
                    value=0,
                    step=1,
                    label="Vocal Pitch (Hz)",
                )

            with gr.Row():
                p15 = gr.Button("15s", size="sm")
                p30 = gr.Button("30s", size="sm")
                p45 = gr.Button("45s", size="sm")
                p60 = gr.Button("60s (Reel)", size="sm")
                p90 = gr.Button("90s", size="sm")

            p15.click(lambda: (True, 15), outputs=[enable_custom_time, target_seconds_input])
            p30.click(lambda: (True, 30), outputs=[enable_custom_time, target_seconds_input])
            p45.click(lambda: (True, 45), outputs=[enable_custom_time, target_seconds_input])
            p60.click(lambda: (True, 60), outputs=[enable_custom_time, target_seconds_input])
            p90.click(lambda: (True, 90), outputs=[enable_custom_time, target_seconds_input])

            generate_btn = gr.Button("Generate & Download MP3", variant="primary")

        with gr.Column(scale=2):
            audio_output = gr.Audio(
                label="Output MP3 (Click ⬇ Icon to Save)",
                type="filepath",
                format="mp3",
                autoplay=True,
            )
            status_box = gr.Textbox(
                label="Status & Timing Report",
                value="Ready — Select a voice tab, enter text, and click Generate.",
                interactive=False,
            )

    for lbl, tab_comp in tab_objects:
        tab_comp.select(
            fn=lambda l=lbl: (l, VOICE_PROFILES[l]["default_text"], False, l),
            outputs=[active_profile, shared_script, enable_custom_time, custom_voice_dropdown],
        )

    custom_time_tab.select(
        fn=lambda: True,
        outputs=[enable_custom_time],
    )
    custom_voice_dropdown.change(
        fn=lambda v: v,
        inputs=[custom_voice_dropdown],
        outputs=[active_profile],
    )

    generate_btn.click(
        fn=generate_speech,
        inputs=[
            shared_script,
            active_profile,
            enable_custom_time,
            target_seconds_input,
            pitch_slider,
        ],
        outputs=[audio_output, status_box],
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
