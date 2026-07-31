import os
import sqlite3
import tempfile

import db


def _fresh_db():
    """임시 DB 파일 경로 반환. 각 테스트마다 독립."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.init_db(path)
    return path


def test_init_db_creates_all_tables():
    path = _fresh_db()
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    os.unlink(path)
    assert {"teams", "players", "aliases", "matches",
            "player_stats_hp", "player_stats_snd"} <= tables


def test_insert_team_and_player():
    path = _fresh_db()
    try:
        team_id = db.insert_team("Alpha", seed=1, path=path)
        player_id = db.insert_player("Ace", team_id, path=path)
        players = db.list_players(team_id, path=path)
        assert len(players) == 1
        assert players[0]["name"] == "Ace"
        assert players[0]["team_id"] == team_id
    finally:
        os.unlink(path)


def test_insert_alias_and_resolve():
    path = _fresh_db()
    try:
        tid = db.insert_team("Alpha", path=path)
        pid = db.insert_player("Ace", tid, path=path)
        db.insert_alias("AcePro", pid, path=path)
        # 표준명과 별명 모두 매칭
        assert db.resolve_player("Ace", path=path) == (pid, tid)
        assert db.resolve_player("AcePro", path=path) == (pid, tid)
        assert db.resolve_player("Unknown", path=path) is None
    finally:
        os.unlink(path)


def test_insert_match_and_count_between():
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        assert db.match_count_between(t1, t2, path=path) == 0
        db.insert_match("HP", "Combine", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        assert db.match_count_between(t1, t2, path=path) == 1
        # 순서 바껴도 같은 쌍으로 카운트
        assert db.match_count_between(t2, t1, path=path) == 1
    finally:
        os.unlink(path)


def test_insert_player_stats_hp_unique_constraint():
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        pid = db.insert_player("Ace", t1, path=path)
        mid = db.insert_match("HP", "Combine", "2026-08-01", t1, t2,
                              250, 200, "round_robin", path=path)
        db.insert_player_stats_hp(mid, pid, t1, kills=20, deaths=10,
                                  assists=5, damage=3000, obj_time=100,
                                  capture_kill=2, path=path)
        # 중복 (match_id, player_id) → 무시되거나 에러 없이 통과
        db.insert_player_stats_hp(mid, pid, t1, kills=99, deaths=99,
                                  assists=0, damage=0, obj_time=0,
                                  capture_kill=0, path=path)
        # 첫 번째 값 유지 확인
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT kills FROM player_stats_hp WHERE match_id=? AND player_id=?",
            (mid, pid)).fetchone()
        conn.close()
        assert row[0] == 20  # 두 번째 INSERT 무시됨
    finally:
        os.unlink(path)
