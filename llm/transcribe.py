from groq import Groq
import sys


def transcribe_audio(audio_bytes, mime_type="audio/webm"):
    try:
        client = Groq(timeout=15.0)
        ext = mime_type.split("/")[-1] if "/" in mime_type else "webm"
        filename = f"audio.{ext}"
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=(filename, audio_bytes),
            response_format="text",
            language="en",
        )
        return transcript.strip()
    except Exception as e:
        print(f"[ERROR] transcribe_audio failed: {type(e).__name__}: {e}", file=sys.stderr)
        raise
