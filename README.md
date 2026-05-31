# reelscribe

A personal Telegram bot that captures Instagram Reels, TikTok videos, and YouTube Shorts and saves them as structured notes in your Obsidian vault.

Send a link to your bot → it downloads the video, transcribes it with Gemini, extracts places and tips, and writes a formatted note.

## What it does

- Detects reel/short links in Telegram messages
- Downloads the video via yt-dlp
- Sends it to Gemini for transcription, OCR, summarisation, and item extraction
- Writes a Markdown note to your Obsidian vault with frontmatter, summary, items, transcription, and caption
- Deduplicates: sending the same link twice returns the existing note path

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Gemini API key (from [Google AI Studio](https://aistudio.google.com))
- An Obsidian vault on the same machine

## Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/adriantimoteo/reel-notes.git
cd reel-notes
uv sync
```

**2. Create a `.env` file**

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id
GEMINI_API_KEY=your_gemini_api_key

VAULT_PATH=/absolute/path/to/your/obsidian/vault
VAULT_NOTES_SUBDIR=Reels
DB_PATH=/absolute/path/to/reelscribe.db
DOWNLOAD_TEMP_DIR=/tmp/reelscribe

# Optional
MAX_VIDEO_DURATION_SECONDS=120
LOG_LEVEL=INFO
```

To find your Telegram user ID, message [@userinfobot](https://t.me/userinfobot).

**3. Run**

```bash
uv run python main.py
```

## Note format

Each captured reel becomes a Markdown file in `VAULT_PATH/VAULT_NOTES_SUBDIR/`:

```markdown
---
source: "https://www.instagram.com/reel/..."
platform: instagram
author: "@username"
posted: 2024-03-01
captured: 2026-05-31
tags: [tokyo, ramen, food]
---

## Summary
A tour of the best tonkatsu restaurants in Tokyo...

## Items mentioned
- **Tonkatsu Maisen Aoyama** — Classic tonkatsu in Aoyama.

## Transcription
> Today we're checking out...

## On-screen text
> Open 11am–10pm · ¥1,500

## Caption
> Best katsu I've ever had
```

## Supported platforms

| Platform | URL types |
|---|---|
| Instagram | `/reel/`, `/p/`, `/tv/` |
| TikTok | `tiktok.com/@user/video/`, `vm.tiktok.com/` |
| YouTube | `/shorts/`, `/watch?v=` |

## Development

```bash
uv run pytest          # run all tests
uv run pytest -q       # quiet output
```

Dependencies are managed with uv. Never use `pip` directly.
