"""토너먼트 전용 SQLite 스키마 + CRUD.

부모 db.py와 완전 분리 — 별도 파일(tournament.db), 별도 스키마.
모든 함수는 path 인자로 DB 파일 지정 (기본값: 이 파일 옆 tournament.db).
"""
import os
import sqlite3

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tournament.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    seed INTEGER
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    UNIQUE(name, team_id)
);
CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY,
    ign TEXT UNIQUE NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(id)
);
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    map_name TEXT,
    match_date TEXT,
    stage TEXT NOT NULL DEFAULT 'round_robin',
    team_a_id INTEGER NOT NULL REFERENCES teams(id),
    team_b_id INTEGER NOT NULL REFERENCES teams(id),
    team_a_score INTEGER,
    team_b_score INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS player_stats_hp (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    kills INTEGER, deaths INTEGER, assists INTEGER,
    damage INTEGER, obj_time REAL, capture_kill INTEGER,
    UNIQUE(match_id, player_id)
);
CREATE TABLE IF NOT EXISTS player_stats_snd (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    kills INTEGER, deaths INTEGER, assists INTEGER,
    damage INTEGER, adr REAL,
    first_kill INTEGER, lone_wolf_win INTEGER,
    UNIQUE(match_id, player_id)
);
"""


def get_conn(path: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DEFAULT_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str = None) -> None:
    conn = get_conn(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_team(name: str, seed: int = None, path: str = None) -> int:
    conn = get_conn(path)
    try:
        cur = conn.execute("INSERT INTO teams(name, seed) VALUES(?, ?)", (name, seed))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # 이미 존재 → 기존 id 반환
        row = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
        return row["id"]
    finally:
        conn.close()


def insert_player(name: str, team_id: int, path: str = None) -> int:
    conn = get_conn(path)
    try:
        cur = conn.execute(
            "INSERT INTO players(name, team_id) VALUES(?, ?)", (name, team_id))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT id FROM players WHERE name=? AND team_id=?",
            (name, team_id)).fetchone()
        return row["id"]
    finally:
        conn.close()


def insert_alias(ign: str, player_id: int, path: str = None) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO aliases(ign, player_id) VALUES(?, ?)",
            (ign, player_id))
        conn.commit()
    finally:
        conn.close()


def resolve_player(ign: str, path: str = None):
    """IGN → (player_id, team_id) 매핑. 표준명/별명 모두 검색.
    매칭 실패 시 None 반환.

    대소문자/클랜태그/특수문자/숫자접미사를 정규화하여 포괄적으로 매칭:
    -MaDara- → madara, Madara → madara (일치)
    Hashirama6974 → hashirama, Hashirama → hashirama (숫자접미사 제거 후 일치)
    """
    import re

    def _norm(s):
        # 소문자화 + 클랜태그/특수문자 제거 + 끝의 숫자 접미사 제거
        s = s.lower().strip()
        s = re.sub(r"\[.*?\]", "", s)       # 클랜태그
        s = re.sub(r"[^a-z0-9가-힣]", "", s)  # 알파벳+숫자+한글만
        s = re.sub(r"\d+$", "", s)           # 끝 숫자 접미사 (6974 등)
        return s

    norm_ign = _norm(ign)
    conn = get_conn(path)
    try:
        # 1) players 표준명 매칭 (정확 → 정규화)
        row = conn.execute(
            """SELECT p.id, p.team_id, p.name FROM players p
               WHERE p.name = ? OR LOWER(p.name) = ?""", (ign, norm_ign)).fetchone()
        if row:
            return (row["id"], row["team_id"])
        # 2) aliases 매칭 (정확 → 정규화)
        for r in conn.execute(
                """SELECT a.player_id, p.team_id, a.ign FROM aliases a
                   JOIN players p ON p.id = a.player_id""").fetchall():
            if _norm(r["ign"]) == norm_ign:
                return (r["player_id"], r["team_id"])
        return None
    finally:
        conn.close()


def insert_match(mode, map_name, match_date, team_a_id, team_b_id,
                 team_a_score, team_b_score, stage="round_robin",
                 path: str = None) -> int:
    conn = get_conn(path)
    try:
        cur = conn.execute(
            """INSERT INTO matches(mode, map_name, match_date, stage,
                   team_a_id, team_b_id, team_a_score, team_b_score)
               VALUES(?,?,?,?,?,?,?,?)""",
            (mode, map_name, match_date, stage,
             team_a_id, team_b_id, team_a_score, team_b_score))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_player_stats_hp(match_id, player_id, team_id, *,
                           kills=0, deaths=0, assists=0, damage=0,
                           obj_time=0, capture_kill=0, path: str = None) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO player_stats_hp
               (match_id, player_id, team_id, kills, deaths, assists,
                damage, obj_time, capture_kill)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (match_id, player_id, team_id, kills, deaths, assists,
             damage, obj_time, capture_kill))
        conn.commit()
    finally:
        conn.close()


def insert_player_stats_snd(match_id, player_id, team_id, *,
                            kills=0, deaths=0, assists=0, damage=0,
                            adr=0, first_kill=0, lone_wolf_win=0,
                            path: str = None) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO player_stats_snd
               (match_id, player_id, team_id, kills, deaths, assists,
                damage, adr, first_kill, lone_wolf_win)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (match_id, player_id, team_id, kills, deaths, assists,
             damage, adr, first_kill, lone_wolf_win))
        conn.commit()
    finally:
        conn.close()


def match_count_between(team_a_id: int, team_b_id: int, path: str = None) -> int:
    """두 팀이 이미 치른 매치 수 (순서 무관). stage 판별용."""
    conn = get_conn(path)
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM matches
               WHERE (team_a_id=? AND team_b_id=?)
                  OR (team_a_id=? AND team_b_id=?)""",
            (team_a_id, team_b_id, team_b_id, team_a_id)).fetchone()
        return row["c"]
    finally:
        conn.close()


def list_teams(path: str = None) -> list:
    conn = get_conn(path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM teams ORDER BY seed, name").fetchall()]
    finally:
        conn.close()


def list_players(team_id: int = None, path: str = None) -> list:
    conn = get_conn(path)
    try:
        if team_id is None:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM players ORDER BY team_id, name").fetchall()]
        return [dict(r) for r in conn.execute(
            "SELECT * FROM players WHERE team_id=? ORDER BY name",
            (team_id,)).fetchall()]
    finally:
        conn.close()
