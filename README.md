# reel-notes

A personal Telegram bot that captures Instagram Reels, TikTok videos and photo slideshows, and YouTube Shorts, and saves them as structured notes in your Obsidian vault.

Send a link to your bot → it downloads the video (or photo slides), analyses it with Gemini, classifies the content type, and writes a formatted note.

## What it does

- Detects reel/short links in Telegram messages
- Downloads the video via yt-dlp
- Also handles TikTok photo-mode slideshows and Instagram photo carousels — every slide image (and TikTok's background audio track, when present) is sent to Gemini the same way a video would be
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

This runs continuously (long polling) — useful for active development, but it requires the machine to stay on and online.

## Running on a schedule

For a bot on a laptop that isn't on 24/7, running continuously doesn't make sense. Telegram holds messages sent to your bot until it next checks in (they aren't lost just because the bot wasn't running), so instead you can run the bot briefly on a schedule to pick up whatever's waiting:

```bash
uv run python main.py --once
```

This drains every message currently queued, processes them one at a time, and exits — it doesn't wait around for new messages. If the machine has no network access when it runs, it logs that and exits cleanly rather than erroring.

**Windows Task Scheduler setup:**

Quickest way — one command (runs only while you're logged in, no password needed):

```powershell
schtasks /create /tn "ReelNotesDrain" /tr 'powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\reel-notes\scripts\run_once.ps1"' /sc hourly /f
```

Adjust `/sc hourly` (e.g. `/sc minute /mo 15`) for a different cadence — a missed run just gets picked up by the next one. To edit later (trigger, conditions, etc.), open Task Scheduler and find it under the task name you gave it (`ReelNotesDrain` above, at the library root).

Equivalent via the Task Scheduler GUI: Create Task → Triggers: on a schedule, repeat every N minutes/hours, indefinitely → Actions: Start a program, `powershell.exe`, arguments `-ExecutionPolicy Bypass -File "C:\path\to\reel-notes\scripts\run_once.ps1"`. On a laptop, also uncheck "Start the task only if the computer is on AC power" under Conditions, and check "Run task as soon as possible after a scheduled start is missed" under Settings so it catches up after sleep.

Output from each run is appended to `logs/drain.log` (not committed to git), since Task Scheduler doesn't show console output.

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

### Failures and retries

Every failure message ends with the link, so it can be copied and resent later. If a reel downloads but extraction fails with something transient (Gemini 503/429, a dropped connection, or a request that exceeds the 120s Gemini timeout set by `REQUEST_TIMEOUT_MS` in `pipeline/extractor.py`), its DB row is left without a note path. Each `--once` run retries those rows after draining new messages, up to 3 times, and messages you only when a retry succeeds or the reel is given up on. The retry step stops starting new retries after 40 minutes (`RETRY_TIME_BUDGET_SECONDS` in `pipeline/retry_sweep.py`) so a long backlog can't crowd out the next hourly run; reels it didn't reach are left untouched and go first next time. Resending a link whose earlier attempt failed also just reprocesses it. Failures that happen before the download finishes leave no row, so those need a resend.

If a link's note was deleted from the vault, resending it says so and points at `/reprocess <url>` to regenerate it.

## Supported platforms

| Platform | URL types |
|---|---|
| Instagram | `/reel/`, `/p/` (single posts and photo/video carousels), `/tv/` |
| TikTok | `tiktok.com/@user/video/`, `tiktok.com/@user/photo/` (slideshows), `tiktok.com/t/`, `vm.tiktok.com/`, `vt.tiktok.com/` |
| YouTube | `/shorts/`, `/watch?v=` |

TikTok photo-mode posts and Instagram carousels are fetched with [gallery-dl](https://github.com/mikf/gallery-dl) instead of yt-dlp, which doesn't support either — Instagram carousel auth reuses the same `YTDLP_COOKIES_FILE`/`YTDLP_COOKIES_FROM_BROWSER` config below. YouTube's 2026 image-carousel Shorts format isn't supported — a matching URL fails with a clear "not supported yet" message rather than a generic error.

## Gemini model and costs

The model is `gemini-3.5-flash`, set as `MODEL_NAME` in `pipeline/extractor.py` — that's the one place to change it if Google deprecates it later. If a configured model is ever retired, extraction fails with a clear `Gemini model retired — update pipeline.extractor.MODEL_NAME` status message instead of a raw API error.

For personal-scale use (a handful of reels a day) this comfortably stays within Gemini's free tier — Google no longer publishes a fixed free-tier rate-limit table, so check the actual current numbers for your project at [AI Studio](https://aistudio.google.com)'s usage page rather than trusting any number quoted elsewhere, including here.

## Development

```bash
uv run pytest          # run all tests (app + packages/reelkit)
uv run pytest -q       # quiet output
```

Dependencies are managed with uv. Never use `pip` directly.

### Repo layout

This repo is a uv workspace with two packages:

- **The app** (repo root): `config.py`, `main.py`, `bot/`, `pipeline/`, `storage/`, `output/`. Everything specific to reel-notes lives here: config loading, the single-user auth, the notes prompt/schema, the orchestrator, SQLite, and the Obsidian writer.
- **`packages/reelkit`**: shared building blocks with no app config: reel link detection and canonicalization (`reelkit.urls`), download via yt-dlp/gallery-dl (`reelkit.fetch`), schema-agnostic Gemini extraction (`reelkit.gemini`), retry, and optional aiogram helpers (`reelkit.telegram`, via the `telegram` extra).

`pipeline/downloader.py` and `pipeline/extractor.py` are thin adapters that pass this app's config and prompt into reelkit. `packages/reelkit/tests/test_isolation.py` fails if reelkit ever imports app code or needs its env vars. See [packages/reelkit/README.md](packages/reelkit/README.md) for using it from another project.
