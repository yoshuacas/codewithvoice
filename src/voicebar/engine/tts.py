from __future__ import annotations

import io

import numpy as np
import soundfile as sf

TTS_SR = 24000
MODEL_REPO = "hexgrad/Kokoro-82M"

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline

        _pipeline = KPipeline(lang_code="a", repo_id=MODEL_REPO)
    return _pipeline


def synthesize(text: str, voice: str = "af_heart") -> tuple[np.ndarray, int]:
    pipe = _get_pipeline()
    chunks = []
    for _, _, audio in pipe(text, voice=voice):
        if audio is None:
            continue
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        return np.zeros(1, dtype=np.float32), TTS_SR
    return np.concatenate(chunks), TTS_SR


def to_wav_bytes(samples: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def warmup(voice: str = "af_heart") -> None:
    synthesize("ok", voice=voice)
