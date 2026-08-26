from __future__ import annotations

import difflib
import re
import threading
from typing import Callable

import numpy as np

from .engine import asr
from .recorder import Recorder

# Never commit the last word of a hypothesis: the audio buffer usually ends
# mid-word and whisper guesses the cut word ("seem" for "seems").
HOLDBACK_WORDS = 1

# Whisper hallucinates word loops over silence ("cooling cooling cooling…"),
# and a loop is self-consistent across passes, so agreement alone won't stop
# it. Refuse to commit once a delta would extend a run of identical words.
MAX_WORD_RUN = 2

_PUNCT = re.compile(r"[^\w']+")


def _norm(word: str) -> str:
    """Case/punctuation-insensitive form, so 'Seems,' agrees with 'seems'."""
    return _PUNCT.sub("", word).casefold()


def _truncate_run(prior: list[str], delta: list[str]) -> list[str]:
    """Drop words from `delta` that extend a run past MAX_WORD_RUN identical
    words; words after the run are kept (whisper can recover mid-hypothesis)."""
    run_word = _norm(prior[-1]) if prior else None
    run = 0
    for w in reversed(prior):
        if _norm(w) != run_word:
            break
        run += 1
    out: list[str] = []
    for w in delta:
        n = _norm(w)
        if n == run_word:
            run += 1
            if run > MAX_WORD_RUN:
                continue
        else:
            run_word, run = n, 1
        out.append(w)
    return out


class StreamingTranscriber:
    """Live-commit transcription of a growing recording (LocalAgreement-2).

    While recording, re-transcribe the whole buffer every `interval` seconds.
    Whisper revises its hypothesis as context grows, so a word is committed
    only when (a) two consecutive passes agree on it (compared normalized) and
    (b) at least HOLDBACK_WORDS words follow it in the hypothesis. Committed
    words are final and emitted incrementally via `on_delta`.

    Committed text can never be retracted, so all alignment against newer
    hypotheses is by content (longest matching block), not word position —
    a revised committed word must not duplicate or drop its neighbors.
    """

    def __init__(
        self,
        recorder: Recorder,
        engine_lock: threading.Lock,
        on_delta: Callable[[str], None],
        interval: float = 2.5,
        min_audio_seconds: float = 1.0,
    ) -> None:
        self._recorder = recorder
        self._engine_lock = engine_lock
        self._on_delta = on_delta
        self._interval = interval
        self._min_samples = int(min_audio_seconds * asr.TARGET_SR)
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._prev_norm: list[str] = []
        self._transcribed_to = 0
        self.committed_words: list[str] = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_evt.wait(self._interval):
            samples = self._recorder.snapshot()
            if len(samples) < self._min_samples:
                continue
            # Re-transcribing without new speech can only hallucinate; skip
            # the pass if nothing arrived since the last one (e.g. the mic
            # stream died) or everything new is near-silence.
            new = samples[self._transcribed_to:]
            if not len(new) or float(np.sqrt(np.mean(new**2))) < 0.005:
                continue
            self._transcribed_to = len(samples)
            try:
                with self._engine_lock:
                    if self._stop_evt.is_set():
                        return
                    hypothesis = asr.transcribe_samples(samples)
            except Exception as e:  # noqa: BLE001
                print(f"[stream] pass failed: {e}", flush=True)
                continue
            had_prior = bool(self.committed_words)
            delta = self._ingest(hypothesis)
            if delta:
                self._emit(delta, had_prior)

    def _ingest(self, hypothesis: str) -> list[str]:
        """Update agreement state with a new hypothesis; return newly committed words."""
        words = hypothesis.split()
        cur_norm = [_norm(w) for w in words]
        agreed = 0
        for a, b in zip(self._prev_norm, cur_norm):
            if a != b:
                break
            agreed += 1
        self._prev_norm = cur_norm
        stable = words[: max(0, min(agreed, len(words) - HOLDBACK_WORDS))]
        delta = self._tail_after_committed(stable)
        delta = _truncate_run(self.committed_words, delta)
        if delta:
            self.committed_words.extend(delta)
        return delta

    def _tail_after_committed(self, words: list[str]) -> list[str]:
        """Words in `words` past the best content alignment of committed_words.

        Anchors on the last matching block so a revised committed word skips
        its replacement instead of re-emitting neighbors.
        """
        if not self.committed_words:
            return list(words)
        a = [_norm(w) for w in self.committed_words]
        b = [_norm(w) for w in words]
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        blocks = [blk for blk in sm.get_matching_blocks() if blk.size]
        if not blocks:
            return list(words[len(a):])
        i, j, n = blocks[-1]
        skip = j + n + (len(a) - (i + n))
        return list(words[skip:])

    def _emit(self, delta_words: list[str], had_prior: bool) -> None:
        text = " ".join(delta_words)
        if had_prior:
            text = " " + text
        try:
            self._on_delta(text)
        except Exception as e:  # noqa: BLE001
            print(f"[stream] on_delta failed: {e}", flush=True)

    def finalize(self, final_text: str) -> str:
        """Tail of the definitive full-clip transcript past the committed text.

        Committed text was already typed and cannot be retracted; if the final
        pass revised a committed word, the revision is skipped by alignment.
        """
        tail = self._tail_after_committed(final_text.split())
        tail = _truncate_run(self.committed_words, tail)
        if not tail:
            return ""
        text = " ".join(tail)
        if self.committed_words:
            text = " " + text
        return text
