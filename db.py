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
    source      TEXT NOT NULL DEFAULT 'Manual',
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
    # AVG(...) → AVG(...)::numeric — Postgres는 ROUND(double) 불가, numeric 캐스팅 필요.
    # AVG 내부는 단순 컬럼(중첩 괄호 없음)으로 가정.
    out = re.sub(
        r"(AVG\([^()]*\))",
        r"\1::numeric",
        out,
    )
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
    # MAX(0, expr) (SQLite 전용 2-arg 최대) → Postgres GREATEST(0, expr)
    # SQLite는 GREATEST 미지원이므로 코드 원본은 MAX(0, ...)로 작성.
    import re
    out = re.sub(r"MAX\(0,\s*([^)]+)\)", r"GREATEST(0, \1)", out)
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
                # 마이그레이션: aliases.source 컬럼 (기존 Postgres DB엔 source 없이 생성되어 있음)
                cur.execute(
                    "ALTER TABLE aliases ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'Manual'"
                )
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
            # 마이그레이션: aliases.source 컬럼 (감사 추적 — Manual/OCR Auto)
            alias_cols = {row[1] for row in conn.execute("PRAGMA table_info(aliases)").fetchall()}
            if "source" not in alias_cols:
                conn.execute("ALTER TABLE aliases ADD COLUMN source TEXT NOT NULL DEFAULT 'Manual'")
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
    """표준 이름/alias로 player_id 조회/생성 + alias 자가학습.

    매칭 순서 (안전망):
      1) aliases.ign 역참조 (정확 → 대소문자 무시) — 이전에 자가학습된 변형
      2) players.name (정확 → COLLATE NOCASE)
      3) 신규 생성
    ign_raw가 표준 name과 다르면 자동으로 alias에 저장(자가학습). 이미 다른 선수에게
    할당된 변형이면 덮어쓰지 않음.
    """
    name = (name or "").strip() or "Unknown"
    ign_raw = (ign_raw or "").strip()
    player_id = None

    # 1) alias 역참조: ign_raw가 있으면 그것을 먼저, 없으면 name 자체로
    lookup = ign_raw if ign_raw and ign_raw != name else name
    if lookup and lookup != "Unknown":
        alias_sql = (
            "SELECT a.player_id FROM aliases a "
            "WHERE LOWER(a.ign) = LOWER(%s)" if USE_POSTGRES else
            "SELECT a.player_id FROM aliases a WHERE a.ign = ? COLLATE NOCASE"
        )
        row = conn.execute(alias_sql, (lookup,)).fetchone()
        if row:
            player_id = row["player_id"]

    # 2) players.name (정확 → 대소문자 무시)
    if not player_id:
        name_sql = (
            "SELECT id FROM players WHERE LOWER(name) = LOWER(%s)" if USE_POSTGRES else
            "SELECT id FROM players WHERE name = ? COLLATE NOCASE"
        )
        row = conn.execute(name_sql, (name,)).fetchone()
        if row:
            player_id = row["id"]

    # 3) 신규 생성
    if not player_id:
        player_id = conn.execute_returning_id(
            "INSERT INTO players(name) VALUES (?)", (name,)
        )

    # 자가학습: ign_raw가 표준 name과 다르면 alias 영구 저장 (다음 매칭 비용 0)
    if ign_raw and ign_raw != name:
        _learn_alias(conn, ign_raw, player_id, source="OCR Auto")
    return player_id


def _learn_alias(conn, ign: str, player_id: int, source: str = "OCR Auto"):
    """변형 IGN을 alias에 영구 저장. 충돌 시 안전하게 무시(덮어쓰지 않음)."""
    try:
        if USE_POSTGRES:
            conn.execute(
                "INSERT INTO aliases(ign, player_id, source) VALUES (%s, %s, %s) "
                "ON CONFLICT (ign) DO NOTHING",
                (ign, player_id, source),
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO aliases(ign, player_id, source) VALUES (?, ?, ?)",
                (ign, player_id, source),
            )
    except Exception:
        pass  # UNIQUE 충돌 등 — 이미 학습됐거나 다른 선수에게 할당됨


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
            conn.execute(
                "INSERT INTO aliases(ign, player_id, source) VALUES (?, ?, 'Manual')",
                (ign, pid),
            )
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


def list_aliases(player_name: str = None, source: str = None) -> list:
    """닉네임 목록. source 필터('Manual'/'OCR Auto')와 반환 dict에 source 포함.

    기존 호출자(반환 dict ign/player_name만 쓰는 곳) 호환 유지.
    """
    with get_conn() as conn:
        # source 컬럼이 마이그레이션 전 DB엔 없을 수 있어 LEFT JOIN 시 NULL 허용
        sql = (
            "SELECT a.ign ign, p.name player_name, a.source AS source "
            "FROM aliases a JOIN players p ON p.id=a.player_id "
            "WHERE 1=1"
        )
        params = []
        if player_name:
            sql += " AND p.name = ? COLLATE NOCASE"
            params.append(player_name.strip())
        if source:
            sql += " AND a.source = ?"
            params.append(source)
        sql += " ORDER BY p.name, a.ign"
        rows = conn.execute(sql, params).fetchall()
        return [{"ign": r["ign"],
                 "player_name": r["player_name"],
                 "source": r["source"] or "Manual"}
                for r in rows]
