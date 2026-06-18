#!/bin/zsh
# Start the codewithvoice menu-bar dictation app.
# Works from anywhere — resolves the project root from this script's location.
cd "$(dirname "$0")" || exit 1
exec uv run python -m voicebar
