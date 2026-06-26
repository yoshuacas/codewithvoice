# How to record an interview to a transcript

**Goal:** capture a whole conversation hands-free — no push-to-talk — and get a
saved, timestamped transcript you can read afterwards to assess a candidate.

Unlike dictation, this mode types nothing into other apps. It records until you
stop it and writes the transcript and the raw audio to a file.

## Record

1. Wait for the menu bar to show `●` (models loaded).
2. Click the menu → **Start interview recording**. The title changes to `🎙`
   and the status line shows elapsed time and a running word count.
3. Run the interview. The transcript is written live, so you can watch the file
   grow if you like.
4. Click the menu → **Stop interview recording**. The title shows `⏳` while the
   final chunk transcribes, then flashes `✓`. A notification gives the saved path.

The microphone captures whatever it can hear, so use a mic that picks up the
room (or a conferencing setup) to catch everyone, not just yourself.

## Where the transcript lands

`~/Documents/codewithvoice-interviews/`, as a pair named by start time:

- `interview_2026-06-26_14-30-05.txt` — the transcript, one `[m:ss] text` line
  per ~30 s window.
- `interview_2026-06-26_14-30-05.wav` — the raw 16 kHz mono audio.

Both are flushed to disk continuously, so if the app is quit or crashes
mid-interview you keep everything captured up to that point — and the `.wav`
lets you re-run transcription later.

## Notes and limits

- **No speaker labels.** It's one continuous transcript; whisper doesn't
  identify who is speaking. Note who's in the room at the top of your own copy
  if you need it.
- **Silence is dropped.** Near-silent 30 s windows are skipped to avoid whisper
  inventing text over thinking pauses, so quiet gaps simply won't appear.
- **One mic at a time.** Push-to-talk and ⌃⌥S speak are ignored while an
  interview is recording — stop it first.
- **Accuracy over latency.** The transcript updates roughly every 30 s; this is
  long-form capture, not live typing.

## Permissions

Same as dictation: Microphone access must be granted to the terminal app that
launched the bar, and grants are read at startup — relaunch after granting. See
[fix hotkeys that do nothing](fix-permissions.md) for the full checklist.
