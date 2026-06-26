from __future__ import annotations

import io
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
CHANNELS = 1
# No hard recording cap by default: record until PTT is released. Set a float
# to re-arm an auto-stop timer (sets `clipped`). Each live streaming pass
# re-transcribes the whole buffer, so long clips trade snappier live typing
# for completeness — see streaming.py.
MAX_SECONDS: float | None = None


class Recorder:
    def __init__(
        self,
        samplerate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        max_seconds: float | None = MAX_SECONDS,
    ) -> None:
        # `samplerate` is the *output* rate every consumer sees. The mic may be
        # opened at a different native rate (see start()); reads downsample to
        # this on the way out.
        self.samplerate = samplerate
        self.channels = channels
        self.max_seconds = max_seconds
        self._capture_rate = samplerate
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self.clipped = False
        self.error: str | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.error = str(status)
        with self._lock:
            self._frames.append(indata.copy())

    def _open_stream(self, samplerate: int) -> sd.InputStream:
        stream = sd.InputStream(
            samplerate=samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        stream.start()
        return stream

    def start(self) -> None:
        with self._lock:
            self._frames.clear()
        self.clipped = False
        self.error = None
        # Many USB/conferencing mics (e.g. Anker PowerConf) reject opening at an
        # arbitrary rate like 16 kHz with CoreAudio error -10851 and capture
        # nothing. Fall back to the device's native rate and resample to our
        # target on read rather than asking the hardware to convert.
        self._capture_rate = self.samplerate
        try:
            self._stream = self._open_stream(self.samplerate)
        except Exception as e:  # noqa: BLE001
            try:
                native = int(sd.query_devices(kind="input")["default_samplerate"])
            except Exception:  # noqa: BLE001
                raise e  # nothing better to try; surface the original failure
            if native == self.samplerate:
                raise
            print(
                f"[recorder] {self.samplerate} Hz rejected ({e}); "
                f"capturing at native {native} Hz and resampling",
                flush=True,
            )
            self._capture_rate = native
            self._stream = self._open_stream(native)

        if self.max_seconds is not None:
            def _on_max() -> None:
                self.clipped = True
                self.stop_internal()

            self._timer = threading.Timer(self.max_seconds, _on_max)
            self._timer.daemon = True
            self._timer.start()

    def stop_internal(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _to_output(self, samples: np.ndarray) -> np.ndarray:
        """Mono float32 at the output samplerate, resampling if the mic was
        opened at a different native rate."""
        if samples.ndim > 1:
            samples = samples.squeeze(-1)
        if self._capture_rate != self.samplerate and len(samples):
            import scipy.signal as ss

            samples = ss.resample_poly(
                samples, self.samplerate, self._capture_rate
            ).astype(np.float32)
        return samples

    def stop(self) -> bytes:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.stop_internal()
        with self._lock:
            if not self._frames:
                return b""
            samples = np.concatenate(self._frames, axis=0)
        samples = self._to_output(samples)
        buf = io.BytesIO()
        sf.write(buf, samples, self.samplerate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def snapshot(self) -> np.ndarray:
        """Mono float32 copy of everything captured so far, while recording."""
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            samples = np.concatenate(self._frames, axis=0)
        return self._to_output(samples)

    def drain_new(self) -> np.ndarray:
        """Pop and return frames captured since the last drain (mono float32).

        Unlike snapshot()/stop() this *removes* the returned frames, so a
        long-running consumer can transcribe and persist in chunks while
        memory stays flat. Do not mix with snapshot()/stop() on the same
        recorder — draining defeats their cumulative semantics. Returns an
        empty array when no new audio has arrived.
        """
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            frames, self._frames = self._frames, []
        samples = np.concatenate(frames, axis=0)
        return self._to_output(samples)

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def has_audio(self) -> bool:
        """True if any frames were captured (also after the 30 s auto-stop)."""
        with self._lock:
            return bool(self._frames)
