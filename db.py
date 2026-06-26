# 데이터베이스 스키마 및 헬퍼 — SQLite / PostgreSQL 양쪽 지원
#
# 환경변수 DATABASE_URL 이 있으면 Postgres, 없으면 로컬 SQLite.
# Railway 배포 시 DATABASE_URL(Postgres) 자동 주입.
# 로컬 개발 시는 codm.db (SQLite).
#
# SQL 方言 차이:
#   - AUTOINCREMENT → SERIAL(Postgres) / AUTOINCREMENT(SQLite)
#   - datetime('now') → NOW()
#   - 플레이스홀더 ?(SQLite) → %s(Postgres) — psycopg2는 ? 를 쓸 수 없으므로
#     get_conn() 이 반환하는 커서는 통일된 execute(sql, params) 인터페이스를 쓴다.
#     단, psycopg2는 %s, sqlite3 는 ? 라서 _adapt_sql() 로 변환한다.

import os
import sqlite3

# DB 종류 판별
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

# SQLite 경로 (로컬 전용)
DB_PATH = os.environ.get("CODM_DB_PATH", "codm.db")


# ── 스키마 (Postgres/SQLite 공통, 방언은 _adapt 처리) ─────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (NOW())
);

CREATE TABLE IF NOT EXISTS aliases (
    id          SERIAL PRIMARY KEY,
    ign         TEXT NOT NULL,
    player_id   INTEGER NOT NULL REFERENCES players(id),
    UNIQUE(ign)
);

CREATE TABLE IF NOT EXISTS matches (
    id              SERIAL PRIMARY KEY,
    mode            TEXT NOT NULL CHECK (mode IN ('HP', 'SND')),
    map_name        TEXT,
    match_date      TEXT,
    raw_date        TEXT,
    result          TEXT,
    team_score      INTEGER,
    opponent_score  INTEGER,
    created_at      TEXT NOT NULL DEFAULT (NOW())
);

CREATE INDEX IF NOT EXISTS idx_matches_mode  ON matches(mode);
CREATE INDEX IF NOT EXISTS idx_matches_date  ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(result);

CREATE TABLE IF NOT EXISTS player_stats_hp (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    player_id       INTEGER NOT NULL REFERENCES players(id),
    ign_raw         TEXT,
    kills           INTEGER,
    deaths          INTEGER,
    kd_ratio        REAL,
    obj_time        INTEGER,
    score           INTEGER,
    impact          REAL,
    total_damage    INTEGER,
    capture_kill    INTEGER,
    UNIQUE(match_id, player_id)
);

CREATE TABLE IF NOT EXISTS player_stats_snd (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    player_id       INTEGER NOT NULL REFERENCES players(id),
    ign_raw         TEXT,
    kills           INTEGER,
    deaths          INTEGER,
    assists         INTEGER,
    kd_ratio        REAL,
    score           INTEGER,
    impact          REAL,
    adr             REAL,
    first_kill      INTEGER,
    lone_wolf_win   INTEGER,
    UNIQUE(match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_hp_player  ON player_stats_hp(player_id);
CREATE INDEX IF NOT EXISTS idx_snd_player ON player_stats_snd(player_id);
"""


def _adapt_sql(sql: str) -> str:
    """SQL 方言 변환.
    Postgres: SERIAL, NOW(), %s, GROUP BY LOWER 등은 그대로.
    SQLite: SERIAL → INTEGER ... AUTOINCREMENT, NOW() → datetime('now'), %s → ?
    """
    if USE_POSTGRES:
        return sql
    # SQLite 변환
    return (sql
            .replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
            .replace("NOW()", "datetime('now')")
            .replace("%s", "?"))


def _adapt_params(params):
    """psycopg2는 단일 param을 튜플/리스트로 감싸야 할 때가 있어 통일."""
    return params


def init_db() -> None:
    """DB 생성 + 스키마 적용 + 마이그레이션(SLite만).

    Postgres: SCHEMA 그대로 실행 (CREATE IF NOT EXISTS).
    SQLite: 기존 matches에 result/team_score/opponent_score 컬럼 없으면 추가.
    """
    if USE_POSTGRES:
        import psycopg2
        with psycopg2.connect(DATABASE_URL) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(_adapt_sql(SCHEMA))
            conn.commit()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            schema_no_result_idx = SCHEMA.replace(
                "CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(result);", ""
            )
            conn.executescript(_adapt_sql(schema_no_result_idx))
            # 마이그레이션: 새 컬럼 추가
            cols = {row[1] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
            for col, decl in [("result", "TEXT"), ("team_score", "INTEGER"),
                              ("opponent_score", "INTEGER")]:
                if col not in cols:
                    conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {decl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(result)")
            conn.commit()


class _RowDict(dict):
    """sqlite3.Row 와 psycopg2 dict 커서 양쪽을 dict 처럼 쓰기 위한 래퍼.
    키 접근과 인덱스 접근(0,1,2..) 모두 지원."""
    pass


class _ConnAdapter:
    """sqlite3.Connection / psycopg2 connection 을 동일 인터페이스로 감쌈.

    execute(sql, params) → row dict 리스트를 반환하는 '커서' 객체를 반환.
    row['col'], row[0] 모두 지원.
    """

    def __init__(self, raw_conn):
        self._conn = raw_conn
        if USE_POSTGRES:
            # psycopg2 RealDictCursor 사용
            pass

    def execute(self, sql, params=()):
        sql = _adapt_sql(sql)
        if USE_POSTGRES:
            import psycopg2.extras
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, _adapt_params(params))
            return cur
        else:
            self._conn.row_factory = sqlite3.Row
            return self._conn.execute(sql, _adapt_params(params))

    def executescript(self, script):
        script = _adapt_sql(script)
        if USE_POSTGRES:
            with self._conn.cursor() as cur:
                cur.execute(script)
        else:
            self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


from contextlib import contextmanager


@contextmanager
def get_conn():
    """커넥션 컨텍스트 매니저. row_factory=dict-like 로 접근."""
    if USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(DB_PATH)
    try:
        adapter = _ConnAdapter(conn)
        yield adapter
        conn.commit()
    finally:
        conn.close()


def resolve_player_id(conn, name: str, ign_raw: str = None) -> int:
    """표준 이름으로 player_id 조회/생성."""
    name = (name or "").strip() or "Unknown"
    cur = conn.execute("SELECT id FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        player_id = row["id"]
    else:
        cur = conn.execute("INSERT INTO players(name) VALUES (?)", (name,))
        player_id = cur.lastrowid

    if ign_raw and ign_raw.strip() and ign_raw.strip() != name:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO aliases(ign, player_id) VALUES (?, ?)",
                (ign_raw.strip(), player_id),
            )
        except Exception:
            # Postgres 는 INSERT OR IGNORE 미지원 → ON CONFLICT 로 처리되어야 하지만
            # 여기서는 UNIQUE 위반 시 무시하도록 예외 흡수
            pass
    return player_id


def add_alias(ign: str, player_name: str) -> dict:
    """새 닉네임(IGN) → 선수 매핑 등록."""
    ign = ign.strip()
    player_name = player_name.strip()
    if not ign or not player_name:
        return {"ok": False, "message": "IGN과 선수 이름 모두 필요합니다"}

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT a.player_id, p.name FROM aliases a JOIN players p ON p.id=a.player_id WHERE a.ign=?",
            (ign,),
        ).fetchone()
        if existing and existing["name"].lower() == player_name.lower():
            return {"ok": True, "message": f"이미 `{ign}` → `{player_name}` 으로 등록되어 있습니다",
                    "player": player_name, "ign": ign}
        if existing and existing["name"].lower() != player_name.lower():
            return {"ok": False,
                    "message": f"`{ign}` 은 이미 `{existing['name']}` 에게 할당되어 있습니다. "
                               f"변경하려면 먼저 /removealias 로 삭제하세요.",
                    "player": existing["name"], "ign": ign}

        pid = resolve_player_id(conn, player_name)
        try:
            conn.execute("INSERT INTO aliases(ign, player_id) VALUES (?, ?)", (ign, pid))
        except Exception:
            return {"ok": False, "message": f"`{ign}` alias 등록 중 충돌 (이미 존재할 수 있음)"}
        return {"ok": True, "message": f"✅ `{ign}` → `{player_name}` 등록 완료",
                "player": player_name, "ign": ign}


def remove_alias(ign: str) -> dict:
    """닉네임 매핑 삭제."""
    ign = ign.strip()
    if not ign:
        return {"ok": False, "message": "IGN을 입력하세요"}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT a.player_id, p.name FROM aliases a JOIN players p ON p.id=a.player_id WHERE a.ign=?",
            (ign,),
        ).fetchone()
        if not row:
            return {"ok": False, "message": f"`{ign}` 은 등록된 alias가 없습니다",
                    "player": None, "ign": ign}
        conn.execute("DELETE FROM aliases WHERE ign=?", (ign,))
        return {"ok": True, "message": f"🗑️ `{ign}` (→ {row['name']}) 삭제 완료",
                "player": row["name"], "ign": ign}


def list_aliases(player_name: str = None) -> list:
    """닉네임 목록."""
    with get_conn() as conn:
        if player_name:
            rows = conn.execute(
                """SELECT a.ign ign, p.name player_name
                   FROM aliases a JOIN players p ON p.id=a.player_id
                   WHERE p.name=? COLLATE NOCASE ORDER BY a.ign""",
                (player_name.strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.ign ign, p.name player_name
                   FROM aliases a JOIN players p ON p.id=a.player_id
                   ORDER BY p.name, a.ign"""
            ).fetchall()
        return [{"ign": r["ign"], "player_name": r["player_name"]} for r in rows]
