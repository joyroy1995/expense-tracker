from groq import Groq


def transcribe_audio(audio_bytes, mime_type="audio/webm"):
    client = Groq()
    ext = mime_type.split("/")[-1] if "/" in mime_type else "webm"
    filename = f"audio.{ext}"
    transcript = client.audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=(filename, audio_bytes),
        response_format="text",
        language="en",
    )
    return transcript.strip()
