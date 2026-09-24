"""reelkit must be importable by another project: no app config, no env vars, no
imports from the reel-notes app packages."""

import os
import subprocess
import sys
from pathlib import Path

MODULES = [
    "reelkit",
    "reelkit.exceptions",
    "reelkit.fetch",
    "reelkit.gemini",
    "reelkit.models",
    "reelkit.retry",
    "reelkit.status",
    "reelkit.telegram.drain",
    "reelkit.telegram.status",
    "reelkit.tempfiles",
    "reelkit.urls",
]

APP_MODULES = ["config", "bot", "pipeline", "storage", "output", "main"]

APP_ENV_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USER_ID",
    "GEMINI_API_KEY",
    "VAULT_PATH",
    "VAULT_NOTES_SUBDIR",
    "DB_PATH",
    "DOWNLOAD_TEMP_DIR",
]


def test_reelkit_imports_without_app_config(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in APP_ENV_VARS and k != "PYTHONPATH"}
    code = (
        "import importlib, sys\n"
        f"for m in {MODULES!r}: importlib.import_module(m)\n"
        f"leaked = [m for m in {APP_MODULES!r} if m in sys.modules]\n"
        "assert not leaked, f'reelkit imported app modules: {leaked}'\n"
    )
    # cwd outside the repo so the app's top-level modules aren't importable by accident
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
