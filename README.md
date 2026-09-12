# reel-notes

A personal Telegram bot that captures Instagram Reels, TikTok videos, and YouTube Shorts and saves them as structured notes in your Obsidian vault.

Send a link to your bot → it downloads the video, analyses it with Gemini, classifies the content type, and writes a formatted note.

## What it does

- Detects reel/short links in Telegram messages
- Downloads the video via yt-dlp
- Sends it to Gemini for transcription, OCR, summarisation, and structured extraction
- Classifies each reel as `list`, `tutorial`, or `other` and renders the note accordingly
- Writes a Markdown note to your Obsidian vault with YAML frontmatter
- Deduplicates: sending the same link twice returns the existing note path
- `/reprocess` command to re-run extraction on an already-captured URL
- `/force` command to bypass the video length cap for a single URL, up to a hard limit

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
DB_PATH=/absolute/path/to/reels.db
DOWNLOAD_TEMP_DIR=/tmp/reel-notes

# Optional
MAX_VIDEO_DURATION_SECONDS=120
FORCE_MAX_VIDEO_DURATION_SECONDS=600
LOG_LEVEL=INFO

# Optional — cookie auth for yt-dlp (Instagram often rejects anonymous downloads)
# Prefer pulling from an installed browser you're logged into...
YTDLP_COOKIES_FROM_BROWSER=edge
# ...or point to an exported cookies.txt (Netscape format). Ignored if the
# browser option above is set.
YTDLP_COOKIES_FILE=/absolute/path/to/cookies.txt
```

To find your Telegram user ID, message [@userinfobot](https://t.me/userinfobot).

**3. Run**

```bash
uv run python main.py
```

## Note format

Each reel becomes a Markdown file in `VAULT_PATH/VAULT_NOTES_SUBDIR/`. The structure adapts to the content type.

**List** — places, restaurants, recommendations:

```markdown
---
source: "https://www.instagram.com/reel/..."
platform: instagram
author: "@username"
posted: 2024-03-01
captured: 2026-06-01
type: list
tags: [tokyo, ramen]
---

## Summary
A tour of the best tonkatsu spots in Tokyo...

## Items mentioned
- **Tonkatsu Maisen Aoyama** — Classic tonkatsu in Aoyama.

## Transcription
> Today we're checking out...
```

**Tutorial** — recipes, step-by-step how-tos:

```markdown
type: tutorial
---

## Summary
A quick pasta recipe...

## Ingredients
- 200g Pasta
- Salt

## Steps
1. Boil water
2. Add pasta and cook for 8 minutes

## Transcription
> Start by boiling water...
```

**Other** — vlogs, commentary, storytelling:

```markdown
type: other
---

## Summary
...

## Transcription
...
```

## Bot commands

| Command | Description |
|---|---|
| Send a URL | Capture and save the reel |
| `/reprocess <url>` | Re-run extraction on an already-captured URL |
| `/reprocess <url> --as tutorial` | Re-run with a forced content type (`list`, `tutorial`, `other`) |
| `/force <url>` | Bypass `MAX_VIDEO_DURATION_SECONDS` for one URL, up to `FORCE_MAX_VIDEO_DURATION_SECONDS` (default 600s) |

## Supported platforms

| Platform | URL types |
|---|---|
| Instagram | `/reel/`, `/p/`, `/tv/` |
| TikTok | `tiktok.com/@user/video/`, `tiktok.com/t/`, `vm.tiktok.com/`, `vt.tiktok.com/` |
| YouTube | `/shorts/`, `/watch?v=` |

## Development

```bash
uv run pytest          # run all tests
uv run pytest -q       # quiet output
```

Dependencies are managed with uv. Never use `pip` directly.
