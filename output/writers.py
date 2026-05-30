import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class VaultWriter(ABC):
    @abstractmethod
    def write(self, filename: str, content: str) -> Path:
        """Write content to the vault. Returns the absolute Path of the written file."""


class LocalFolderWriter(VaultWriter):
    def __init__(self, vault_path: Path, subdir: str) -> None:
        self.notes_dir = vault_path / subdir

    def write(self, filename: str, content: str) -> Path:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        dest = self.notes_dir / filename
        dest.write_text(content, encoding="utf-8")
        logger.info("wrote note: %s", dest)
        return dest
