.PHONY: help install run smoke espeak docs login login-remove app dmg

help:
	@echo "Targets:"
	@echo "  install        uv sync (creates venv, installs everything)"
	@echo "  run            Run the menu-bar app in the foreground"
	@echo "  smoke          In-process ASR + TTS engine smoke test"
	@echo "  espeak         brew install espeak-ng (Kokoro fallback)"
	@echo "  docs           Serve the documentation site locally"
	@echo "  login          Register as a macOS Login Item (source checkouts)"
	@echo "  login-remove   Unregister the Login Item"
	@echo "  app            Build dist/CodeWithVoice.app (self-contained bundle)"
	@echo "  dmg            Build dist/CodeWithVoice-<version>.dmg"

install:
	uv sync
	@# rumps notifications need a CFBundleIdentifier next to the interpreter
	@test -f .venv/bin/Info.plist || /usr/libexec/PlistBuddy \
		-c 'Add :CFBundleIdentifier string "codewithvoice"' .venv/bin/Info.plist

run:
	uv run python -m voicebar

smoke:
	uv run python -c "\
	from pathlib import Path; \
	from voicebar.engine import asr, tts; \
	print('ASR:', asr.transcribe_wav_bytes(Path('samples/Example.ogg').read_bytes())); \
	samples, sr = tts.synthesize('engine smoke test passed'); \
	print('TTS:', round(len(samples)/sr, 2), 'seconds at', sr, 'Hz')"

espeak:
	brew install espeak-ng

docs:
	uv run --group docs mkdocs serve

login:
	./scripts/login-item.sh install

login-remove:
	./scripts/login-item.sh remove

app:
	./scripts/build-app.sh

dmg: app
	./scripts/build-dmg.sh
