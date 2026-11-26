"""Filesystem locations that work both from source and from a frozen build.

When the app is packaged with PyInstaller, ``sys.frozen`` is set and
``__file__`` points inside a temporary extraction folder, so paths must be
derived from the executable instead.
"""

import os
import sys
from pathlib import Path


def is_frozen():
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """Folder the application lives in (the exe's folder when frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_env():
    """Load settings from a ``.env`` file next to the app.

    Returns the path that was loaded, or ``None``. Values already present in the
    real environment always win.
    """
    from dotenv import load_dotenv

    candidates = [app_dir() / ".env"]
    cwd_env = Path.cwd() / ".env"
    if cwd_env not in candidates:
        candidates.append(cwd_env)

    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


def _is_writable(folder):
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir():
    """Writable folder that holds the database.

    Prefers a ``data`` folder next to the executable so the app stays portable,
    and falls back to ``%LOCALAPPDATA%`` when that location is read-only (for
    example when installed under Program Files).
    """
    preferred = app_dir() / "data"
    if _is_writable(preferred):
        return preferred

    fallback = Path(
        os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()
    ) / "BillingSoftware"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def database_path():
    """Full path of the SQLite database file."""
    return data_dir() / "billing.db"
