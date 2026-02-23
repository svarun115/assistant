from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest


def _fake_completed_process(returncode: int, stdout: str | None = "", stderr: str | None = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_backup_sql_uses_file_output_and_creates_gz(tmp_path, monkeypatch):
    """Regression for #92: SQL backup should not depend on stdout being a str."""

    import backup.backup_sql as mod
    from config import DatabaseConfig

    # Avoid loading .env / safety checks from the real environment.
    fake_config = DatabaseConfig(
        host="localhost",
        port=5432,
        database="assistant_dev",
        user="postgres",
        password="",
        ssl_mode="prefer",
    )

    monkeypatch.setattr(mod, "find_pg_dump", lambda: "pg_dump")
    monkeypatch.setattr(mod, "find_psql", lambda: "psql")
    monkeypatch.setattr(mod.DatabaseConfig, "from_environment", classmethod(lambda cls: fake_config))
    monkeypatch.setattr(mod, "generate_metadata", lambda _cfg: {"ok": True})

    def fake_run(cmd, capture_output, text, timeout, env):
        exe = cmd[0]
        if exe == "psql":
            return _fake_completed_process(0, stdout="1\n", stderr="")

        assert exe == "pg_dump"
        # Ensure we're using -f rather than writing stdout.
        assert "-f" in cmd
        out_path = cmd[cmd.index("-f") + 1]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("-- fake dump --\n")
        # stdout can be None in some subprocess configurations; we should not use it.
        return _fake_completed_process(0, stdout=None, stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    gz_path = mod.backup_database(backup_dir=tmp_path, backup_name="backup_assistant_dev_unit")

    assert gz_path.exists()
    assert str(gz_path).endswith(".sql.gz")
    assert gz_path.stat().st_size > 0
