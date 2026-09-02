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

# Bound on how long stopping the input stream may block. PortAudio's
# Pa_StopStream can deadlock against the CoreAudio HAL IO thread (observed
# 2026-08-25: AudioOutputUnitStop held the AudioUnit mutex while waiting on
# the HAL IO mutex, whose owner was inside PortAudio's startStopCallback
# waiting on the AudioUnit mutex). The captured frames don't depend on the
# stream closing, so on timeout the stream is abandoned instead of hanging
# the caller forever.
STOP_TIMEOUT_SECONDS = 3.0

# Bound on how long opening the input stream may block. Pa_OpenStream takes
# the same CoreAudio HAL mutex that an abandoned close (above) can hold
# forever (observed 2026-09-02: a PTT press after an abandoned stop sat in
# Pa_OpenStream → HALB_Mutex::Lock and never returned). Opening on a helper
# thread with a bounded join turns that deadlock into a surfaced error.
OPEN_TIMEOUT_SECONDS = 5.0


class StreamOpenTimeout(RuntimeError):
    """Opening the mic stream hung — the CoreAudio HAL is likely wedged by an
    earlier abandoned stream close; only an app restart recovers."""


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
        self._accept: dict[str, bool] | None = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self.clipped = False
        self.error: str | None = None

    def _open_stream(self, samplerate: int) -> sd.InputStream:
        # Per-stream accept flag: an abandoned stream (see stop_internal) may
        # keep firing its callback; the flag stops it from polluting frames
        # captured by a later stream.
        accept = {"accept": True}

        def _callback(indata, frames, time_info, status) -> None:
            if status:
                self.error = str(status)
            if not accept["accept"]:
                return
            with self._lock:
                self._frames.append(indata.copy())

        result: dict[str, object] = {}

        def _open() -> None:
            try:
                stream = sd.InputStream(
                    samplerate=samplerate,
                    channels=self.channels,
                    dtype="float32",
                    callback=_callback,
                )
                stream.start()
            except Exception as e:  # noqa: BLE001
                result["error"] = e
                return
            result["stream"] = stream
            if not accept["accept"]:
                # The join below already timed out and abandoned this open;
                # best-effort close so a late success doesn't leak a stream.
                try:
                    stream.stop()
                    stream.close()
                except Exception as e:  # noqa: BLE001
                    print(f"[recorder] late stream close failed: {e}", flush=True)

        opener = threading.Thread(target=_open, daemon=True)
        opener.start()
        opener.join(OPEN_TIMEOUT_SECONDS)
        if opener.is_alive():
            accept["accept"] = False  # a late open must not capture anything
            raise StreamOpenTimeout(
                f"Opening the microphone hung for {OPEN_TIMEOUT_SECONDS:.0f}s "
                "(audio system wedged?) — quit and relaunch the app"
            )
        if "error" in result:
            raise result["error"]
        self._accept = accept
        return result["stream"]

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
        except StreamOpenTimeout:
            raise  # the HAL is wedged; retrying at another rate would hang too
        except Exception as e:
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
        """Close the input stream without ever blocking longer than
        STOP_TIMEOUT_SECONDS; the frames captured so far stay readable either
        way. See STOP_TIMEOUT_SECONDS for the CoreAudio deadlock this guards
        against."""
        stream, self._stream = self._stream, None
        accept, self._accept = self._accept, None
        if stream is None:
            return

        def _close() -> None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            finally:
                if accept is not None:
                    accept["accept"] = False

        closer = threading.Thread(target=_close, daemon=True)
        closer.start()
        closer.join(STOP_TIMEOUT_SECONDS)
        if closer.is_alive():
            if accept is not None:
                accept["accept"] = False  # drop anything the wedged stream still delivers
            print(
                "[recorder] stream stop hung (CoreAudio deadlock?); "
                "abandoning the stream and keeping captured audio",
                flush=True,
            )

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
