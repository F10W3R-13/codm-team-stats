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


def test_insert_player_stats_snd_value_count():
    """SND INSERT — 컬럼 10개에 VALUES 자리표시자 10개 일치 (회귀 방지).

    이전 버그: VALUES(?,?,?,?,?,?,?,?,?) — 9개 자리표시자라
    '9 values for 10 columns' 에러로 SND 매치 저장 전체 실패.
    """
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        pid = db.insert_player("Ace", t1, path=path)
        mid = db.insert_match("SND", "Coastal", "2026-08-01", t1, t2,
                              6, 4, "round_robin", path=path)
        db.insert_player_stats_snd(mid, pid, t1, kills=17, deaths=12,
                                   assists=1, damage=2000, adr=150,
                                   first_kill=2, lone_wolf_win=1, path=path)
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT kills, adr, first_kill, lone_wolf_win FROM player_stats_snd "
            "WHERE match_id=? AND player_id=?", (mid, pid)).fetchone()
        conn.close()
        assert row[0] == 17
        assert row[1] == 150
        assert row[2] == 2
        assert row[3] == 1
    finally:
        os.unlink(path)
