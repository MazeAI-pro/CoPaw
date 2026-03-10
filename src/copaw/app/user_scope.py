# -*- coding: utf-8 -*-
"""User-scoped storage helpers.

Current phase keeps a single default user and isolates runtime data under:
``WORKING_DIR/users/<user_id>/``.
"""
from __future__ import annotations

import contextvars
import shutil
from pathlib import Path

from .runner.session import sanitize_filename
from ..constant import WORKING_DIR

DEFAULT_USER_ID = "default"
_CURRENT_USER_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "copaw_current_user_id",
    default=DEFAULT_USER_ID,
)
_LEGACY_MIGRATED = False


def normalize_user_id(user_id: str | None) -> str:
    """Return a filesystem-safe user identifier."""
    raw = (user_id or "").strip()
    safe = sanitize_filename(raw) if raw else DEFAULT_USER_ID
    return safe or DEFAULT_USER_ID


def get_current_user_id(_request=None) -> str:
    """Return current user id.

    Future versions can resolve from request/auth; for now it always falls
    back to context variable defaulting to ``default``.
    """
    return normalize_user_id(_CURRENT_USER_ID.get())


def set_current_user_id(user_id: str | None):
    """Set current request-scoped user id context."""
    return _CURRENT_USER_ID.set(normalize_user_id(user_id))


def reset_current_user_id(token) -> None:
    """Reset current request-scoped user id context."""
    _CURRENT_USER_ID.reset(token)


def get_users_root() -> Path:
    root = WORKING_DIR / "users"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_user_root(user_id: str | None) -> Path:
    root = get_users_root() / normalize_user_id(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_user_chats_path(user_id: str | None) -> Path:
    return get_user_root(user_id) / "chats.json"


def get_user_sessions_dir(user_id: str | None) -> Path:
    path = get_user_root(user_id) / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_memory_dir(user_id: str | None) -> Path:
    path = get_user_root(user_id) / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_profile_path(user_id: str | None) -> Path:
    return get_user_root(user_id) / "PROFILE.md"


def get_user_workspace_dir(user_id: str | None) -> Path:
    path = get_user_root(user_id) / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _move_path(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        if not dst.exists():
            shutil.move(str(src), str(dst))
        return

    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            child_dst = dst / child.name
            if child.is_dir():
                _move_path(child, child_dst)
            else:
                if not child_dst.exists():
                    shutil.move(str(child), str(child_dst))
        try:
            src.rmdir()
        except OSError:
            pass


def migrate_legacy_to_user_dir(user_id: str | None = None) -> None:
    """Best-effort migration from legacy global paths to user-scoped paths."""
    global _LEGACY_MIGRATED
    if _LEGACY_MIGRATED:
        return

    uid = normalize_user_id(user_id)
    user_root = get_user_root(uid)
    _move_path(WORKING_DIR / "chats.json", user_root / "chats.json")
    _move_path(WORKING_DIR / "sessions", user_root / "sessions")
    _move_path(WORKING_DIR / "memory", user_root / "memory")
    _move_path(WORKING_DIR / "MEMORY.md", user_root / "memory" / "MEMORY.md")
    _move_path(WORKING_DIR / "PROFILE.md", user_root / "PROFILE.md")
    _move_path(WORKING_DIR / "user_files", user_root / "workspace")
    _LEGACY_MIGRATED = True
