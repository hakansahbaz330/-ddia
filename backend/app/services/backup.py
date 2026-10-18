from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import REPO_DIR, get_settings


class BackupUnsupported(Exception):
    pass


def _sqlite_path() -> Path:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise BackupUnsupported("Otomatik yedek yalnızca SQLite içindir. PostgreSQL için: pg_dump / pg_restore kullanın.")
    return Path(url.removeprefix("sqlite:///"))


def backup_database(dest_dir: Path | None = None) -> Path:
    src = _sqlite_path()
    dest_dir = dest_dir or REPO_DIR / "data" / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"football-{datetime.now():%Y%m%d-%H%M%S}.sqlite"
    with sqlite3.connect(src) as a, sqlite3.connect(dest) as b:
        a.backup(b)  # çalışan veritabanında tutarlı kopya
    return dest


def restore_database(backup: Path) -> None:
    """Yedeği geri yükler. Çalışan API sürecini durdurup çağırın."""
    dst = _sqlite_path()
    if not backup.exists():
        raise FileNotFoundError(backup)
    with sqlite3.connect(backup) as a, sqlite3.connect(dst) as b:
        a.backup(b)
