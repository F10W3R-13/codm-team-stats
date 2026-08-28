# save_match 상대팀(enemy) 저장 통합 테스트 — spec §5.3 부분 실패 격리.
# brief 원본 + db.init_db() 호출 한 줄 (get_conn은 스키마를 생성하지 않아 필요)
# + autouse 격리 fixture (세션 공유 임시 DB에서 _seed_team의 UNIQUE(name)
#   재삽입 충돌 방지 — 상대팀 테이블만 초기화, 선례: test_opponent_resolve.py)
import pytest

import stats_repo
import db

db.init_db()


@pytest.fixture(autouse=True)
def _fresh_opponent_tables():
    with db.get_conn() as conn:
        for tbl in ("opponent_aliases", "opponent_team_rosters",
                    "opponent_stats_hp", "opponent_stats_snd",
                    "opponent_players", "opponent_teams"):
            conn.execute(f"DELETE FROM {tbl}")
        # 이전 테스트가 남긴 player_stats 없는 고아 매치 정리 (시드 매치는 보존)
        conn.execute(
            "DELETE FROM matches WHERE id NOT IN "
            "(SELECT match_id FROM player_stats_hp UNION "
            " SELECT match_id FROM player_stats_snd)")
    yield

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

# 우리팀 픽스처 선수는 고유 이름 사용 — 이 테스트가 만든 매치가 세션 공유
# 임시 DB에 남아도 Shisui HP 평균 지표 단언(test_sql_compat)을 오염시키지 않게.
OURS = [
    {"name": "PipeTest", "k": 20, "d": 10, "kd_ratio": 2.0, "time": 100, "score": 2500,
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
