# SQL 이중 호환(SQLite/Postgres) 테스트
#
# 1) _adapt_sql이 SQLite 스타일 SQL을 Postgres 문법으로 올바르게 변환하는지
#    (AGENTS.md §8의 Postgres 전용 함정 재발 방지)
# 2) SQL 인라인 ZCS/RDS 공식이 metrics.py 파이썬 공식과 같은 값을 내는지
#    (공식 드리프트 방지 — 한쪽만 고치면 이 테스트가 실패)

import db
import queries
import metrics

ZCS_SQL = ("SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill "
           "+ 4.1*(kills - capture_kill) - 5*deaths)),1) zcs FROM player_stats_hp WHERE player_id=?")
RDS_SQL = ("SELECT ROUND(AVG(MAX(0, 4.1*kills + 3.5*assists + 14*first_kill "
           "+ 20*lone_wolf_win + 0.12*adr - 5*deaths)),1) rds "
           "FROM player_stats_snd WHERE player_id=?")


def _as_postgres(sql: str) -> str:
    old = db.USE_POSTGRES
    db.USE_POSTGRES = True
    try:
        return db._adapt_sql(sql)
    finally:
        db.USE_POSTGRES = old


def test_adapt_placeholder_conversion():
    out = _as_postgres("SELECT * FROM t WHERE a=? AND b=?")
    assert "?" not in out
    assert out.count("%s") == 2


def test_adapt_max0_to_greatest():
    out = _as_postgres("SELECT MAX(0, 4.1*kills - 5*deaths) FROM t")
    assert "MAX(0," not in out
    assert "GREATEST(0, 4.1*kills - 5*deaths)" in out


def test_adapt_avg_numeric_cast():
    out = _as_postgres("SELECT ROUND(AVG(kd_ratio),2) FROM t")
    assert "::numeric" in out


def test_adapt_datetime_now():
    out = _as_postgres("SELECT datetime('now')")
    assert "NOW()" in out and "datetime" not in out


def test_adapt_zcs_query_postgres_safe():
    # AGENTS.md 함정 조합: AVG 중첩 괄호 + MAX(0,...) + 플레이스홀더 동시 처리
    out = _as_postgres(ZCS_SQL)
    assert "?" not in out
    assert "MAX(0," not in out
    assert "GREATEST(0," in out
    assert "::numeric" in out
    assert out.count("(") == out.count(")")  # 괄호 균형 — 캐스팅 삽입이 파서를 안 깨뜨렸는지


def test_adapt_rds_query_postgres_safe():
    out = _as_postgres(RDS_SQL)
    assert "?" not in out
    assert "MAX(0," not in out
    assert "GREATEST(0," in out
    assert "::numeric" in out
    assert out.count("(") == out.count(")")


# ── SQL 공식 ↔ metrics.py 공식 일치 (드리프트 방지) ────────────────────────

def test_sql_zcs_matches_python_formula(seeded_db):
    # Shisui HP 2매치: 153.7, 147.5 → 평균 150.6 (ROUND 1자리)
    pid = queries.get_player_id("Shisui")
    expected = (metrics.compute_zcs(100, 3, 20, 10)
                + metrics.compute_zcs(95, 2, 22, 11)) / 2
    got = queries._player_overall_zcs(pid)
    assert got is not None
    assert abs(got - expected) < 0.11  # ROUND 방향(160.8/160.9) 흔들림 허용


def test_sql_rds_matches_python_formula(seeded_db):
    pid = queries.get_player_id("Shisui")
    # SND 2매치 평균: (327.5 + 225.6) / 2 = 276.55
    expected = (metrics.compute_rds(20, 5, 3, 1, 1800, 10)
                + metrics.compute_rds(16, 4, 1, 0, 1600, 12)) / 2
    got = queries._player_overall_rds(pid)
    assert got is not None
    assert abs(got - expected) < 0.11


def test_sql_zcs_matches_python_formula_second_player(seeded_db):
    # 선수 한 명 더 교차 검증 — Cartels HP 2매치 평균
    pid = queries.get_player_id("Cartels")
    expected = (metrics.compute_zcs(80, 1, 15, 12)
                + metrics.compute_zcs(70, 1, 14, 10)) / 2
    got = queries._player_overall_zcs(pid)
    assert got is not None
    assert abs(got - expected) < 0.11
