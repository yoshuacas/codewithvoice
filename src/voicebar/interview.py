from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from .engine import asr
from .recorder import Recorder

# Where finished and in-progress interviews land. Plain .txt transcripts with
# the raw .wav kept alongside, so the audio survives even if transcription
# fails or the app is killed mid-session.
OUTPUT_DIR = Path.home() / "Documents" / "codewithvoice-interviews"

# Long-form capture is transcribed in windows rather than one final pass:
# memory stays flat regardless of interview length, and a crash leaves both
# the .wav and the transcript-so-far on disk. ~30 s suits whisper's training
# window; the worker wakes more often to keep the .wav current.
CHUNK_SECONDS = 30.0
DRAIN_INTERVAL = 5.0


def _fmt_clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


class InterviewSession:
    """Hands-free, long-form recording to a saved transcript.

    Unlike the PTT flow this types nothing into other apps: it records until
    explicitly stopped, transcribes in CHUNK_SECONDS windows, and streams the
    transcript (.txt) and raw audio (.wav) to OUTPUT_DIR as it goes. The
    shared engine lock is held only for the duration of each whisper call, so
    PTT and speak still work between chunks (though not concurrently).
    """

    def __init__(
        self,
        engine_lock: threading.Lock,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self._engine_lock = engine_lock
        self._on_progress = on_progress
        self._recorder = Recorder()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._buffer: list[np.ndarray] = []
        self._buffered_samples = 0
        self._wav: sf.SoundFile | None = None
        self._chunk_index = 0
        self._words = 0
        self._elapsed = 0.0
        self.txt_path: Path | None = None
        self.wav_path: Path | None = None

    @property
    def is_active(self) -> bool:
        return self._thread is not None

    # ---------- lifecycle ----------

    def start(self) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.txt_path = OUTPUT_DIR / f"interview_{stamp}.txt"
        self.wav_path = OUTPUT_DIR / f"interview_{stamp}.wav"

        self._wav = sf.SoundFile(
            str(self.wav_path),
            mode="w",
            samplerate=self._recorder.samplerate,
            channels=1,
            subtype="PCM_16",
        )
        header = f"# Interview transcript — started {datetime.now():%Y-%m-%d %H:%M}\n\n"
        self.txt_path.write_text(header)

        self._recorder.start()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self.txt_path

    def stop(self) -> Path | None:
        """Stop recording, flush the final partial chunk, return the transcript path."""
        if self._thread is None:
            return self.txt_path
        self._stop_evt.set()
        self._thread.join()
        self._thread = None

        self._recorder.stop_internal()
        self._drain_to_wav()  # capture anything between the last tick and stop
        self._flush_buffer(final=True)
        if self._wav is not None:
            self._wav.close()
            self._wav = None
        self._report()
        return self.txt_path

    # ---------- worker ----------

    def _loop(self) -> None:
        while not self._stop_evt.wait(DRAIN_INTERVAL):
            self._drain_to_wav()
            if self._buffered_samples >= int(CHUNK_SECONDS * asr.TARGET_SR):
                self._flush_buffer(final=False)
            self._report()

    def _drain_to_wav(self) -> None:
        """Persist newly captured audio to the .wav and queue it for transcription."""
        new = self._recorder.drain_new()
        if not len(new):
            return
        if self._wav is not None:
            self._wav.write(new)
            self._wav.flush()
        self._buffer.append(new)
        self._buffered_samples += len(new)
        self._elapsed += len(new) / asr.TARGET_SR

    def _flush_buffer(self, final: bool) -> None:
        if not self._buffered_samples:
            return
        samples = np.concatenate(self._buffer)
        self._buffer = []
        self._buffered_samples = 0

        # Skip a near-silent window: whisper invents text over silence, and an
        # interview has long quiet stretches while the candidate thinks.
        if float(np.sqrt(np.mean(samples**2))) < 0.005:
            return

        chunk_start = self._elapsed - len(samples) / asr.TARGET_SR
        try:
            with self._engine_lock:
                if self._stop_evt.is_set() and not final:
                    # Re-queue: a stop landed mid-window; the final flush handles it.
                    self._buffer.insert(0, samples)
                    self._buffered_samples += len(samples)
                    return
                text = asr.transcribe_samples(samples).strip()
        except Exception as e:  # noqa: BLE001
            print(f"[interview] chunk transcription failed: {e}", flush=True)
            return
        if not text:
            return
        self._append_text(chunk_start, text)

    def _append_text(self, chunk_start: float, text: str) -> None:
        self._chunk_index += 1
        self._words += len(text.split())
        line = f"[{_fmt_clock(chunk_start)}] {text}\n"
        if self.txt_path is not None:
            with self.txt_path.open("a") as f:
                f.write(line)

    def _report(self) -> None:
        if self._on_progress is None:
            return
        self._on_progress(f"{_fmt_clock(self._elapsed)} · {self._words} words")
