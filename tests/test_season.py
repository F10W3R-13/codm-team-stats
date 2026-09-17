# 시즌 아카이빙 통합 테스트 — docs/plans/season-archive.plan.md 슬라이스 S1~S6 대응.
#
# 공유 seeded_db(conftest)를 오염시키지 않기 위해 독립 임시 SQLite를 쓴다:
# db.get_conn()/init_db()은 호출 시점의 db.DB_PATH/USE_POSTGRES 전역을 읽으므로
# monkeypatch로 격리한다.

import sqlite3

import pytest

import db


@pytest.fixture()
def season_db(tmp_path, monkeypatch):
    """시즌 테스트 전용 독립 DB (tmp_path 아래 신규 파일)."""
    path = str(tmp_path / "season.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(db, "USE_POSTGRES", False)
    db.init_db()
    return path


def _insert_match(path, mode="HP", match_date=None, map_name="Takeoff", result=None):
    conn = sqlite3.connect(path)
    cur = conn.execute(
        "INSERT INTO matches(mode, map_name, match_date, result) VALUES (?,?,?,?)",
        (mode, map_name, match_date, result),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


def _season_of(path, match_id):
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT season FROM matches WHERE id=?", (match_id,)).fetchone()
    conn.close()
    return row[0] if row else None


# ── S1: 스키마 + 멱등 백필 + 상수 ─────────────────────────────────────────

class TestS1SchemaBackfill:
    def test_season_constants_defined(self):
        """시즌 상수가 db.py에 정의된다."""
        assert db.CURRENT_SEASON == "s2"
        assert db.SEASON_CUTOFF == "2026-09-05"

    def test_new_schema_has_season_column(self, season_db):
        """신규 생성 DB의 matches에 season 컬럼이 있다."""
        conn = sqlite3.connect(season_db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)").fetchall()}
        conn.close()
        assert "season" in cols

    def test_backfill_classifies_boundary_dates(self, season_db):
        """기존(미태그) 행 백필: 경계일(09-05)=s2, 전일(09-04)=s1, NULL=s1."""
        m_s2 = _insert_match(season_db, match_date="2026-09-05")
        m_s1 = _insert_match(season_db, match_date="2026-09-04")
        m_null = _insert_match(season_db, match_date=None)

        db.init_db()  # 마이그레이션 재실행 → 백필

        assert _season_of(season_db, m_s2) == "s2"
        assert _season_of(season_db, m_s1) == "s1"
        assert _season_of(season_db, m_null) == "s1"

    def test_backfill_idempotent_preserves_manual_tags(self, season_db):
        """백필은 season IS NULL만 건드린다 — 수동 태그를 덮어쓰지 않는다."""
        m = _insert_match(season_db, match_date="2026-09-04")
        db.init_db()
        conn = sqlite3.connect(season_db)
        conn.execute("UPDATE matches SET season='s2' WHERE id=?", (m,))
        conn.commit()
        conn.close()

        db.init_db()  # 멱등 재실행

        assert _season_of(season_db, m) == "s2"


# ── S2: 쓰기 태깅 + 재업로드 dedup 시즌 가드 ──────────────────────────────

HP_ONE = [{"name": "Veteran", "k": 10, "d": 5, "kd_ratio": 2.0, "time": 60,
           "score": 2000, "total_damage": 2000, "capture_kill": 1}]

HP_ROOKIE = [{"name": "Rookie", "k": 12, "d": 6, "kd_ratio": 2.0, "time": 70,
              "score": 2100, "total_damage": 2100, "capture_kill": 1}]


def _set_season(path, match_id, season):
    conn = sqlite3.connect(path)
    conn.execute("UPDATE matches SET season=? WHERE id=?", (season, match_id))
    conn.commit()
    conn.close()


def _insert_stats_hp(path, match_id, player_name, k, d, score):
    """병합 후보 조건(스탯 부분집합)을 만들기 위한 직접 스탯 삽입.

    metrics 계산(all_hp_metrics)이 NULL 입력으로 깨지지 않게 전 컬럼 채운다.
    """
    conn = sqlite3.connect(path)
    cur = conn.execute("INSERT INTO players(name) VALUES (?)", (player_name,))
    pid = cur.lastrowid
    conn.execute(
        "INSERT INTO player_stats_hp(match_id, player_id, ign_raw, kills, deaths, "
        "kd_ratio, obj_time, score, impact, total_damage, capture_kill) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (match_id, pid, player_name, k, d,
         round(k / d, 2) if d else float(k), 60, score, 200, 2000, 1),
    )
    conn.commit()
    conn.close()


class TestS2WriteTagging:
    def test_save_match_tags_current_season(self, season_db):
        """신규 저장 매치는 CURRENT_SEASON(s2)으로 태깅된다."""
        import stats_repo
        out = stats_repo.save_match("HP", HP_ONE, "2026-09-10", map_name="Summit")
        assert out["duplicate"] is False
        assert _season_of(season_db, out["match_id"]) == "s2"

    def test_reupload_never_merges_into_s1(self, season_db):
        """s1 아카이브 매치와 동일 스탯 재업로드 → 병합 금지, 신규 매치 생성."""
        import stats_repo
        mid_s1 = _insert_match(season_db, match_date="2026-09-10", map_name="Summit")
        _set_season(season_db, mid_s1, "s1")
        _insert_stats_hp(season_db, mid_s1, "Veteran", 10, 5, 2000)

        out = stats_repo.save_match("HP", HP_ONE, "2026-09-10", map_name="Summit")

        assert out["duplicate"] is False
        assert out["match_id"] != mid_s1
        assert _season_of(season_db, out["match_id"]) == "s2"


# ── S3: 읽기 계층 시즌 필터 ────────────────────────────────────────────────

@pytest.fixture()
def two_season_db(season_db):
    """s2 매치(save_match) + s1 매치(직접) + 미태그(NULL) 매치 시드.

    - Rookie  = s2 (save_match가 태깅)
    - Veteran = s1 (아카이브)
    - Ghost   = 미태그 (전환기 폴백 — 양쪽 시즌 뷰에 노출되어야 함)
    """
    import stats_repo
    s2 = stats_repo.save_match(
        "HP", HP_ROOKIE, "2026-09-10", map_name="Summit",
        result="WIN", team_score=250, opponent_score=200)
    mid_s1 = _insert_match(season_db, match_date="2026-08-31",
                           map_name="Summit", result="LOSS")
    _set_season(season_db, mid_s1, "s1")
    _insert_stats_hp(season_db, mid_s1, "Veteran", 30, 10, 3000)
    mid_null = _insert_match(season_db, match_date="2026-09-12", map_name="Summit")
    _insert_stats_hp(season_db, mid_null, "Ghost", 5, 5, 500)
    return {"s2": s2["match_id"], "s1": mid_s1, "null": mid_null}


class TestS3ReadFilter:
    def test_leaderboard_default_hides_s1(self, two_season_db):
        import queries
        names = {r["name"] for r in queries.leaderboard("HP")}
        assert "Rookie" in names and "Ghost" in names
        assert "Veteran" not in names

    def test_leaderboard_s1_view(self, two_season_db):
        import queries
        names = {r["name"] for r in queries.leaderboard("HP", season="s1")}
        assert "Veteran" in names and "Ghost" in names
        assert "Rookie" not in names

    def test_all_players_overview_default(self, two_season_db):
        import queries
        names = {p["name"] for p in queries.all_players_overview("HP")}
        assert "Veteran" not in names and "Rookie" in names

    def test_all_players_overview_s1(self, two_season_db):
        import queries
        names = {p["name"] for p in queries.all_players_overview("HP", season="s1")}
        assert "Veteran" in names and "Rookie" not in names

    def test_player_overall_stats_scoped(self, two_season_db):
        import queries
        vet_id = queries.get_player_id("Veteran")
        assert queries.player_overall_stats(vet_id)["hp"] is None
        assert queries.player_overall_stats(vet_id, season="s1")["hp"]["matches"] == 1

    def test_win_loss_summary_scoped(self, two_season_db):
        import queries
        cur = queries.win_loss_summary()
        s1 = queries.win_loss_summary(season="s1")
        assert cur["total"] == 2 and s1["total"] == 2  # 각자 시즌 1 + 미태그 1
        assert cur["wins"] == 1 and cur["losses"] == 0
        assert s1["wins"] == 0 and s1["losses"] == 1

    def test_recent_results_scoped(self, two_season_db):
        import queries
        d = two_season_db
        assert {r["id"] for r in queries.recent_results()} == {d["s2"], d["null"]}
        assert {r["id"] for r in queries.recent_results(season="s1")} == {d["s1"], d["null"]}

    def test_map_team_stats_scoped(self, two_season_db):
        import queries
        cur = {r["map_name"]: r["matches"]
               for r in queries.map_team_stats("HP", min_matches=1)}
        s1 = {r["map_name"]: r["matches"]
              for r in queries.map_team_stats("HP", min_matches=1, season="s1")}
        assert cur.get("Summit") == 2
        assert s1.get("Summit") == 2

    def test_last_match_summary_scoped(self, season_db):
        """s1 매치가 id 최고여도 기본 뷰는 스킵 — 현시즌 필터 확인."""
        import queries
        import stats_repo
        out = stats_repo.save_match("HP", HP_ROOKIE, "2026-09-10", map_name="Summit")
        mid_s1 = _insert_match(season_db, match_date="2026-08-31", map_name="Summit")
        _set_season(season_db, mid_s1, "s1")
        _insert_stats_hp(season_db, mid_s1, "Veteran", 30, 10, 3000)

        assert queries.last_match_summary()["match_id"] == out["match_id"]
        assert queries.last_match_summary(season="s1")["match_id"] == mid_s1


# ── S4: 웹 ?season= 라우트 + nav 토글 ──────────────────────────────────────

@pytest.fixture()
def web(two_season_db):
    """two_season_db(monkeypatch된 임시 DB)를 바라보는 TestClient (S4/S5 공용)."""
    import analytics_insights
    for fn in ("player_profile_insight", "match_insight", "map_advice",
               "briefing_insight", "summarize_transcript"):
        setattr(analytics_insights, fn, lambda *a, **k: "[TEST] mock insight")
    import web_api
    from fastapi.testclient import TestClient
    with TestClient(web_api.app) as c:
        yield c


class TestS4Routes:
    def test_leaderboard_default_hides_s1(self, web):
        r = web.get("/leaderboard")
        assert r.status_code == 200
        assert "Rookie" in r.text
        assert "Veteran" not in r.text

    def test_leaderboard_s1_view(self, web):
        r = web.get("/leaderboard", params={"season": "s1"})
        assert r.status_code == 200
        assert "Veteran" in r.text
        assert "Rookie" not in r.text

    def test_invalid_season_rejected_422(self, web):
        assert web.get("/leaderboard", params={"season": "bogus"}).status_code == 422

    def test_nav_has_season_switcher(self, web):
        r = web.get("/players")
        assert r.status_code == 200
        assert "season-switcher" in r.text

    def test_lang_and_season_combined(self, web):
        r = web.get("/players", params={"lang": "en", "season": "s1"})
        assert r.status_code == 200


# ── S5: insight_cache 시즌 키 분리 ────────────────────────────────────────

class TestS5InsightCacheSeason:
    def test_cache_key_separates_seasons(self):
        """같은 선수·언어라도 시즌이 다르면 캐시가 분리된다."""
        import insight_cache
        insight_cache.set("player", "Veteran", "ko", "s1 인사이트", season="s1")
        assert insight_cache.get("player", "Veteran", "ko", season="s1") == "s1 인사이트"
        assert insight_cache.get("player", "Veteran", "ko", season="s2") is None

    def test_backward_compat_no_season(self):
        """season 미지정(기존 3-인자) 호출은 기존 동작 유지."""
        import insight_cache
        insight_cache.set("player", "Rookie", "ko", "기본 인사이트")
        assert insight_cache.get("player", "Rookie", "ko") == "기본 인사이트"

    def test_api_insight_season_scoped(self, web, two_season_db):
        """같은 선수 인사이트 API가 시즌별로 다른 데이터를 본다."""
        r1 = web.get("/api/insight/player/Rookie", params={"season": "s1"})
        r2 = web.get("/api/insight/player/Rookie", params={"season": "s2"})
        # Rookie는 s1에 스탯 없음 → 빈 인사이트 / s2에는 목킹 인사이트
        assert r1.json()["insight"] == ""
        assert r2.json()["insight"] == "[TEST] mock insight"


# ── S6: 날짜→시즌 매핑 (import_sheets·백필 공용 진실) ───────────────────────

class TestS6SeasonMapping:
    def test_season_for_date_mapping(self):
        """경계일 s2 / 전일 s1 / NULL·빈값 s1 — 백필 SQL과 동일 규칙."""
        assert db.season_for_date("2026-09-05") == "s2"
        assert db.season_for_date("2026-09-04") == "s1"
        assert db.season_for_date(None) == "s1"
        assert db.season_for_date("") == "s1"
