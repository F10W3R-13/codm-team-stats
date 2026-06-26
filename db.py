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


# ── 스키마 (SQLite 기본 작성, _adapt_sql이 Postgres로 변환) ───────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ign         TEXT NOT NULL,
    player_id   INTEGER NOT NULL REFERENCES players(id),
    UNIQUE(ign)
);

CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mode            TEXT NOT NULL CHECK (mode IN ('HP', 'SND')),
    map_name        TEXT,
    match_date      TEXT,
    raw_date        TEXT,
    result          TEXT,
    team_score      INTEGER,
    opponent_score  INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_matches_mode  ON matches(mode);
CREATE INDEX IF NOT EXISTS idx_matches_date  ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(result);

CREATE TABLE IF NOT EXISTS player_stats_hp (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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
    """SQL 方言 변환. 코드는 SQLite 스타일(기본)로 작성하고 Postgres로 변환.

    SQLite(코드 원본) → Postgres 변환 규칙:
      - ? → %s (플레이스홀더)
      - datetime('now') → NOW()
      - date('now', '-N days') → CURRENT_DATE - INTERVAL 'N days'
      - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL (SCHEMA 전용)
      - INSERT OR REPLACE → ON CONFLICT DO UPDATE (upsert 헬퍼에서 처리)
      - INSERT OR IGNORE → ON CONFLICT DO NOTHING
      - COLLATE NOCASE → 제거 (Postgres 미지원)
      - PRAGMA table_info → Postgres information_schema (호출부 분기)

    SQLite 로컬에서는 원본 그대로 통과.
    """
    if not USE_POSTGRES:
        return sql  # SQLite 원본 그대로

    # SQLite → Postgres 변환
    import re
    out = sql
    # SCHEMA 전용: SQLite AUTOINCREMENT → Postgres SERIAL
    out = out.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    out = out.replace("?", "%s")
    out = out.replace("datetime('now')", "NOW()")
    # date('now', '-N days') → CURRENT_DATE - INTERVAL 'N days'
    out = re.sub(
        r"date\('now',\s*'-(\d+) days'\)",
        r"CURRENT_DATE - INTERVAL '\1 days'",
        out,
    )
    out = re.sub(
        r"date\('now'\)",
        "CURRENT_DATE",
        out,
    )
    # INSERT OR IGNORE → ON CONFLICT DO NOTHING
    out = re.sub(
        r"INSERT OR IGNORE INTO (\w+)",
        r"INSERT INTO \1",
        out,
    )
    # COLLATE NOCASE → Postgres 미지원, 제거
    out = out.replace(" COLLATE NOCASE", "")
    return out


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
            # 마이그레이션: 새 컬럼 추가 (SQLite 전용 — Postgres는 SCHEMA에 이미 포함)
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

    def execute_returning_id(self, sql, params=()):
        """INSERT 후 새 행의 id를 반환. SQLite는 lastrowid, Postgres는 RETURNING.

        SQL은 'INSERT INTO ... VALUES (...)' 형태여야 하며,
        Postgres용으로 자동으로 'RETURNING id'가 붙는다.
        """
        sql = _adapt_sql(sql)
        if USE_POSTGRES:
            if "returning" not in sql.lower():
                sql = sql.rstrip(";") + " RETURNING id"
            import psycopg2.extras
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, _adapt_params(params))
            row = cur.fetchone()
            return row["id"] if row else None
        else:
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(sql, _adapt_params(params))
            return cur.lastrowid

    def upsert(self, table: str, columns: list, values: tuple,
               conflict_col: str, update_cols: list = None):
        """UPSERT (있으면 업데이트, 없으면 삽입). 새 id 반환.

        SQLite: INSERT OR REPLACE
        Postgres: INSERT ... ON CONFLICT(conflict_col) DO UPDATE SET ...
        """
        placeholders = ", ".join(["?"] * len(columns))
        col_list = ", ".join(columns)
        if USE_POSTGRES:
            placeholders = ", ".join(["%s"] * len(columns))
            if update_cols:
                set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                sql = (f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                       f"ON CONFLICT ({conflict_col}) DO UPDATE SET {set_clause} RETURNING id")
            else:
                sql = (f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                       f"ON CONFLICT ({conflict_col}) DO NOTHING RETURNING id")
            import psycopg2.extras
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, values)
            row = cur.fetchone()
            return row["id"] if row else None
        else:
            sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(sql, values)
            return cur.lastrowid

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
        # Postgres는 lastrowid 미지원 → execute_returning_id (RETURNING id) 사용
        player_id = conn.execute_returning_id(
            "INSERT INTO players(name) VALUES (?)", (name,)
        )

    if ign_raw and ign_raw.strip() and ign_raw.strip() != name:
        try:
            # SQLite: INSERT OR IGNORE, Postgres: ON CONFLICT DO NOTHING (_adapt_sql이 처리)
            conn.execute(
                "INSERT OR IGNORE INTO aliases(ign, player_id) VALUES (?, ?)",
                (ign_raw.strip(), player_id),
            )
        except Exception:
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
