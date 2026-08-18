from __future__ import annotations

import threading
import time
from pathlib import Path

import rumps
from PyObjCTools import AppHelper

from . import bundle, login_item
from .engine import asr, tts
from .hotkeys import HotkeyManager
from .inject import inject_text, type_text
from .interview import InterviewSession
from .playback import play_async
from .recorder import Recorder
from .selection import grab_selection
from .speech_clean import clean_for_speech
from .spool import SpoolWatcher
from .state import Runtime, load_config, save_config
from .streaming import StreamingTranscriber

DEFAULT_VOICE = "af_heart"
VOICES = [
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sarah",
    "am_michael",
    "am_adam",
    "bf_emma",
    "bm_george",
]

ICON_IDLE = "●"
ICON_REC = "🔴"
ICON_INTERVIEW = "🎙"
ICON_BUSY = "⏳"
ICON_OK = "✓"
ICON_WARN = "⚠"
ICON_EMPTY = "∅"


def _models_cached() -> bool:
    """Best-effort check whether the speech models are already downloaded."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    return all(
        (hub / f"models--{repo.replace('/', '--')}").exists()
        for repo in (asr.MODEL_REPO, tts.MODEL_REPO)
    )


def _notify(title: str, message: str) -> None:
    """Notification that degrades to a log line.

    rumps.notification raises when the interpreter lacks an Info.plist with
    CFBundleIdentifier (bare venv python). A failed notification must never
    take down the calling flow.
    """
    try:
        rumps.notification("VoiceBar", title, message)
    except Exception as e:  # noqa: BLE001
        print(f"[notify] {title}: {message} ({e})", flush=True)


class VoiceBarApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("VoiceBar", title=ICON_BUSY, quit_button=None)
        self.config = load_config()
        self.recorder = Recorder()
        self._engine_lock = threading.Lock()
        self._streamer: StreamingTranscriber | None = None
        self._interview: InterviewSession | None = None
        self._engines_ready = False
        self._load_seconds = 0.0
        self._hotkeys = HotkeyManager(
            on_ptt_down=self._on_ptt_down,
            on_ptt_up=self._on_ptt_up,
            on_speak=self._on_speak,
        )
        self._spool = SpoolWatcher(on_text=self._on_spool_text)
        self._build_menu()
        self._hotkeys.start()
        threading.Thread(target=self._load_engines, daemon=True).start()

    # ---------- engine load ----------

    def _load_engines(self) -> None:
        t0 = time.time()
        if not _models_cached():
            _notify(
                "First run",
                "Downloading speech models (~850 MB). "
                "The menu bar shows ⏳ until ready.",
            )
            AppHelper.callAfter(
                setattr,
                self.status_item,
                "title",
                "Status: downloading models (first run)…",
            )
        try:
            asr.warmup()
            tts.warmup(self.config.get("voice", DEFAULT_VOICE))
        except Exception as e:  # noqa: BLE001
            print(f"[load] failed: {e}", flush=True)
            AppHelper.callAfter(self._on_load_failed, str(e))
            return
        self._load_seconds = time.time() - t0
        print(f"[load] ready in {self._load_seconds:.1f}s", flush=True)
        AppHelper.callAfter(self._on_load_ready)

    def _on_load_ready(self) -> None:
        self._engines_ready = True
        self.title = ICON_IDLE
        self.status_item.title = f"Status: ready ({self._load_seconds:.0f}s load)"
        self._spool.start()  # only accept speak requests once Kokoro is up

    def _on_load_failed(self, msg: str) -> None:
        self.title = ICON_WARN
        self.status_item.title = "Status: load failed"
        _notify("Engines failed to load", msg)

    # ---------- menu ----------

    def _build_menu(self) -> None:
        self.status_item = rumps.MenuItem("Status: loading models…")

        self.voice_menu = rumps.MenuItem("Voice")
        for v in VOICES:
            mi = rumps.MenuItem(v, callback=self._on_voice_pick)
            mi.state = 1 if v == self.config.get("voice", DEFAULT_VOICE) else 0
            self.voice_menu[v] = mi

        self.live_typing_item = rumps.MenuItem(
            "Live typing", callback=self._on_live_typing_toggle
        )
        self.live_typing_item.state = 1 if self.config.get("live_typing", True) else 0

        self.mute_summaries_item = rumps.MenuItem(
            "Mute summaries", callback=self._on_mute_summaries_toggle
        )
        self.mute_summaries_item.state = (
            1 if self.config.get("mute_summaries", False) else 0
        )

        self.interview_item = rumps.MenuItem(
            "Start interview recording", callback=self._on_interview_toggle
        )

        extras = []
        if bundle.is_bundled():
            # Only the .app can register itself as a login item (SMAppService
            # needs a main bundle); from a source checkout use `make login`.
            self.login_item_item = rumps.MenuItem(
                "Start at Login", callback=self._on_login_item_toggle
            )
            self.login_item_item.state = 1 if login_item.is_enabled() else 0
            extras.append(self.login_item_item)

        self.menu = [
            self.status_item,
            self.interview_item,
            self.voice_menu,
            self.live_typing_item,
            self.mute_summaries_item,
            *extras,
            None,
            rumps.MenuItem("Quit", callback=self._on_quit),
        ]

    def _on_live_typing_toggle(self, sender: rumps.MenuItem) -> None:
        sender.state = 0 if sender.state else 1
        self.config["live_typing"] = bool(sender.state)
        save_config(self.config)

    def _on_mute_summaries_toggle(self, sender: rumps.MenuItem) -> None:
        sender.state = 0 if sender.state else 1
        self.config["mute_summaries"] = bool(sender.state)
        save_config(self.config)

    def _on_login_item_toggle(self, sender: rumps.MenuItem) -> None:
        want = not sender.state
        err = login_item.set_enabled(want)
        if err is not None:
            _notify("Start at Login failed", err)
            return
        sender.state = 1 if want else 0

    def _on_interview_toggle(self, sender: rumps.MenuItem) -> None:
        if self._interview is not None:
            self._stop_interview()
            return
        if not self._engines_ready:
            self._not_ready_notice()
            return
        if self.recorder.is_recording:
            _notify("Busy", "Finish the current dictation before recording an interview.")
            return
        session = InterviewSession(self._engine_lock, on_progress=self._on_interview_progress)
        try:
            path = session.start()
        except Exception as e:  # noqa: BLE001
            _notify(
                "Microphone error",
                f"{e}. Grant Microphone permission in System Settings.",
            )
            self._set_title(ICON_WARN)
            return
        self._interview = session
        sender.title = "Stop interview recording"
        self._set_title(ICON_INTERVIEW)
        self.status_item.title = "Interview: recording…"
        _notify("Interview recording", f"Saving to {path.name}")

    def _stop_interview(self) -> None:
        session, self._interview = self._interview, None
        self.interview_item.title = "Start interview recording"
        if session is None:
            return
        self._set_title(ICON_BUSY)
        self.status_item.title = "Interview: finishing transcription…"

        def _finish() -> None:
            try:
                path = session.stop()
            except Exception as e:  # noqa: BLE001
                self._warn("Interview save failed", str(e))
                return
            AppHelper.callAfter(self._on_interview_saved, path)

        threading.Thread(target=_finish, daemon=True).start()

    def _on_interview_progress(self, status: str) -> None:
        # Runs on the session worker thread; touch the menu on the main thread.
        AppHelper.callAfter(setattr, self.status_item, "title", f"Interview: {status}")

    def _on_interview_saved(self, path) -> None:
        self.status_item.title = f"Status: ready ({self._load_seconds:.0f}s load)"
        self._flash_title(ICON_OK)
        if path is not None:
            _notify("Interview saved", str(path))

    def _on_voice_pick(self, sender: rumps.MenuItem) -> None:
        for v in VOICES:
            self.voice_menu[v].state = 0
        sender.state = 1
        self.config["voice"] = str(sender.title)
        save_config(self.config)

    def _on_quit(self, _sender) -> None:
        if self._interview is not None:
            try:
                self._interview.stop()  # flush + close the .wav/.txt cleanly
            except Exception as e:  # noqa: BLE001
                print(f"[quit] interview stop failed: {e}", flush=True)
            self._interview = None
        self._hotkeys.stop()
        self._spool.stop()
        rumps.quit_application()

    # ---------- main-thread title helpers ----------

    def _set_title(self, title: str) -> None:
        AppHelper.callAfter(setattr, self, "title", title)

    def _flash_title(self, transient: str, after: float = 0.6) -> None:
        self._set_title(transient)
        threading.Timer(after, self._set_title, args=(ICON_IDLE,)).start()

    def _warn(self, title: str, message: str) -> None:
        _notify(title, message)
        self._flash_title(ICON_WARN, after=0.8)

    def _not_ready_notice(self) -> None:
        _notify(
            "Still loading", "Models aren't ready yet — try again in a moment."
        )

    # ---------- PTT flow ----------

    def _on_ptt_down(self) -> None:
        if not self._engines_ready:
            self._not_ready_notice()
            return
        if self._interview is not None:
            return  # interview owns the mic; ignore PTT until it stops
        if self.recorder.is_recording:
            return
        try:
            self.recorder.start()
        except Exception as e:  # noqa: BLE001
            _notify(
                "Microphone error",
                f"{e}. Grant Microphone permission in System Settings.",
            )
            self._set_title(ICON_WARN)
            return
        if self.config.get("live_typing", True):
            self._streamer = StreamingTranscriber(
                self.recorder, self._engine_lock, on_delta=self._on_stream_delta
            )
            self._streamer.start()
        self._set_title(ICON_REC)

    def _on_stream_delta(self, text: str) -> None:
        if not type_text(text):
            print("[stream] live typing blocked (secure field?)", flush=True)

    def _on_ptt_up(self) -> None:
        if not self.recorder.is_recording and not self.recorder.has_audio:
            return
        streamer, self._streamer = self._streamer, None
        try:
            wav = self.recorder.stop()
        except Exception as e:  # noqa: BLE001
            if streamer:
                streamer.stop()
            self._warn("Recording error", str(e))
            return

        clipped = self.recorder.clipped
        if not wav:
            if streamer:
                streamer.stop()
            self._flash_title(ICON_EMPTY)
            return

        self._set_title(ICON_BUSY)
        threading.Thread(
            target=self._asr_and_inject, args=(wav, clipped, streamer), daemon=True
        ).start()

    def _asr_and_inject(
        self, wav: bytes, clipped: bool, streamer: StreamingTranscriber | None
    ) -> None:
        if streamer:
            streamer.stop()  # joins the worker; no further deltas after this
        try:
            with self._engine_lock:
                text = asr.transcribe_wav_bytes(wav)
        except Exception as e:  # noqa: BLE001
            self._warn("ASR failed", str(e))
            return

        text = (text or "").strip()
        if not text:
            self._flash_title(ICON_EMPTY)
            return

        if streamer and streamer.committed_words:
            tail = streamer.finalize(text)
            ok = type_text(tail)
            full_text = " ".join(streamer.committed_words)
            if tail:
                full_text += tail
        else:
            ok = inject_text(text)
            full_text = text

        if ok:
            Runtime.last_injected = full_text
            self._flash_title(ICON_OK)
            if clipped:
                _notify("Clip cut at 30s", "Long dictation truncated.")
        else:
            self._warn("Paste blocked", "Likely a secure field. Text left on clipboard.")

    # ---------- speak flow ----------

    def _on_speak(self) -> None:
        if not self._engines_ready:
            self._not_ready_notice()
            return
        text = grab_selection() or Runtime.last_injected
        if not text:
            _notify(
                "Nothing to speak", "Select text or dictate first."
            )
            return
        self._set_title(ICON_BUSY)
        threading.Thread(target=self._tts_and_play, args=(text,), daemon=True).start()

    def _on_spool_text(self, text: str) -> None:
        """Speak text dropped into the spool dir (runs on the watcher thread).

        Muting drops the request rather than queueing it: the watcher has
        already consumed the file, and a backlog of stale summaries playing
        on unmute is worse than silence.
        """
        if self.config.get("mute_summaries", False):
            return
        text = clean_for_speech(text)
        if not text:
            return
        self._set_title(ICON_BUSY)
        self._tts_and_play(text)

    def _tts_and_play(self, text: str) -> None:
        try:
            with self._engine_lock:
                samples, sr = tts.synthesize(
                    text, voice=self.config.get("voice", DEFAULT_VOICE)
                )
        except Exception as e:  # noqa: BLE001
            self._warn("TTS failed", str(e))
            return
        self._set_title(ICON_IDLE)
        play_async(tts.to_wav_bytes(samples, sr))


def main() -> None:
    VoiceBarApp().run()


if __name__ == "__main__":
    main()
