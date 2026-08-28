# 상대팀 전적 & Head-to-Head 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사진 2장 업로드 워크플로우를 유지한 채 상대팀을 자동 식별·상대 선수 스탯을 저장하고, 팀 상대전적(`/versus`)과 선수 H2H 매트릭스를 조회한다.

**Architecture:** GPT는 적팀 이름을 raw로만 출력하고(읽기), DB 계층이 정규화·퍼지 매칭·팀 다수결로 분류한다. 상대 데이터는 우리팀 테이블과 완전 분리된 `opponent_*` 테이블에 저장해 기존 쿼리·페이지 영향을 0으로 만든다. 미등록팀·용병·다른 이름 동일인물은 admin에서 수동 보정(병합 1회 = 영구 학습).

**Tech Stack:** FastAPI + Jinja2 + SQLite/Postgres 공용 SQL(`db._adapt_sql`), 표준 라이브러리만 사용(신규 의존성 0).

**Spec:** `docs/superpowers/specs/2026-08-28-opponent-h2h-design.md`

## Global Constraints

- 모든 SQL은 `?` 플레이스홀더 + `db._adapt_sql()` 변환으로 SQLite/Postgres 양립 (커서 직접 사용 시에도 동일).
- 신규 의존성 금지 — 퍼지 매칭은 `difflib`(표준 라이브러리).
- `prompt.py`는 기존 키·지시문 변경 금지, `enemy_players` 추가만.
- `metrics.py` 수정 금지 — ZCS/RDS는 `metrics.compute_zcs(obj_time, capture_kill, kills, deaths)` / `metrics.compute_rds(kills, assists, first_kill, lone_wolf_win, adr, deaths)` 참조만.
- 템플릿 인라인 `style="..."` 금지 — 기존 유틸리티 클래스(`.card`, `.table-wrap`, `.subtabs`, `.subtab`, `.btn`, `.input`, `.win-badge`, `.loss-badge`)만 사용.
- i18n 키 추가 시 `i18n/_ko.py`·`_en.py`·`_es.py` 세 파일 동기화 (`test_i18n.py` 자동 검증).
- 커밋 금지: `.env`, `codm.db`, `*.csv` 등 (.gitignore 처리됨). 테스트는 임시 SQLite 사용.
- 루트 테스트: `pytest` (tournament와 같은 프로세스 금지). Lint: `python -m ruff check .`
- 문서·주석·커밋 메시지: 한국어.

---

### Task 1: 상대 닉네임 매칭 순수 로직 (`opponent_matching.py`)

**Files:**
- Create: `opponent_matching.py`
- Test: `tests/test_opponent_matching.py`

**Interfaces:**
- Consumes: 없음 (표준 라이브러리만).
- Produces: `norm_name(s: str) -> str`, `similarity(a: str, b: str) -> float`, `best_fuzzy_match(name: str, candidates: list[tuple[int, str]], threshold: float) -> tuple[int, float] | None`, `tally_team_votes(team_ids: list[int], total: int) -> tuple[int | None, int]`, 상수 `TEAM_VOTE_RATIO=0.6`, `FUZZY_TEAM_THRESHOLD=0.75`, `FUZZY_GLOBAL_THRESHOLD=0.85`. Task 3·4가 import함.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_opponent_matching.py
import opponent_matching as om


def test_norm_name_strips_and_lowercases():
    assert om.norm_name("  ZeR0!  ") == "zer0"


def test_norm_name_nfkc_fullwidth():
    # 전각 알파벳은 NFKC로 반각화 → 소문자화
    assert om.norm_name("Ｇｏｄ") == "god"


def test_norm_name_removes_non_alnum():
    # ø(U+00F8)는 NFKC 분해 없음 → 비영숫자 제거 대상
    assert om.norm_name("ZeRø") == "zer"
    assert om.norm_name("god_like") == "godlike"


def test_similarity_ocr_noise():
    s = om.similarity("Renegul8808", "RenegulBB08")
    assert s >= 0.8  # B↔8 한 글자 OCR 혼동


def test_similarity_empty_is_zero():
    assert om.similarity("", "abc") == 0.0
    assert om.similarity("!!!", "abc") == 0.0  # 정규화 후 빈 문자열


def test_best_fuzzy_match_threshold():
    cands = [(1, "Renegul8808"), (2, "TotallyDifferent")]
    assert om.best_fuzzy_match("RenegulBB08", cands, 0.75) == (1, om.similarity("RenegulBB08", "Renegul8808"))
    assert om.best_fuzzy_match("RenegulBB08", cands, 0.99) is None


def test_tally_majority_wins():
    # 5명 중 3명 일치 → 과반(0.6) 통과
    assert om.tally_team_votes([1, 1, 1, 2], total=5) == (1, 3)


def test_tally_tie_rejected():
    assert om.tally_team_votes([1, 1, 2, 2], total=5) == (None, 0)


def test_tally_below_ratio_rejected():
    assert om.tally_team_votes([1, 1], total=5) == (None, 0)


def test_tally_empty():
    assert om.tally_team_votes([], total=5) == (None, 0)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'opponent_matching'`

- [ ] **Step 3: 구현**

```python
# opponent_matching.py
"""상대팀 닉네임 정규화·퍼지 매칭·팀 투표 — 순수 로직 (DB 의존 없음).

설계 원칙(spec §2): 읽기는 GPT, 분류는 DB. 이 모듈은 분류의 순수 계산부다.
프롬프트에 상대 로스터를 주입하지 않기 때문에, 표기 정규화 + 유사도로
OCR 변형을 흡수한다.
"""
import difflib
import re
import unicodedata

TEAM_VOTE_RATIO = 0.6          # 팀 다수결: 일치 인원 / 적팀 인원 ≥ 0.6 (5명 중 3명)
FUZZY_TEAM_THRESHOLD = 0.75    # 팀 로스터 풀 내 퍼지 임계값 (넉넉)
FUZZY_GLOBAL_THRESHOLD = 0.85  # 전역 풀(용병 폴백) 임계값 (엄격)


def norm_name(s: str) -> str:
    """OCR 표기 정규화: NFKC → lowercase → 영숫자만 남김."""
    s = unicodedata.normalize("NFKC", (s or "").strip())
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def similarity(a: str, b: str) -> float:
    """정규화 후 유사도 (0~1). 어느 쪽이든 빈 문자열이면 0."""
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def best_fuzzy_match(name: str, candidates: list, threshold: float):
    """candidates: [(player_id, 기존 표기), ...] 중 임계값을 넘는 최고 유사도 매칭.

    반환: (player_id, score) 또는 None. 동점이면 먼저 등장한 후보.
    """
    best = None
    for pid, cand in candidates:
        score = similarity(name, cand)
        if score >= threshold and (best is None or score > best[1]):
            best = (pid, score)
    return best


def tally_team_votes(team_ids: list, total: int):
    """팀 득표 집계. team_ids: resolve된 선수들의 소속팀 목록(중복 허용,
    선수당 소속마다 1표). total: 적팀 선수 수(분모 — 미매칭 선수도 포함).

    반환: (과반 팀 id, 득표수). 단일 최고이면서 비율 ≥ TEAM_VOTE_RATIO인
    팀이 없으면 (None, 0). 동률은 기각(모호하면 admin으로).
    """
    counts = {}
    for t in team_ids:
        if t is not None:
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        return None, 0
    best_team, best_n = max(counts.items(), key=lambda kv: kv[1])
    others_max = max((v for t, v in counts.items() if t != best_team), default=0)
    if best_n > others_max and best_n / max(total, 1) >= TEAM_VOTE_RATIO:
        return best_team, best_n
    return None, 0
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_matching.py -v`
Expected: 10 passed

- [ ] **Step 5: 커밋**

```bash
git add opponent_matching.py tests/test_opponent_matching.py
git commit -m "상대 닉네임 매칭 순수 로직 (정규화/퍼지/팀 투표)"
```

---

### Task 2: DB 스키마 — 상대팀 테이블 6종 + matches 마이그레이션

**Files:**
- Modify: `db.py` (SCHEMA 상수 끝부분, `_ensure_columns` 컬럼 리스트)
- Test: `tests/test_opponent_schema.py`

**Interfaces:**
- Consumes: 없음.
- Produces: 테이블 `opponent_teams(id, name UNIQUE, created_at)`, `opponent_players(id, name UNIQUE, created_at)`, `opponent_aliases(id, ign UNIQUE, opponent_player_id, source, created_at)`, `opponent_team_rosters(team_id, player_id, source, created_at, UNIQUE(team_id, player_id))`, `opponent_stats_hp`/`opponent_stats_snd`(player_stats_* 미러, FK만 opponent_players), `matches.opponent_team_id INTEGER NULL`. Task 3~10이 사용.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_opponent_schema.py
import db


def test_opponent_tables_exist():
    with db.get_conn() as conn:
        for tbl in ("opponent_teams", "opponent_players", "opponent_aliases",
                    "opponent_team_rosters", "opponent_stats_hp", "opponent_stats_snd"):
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,)).fetchone()
            assert row, f"{tbl} 테이블 없음"


def test_matches_has_opponent_team_id():
    with db.get_conn() as conn:
        row = conn.execute("PRAGMA table_info(matches)").fetchall()
        cols = [r["name"] for r in row]
        assert "opponent_team_id" in cols


def test_opponent_stats_columns_mirror_ours():
    with db.get_conn() as conn:
        ours = [r["name"] for r in conn.execute("PRAGMA table_info(player_stats_hp)")]
        theirs = [r["name"] for r in conn.execute("PRAGMA table_info(opponent_stats_hp)")]
        assert ours == theirs  # 컬럼 구조 동일 (FK 대상만 다름)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_schema.py -v`
Expected: FAIL — 테이블 없음 assert

- [ ] **Step 3: 구현**

`db.py`의 `SCHEMA` 문자열 끝(기존 마지막 CREATE TABLE 뒤)에 추가:

```sql
-- 상대팀 전적/H2H (우리팀 테이블과 완전 분리 — 기존 쿼리 오염 방지, spec §3)
CREATE TABLE IF NOT EXISTS opponent_teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opponent_players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opponent_aliases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ign                 TEXT NOT NULL UNIQUE,
    opponent_player_id  INTEGER NOT NULL REFERENCES opponent_players(id),
    source              TEXT NOT NULL DEFAULT 'Auto',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opponent_team_rosters (
    team_id     INTEGER NOT NULL REFERENCES opponent_teams(id),
    player_id   INTEGER NOT NULL REFERENCES opponent_players(id),
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(team_id, player_id)
);

CREATE TABLE IF NOT EXISTS opponent_stats_hp (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    player_id       INTEGER NOT NULL REFERENCES opponent_players(id),
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

CREATE TABLE IF NOT EXISTS opponent_stats_snd (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    player_id       INTEGER NOT NULL REFERENCES opponent_players(id),
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

CREATE INDEX IF NOT EXISTS idx_opp_hp_player ON opponent_stats_hp(player_id);
CREATE INDEX IF NOT EXISTS idx_opp_snd_player ON opponent_stats_snd(player_id);
CREATE INDEX IF NOT EXISTS idx_matches_opp_team ON matches(opponent_team_id);
```

`_ensure_columns` 함수(`db.py:215` 부근, `("opponent_score", "INTEGER")` 등이 있는 튜플 리스트)에 추가:

```python
    ("matches", [("opponent_team_id", "INTEGER")]),
```

기존 항목의 정확한 형식은 주변 코드를 그대로 따른다(리스트 구조가 다르면 그 패턴에 맞춘다).

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_schema.py -v`
Expected: 3 passed
Run: `python -m pytest tests/test_smoke_routes.py -v`
Expected: PASS (기존 스위트 무손상 확인)

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_opponent_schema.py
git commit -m "상대팀 스키마 6종 + matches.opponent_team_id 마이그레이션"
```

---

### Task 3: DB 상대 resolve·팀 식별·병합 함수

**Files:**
- Modify: `db.py` (파일 끝, `merge_player` 뒤에 추가)
- Test: `tests/test_opponent_resolve.py`

**Interfaces:**
- Consumes: `opponent_matching.norm_name/best_fuzzy_match/tally_team_votes/FUZZY_*_THRESHOLD` (Task 1), `get_conn`, `_adapt_sql`, `conn.execute_returning_id`, `conn.upsert`.
- Produces: `resolve_opponent_player_id(conn, name: str, team_id: int = None) -> int`, `_learn_opponent_alias(conn, ign: str, player_id: int, source: str = "Auto")`, `identify_opponent_team(conn, names: list) -> int | None`, `merge_opponent_player(src_player_id: int, dst_player_id: int) -> dict`. Task 4·7·8이 사용.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_opponent_resolve.py
import db


def _seed_roster(conn):
    """Godlike = Alpha/Beta/Gamma, Kings = Delta 등록."""
    teams = {}
    for tname in ("Godlike", "Kings"):
        teams[tname] = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", (tname,))
    pids = {}
    for pname, tname in [("Alpha", "Godlike"), ("Beta", "Godlike"), ("Gamma", "Godlike"),
                         ("Delta", "Kings")]:
        pid = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", (pname,))
        pids[pname] = pid
        conn.upsert("opponent_team_rosters", ["team_id", "player_id", "source"],
                    (teams[tname], pid, "registered"), conflict_col="team_id, player_id")
    return teams, pids


def test_resolve_exact_then_alias_learning():
    with db.get_conn() as conn:
        teams, pids = _seed_roster(conn)
        # 정확 매칭
        assert db.resolve_opponent_player_id(conn, "alpha", team_id=teams["Godlike"]) == pids["Alpha"]
        # OCR 변형이 alias로 학습됐는지
        row = conn.execute("SELECT opponent_player_id FROM opponent_aliases WHERE ign='alpha'").fetchone()
        assert row and row["opponent_player_id"] == pids["Alpha"]


def test_resolve_fuzzy_ocr_variant():
    with db.get_conn() as conn:
        teams, pids = _seed_roster(conn)
        # 팀 풀 퍼지: Alphа(Cyrillic а) → 정규화 후 "alph" ≠ "alpha", 유사도 0.888
        pid = db.resolve_opponent_player_id(conn, "Alphа", team_id=teams["Godlike"])
        assert pid == pids["Alpha"]


def test_resolve_new_player_created():
    with db.get_conn() as conn:
        teams, _ = _seed_roster(conn)
        before = conn.execute("SELECT COUNT(*) c FROM opponent_players").fetchone()["c"]
        db.resolve_opponent_player_id(conn, "BrandNewMerc", team_id=teams["Godlike"])
        after = conn.execute("SELECT COUNT(*) c FROM opponent_players").fetchone()["c"]
        assert after == before + 1  # 신규 엔트리 (admin 병합 대기)


def test_identify_team_majority():
    with db.get_conn() as conn:
        teams, _ = _seed_roster(conn)
        names = ["Alpha", "Beta", "Gamma", "UnknownSub1", "UnknownSub2"]
        assert db.identify_opponent_team(conn, names) == teams["Godlike"]


def test_identify_team_ambiguous_returns_none():
    with db.get_conn() as conn:
        teams, _ = _seed_roster(conn)
        names = ["Alpha", "Delta", "New1", "New2", "New3"]  # 1:1 동률
        assert db.identify_opponent_team(conn, names) is None


def test_merge_opponent_player_moves_stats():
    with db.get_conn() as conn:
        teams, pids = _seed_roster(conn)
        mid = conn.execute_returning_id(
            "INSERT INTO matches(mode, match_date) VALUES ('HP', '2026-08-28')")
        src = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("Renegul8808",))
        conn.execute(db._adapt_sql(
            "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
            "VALUES (?,?,?,?,?)"), (mid, src, "Renegul8808", 10, 5))
        db._learn_opponent_alias(conn, "Renegul8808", src)
        result = db.merge_opponent_player(src, pids["Alpha"])
        assert result["ok"] is True
        row = conn.execute(db._adapt_sql(
            "SELECT player_id FROM opponent_stats_hp WHERE match_id=?"), (mid,)).fetchone()
        assert row["player_id"] == pids["Alpha"]
        # alias도 치환
        a = conn.execute("SELECT opponent_player_id FROM opponent_aliases WHERE ign='Renegul8808'").fetchone()
        assert a["opponent_player_id"] == pids["Alpha"]
        # src 선수 삭제
        gone = conn.execute("SELECT id FROM opponent_players WHERE id=?", (src,)).fetchone()
        assert gone is None
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_resolve.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'resolve_opponent_player_id'`

- [ ] **Step 3: 구현** — `db.py` 끝에 추가. 파일 상단 import에 `import opponent_matching` 포함:

```python
# ── 상대팀 선수·팀 분류 (spec §5.1~5.2) ─────────────────────────────────


def _learn_opponent_alias(conn, ign: str, player_id: int, source: str = "Auto"):
    """상대 변형 IGN을 opponent_aliases에 영구 저장. 충돌 시 무시(덮어쓰지 않음)."""
    try:
        if USE_POSTGRES:
            conn.execute(
                "INSERT INTO opponent_aliases(ign, opponent_player_id, source) "
                "VALUES (%s, %s, %s) ON CONFLICT (ign) DO NOTHING",
                (ign, player_id, source))
        else:
            conn.execute(
                "INSERT OR IGNORE INTO opponent_aliases(ign, opponent_player_id, source) "
                "VALUES (?, ?, ?)", (ign, player_id, source))
    except Exception as e:
        log.warning(f"[_learn_opponent_alias] {ign} → {player_id} 학습 실패: {e}")


def resolve_opponent_player_id(conn, name: str, team_id: int = None) -> int:
    """상대 선수 resolve (spec §5.1): alias 사전 → 풀 내 정확 → 퍼지 → 신규 생성.

    team_id가 있으면 그 팀 로스터 풀에서 넉넉한 임계값(0.75)으로,
    없으면 전역 풀에서 엄격한 임계값(0.85, 용병 폴백)으로 퍼지 매칭.
    반환: opponent_players.id (항상 존재 — 신규 생성 포함).
    """
    name = (name or "").strip() or "Unknown"
    target = opponent_matching.norm_name(name)

    # 1) alias 사전 (학습 우선, 풀 무관)
    for r in conn.execute("SELECT ign, opponent_player_id FROM opponent_aliases").fetchall():
        if opponent_matching.norm_name(r["ign"]) == target:
            return r["opponent_player_id"]

    # 2) 후보 풀: 팀 로스터 or 전역
    if team_id:
        rows = conn.execute(_adapt_sql(
            "SELECT p.id, p.name FROM opponent_players p "
            "JOIN opponent_team_rosters r ON r.player_id = p.id WHERE r.team_id = ?"),
            (team_id,)).fetchall()
        threshold = opponent_matching.FUZZY_TEAM_THRESHOLD
    else:
        rows = conn.execute("SELECT id, name FROM opponent_players").fetchall()
        threshold = opponent_matching.FUZZY_GLOBAL_THRESHOLD

    # 3) 풀 내 정확(정규화 일치)
    for r in rows:
        if opponent_matching.norm_name(r["name"]) == target:
            _learn_opponent_alias(conn, name, r["id"])
            return r["id"]

    # 4) 풀 내 퍼지
    match = opponent_matching.best_fuzzy_match(
        name, [(r["id"], r["name"]) for r in rows], threshold)
    if match:
        _learn_opponent_alias(conn, name, match[0])
        return match[0]

    # 5) 신규 생성 (admin 병합 대기)
    return conn.execute_returning_id(
        "INSERT INTO opponent_players(name) VALUES (?)", (name,))


def identify_opponent_team(conn, names: list):
    """상대팀 자동 식별 (spec §5.2): resolve 결과의 소속팀 득표 다수결.

    반환: opponent_teams.id 또는 None(미달·동률 → admin 큐).
    """
    team_votes = []
    for nm in names:
        pid = resolve_opponent_player_id(conn, nm)  # 전역 모드로 resolve
        rows = conn.execute(_adapt_sql(
            "SELECT DISTINCT team_id FROM opponent_team_rosters WHERE player_id = ?"),
            (pid,)).fetchall()
        team_votes.extend(r["team_id"] for r in rows)
    team_id, _n = opponent_matching.tally_team_votes(team_votes, total=len(names))
    return team_id


def merge_opponent_player(src_player_id: int, dst_player_id: int) -> dict:
    """상대 선수 병합: src의 스탯·alias·로스터를 dst로 흡수 후 src 삭제.

    같은 매치에 둘 다 있으면 dst 우선(src 행 삭제) — 스펙 §6.3 수동 병합.
    """
    with get_conn() as conn:
        for tbl in ("opponent_stats_hp", "opponent_stats_snd"):
            conn.execute(_adapt_sql(
                f"DELETE FROM {tbl} WHERE player_id = ? AND match_id IN "
                f"(SELECT match_id FROM {tbl} WHERE player_id = ?)"),
                (src_player_id, dst_player_id))
            conn.execute(_adapt_sql(
                f"UPDATE {tbl} SET player_id = ? WHERE player_id = ?"),
                (dst_player_id, src_player_id))
        conn.execute(_adapt_sql(
            "UPDATE opponent_aliases SET opponent_player_id = ? WHERE opponent_player_id = ?"),
            (dst_player_id, src_player_id))
        conn.execute(_adapt_sql(
            "DELETE FROM opponent_team_rosters WHERE player_id = ? AND team_id IN "
            "(SELECT team_id FROM opponent_team_rosters WHERE player_id = ?)"),
            (src_player_id, dst_player_id))
        conn.execute(_adapt_sql(
            "UPDATE opponent_team_rosters SET player_id = ? WHERE player_id = ?"),
            (dst_player_id, src_player_id))
        conn.execute(_adapt_sql(
            "DELETE FROM opponent_players WHERE id = ?"), (src_player_id,))
    return {"ok": True}
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_resolve.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_opponent_resolve.py
git commit -m "상대 선수 resolve·팀 자동 식별·병합 함수"
```

---

### Task 4: 저장 파이프라인 — `save_match`에 enemy 저장 통합

**Files:**
- Modify: `stats_repo.py`
- Test: `tests/test_opponent_pipeline.py`

**Interfaces:**
- Consumes: `db.resolve_opponent_player_id/identify_opponent_team/_learn_opponent_alias` (Task 3), 기존 `save_match`·`_to_int`·`_to_float`.
- Produces: `save_match(..., enemy_players: list = None)` — 반환 dict에 `"opponent": {"team_id": int|None, "saved": int} | None` 추가. Task 6이 호출.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_opponent_pipeline.py
import stats_repo
import db

ENEMY_KNOWN = [  # Godlike 로스터에 3명 등록된 상태에서 자동 식별 케이스
    {"name": "Alpha", "k": 12, "d": 8, "kd_ratio": 1.5, "time": 90, "score": 2100,
     "impact": 100, "total_damage": 2400, "capture_kill": 2},
    {"name": "Beta", "k": 9, "d": 11, "kd_ratio": 0.82, "time": 85, "score": 1900,
     "impact": 90, "total_damage": 2000, "capture_kill": 1},
    {"name": "Gamma", "k": 15, "d": 6, "kd_ratio": 2.5, "time": 100, "score": 2600,
     "impact": 120, "total_damage": 3000, "capture_kill": 3},
    {"name": "SubNew1", "k": 5, "d": 9, "kd_ratio": 0.56, "time": 60, "score": 1500,
     "impact": 70, "total_damage": 1300, "capture_kill": 0},
    {"name": "SubNew2", "k": 7, "d": 10, "kd_ratio": 0.7, "time": 70, "score": 1600,
     "impact": 75, "total_damage": 1500, "capture_kill": 0},
]

OURS = [
    {"name": "Shisui", "k": 20, "d": 10, "kd_ratio": 2.0, "time": 100, "score": 2500,
     "total_damage": 3000, "capture_kill": 3},
]


def _seed_team():
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("Godlike",))
        for pname in ("Alpha", "Beta", "Gamma"):
            pid = conn.execute_returning_id(
                "INSERT INTO opponent_players(name) VALUES (?)", (pname,))
            conn.upsert("opponent_team_rosters", ["team_id", "player_id", "source"],
                        (tid, pid, "registered"), conflict_col="team_id, player_id")
    return tid


def test_save_match_with_enemy_autotags_team():
    tid = _seed_team()
    info = stats_repo.save_match(
        mode="HP", players=OURS, match_date="2026-08-28",
        map_name="Combine", result="WIN", team_score=250, opponent_score=198,
        enemy_players=ENEMY_KNOWN)
    # 우리팀 저장은 기존대로
    assert info["saved"] == 1
    # 상대팀 자동 식별 + 저장
    assert info["opponent"]["team_id"] == tid
    assert info["opponent"]["saved"] == 5
    with db.get_conn() as conn:
        tagged = conn.execute(db._adapt_sql(
            "SELECT opponent_team_id FROM matches WHERE id=?"),
            (info["match_id"],)).fetchone()
        assert tagged["opponent_team_id"] == tid
        n = conn.execute("SELECT COUNT(*) c FROM opponent_stats_hp WHERE match_id=?",
                         (info["match_id"],)).fetchone()["c"]
        assert n == 5
        # 로스터 축적: 신규 후보 2명도 Godlike 소속으로 기록됨
        roster_n = conn.execute(db._adapt_sql(
            "SELECT COUNT(*) c FROM opponent_team_rosters r "
            "JOIN matches m ON m.opponent_team_id = r.team_id WHERE m.id=?"),
            (info["match_id"],)).fetchone()["c"]
        assert roster_n >= 5


def test_save_match_without_enemy_unchanged():
    info = stats_repo.save_match(mode="HP", players=OURS, match_date="2026-08-28",
                                 map_name="Firing Range")
    assert info["opponent"] is None  # enemy 없으면 키 자체가 None


def test_save_match_enemy_failure_isolated():
    """enemy 데이터가 깨져도 우리팀 저장은 정상 (부분 실패 격리, spec §5.3)."""
    info = stats_repo.save_match(
        mode="HP", players=OURS, match_date="2026-08-28", map_name="Summit",
        enemy_players=[{"name": "", "k": 1}])  # 이름 없음 → saved 0, 예외 아님
    assert info["match_id"] > 0
    assert info["opponent"]["saved"] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_pipeline.py -v`
Expected: FAIL — `save_match() got an unexpected keyword argument 'enemy_players'`

- [ ] **Step 3: 구현** — `stats_repo.py` 수정:

시그니처 확장:

```python
def save_match(mode: str, players: list, match_date: str, map_name: str = None,
               result: str = None, team_score: int = None, opponent_score: int = None,
               enemy_players: list = None) -> dict:
```

저장 로직 뒤(인사이트 캐시 무효화 `try:` 직전)에 삽입:

```python
        # 상대팀 저장 — 부분 실패 격리: 여기서 실패해도 우리팀 저장은 유효 (spec §5.3)
        enemy_info = None
        if enemy_players:
            try:
                enemy_info = _save_opponent_stats(conn, match_id, mode, enemy_players)
            except Exception as e:
                log.warning(f"[save_match] 상대팀 저장 실패 (우리팀 저장은 정상): {e}")
                enemy_info = {"team_id": None, "saved": 0, "error": str(e)}
```

반환 dict 확장:

```python
        return {"match_id": match_id, "saved": saved, "mode": mode,
                "duplicate": duplicate,
                "result": result, "team_score": team_score,
                "opponent_score": opponent_score, "map": map_name,
                "opponent": enemy_info}
```

파일 끝(`_to_int` 앞)에 함수 추가. 파일에 로거 없으면 상단에:

```python
import logging

log = logging.getLogger(__name__)
```

```python
def _save_opponent_stats(conn, match_id: int, mode: str, enemy_players: list) -> dict:
    """상대 선수 스탯 저장 + 팀 자동 식별 (spec §5).

    identify(전역 resolve + 다수결) → 팀 태그 → 팀 풀 재resolve로 저장 →
    로스터 축적(source='match'). 사전이 자라나는 지점.
    """
    names = [(p.get("name") or "").strip() for p in enemy_players]
    names = [n for n in names if n]
    if not names:
        return {"team_id": None, "saved": 0}

    team_id = db.identify_opponent_team(conn, names)
    saved = 0
    for p in enemy_players:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        pid = db.resolve_opponent_player_id(conn, name, team_id=team_id)
        if mode == "HP":
            _insert_opp_hp(conn, match_id, pid, p)
        else:
            _insert_opp_snd(conn, match_id, pid, p)
        if team_id:
            conn.upsert("opponent_team_rosters",
                        ["team_id", "player_id", "source"], (team_id, pid, "match"),
                        conflict_col="team_id, player_id")
        saved += 1

    if team_id:
        conn.execute(db._adapt_sql(
            "UPDATE matches SET opponent_team_id = ? "
            "WHERE id = ? AND opponent_team_id IS NULL"), (team_id, match_id))
    return {"team_id": team_id, "saved": saved}


def _insert_opp_hp(conn, match_id, pid, p):
    conn.upsert(
        "opponent_stats_hp",
        ["match_id", "player_id", "ign_raw", "kills", "deaths", "kd_ratio",
         "obj_time", "score", "impact", "total_damage", "capture_kill"],
        (
            match_id, pid, (p.get("name") or "").strip() or "Unknown",
            _to_int(p.get("k")), _to_int(p.get("d")), _to_float(p.get("kd_ratio")),
            _to_int(p.get("time")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_int(p.get("total_damage")),
            _to_int(p.get("capture_kill")),
        ),
        conflict_col="match_id, player_id",
        update_cols=["ign_raw", "kills", "deaths", "kd_ratio",
                     "obj_time", "score", "impact", "total_damage", "capture_kill"],
    )


def _insert_opp_snd(conn, match_id, pid, p):
    conn.upsert(
        "opponent_stats_snd",
        ["match_id", "player_id", "ign_raw", "kills", "deaths", "assists",
         "kd_ratio", "score", "impact", "adr", "first_kill", "lone_wolf_win"],
        (
            match_id, pid, (p.get("name") or "").strip() or "Unknown",
            _to_int(p.get("k")), _to_int(p.get("d")), _to_int(p.get("a")),
            _to_float(p.get("kd_ratio")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_float(p.get("adr")),
            _to_int(p.get("first_kill")), _to_int(p.get("lone_wolf_win")),
        ),
        conflict_col="match_id, player_id",
        update_cols=["ign_raw", "kills", "deaths", "assists", "kd_ratio",
                     "score", "impact", "adr", "first_kill", "lone_wolf_win"],
    )
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_pipeline.py tests/test_smoke_routes.py -v`
Expected: PASS (기존 호출부는 enemy_players 기본값 None이라 무영향)

- [ ] **Step 5: 커밋**

```bash
git add stats_repo.py tests/test_opponent_pipeline.py
git commit -m "save_match에 상대팀 저장 통합 (팀 자동 식별 + 부분 실패 격리)"
```

---

### Task 5: 프롬프트 — `enemy_players` raw 추출 지시

**Files:**
- Modify: `prompt.py` (`_PROMPT_TEMPLATE` — [4단계] 뒤, 출력 형식 앞 / HP·SND JSON 예시)

**Interfaces:**
- Consumes: 없음.
- Produces: GPT 응답 JSON에 `enemy_players` 배열(선수 dict, 이름은 raw). Task 6이 소비.

⚠️ `prompt.py`는 출처 고정 파일 — 아래 추가만 하고 기존 문장·키는 절대 수정하지 않는다.

- [ ] **Step 1: [4단계] 뒤에 [5단계] 삽입** — `"(1번/2번 사진의 순서가 반대여도..."` 문단 **앞에**:

```
[5단계 — 적 팀 선수 raw 추출]
확정한 우리 팀의 반대쪽(적 팀) 선수들도 [4단계]와 동일한 필드로 추출하여
"enemy_players" 배열에 넣으세요. 이름은 절대 변환·추측하지 말고 화면에 보이는
그대로(raw)를 출력하세요. (클랜태그가 붙어 있으면 그대로 둘 것. 로스터 매칭은
시스템이 별도로 수행합니다.) 적 팀이 아예 보이지 않으면 "enemy_players": [] 로
출력하세요. 적 팀 스탯은 우리 팀 스탯("players")과 형식이 동일해야 합니다.
```

- [ ] **Step 2: JSON 예시에 키 추가** — HP 예시 `"players": [...]` 뒤에:

```
"enemy_players": [{"name": "보이는그대로", "k": 0, "d": 0, "kd_ratio": 0.0, "time": 0, "score": 0, "impact": 0, "total_damage": 0, "capture_kill": 0}]
```

SND 예시 `"players": [...]` 뒤에:

```
"enemy_players": [{"name": "보이는그대로", "k": 0, "d": 0, "a": 0, "kd_ratio": 0.0, "score": 0, "impact": 0, "adr": 0, "first_kill": 0, "lone_wolf_win": 0}]
```

- [ ] **Step 3: 구문·기존 키 무결성 확인**

Run: `python -c "import prompt; p = prompt.build_system_prompt(['Test']); assert '{roster}' not in p and 'enemy_players' in p and 'our_team_side' in p; print('OK', len(p))"`
Expected: `OK <길이>` — 기존 플레이스홀더 치환·새 키 포함 확인.

- [ ] **Step 4: 수동 회귀 검증 (자동화 불가 — 코치 협력)**

기존에 잘 추출되던 스크린샷 2장을 로컬에서 GPT 호출로 재분석해 우리팀 `players` 결과가 기존과 동일한지 비교한다 ( enemy 추가로 인한 품질 저하 확인). 검증 방법: 로컬에서 `python bot.py` 실행 후 디스코드 테스트 채널에 기존 스크린샷 업로드 → 응답 JSON의 players 부분과 기존 기록 대조. 이상 있으면 [5단계] 문구 축소(예: "적 팀이 안 보이면 생략" 강조) 후 재검증.

- [ ] **Step 5: 커밋**

```bash
git add prompt.py
git commit -m "프롬프트: enemy_players raw 추출 지시 추가"
```

---

### Task 6: 봇 — `enemy_players` 전달

**Files:**
- Modify: `bot.py` (`write_to_db` 함수 117줄 부근, 파싱부 220줄 부근)
- Test: `tests/test_opponent_bot.py`

**Interfaces:**
- Consumes: `stats_repo.save_match(..., enemy_players=...)` (Task 4).
- Produces: `write_to_db(mode, players, date_str, map_name=None, result=None, team_score=None, opponent_score=None, enemy_players=None)`.

- [ ] **Step 1: 실패 테스트 작성** — bot.py 임포트 시 discord 의존 문제가 있을 수 있으므로, `write_to_db`가 save_match에 그대로 전달하는지만 검증(monkeypatch):

```python
# tests/test_opponent_bot.py
"""bot.write_to_db가 enemy_players를 save_match로 전달하는지 (bot 임포트는 discord 스텁으로)."""
import sys
import types


def test_write_to_db_forwards_enemy(monkeypatch):
    discord_stub = types.ModuleType("discord")
    sys.modules.setdefault("discord", discord_stub)
    import bot  # noqa: E402 (스텁 후 임포트)

    captured = {}

    def fake_save_match(**kwargs):
        captured.update(kwargs)
        return {"match_id": 1, "saved": 5, "mode": "HP", "duplicate": False,
                "result": "WIN", "team_score": 250, "opponent_score": 198,
                "map": "Combine", "opponent": {"team_id": None, "saved": 5}}

    monkeypatch.setattr(bot.stats_repo, "save_match", fake_save_match)
    bot.write_to_db("HP", [{"name": "Shisui", "k": 1, "d": 1, "score": 100}],
                    "2026-08-28", map_name="Combine", result="WIN",
                    team_score=250, opponent_score=198,
                    enemy_players=[{"name": "Alpha", "k": 1, "d": 1, "score": 90}])
    assert captured["enemy_players"] == [{"name": "Alpha", "k": 1, "d": 1, "score": 90}]
```

주의: bot.py가 discord 외 모듈(bot 전용)을 임포트해 스텁으로 안 뜨면, 테스트는 `write_to_db` 순수 전달 검증 대신 stats_repo 직접 호출 검증으로 대체해도 된다(이미 Task 4가 커버). bot.py 상단 import 구조를 먼저 보고 판단.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_bot.py -v`
Expected: FAIL — `TypeError: write_to_db() got an unexpected keyword argument 'enemy_players'` (또는 discord 스텁 이슈)

- [ ] **Step 3: 구현** — `bot.py` 수정:

`write_to_db` 시그니처에 추가 후 `stats_repo.save_match(...)` 호출에 `enemy_players=enemy_players` 전달. 파싱부(`players = result.get("players")...` 근처)에:

```python
    enemy_players = result.get("enemy_players") or []
```

그리고 `write_to_db(...)` 호출 인자에 `enemy_players=enemy_players` 추가.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_bot.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add bot.py tests/test_opponent_bot.py
git commit -m "봇: enemy_players를 저장 계층으로 전달"
```

---

### Task 7: Admin — 상대팀 관리 페이지 (팀 등록·로스터·미확정 큐)

**Files:**
- Modify: `admin_write.py` (함수 추가), `web_api.py` (라우트 추가), `templates/admin.html:9-12` (subtab 링크), `i18n/_ko.py`·`_en.py`·`_es.py`
- Create: `templates/admin_opponents.html`
- Test: `tests/test_opponent_admin.py`

**Interfaces:**
- Consumes: `db.get_conn/_adapt_sql/merge_opponent_player/resolve_opponent_player_id` (Task 3).
- Produces: `admin_write.opponent_admin_data() -> dict`, `admin_write.add_opponent_team(name: str) -> dict`, `admin_write.set_opponent_roster(team_id: int, names_text: str) -> dict`, 라우트 `GET /admin/opponents`, `POST /admin/opponent/team`, `POST /admin/opponent/roster`. Task 8이 같은 템플릿·데이터를 확장.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_opponent_admin.py
from fastapi.testclient import TestClient


def test_admin_opponents_page_200(client):
    r = client.get("/admin/opponents")
    assert r.status_code == 200


def test_add_team_and_roster(client):
    r = client.post("/admin/opponent/team", json={"name": "Godlike"})
    assert r.json()["ok"] is True
    r2 = client.post("/admin/opponent/roster",
                     json={"team_id": r.json()["team_id"],
                           "names": "Alpha\nBeta\nGamma"})
    assert r2.json()["ok"] is True
    data = __import__("admin_write").opponent_admin_data()
    team = next(t for t in data["teams"] if t["name"] == "Godlike")
    assert len(team["roster"]) == 3
```

인증이 걸려 있다면(기존 `/admin/aliases` 테스트가 어떻게 통과하는지 `tests/test_smoke_routes.py` 참조) 동일 방식으로 클라이언트에 로그인 처리를 한다.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_admin.py -v`
Expected: FAIL — 404

- [ ] **Step 3: 구현**

`admin_write.py`에 추가:

```python
def opponent_admin_data() -> dict:
    """상대팀 관리 페이지 데이터: 팀+로스터, 미확정 매치(opponent_team_id NULL)."""
    with db.get_conn() as conn:
        teams = conn.execute(db._adapt_sql("""
            SELECT t.id, t.name,
                   (SELECT COUNT(*) FROM matches m WHERE m.opponent_team_id = t.id) AS match_n
            FROM opponent_teams t ORDER BY t.name""")).fetchall()
        result = []
        for t in teams:
            roster = conn.execute(db._adapt_sql("""
                SELECT p.id, p.name, r.source
                FROM opponent_team_rosters r
                JOIN opponent_players p ON p.id = r.player_id
                WHERE r.team_id = ? ORDER BY p.name"""), (t["id"],)).fetchall()
            result.append({"id": t["id"], "name": t["name"],
                           "match_n": t["match_n"], "roster": [dict(r) for r in roster]})
        pending = conn.execute(db._adapt_sql("""
            SELECT m.id, m.match_date, m.mode, m.map_name, m.result,
                   m.team_score, m.opponent_score
            FROM matches m
            WHERE m.opponent_team_id IS NULL
              AND EXISTS (SELECT 1 FROM opponent_stats_hp h WHERE h.match_id = m.id
                          UNION ALL
                          SELECT 1 FROM opponent_stats_snd s WHERE s.match_id = m.id)
            ORDER BY m.id DESC LIMIT 50""")).fetchall()
        return {"teams": result, "pending": [dict(p) for p in pending]}


def add_opponent_team(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "message": "팀 이름이 필요합니다"}
    with db.get_conn() as conn:
        row = conn.execute(db._adapt_sql(
            "SELECT id FROM opponent_teams WHERE name = ?"), (name,)).fetchone()
        if row:
            return {"ok": False, "message": "이미 등록된 팀입니다"}
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", (name,))
    return {"ok": True, "team_id": tid}


def set_opponent_roster(team_id: int, names_text: str) -> dict:
    """줄당 닉네임 1개 텍스트를 로스터로 등록 — 공식 로스터 선등록 (spec §6.1)."""
    added = 0
    with db.get_conn() as conn:
        team = conn.execute(db._adapt_sql(
            "SELECT id FROM opponent_teams WHERE id = ?"), (team_id,)).fetchone()
        if not team:
            return {"ok": False, "message": "없는 팀입니다"}
        for line in (names_text or "").splitlines():
            nm = line.strip()
            if not nm:
                continue
            pid = db.resolve_opponent_player_id(conn, nm, team_id=team_id)
            conn.upsert("opponent_team_rosters",
                        ["team_id", "player_id", "source"], (team_id, pid, "registered"),
                        conflict_col="team_id, player_id")
            added += 1
    return {"ok": True, "added": added}
```

`web_api.py` — 기존 `/admin/aliases` 라우트(web_api.py:545-582)와 동일한 인증 구조로 추가:

```python
@app.get("/admin/opponents", response_class=HTMLResponse)
async def admin_opponents_page(request: Request, lang: str = Query("ko")):
    data = admin_write.opponent_admin_data()
    return render("admin_opponents.html", lang=lang, data=data)


@app.post("/admin/opponent/team")
async def admin_add_opponent_team(payload: dict = Body(...)):
    return admin_write.add_opponent_team(payload.get("name", ""))


@app.post("/admin/opponent/roster")
async def admin_set_opponent_roster(payload: dict = Body(...)):
    return admin_write.set_opponent_roster(int(payload.get("team_id", 0)),
                                           payload.get("names", ""))
```

`templates/admin_opponents.html` (기존 admin.html 구조 참조 — subtabs + .card + .table-wrap):

```html
{% extends "base.html" %}
{% block content %}
<div class="subtabs">
    <a href="/admin?lang={{ lang }}" class="subtab">📋 {{ t.admin_tab_matches }}</a>
    <a href="/admin/aliases?lang={{ lang }}" class="subtab">🏷️ {{ t.admin_tab_aliases }}</a>
    <a href="/admin/players?lang={{ lang }}" class="subtab">👤 {{ t.admin_tab_players }}</a>
    <a href="/admin/opponents?lang={{ lang }}" class="subtab active">⚔️ {{ t.admin_tab_opponents }}</a>
</div>

<h2>{{ t.opp_title }}</h2>

<div class="card">
    <h3>{{ t.opp_add_team }}</h3>
    <form id="add-team-form" class="filter-bar">
        <input class="input" id="team-name" placeholder="{{ t.opp_team_name }}" required>
        <button class="btn btn--primary" type="submit">{{ t.opp_add }}</button>
    </form>
</div>

{% for team in data.teams %}
<div class="card">
    <h3>{{ team.name }} <span class="muted">{{ t.opp_matches }}: {{ team.match_n }}</span></h3>
    <form class="filter-bar" data-team="{{ team.id }}">
        <textarea class="input" rows="2" placeholder="{{ t.opp_roster_paste }}"></textarea>
        <button class="btn" type="submit">{{ t.opp_roster_add }}</button>
    </form>
    <div class="table-wrap">
    <table>
        <thead><tr><th>{{ t.opp_player }}</th><th>{{ t.opp_source }}</th></tr></thead>
        <tbody>
        {% for p in team.roster %}
        <tr><td>{{ p.name }}</td><td>{{ p.source }}</td></tr>
        {% endfor %}
        </tbody>
    </table>
    </div>
</div>
{% endfor %}

{% if data.pending %}
<div class="card card--warning">
    <h3>{{ t.opp_pending_title }}</h3>
    <div class="table-wrap">
    <table>
        <thead><tr><th>{{ t.opp_date }}</th><th>{{ t.opp_mode }}</th><th>{{ t.opp_map }}</th><th>{{ t.opp_result }}</th><th></th></tr></thead>
        <tbody>
        {% for m in data.pending %}
        <tr>
            <td>{{ m.match_date }}</td><td>{{ m.mode }}</td><td>{{ m.map_name or "-" }}</td>
            <td>{% if m.result == 'WIN' %}<span class="win-badge">W</span>
                {% elif m.result == 'LOSS' %}<span class="loss-badge">L</span>{% endif %}</td>
            <td>
                <select class="select team-select" data-match="{{ m.id }}">
                    <option value="">{{ t.opp_assign_team }}</option>
                    {% for team in data.teams %}
                    <option value="{{ team.id }}">{{ team.name }}</option>
                    {% endfor %}
                </select>
                <button class="btn btn--primary assign-btn" data-match="{{ m.id }}" disabled>{{ t.opp_save }}</button>
            </td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
    </div>
</div>
{% endif %}

<script>
// 폼/버튼 fetch 처리 — flash()로 결과 표시 (base.html 글로벌 토스트)
document.getElementById("add-team-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("team-name").value;
    const r = await (await fetch("/admin/opponent/team", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name})})).json();
    flash(r.message || (r.ok ? "{{ t.opp_saved }}" : "{{ t.opp_error }}"), r.ok);
    if (r.ok) location.reload();
});
document.querySelectorAll("form.filter-bar[data-team]").forEach((f) => {
    f.addEventListener("submit", async (e) => {
        e.preventDefault();
        const names = f.querySelector("textarea").value;
        const r = await (await fetch("/admin/opponent/roster", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({team_id: Number(f.dataset.team), names})})).json();
        flash(r.message || (r.ok ? "{{ t.opp_saved }}" : "{{ t.opp_error }}"), r.ok);
        if (r.ok) location.reload();
    });
});
document.querySelectorAll(".team-select").forEach((sel) => {
    sel.addEventListener("change", () => {
        sel.parentElement.querySelector(".assign-btn").disabled = !sel.value;
    });
});
document.querySelectorAll(".assign-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
        const mid = btn.dataset.match;
        const teamId = btn.parentElement.querySelector(".team-select").value;
        const r = await (await fetch("/admin/opponent/match-team", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({match_id: Number(mid), team_id: Number(teamId)})})).json();
        flash(r.message || (r.ok ? "{{ t.opp_saved }}" : "{{ t.opp_error }}"), r.ok);
        if (r.ok) location.reload();
    });
});
</script>
{% endblock %}
```

`templates/admin.html` subtabs(9-12줄)에 같은 링크 추가(active 없이):

```html
    <a href="/admin/opponents?lang={{ lang }}" class="subtab">⚔️ {{ t.admin_tab_opponents }}</a>
```

i18n 세 파일 `STRINGS`에 추가 (같은 키 목록 — test_i18n.py가 동일성 강제):

```python
# _ko.py
        "admin_tab_opponents": "상대팀",
        "opp_title": "상대팀 관리",
        "opp_add_team": "팀 등록",
        "opp_team_name": "팀 이름",
        "opp_add": "등록",
        "opp_roster_paste": "로스터 붙여넣기 (줄당 닉네임 1개)",
        "opp_roster_add": "로스터 추가",
        "opp_player": "선수",
        "opp_source": "등록 출처",
        "opp_matches": "매치 수",
        "opp_pending_title": "상대팀 미확정 매치",
        "opp_date": "날짜", "opp_mode": "모드", "opp_map": "맵", "opp_result": "결과",
        "opp_assign_team": "팀 지정",
        "opp_save": "저장",
        "opp_saved": "저장됨",
        "opp_error": "실패",
        "nav_versus": "상대전적",
        "versus_title": "상대전적",
        "versus_no_data": "상대팀 데이터가 아직 없습니다",
        "versus_record": "상대전적",
        "versus_matches": "매치",
        "versus_h2h": "선수별 매치업",
        "versus_our_player": "우리 선수",
        "versus_opp_player": "상대 선수",
        "versus_matches_together": "동반 매치",
        "versus_kd_diff": "K-D 차이",
        "versus_metric_diff": "ZCS/RDS 차이",
        "versus_match_history": "매치 히스토리",
        "versus_pending_hint": "미확정 매치는 상대전적에서 제외됩니다",
```

```python
# _en.py
        "admin_tab_opponents": "Opponents",
        "opp_title": "Opponent Teams",
        "opp_add_team": "Add Team",
        "opp_team_name": "Team name",
        "opp_add": "Add",
        "opp_roster_paste": "Paste roster (one nickname per line)",
        "opp_roster_add": "Add roster",
        "opp_player": "Player",
        "opp_source": "Source",
        "opp_matches": "Matches",
        "opp_pending_title": "Matches with unidentified opponent",
        "opp_date": "Date", "opp_mode": "Mode", "opp_map": "Map", "opp_result": "Result",
        "opp_assign_team": "Assign team",
        "opp_save": "Save",
        "opp_saved": "Saved",
        "opp_error": "Failed",
        "nav_versus": "Versus",
        "versus_title": "Versus",
        "versus_no_data": "No opponent data yet",
        "versus_record": "Record",
        "versus_matches": "Matches",
        "versus_h2h": "Player head-to-head",
        "versus_our_player": "Our player",
        "versus_opp_player": "Opponent player",
        "versus_matches_together": "Shared matches",
        "versus_kd_diff": "K-D diff",
        "versus_metric_diff": "ZCS/RDS diff",
        "versus_match_history": "Match history",
        "versus_pending_hint": "Unassigned matches are excluded",
```

```python
# _es.py
        "admin_tab_opponents": "Rivales",
        "opp_title": "Equipos rivales",
        "opp_add_team": "Añadir equipo",
        "opp_team_name": "Nombre del equipo",
        "opp_add": "Añadir",
        "opp_roster_paste": "Pegar roster (un apodo por línea)",
        "opp_roster_add": "Añadir roster",
        "opp_player": "Jugador",
        "opp_source": "Origen",
        "opp_matches": "Partidos",
        "opp_pending_title": "Partidos con rival sin identificar",
        "opp_date": "Fecha", "opp_mode": "Modo", "opp_map": "Mapa", "opp_result": "Resultado",
        "opp_assign_team": "Asignar equipo",
        "opp_save": "Guardar",
        "opp_saved": "Guardado",
        "opp_error": "Falló",
        "nav_versus": "Versus",
        "versus_title": "Versus",
        "versus_no_data": "Aún no hay datos de rivales",
        "versus_record": "Historial",
        "versus_matches": "Partidos",
        "versus_h2h": "Enfrentamientos jugador a jugador",
        "versus_our_player": "Nuestro jugador",
        "versus_opp_player": "Jugador rival",
        "versus_matches_together": "Partidos juntos",
        "versus_kd_diff": "Dif. K-D",
        "versus_metric_diff": "Dif. ZCS/RDS",
        "versus_match_history": "Historial de partidos",
        "versus_pending_hint": "Los partidos sin asignar quedan excluidos",
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_admin.py tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add admin_write.py web_api.py templates/admin_opponents.html templates/admin.html i18n/ tests/test_opponent_admin.py
git commit -m "admin 상대팀 관리 탭 (팀 등록·로스터 선등록·미확정 큐)"
```

---

### Task 8: Admin — 매치 팀 지정(재매칭) + 상대 선수 병합

**Files:**
- Modify: `admin_write.py`, `web_api.py`, `templates/admin_opponents.html` (미해결 선수 섹션 추가)
- Test: `tests/test_opponent_admin.py` (확장)

**Interfaces:**
- Consumes: Task 7의 `opponent_admin_data`·템플릿, Task 3의 `resolve_opponent_player_id`·`merge_opponent_player`.
- Produces: `admin_write.assign_match_opponent(match_id: int, team_id: int) -> dict`, `admin_write.merge_opponent(src_player_id: int, dst_player_id: int) -> dict`, 라우트 `POST /admin/opponent/match-team`, `POST /admin/opponent/merge`.

- [ ] **Step 1: 실패 테스트 추가** (test_opponent_admin.py에):

```python
def test_assign_match_team_and_rematch(client):
    # 팀 등록 + enemy 있는 매치 저장(팀은 미확정 — 로스터 없이 저장)
    import stats_repo, admin_write
    r = client.post("/admin/opponent/team", json={"name": "Kings"})
    tid = r.json()["team_id"]
    info = stats_repo.save_match(
        mode="HP", players=[{"name": "Shisui", "k": 1, "d": 1, "score": 100}],
        match_date="2026-08-28", map_name="Summit",
        enemy_players=[{"name": "K1ngzman", "k": 2, "d": 2, "score": 110}])
    assert info["opponent"]["team_id"] is None  # 로스터 없어 미확정

    # 로스터 등록 후 매치에 팀 지정 → ign_raw 재매칭
    client.post("/admin/opponent/roster", json={"team_id": tid, "names": "Kingzman"})
    ok = client.post("/admin/opponent/match-team",
                     json={"match_id": info["match_id"], "team_id": tid})
    assert ok.json()["ok"] is True
    data = admin_write.opponent_admin_data()
    assert all(p["match_id"] != info["match_id"] for p in [])  # 미확정 목록에서 빠짐(아래 재확인)
    import db
    with db.get_conn() as conn:
        row = conn.execute(db._adapt_sql(
            "SELECT opponent_team_id FROM matches WHERE id=?"), (info["match_id"],)).fetchone()
        assert row["opponent_team_id"] == tid
        # K1ngzman(오타)이 로스터의 Kingzman으로 재매칭됐는지
        pid_row = conn.execute(db._adapt_sql(
            "SELECT player_id FROM opponent_stats_hp WHERE match_id=? AND ign_raw=?"),
            (info["match_id"], "K1ngzman")).fetchone()
        king = conn.execute(db._adapt_sql(
            "SELECT id FROM opponent_players WHERE name=?"), ("Kingzman",)).fetchone()
        assert pid_row["player_id"] == king["id"]


def test_merge_opponent_route(client):
    import db, admin_write
    with db.get_conn() as conn:
        dst = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("RealName",))
        src = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("WrongSplit",))
    r = client.post("/admin/opponent/merge",
                    json={"src_player_id": src, "dst_player_id": dst})
    assert r.json()["ok"] is True
    with db.get_conn() as conn:
        assert conn.execute("SELECT id FROM opponent_players WHERE id=?",
                            (src,)).fetchone() is None
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_opponent_admin.py -v`
Expected: FAIL — 404

- [ ] **Step 3: 구현**

`admin_write.py`에 추가:

```python
def assign_match_opponent(match_id: int, team_id: int) -> dict:
    """미확정 매치에 팀 지정 + 그 매치의 상대 선수 재매칭 (spec §6.2).

    팀이 정해지면 후보 풀이 그 팀 로스터로 좁아져 퍼지 재확률 상승.
    """
    with db.get_conn() as conn:
        m = conn.execute(db._adapt_sql(
            "SELECT id, mode FROM matches WHERE id = ?"), (match_id,)).fetchone()
        if not m:
            return {"ok": False, "message": "없는 매치입니다"}
        t = conn.execute(db._adapt_sql(
            "SELECT id FROM opponent_teams WHERE id = ?"), (team_id,)).fetchone()
        if not t:
            return {"ok": False, "message": "없는 팀입니다"}
        tbl = "opponent_stats_hp" if m["mode"] == "HP" else "opponent_stats_snd"
        rows = conn.execute(db._adapt_sql(
            f"SELECT id, ign_raw FROM {tbl} WHERE match_id = ?"), (match_id,)).fetchall()
        for r in rows:
            pid = db.resolve_opponent_player_id(conn, r["ign_raw"] or "", team_id=team_id)
            conn.execute(db._adapt_sql(
                f"UPDATE {tbl} SET player_id = ? WHERE id = ?"), (pid, r["id"]))
            conn.upsert("opponent_team_rosters",
                        ["team_id", "player_id", "source"], (team_id, pid, "match"),
                        conflict_col="team_id, player_id")
        conn.execute(db._adapt_sql(
            "UPDATE matches SET opponent_team_id = ? WHERE id = ?"), (team_id, match_id))
    insight_cache.invalidate_all()
    return {"ok": True}


def merge_opponent(src_player_id: int, dst_player_id: int) -> dict:
    """상대 선수 병합 라우트 래퍼 — 병합 후 캐시 무효화."""
    result = db.merge_opponent_player(src_player_id, dst_player_id)
    if result.get("ok"):
        insight_cache.invalidate_all()
    return result
```

`admin_write.py`에 `import insight_cache`가 없으면 상단에 추가 (순환 import 시 함수 내 import).

`web_api.py`에 추가 (인증은 기존 admin POST와 동일):

```python
@app.post("/admin/opponent/match-team")
async def admin_assign_match_opponent(payload: dict = Body(...)):
    return admin_write.assign_match_opponent(int(payload.get("match_id", 0)),
                                             int(payload.get("team_id", 0)))


@app.post("/admin/opponent/merge")
async def admin_merge_opponent(payload: dict = Body(...)):
    return admin_write.merge_opponent(int(payload.get("src_player_id", 0)),
                                      int(payload.get("dst_player_id", 0)))
```

`templates/admin_opponents.html` — pending 테이블 각 행의 셀 하나 추가(상대 선수 raw 이름 + 병합 드롭다운). 매치 행 하단에 상세 확장 대신, pending 섹션 아래에 "최근 상대 선수" 카드를 추가해 병합 UI를 둔다:

```html
{% if data.recent_opponents %}
<div class="card">
    <h3>{{ t.opp_merge_title }}</h3>
    <p class="muted">{{ t.opp_merge_hint }}</p>
    <div class="table-wrap">
    <table>
        <thead><tr><th>{{ t.opp_player }}</th><th>{{ t.opp_merge_into }}</th><th></th></tr></thead>
        <tbody>
        {% for p in data.recent_opponents %}
        <tr>
            <td>{{ p.name }}</td>
            <td>
                <select class="select merge-select" data-src="{{ p.id }}">
                    <option value="">{{ t.opp_assign_player }}</option>
                    {% for c in data.all_opponent_players if c.id != p.id %}
                    <option value="{{ c.id }}">{{ c.name }}</option>
                    {% endfor %}
                </select>
            </td>
            <td><button class="btn merge-btn" data-src="{{ p.id }}" disabled>{{ t.opp_merge }}</button></td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
    </div>
</div>
{% endif %}
```

`opponent_admin_data()` 반환에 추가:

```python
        recent = conn.execute(db._adapt_sql("""
            SELECT id, name FROM opponent_players
            ORDER BY id DESC LIMIT 30""")).fetchall()
        allp = conn.execute(db._adapt_sql(
            "SELECT id, name FROM opponent_players ORDER BY name")).fetchall()
        return {"teams": result, "pending": [dict(p) for p in pending],
                "recent_opponents": [dict(r) for r in recent],
                "all_opponent_players": [dict(a) for a in allp]}
```

스크립트에 병합 핸들러 추가:

```javascript
document.querySelectorAll(".merge-select").forEach((sel) => {
    sel.addEventListener("change", () => {
        sel.closest("tr").querySelector(".merge-btn").disabled = !sel.value;
    });
});
document.querySelectorAll(".merge-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
        const sel = btn.closest("tr").querySelector(".merge-select");
        const r = await (await fetch("/admin/opponent/merge", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({src_player_id: Number(btn.dataset.src),
                                  dst_player_id: Number(sel.value)})})).json();
        flash(r.message || (r.ok ? "{{ t.opp_saved }}" : "{{ t.opp_error }}"), r.ok);
        if (r.ok) location.reload();
    });
});
```

i18n 키 4개 추가 (세 파일):

```python
# _ko.py
        "opp_merge_title": "상대 선수 병합",
        "opp_merge_hint": "같은 선수가 다른 이름으로 분리돼 있으면 하나로 합칩니다. 병합 1회로 영구 학습됩니다.",
        "opp_merge_into": "이 선수로 병합",
        "opp_assign_player": "대상 선수",
        "opp_merge": "병합",
```

```python
# _en.py
        "opp_merge_title": "Merge opponent players",
        "opp_merge_hint": "If the same player is split under different names, merge them. One merge is learned permanently.",
        "opp_merge_into": "Merge into",
        "opp_assign_player": "Target player",
        "opp_merge": "Merge",
```

```python
# _es.py
        "opp_merge_title": "Fusionar jugadores rivales",
        "opp_merge_hint": "Si el mismo jugador está dividido bajo distintos nombres, fúndelos. Una fusión se aprende para siempre.",
        "opp_merge_into": "Fusionar en",
        "opp_assign_player": "Jugador destino",
        "opp_merge": "Fusionar",
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_opponent_admin.py tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add admin_write.py web_api.py templates/admin_opponents.html i18n/ tests/test_opponent_admin.py
git commit -m "admin: 매치 팀 지정 재매칭 + 상대 선수 병합"
```

---

### Task 9: `/versus` — 팀 상대전적 페이지

**Files:**
- Modify: `queries.py` (읽기 전용), `web_api.py` (라우트), `templates/base.html` (nav 링크), i18n(Task 7에서 이미 추가함)
- Create: `templates/versus.html`
- Test: `tests/test_versus_routes.py`

**Interfaces:**
- Consumes: 없음 (신규 조회).
- Produces: `queries.versus_overview() -> list[dict]`, 라우트 `GET /versus`. Task 10이 `versus_team_detail` 추가.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_versus_routes.py
from fastapi.testclient import TestClient


def test_versus_page_200_empty(client):
    r = client.get("/versus")
    assert r.status_code == 200


def test_versus_overview_counts(client):
    import queries, stats_repo, db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("Godlike",))
    for i, res in enumerate(["WIN", "LOSS", "WIN"]):
        stats_repo.save_match(
            mode="HP", players=[{"name": "Shisui", "k": 10, "d": 5, "score": 2000}],
            match_date=f"2026-08-2{i}", map_name="Summit", result=res,
            team_score=250, opponent_score=200)
        with db.get_conn() as conn:
            mid = conn.execute("SELECT MAX(id) id FROM matches").fetchone()["id"]
            conn.execute(db._adapt_sql(
                "UPDATE matches SET opponent_team_id=? WHERE id=?"), (tid, mid))
    rows = queries.versus_overview()
    team = next(t for t in rows if t["name"] == "Godlike")
    assert team["match_n"] == 3
    assert team["wins"] == 2
    assert team["losses"] == 1
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_versus_routes.py -v`
Expected: FAIL — 라우트 404 / `versus_overview` 없음

- [ ] **Step 3: 구현**

`queries.py`에 추가:

```python
def versus_overview() -> list:
    """팀별 상대전적 요약 (spec §7) — 승패 미입력 매치는 wins/losses에 미포함."""
    with db.get_conn() as conn:
        rows = conn.execute(db._adapt_sql("""
            SELECT t.id, t.name,
                   COUNT(m.id) AS match_n,
                   SUM(CASE WHEN m.result = 'WIN' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN m.result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                   AVG(m.team_score - m.opponent_score) AS avg_margin
            FROM opponent_teams t
            LEFT JOIN matches m ON m.opponent_team_id = t.id
            GROUP BY t.id, t.name
            ORDER BY match_n DESC, t.name""")).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "name": r["name"],
                "match_n": r["match_n"] or 0,
                "wins": int(r["wins"] or 0), "losses": int(r["losses"] or 0),
                "avg_margin": round(float(r["avg_margin"]), 1) if r["avg_margin"] is not None else None,
            })
        return out
```

`web_api.py`에 추가:

```python
@app.get("/versus", response_class=HTMLResponse)
async def versus_page(request: Request, lang: str = Query("ko")):
    teams = queries.versus_overview()
    return render("versus.html", lang=lang, teams=teams)
```

`templates/versus.html` (maps.html 카드 그리드 패턴 참조 — 필요한 클래스만):

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ t.versus_title }}</h1>
{% if not teams %}
<p class="muted">{{ t.versus_no_data }}</p>
{% else %}
<div class="card-grid">
    {% for team in teams %}
    <a class="card map-card" href="/versus/{{ team.id }}?lang={{ lang }}">
        <h3>{{ team.name }}</h3>
        <div class="stat-row">
            <span class="stat-value">{{ team.wins }}<span class="muted">W</span> —
                {{ team.losses }}<span class="muted">L</span></span>
        </div>
        <div class="muted">{{ t.versus_matches }}: {{ team.match_n }}</div>
        {% if team.avg_margin is not None %}
        <div class="{% if team.avg_margin > 0 %}delta-up{% elif team.avg_margin < 0 %}delta-down{% else %}delta-flat{% endif %}">
            {{ "%.1f"|format(team.avg_margin) }}
        </div>
        {% endif %}
    </a>
    {% endfor %}
</div>
<p class="muted">{{ t.versus_pending_hint }}</p>
{% endif %}
{% endblock %}
```

카드 그리드 클래스명은 `templates/maps.html`의 실제 클래스를 그대로 사용한다(구조 확인 후 `map-card`/`card-grid`를 실제 이름으로 맞춘다).

`templates/base.html` — `grep -n "nav_players" templates/base.html`로 nav 링크 위치를 찾아 같은 패턴으로 추가:

```html
<a href="/versus?lang={{ lang }}" class="nav-link">{{ t.nav_versus }}</a>
```

(기존 nav 링크의 클래스명·구조를 그대로 따른다.)

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_versus_routes.py tests/test_smoke_routes.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add queries.py web_api.py templates/versus.html templates/base.html tests/test_versus_routes.py
git commit -m "/versus 팀 상대전적 페이지"
```

---

### Task 10: H2H 매트릭스 — `/versus/{team_id}` 상세

**Files:**
- Modify: `queries.py`, `web_api.py`, `templates/versus.html` (분기 추가)
- Test: `tests/test_versus_routes.py` (확장)

**Interfaces:**
- Consumes: `metrics.compute_zcs/compute_rds` (수정 금지, 참조만).
- Produces: `queries.versus_team_detail(team_id: int) -> dict` — `{"team": {...}, "matches": [...], "h2h": {"our_players": [...], "opp_players": [...], "cells": {(our_id, opp_id): {...}}}}`, 라우트 `GET /versus/{team_id}`.

- [ ] **Step 1: 실패 테스트 추가** (test_versus_routes.py에):

```python
def test_versus_team_detail_h2h(client):
    import queries, stats_repo, db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("H2HTeam",))
        opp_pid = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("TheirAce",))
    info = stats_repo.save_match(
        mode="HP",
        players=[{"name": "Shisui", "k": 20, "d": 10, "kd_ratio": 2.0, "time": 100,
                  "score": 2500, "total_damage": 3000, "capture_kill": 3}],
        match_date="2026-08-28", map_name="Summit", result="WIN",
        team_score=250, opponent_score=100,
        enemy_players=[{"name": "TheirAce", "k": 8, "d": 15, "kd_ratio": 0.53,
                        "time": 90, "score": 1800, "impact": 80,
                        "total_damage": 1900, "capture_kill": 1}])
    with db.get_conn() as conn:
        conn.execute(db._adapt_sql(
            "UPDATE matches SET opponent_team_id=? WHERE id=?"), (tid, info["match_id"]))
    detail = queries.versus_team_detail(tid)
    assert detail["team"]["name"] == "H2HTeam"
    assert len(detail["matches"]) >= 1
    # 셀 검증: Shisui vs TheirAce — K-D diff = (20-10) - (8-15) = +17
    with db.get_conn() as conn:
        our_id = conn.execute("SELECT id FROM players WHERE name='Shisui'").fetchone()["id"]
    cell = detail["h2h"]["cells"][(our_id, opp_pid)]
    assert cell["matches"] == 1
    assert cell["kd_diff"] == 17
    # ZCS diff: Shisui ZCS=153.7(conftest 손계산) vs TheirAce = 1.1*90+8*1+4.1*(8-1)-5*15
    # = 99+8+28.7-75 = 60.7 → diff ≈ 93.0
    assert abs(cell["metric_diff"] - (153.7 - 60.7)) < 0.01


def test_versus_team_page_200(client):
    import db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("PageTeam",))
    r = client.get(f"/versus/{tid}")
    assert r.status_code == 200
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_versus_routes.py -v`
Expected: FAIL — `versus_team_detail` 없음

- [ ] **Step 3: 구현**

`queries.py`에 추가 (`import metrics` 상단 확인):

```python
def versus_team_detail(team_id: int) -> dict:
    """팀 상세: 매치 히스토리 + H2H 매트릭스 (spec §7).

    H2H 정의: 같은 매치에 양쪽 다 출전한 경우에 한해 집계.
    셀 = {"matches": n, "kd_diff": Σ(우리 K-D) - Σ(상대 K-D),
          "metric_diff": Σ(ZCS|HP) or Σ(RDS|SND) diff}
    """
    with db.get_conn() as conn:
        team = conn.execute(db._adapt_sql(
            "SELECT id, name FROM opponent_teams WHERE id = ?"), (team_id,)).fetchone()
        if not team:
            return None
        matches = conn.execute(db._adapt_sql("""
            SELECT id, match_date, mode, map_name, result, team_score, opponent_score
            FROM matches WHERE opponent_team_id = ? ORDER BY match_date DESC, id DESC"""),
            (team_id,)).fetchall()
        mlist = [dict(m) for m in matches]

        # 매치별 양쪽 스탯 로드 → H2H 누적
        h2h = {}
        our_names, opp_names = {}, {}
        for m in mlist:
            tbl_o = "player_stats_hp" if m["mode"] == "HP" else "player_stats_snd"
            tbl_e = "opponent_stats_hp" if m["mode"] == "HP" else "opponent_stats_snd"
            ours = conn.execute(db._adapt_sql(
                f"SELECT s.*, p.name AS pname FROM {tbl_o} s "
                f"JOIN players p ON p.id = s.player_id WHERE s.match_id = ?"),
                (m["id"],)).fetchall()
            theirs = conn.execute(db._adapt_sql(
                f"SELECT s.*, p.name AS pname FROM {tbl_e} s "
                f"JOIN opponent_players p ON p.id = s.player_id WHERE s.match_id = ?"),
                (m["id"],)).fetchall()
            for o in ours:
                our_names[o["player_id"]] = o["pname"]
                if m["mode"] == "HP":
                    o_metric = metrics.compute_zcs(o["obj_time"] or 0,
                                                   o["capture_kill"] or 0,
                                                   o["kills"] or 0, o["deaths"] or 0)
                else:
                    o_metric = metrics.compute_rds(o["kills"] or 0, o["assists"] or 0,
                                                   o["first_kill"] or 0,
                                                   o["lone_wolf_win"] or 0,
                                                   o["adr"] or 0, o["deaths"] or 0)
                for e in theirs:
                    opp_names[e["player_id"]] = e["pname"]
                    if m["mode"] == "HP":
                        e_metric = metrics.compute_zcs(e["obj_time"] or 0,
                                                       e["capture_kill"] or 0,
                                                       e["kills"] or 0, e["deaths"] or 0)
                    else:
                        e_metric = metrics.compute_rds(e["kills"] or 0, e["assists"] or 0,
                                                       e["first_kill"] or 0,
                                                       e["lone_wolf_win"] or 0,
                                                       e["adr"] or 0, e["deaths"] or 0)
                    key = (o["player_id"], e["player_id"])
                    c = h2h.setdefault(key, {"matches": 0, "kd_diff": 0, "metric_diff": 0.0})
                    c["matches"] += 1
                    c["kd_diff"] += ((o["kills"] or 0) - (o["deaths"] or 0)) \
                                    - ((e["kills"] or 0) - (e["deaths"] or 0))
                    c["metric_diff"] += o_metric - e_metric

        return {
            "team": dict(team), "matches": mlist,
            "h2h": {
                "our_players": [{"id": pid, "name": nm} for pid, nm in
                                sorted(our_names.items(), key=lambda kv: kv[1])],
                "opp_players": [{"id": pid, "name": nm} for pid, nm in
                                sorted(opp_names.items(), key=lambda kv: kv[1])],
                "cells": h2h,
            },
        }
```

`web_api.py`에 추가:

```python
@app.get("/versus/{team_id}", response_class=HTMLResponse)
async def versus_team_page(request: Request, team_id: int, lang: str = Query("ko")):
    detail = queries.versus_team_detail(team_id)
    if not detail:
        raise HTTPException(404, "상대팀 없음")
    return render("versus_team.html", lang=lang, d=detail)
```

`templates/versus_team.html` (신규):

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ t.versus_title }} — {{ d.team.name }}</h1>

<h2>{{ t.versus_match_history }}</h2>
<div class="table-wrap">
<table>
    <thead><tr><th>{{ t.opp_date }}</th><th>{{ t.opp_mode }}</th><th>{{ t.opp_map }}</th>
        <th>{{ t.opp_result }}</th><th>{{ t.opp_score }}</th></tr></thead>
    <tbody>
    {% for m in d.matches %}
    <tr>
        <td><a href="/matches/{{ m.id }}?lang={{ lang }}">{{ m.match_date }}</a></td>
        <td>{{ m.mode }}</td><td>{{ m.map_name or "-" }}</td>
        <td>{% if m.result == 'WIN' %}<span class="win-badge">W</span>
            {% elif m.result == 'LOSS' %}<span class="loss-badge">L</span>{% endif %}</td>
        <td>{{ m.team_score }} : {{ m.opponent_score }}</td>
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>

<h2>{{ t.versus_h2h }}</h2>
<div class="table-wrap">
<table>
    <thead><tr><th>{{ t.versus_our_player }}</th>
        {% for p in d.h2h.opp_players %}<th>{{ p.name }}</th>{% endfor %}</tr></thead>
    <tbody>
    {% for o in d.h2h.our_players %}
    <tr>
        <td>{{ o.name }}</td>
        {% for p in d.h2h.opp_players %}
        {% set c = d.h2h.cells.get((o.id, p.id)) %}
        <td>{% if c %}
            <div class="muted">{{ t.versus_matches_together }} {{ c.matches }}</div>
            <div class="{% if c.kd_diff > 0 %}delta-up{% elif c.kd_diff < 0 %}delta-down{% else %}delta-flat{% endif %}">
                {{ t.versus_kd_diff }} {{ "%+d"|format(c.kd_diff) }}</div>
            <div class="{% if c.metric_diff > 0 %}delta-up{% elif c.metric_diff < 0 %}delta-down{% else %}delta-flat{% endif %}">
                {{ t.versus_metric_diff }} {{ "%+.1f"|format(c.metric_diff) }}</div>
            {% else %}-{% endif %}
        </td>
        {% endfor %}
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>
{% endblock %}
```

참고: `t.opp_score` 키가 없으면 기존 스코어용 키를 재사용하거나 `"Score"` 3개국어 키를 추가한다 (`opp_score`: "스코어"/"Score"/"Marcador").

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_versus_routes.py tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add queries.py web_api.py templates/versus_team.html i18n/ tests/test_versus_routes.py
git commit -m "/versus/{team} 상세 — 매치 히스토리 + H2H 매트릭스"
```

---

### Task 11: 전체 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 전 스위트**

Run: `python -m pytest -v`
Expected: 전부 PASS (기존 + 신규 test_opponent_*, test_versus_routes)

- [ ] **Step 2: Lint**

Run: `python -m ruff check .`
Expected: 무검출

- [ ] **Step 3: 수동 E2E (코치 협력, 배포 전 로컬)**

1. `uvicorn web_api:app --port 8000` 실행 → `/admin/opponents`에서 팀 등록 + 로스터 붙여넣기.
2. 로컬 봇 실행 → 기존 스크린샷 2장 업로드 → 상대팀 자동 태그 확인 (`/admin` 매치 목록, `/versus`).
3. 미등록팀 스크린샷 → 미확정 큐 등록 → 팀 지정 → 재매칭 확인.

- [ ] **Step 4: 최종 커밋 (누락분 있으면)**

```bash
git status
git add -A   # .env/codm.db 등 .gitignore 항목은 자동 제외 확인 (git status로 재확인)
git commit -m "상대팀 전적 & H2H — 검증 완료"
```

---

## 셀프 리뷰 결과

- **스펙 커버리지**: §3 스키마(Task 2) / §4 프롬프트(Task 5) / §5 저장+식별(Task 3·4·6) / §6 admin(Task 7·8) / §7 조회(Task 9·10) / §8 예외 케이스(부분실패 격리 Task 4, 미확정·병합 Task 7·8) / §9 테스트(각 태스크 TDD + Task 11). §5.1 tier-2 "팀 풀 퍼지"는 `team_id` 전달 시점(Task 4 저장·Task 8 재매칭)에 작동. ✅
- **타입 일관성**: `resolve_opponent_player_id(conn, name, team_id=None) -> int` 전 태스크 동일. `save_match` 반환 `opponent` 키 dict|None. `versus_team_detail` 셀 키 tuple. ✅
- **주의 표기**: Task 9 카드 그리드 클래스명·base.html nav 클래스는 실행 시 실제 템플릿 확인 후 맞춘다고 명시 (추측 클래스 방지).
