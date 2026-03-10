# -*- coding: utf-8 -*-
from pathlib import Path

from copaw.app import user_scope


def test_user_scope_dirs_created(tmp_path, monkeypatch):
    monkeypatch.setattr(user_scope, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(user_scope, "_LEGACY_MIGRATED", False)

    user_id = "alice:demo"
    root = user_scope.get_user_root(user_id)
    assert root == tmp_path / "users" / "alice--demo"
    assert root.is_dir()

    assert user_scope.get_user_chats_path(user_id).parent == root
    assert user_scope.get_user_sessions_dir(user_id).is_dir()
    assert user_scope.get_user_memory_dir(user_id).is_dir()
    assert user_scope.get_user_workspace_dir(user_id).is_dir()
    assert user_scope.get_user_profile_path(user_id) == root / "PROFILE.md"


def test_current_user_context_roundtrip():
    token = user_scope.set_current_user_id("bob")
    try:
        assert user_scope.get_current_user_id() == "bob"
    finally:
        user_scope.reset_current_user_id(token)


def test_migrate_legacy_to_default_user(tmp_path, monkeypatch):
    monkeypatch.setattr(user_scope, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(user_scope, "_LEGACY_MIGRATED", False)

    # legacy files/dirs
    (tmp_path / "chats.json").write_text('{"version":1,"chats":[]}', encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("legacy memory", encoding="utf-8")
    (tmp_path / "PROFILE.md").write_text("legacy profile", encoding="utf-8")

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "u_s.json").write_text("{}", encoding="utf-8")

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "2026-03-09.md").write_text("daily", encoding="utf-8")

    user_files = tmp_path / "user_files"
    user_files.mkdir(parents=True)
    (user_files / "a.txt").write_text("hello", encoding="utf-8")

    user_scope.migrate_legacy_to_user_dir()

    target = tmp_path / "users" / "default"
    assert (target / "chats.json").exists()
    assert (target / "sessions" / "u_s.json").exists()
    assert (target / "memory" / "2026-03-09.md").exists()
    assert (target / "memory" / "MEMORY.md").exists()
    assert (target / "PROFILE.md").exists()
    assert (target / "workspace" / "a.txt").exists()

    # legacy paths should be moved away where possible
    assert not (tmp_path / "chats.json").exists()
    assert not (tmp_path / "MEMORY.md").exists()
