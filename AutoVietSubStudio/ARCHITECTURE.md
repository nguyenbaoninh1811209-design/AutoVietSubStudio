# Architecture v0.1

## UI
PySide6 desktop UI.

## Core
- Project/domain models
- SRT parser/writer
- Translation engine + validator
- Pipeline/checkpoints
- Settings persistence

## Providers
- Translation: OpenAI API adapter
- OCR: optional provider interface
- ASR: optional provider interface
- TTS: optional provider interface
- Video: FFmpeg adapter

## Data
- `data/projects/*.json`
- `data/settings.json`
- `data/models/`
- `data/cache/`
- `data/logs/`
- `data/exports/`

## Safety
- No ChatGPT Web cookie/session scraping.
- No bypass of proprietary voice assets.
- Never overwrite the original video by default.
