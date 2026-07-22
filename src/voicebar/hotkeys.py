from __future__ import annotations

from typing import Callable

from pynput import keyboard


def _warm_ax_trust() -> None:
    """Resolve HIServices.AXIsProcessTrusted once, on the calling thread.

    pynput's two listener threads each call AXIsProcessTrusted() on startup.
    pyobjc-core 12.2's lazy-import machinery is not thread-safe when it first
    resolves a symbol: the winner does `funcmap.pop(name)` and a racing thread
    hits `KeyError: 'AXIsProcessTrusted'`, killing that listener (so PTT never
    fires). Touching it once here caches it in the module dict; every later
    access is a plain, thread-safe lookup.
    """
    try:
        import HIServices

        HIServices.AXIsProcessTrusted()
    except Exception as e:  # noqa: BLE001
        print(f"[hotkeys] AX trust warmup skipped: {e}", flush=True)


class HotkeyManager:
    """Two listeners running in background threads:
    1. PTT listener for Right Option (alt_r)
    2. GlobalHotKeys for Ctrl+Alt+S (speak)
    """

    def __init__(
        self,
        on_ptt_down: Callable[[], None],
        on_ptt_up: Callable[[], None],
        on_speak: Callable[[], None],
    ) -> None:
        self._on_ptt_down = on_ptt_down
        self._on_ptt_up = on_ptt_up
        self._on_speak = on_speak
        self._ptt_active = False
        self._ptt_listener: keyboard.Listener | None = None
        self._speak_listener: keyboard.GlobalHotKeys | None = None

    def _is_right_option(self, key) -> bool:
        return key == keyboard.Key.alt_r

    def _on_press(self, key) -> None:
        if self._is_right_option(key) and not self._ptt_active:
            self._ptt_active = True
            try:
                self._on_ptt_down()
            except Exception as e:  # noqa: BLE001
                print(f"[hotkeys] on_ptt_down error: {e}", flush=True)

    def _on_release(self, key) -> None:
        if self._is_right_option(key) and self._ptt_active:
            self._ptt_active = False
            try:
                self._on_ptt_up()
            except Exception as e:  # noqa: BLE001
                print(f"[hotkeys] on_ptt_up error: {e}", flush=True)

    def start(self) -> None:
        _warm_ax_trust()
        self._ptt_listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._ptt_listener.start()
        self._speak_listener = keyboard.GlobalHotKeys(
            {"<ctrl>+<alt>+s": self._safe_speak}
        )
        self._speak_listener.start()

    def _safe_speak(self) -> None:
        try:
            self._on_speak()
        except Exception as e:  # noqa: BLE001
            print(f"[hotkeys] on_speak error: {e}", flush=True)

    def stop(self) -> None:
        if self._ptt_listener is not None:
            self._ptt_listener.stop()
        if self._speak_listener is not None:
            self._speak_listener.stop()
