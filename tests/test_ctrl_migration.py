"""SQLite matches.mode CHECK 마이그레이션 — 재구축 시 컬럼 값(season 포함) 보존."""
import sqlite3

import db


def test_sqlite_mode_check_rebuild_keeps_all_columns():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "mode TEXT NOT NULL CHECK (mode IN ('HP', 'SND')), map_name TEXT)")
    conn.execute("ALTER TABLE matches ADD COLUMN season TEXT")
    conn.execute("INSERT INTO matches (mode, map_name, season) VALUES ('HP', 'Raid', 'custom')")
    conn.commit()

    assert db._migrate_matches_mode_check_sqlite(conn) is True
    assert conn.execute("SELECT mode, map_name, season FROM matches").fetchone() == \
        ("HP", "Raid", "custom")
    conn.execute("INSERT INTO matches (mode) VALUES ('CTRL')")  # CHECK가 CTRL 허용
    assert db._migrate_matches_mode_check_sqlite(conn) is False  # 멱등
