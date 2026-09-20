import json
import os
import uuid
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .net import default_ssl_context

DEFAULT_BASE_URL = "https://api.slng.ai/v1"
DEFAULT_MODEL = "slng/deepgram/nova:3-en"
REQUEST_TIMEOUT = 45.0
MAX_AUDIO_BYTES = 12 * 1024 * 1024
EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}


class SpeechConfigurationError(RuntimeError):
    pass


class SpeechAPIError(RuntimeError):
    pass


def api_key() -> str:
    for name in ("SLNG_API", "SLNG_API_KEY", "VOICEAI_API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise SpeechConfigurationError("Voice input is not configured on this server.")


def transcribe(audio: bytes, content_type: Optional[str]) -> str:
    if not audio:
        raise SpeechAPIError("No audio was recorded.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise SpeechAPIError("That recording is too long.")

    base_url = os.getenv("SLNG_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("SLNG_STT_MODEL", DEFAULT_MODEL)
    mime = (content_type or "audio/webm").split(";")[0].strip().lower()
    body, boundary = _multipart(audio, mime)
    request = Request(
        f"{base_url}/stt/{model}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(
            request, timeout=REQUEST_TIMEOUT, context=default_ssl_context()
        ) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SpeechAPIError(
            f"The speech service returned HTTP {error.code}: {detail[:300]}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise SpeechAPIError(f"Could not reach the speech service: {error}") from error
    except ValueError as error:
        raise SpeechAPIError("The speech service returned invalid JSON.") from error

    transcript = _extract_transcript(payload)
    if not transcript:
        raise SpeechAPIError("Nothing was recognised in that recording.")
    return transcript


def _extract_transcript(payload: object) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("transcript", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("results", "result", "data", "output"):
        nested = payload.get(key)
        found = _extract_transcript(nested)
        if found:
            return found
    channels = payload.get("channels")
    if isinstance(channels, list):
        for channel in channels:
            found = _extract_transcript(channel)
            if found:
                return found
    alternatives = payload.get("alternatives")
    if isinstance(alternatives, list):
        for alternative in alternatives:
            found = _extract_transcript(alternative)
            if found:
                return found
    return ""


def _multipart(audio: bytes, mime: str) -> tuple:
    boundary = uuid.uuid4().hex
    extension = EXTENSIONS.get(mime, "webm")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="audio"; filename="clip.{extension}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + audio + tail, boundary
