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
import logging

log = logging.getLogger("codm-db")

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
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mode                TEXT NOT NULL CHECK (mode IN ('HP', 'SND')),
    map_name            TEXT,
    match_date          TEXT,
    raw_date            TEXT,
    result              TEXT,
    team_score          INTEGER,
    opponent_score      INTEGER,
    coach_note          TEXT,
    vod_url             TEXT,
    transcript_summary  TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
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

-- 날짜 단위 복기 데이터 (VOD/코치메모/전사요약). matches가 매치 단위라
-- 하루치 VOD/전사가 매치마다 중복 저장되는 문제를 해결하기 위해 날짜 PK로 분리.
CREATE TABLE IF NOT EXISTS match_day_notes (
    match_date          TEXT PRIMARY KEY,
    coach_note          TEXT,
    vod_url             TEXT,
    transcript_summary  TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 코칭 노트 (액션 아이템) — "다음 매치 전에 고칠 것". 복기→준비 루프.
-- open: 허브 최상단 표시. done: 허브 숨김, 매치 상세에서만 이력 확인.
CREATE TABLE IF NOT EXISTS coaching_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,
    match_id    INTEGER,                 -- 어느 매치 복기에서 나왔는지 (nullable)
    player_id   INTEGER,                 -- 특정 선수 태그 (nullable)
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);
CREATE INDEX IF NOT EXISTS idx_coaching_notes_status ON coaching_notes(status);
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
    # 괄호 중첩(AVG(MAX(0,...)) 등)도 처리: 짝이 맞는 닫는 괄호까지 매칭.
    def _add_numeric_cast(sql: str) -> str:
        out = []
        i = 0
        while i < len(sql):
            m = re.match(r'AVG\(', sql[i:], flags=re.IGNORECASE)
            if m:
                start = i + len(m.group(0)) - 1  # '(' 위치
                depth = 0
                j = start
                while j < len(sql):
                    if sql[j] == '(':
                        depth += 1
                    elif sql[j] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                # AVG(...) 전체 블록 (i부터 j 포함)
                block = sql[i:j + 1]
                out.append(block + "::numeric")
                i = j + 1
            else:
                out.append(sql[i])
                i += 1
        return "".join(out)

    out = _add_numeric_cast(out)
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
    """현재는 변환 불필요 (SQLite/Postgres 양쪽 같은 params 형식 사용). 향후 方言 차이 시 확장 지점."""
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
                # 동시 init_db(다중 워커)가 ALTER TABLE을 병렬로 실행해 데드락이 나는 것을 방지.
                # 어드바이저 락으로 직렬화. autocommit 모드여야 즉시 락 획득/해제.
                cur.execute("SELECT pg_advisory_lock(89473124)")  # 고정 키
                try:
                    cur.execute(_adapt_sql(SCHEMA))
                    # 마이그레이션: aliases.source 컬럼 (기존 Postgres DB엔 source 없이 생성되어 있음)
                    cur.execute(
                        "ALTER TABLE aliases ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'Manual'"
                    )
                    # 마이그레이션: matches 복기 워크플로우 컬럼 (코치 메모 / VOD 링크 / 전사 요약)
                    cur.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS coach_note TEXT")
                    cur.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS vod_url TEXT")
                    cur.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS transcript_summary TEXT")
                    conn.commit()
                finally:
                    cur.execute("SELECT pg_advisory_unlock(89473124)")
    else:
        with sqlite3.connect(DB_PATH) as conn:
            schema_no_result_idx = SCHEMA.replace(
                "CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(result);", ""
            )
            conn.executescript(_adapt_sql(schema_no_result_idx))
            # 마이그레이션: 새 컬럼 추가 (SQLite 전용 — Postgres는 SCHEMA에 이미 포함)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
            for col, decl in [("result", "TEXT"), ("team_score", "INTEGER"),
                              ("opponent_score", "INTEGER"),
                              ("coach_note", "TEXT"), ("vod_url", "TEXT"),
                              ("transcript_summary", "TEXT")]:
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
        """UPSERT (있으면 업데이트, 없으면 삽입). 새 id 반환 (없으면 None).

        SQLite: INSERT OR REPLACE
        Postgres: INSERT ... ON CONFLICT(conflict_col) DO UPDATE SET ...

        ★ RETURNING id 를 무조건 붙이지 않음 — id 컬럼이 없는 테이블
          (예: match_day_notes, PK=match_date)에선 Postgres에서
          "column id does not exist" 에러. id 컬럼이 있는 테이블만 반환.
        """
        placeholders = ", ".join(["?"] * len(columns))
        col_list = ", ".join(columns)
        if USE_POSTGRES:
            placeholders = ", ".join(["%s"] * len(columns))
            # id 컬럼 존재 여부 판단 — 정보 스키마에서 조회
            has_id = self._has_column(table, "id")
            returning = " RETURNING id" if has_id else ""
            if update_cols:
                set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                sql = (f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                       f"ON CONFLICT ({conflict_col}) DO UPDATE SET {set_clause}{returning}")
            else:
                sql = (f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                       f"ON CONFLICT ({conflict_col}) DO NOTHING{returning}")
            import psycopg2.extras
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, values)
            if returning:
                row = cur.fetchone()
                return row["id"] if row else None
            return None
        else:
            sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(sql, values)
            return cur.lastrowid

    def _has_column(self, table: str, column: str) -> bool:
        """Postgres 전용 — 테이블에 특정 컬럼이 있는지 조회. SQLite는 미사용."""
        if not USE_POSTGRES:
            return False
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s",
                (table, column),
            )
            return cur.fetchone() is not None
        except Exception as e:
            log.warning(f"[_has_column] {table}.{column} 확인 실패: {e}")
            return False

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
    except Exception as e:
        log.warning(f"[_learn_alias] {ign} → player_id={player_id} 학습 실패: {e}")
        # UNIQUE 충돌 등 — 이미 학습됐거나 다른 선수에게 할당됨. 부수 기능이라 삼킴.


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
        except Exception as e:
            log.warning(f"[add_alias] {ign} → {player_name} 등록 실패: {e}")
            return {"ok": False, "message": f"`{ign}` alias 등록 중 충돌 (이미 존재하거나 DB 오류): {e}"}
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


# ── 선수 병합 (게스트 → 정식 선수, 또는 선수 → 선수) ──────────────────
# 미매칭 닉네임 전용 뷰는 선수관리 탭(/admin/players)으로 통합되었다.
# list_unmatched_players/ROSTER_NAMES 는 제거 — 동일 병합 엔진을 선수관리 탭에서 재사용.


def merge_player(src_player_id: int, dst_player_name: str) -> dict:
    """게스트(src)를 정식 선수(dst)로 병합.

    src 의 모든 매치 스탯/alias 를 dst 로 옮긴 뒤 src 행 삭제.
    같은 매치에 src/dst 둘 다 있으면 충돌(UNIQUE(match_id,player_id)) — 그런 행은 스킵.
    """
    with get_conn() as conn:
        # dst player 확보 (없으면 생성)
        dst_sql = (
            "SELECT id FROM players WHERE LOWER(name) = LOWER(%s)" if USE_POSTGRES else
            "SELECT id FROM players WHERE name = ? COLLATE NOCASE"
        )
        row = conn.execute(dst_sql, (dst_player_name,)).fetchone()
        dst_id = row["id"] if row else conn.execute_returning_id(
            "INSERT INTO players(name) VALUES (?)", (dst_player_name,)
        )
        if dst_id == src_player_id:
            return {"ok": False, "message": "같은 선수입니다"}

        # alias 이관.
        # 1) dst 에 이미 존재하는 ign (충돌) — src 행을 먼저 리스트업 후 삭제
        # 2) 남은 src alias 는 player_id 를 dst 로 UPDATE
        # (SELECT 커서 순회 중 INSERT/UPDATE 시 SQLite 커서 충돌 방지를 위해 id 리스트로 선수집)
        src_alias_igns = [r["ign"] for r in conn.execute(
            "SELECT ign FROM aliases WHERE player_id = ?", (src_player_id,)
        ).fetchall()]
        if src_alias_igns:
            # 충돌 ign (dst 에 이미 있음) 삭제
            placeholders_ign = ",".join(["?"] * len(src_alias_igns))
            conn.execute(
                f"DELETE FROM aliases WHERE player_id = ? AND ign IN ("
                f"SELECT ign FROM aliases WHERE player_id = ? AND ign IN ({placeholders_ign}))",
                (src_player_id, dst_id, *src_alias_igns),
            )
            # 남은 src alias 를 dst 로 이관
            conn.execute(
                "UPDATE aliases SET player_id = ? WHERE player_id = ?",
                (dst_id, src_player_id),
            )

        # 매치 스탯 이관: 같은 match_id 에 dst 가 이미 있으면 충돌 행은 삭제(src 버림)
        for tbl in ("player_stats_hp", "player_stats_snd"):
            # 충돌행(같은 match_id 에 dst 있음) 먼저 삭제
            conn.execute(
                f"DELETE FROM {tbl} WHERE player_id = ? AND match_id IN "
                f"(SELECT match_id FROM {tbl} WHERE player_id = ?)",
                (src_player_id, dst_id),
            )
            conn.execute(
                f"UPDATE {tbl} SET player_id = ? WHERE player_id = ?",
                (dst_id, src_player_id),
            )

        # src player 행 삭제
        conn.execute("DELETE FROM players WHERE id = ?", (src_player_id,))
        return {"ok": True, "message": f"✅ 병합 완료 → {dst_player_name}", "dst": dst_player_name}
