# 테스트 공통 환경 — web_api/db 임포트 전에 환경변수를 고정한다.
#
# db.py는 모듈 임포트 시점에 CODM_DB_PATH/DATABASE_URL을 읽고,
# config.py는 임포트 시점에 DISCORD_BOT_TOKEN/OPENAI_API_KEY를 요구한다.
# pytest는 conftest를 테스트 모듈보다 먼저 로드하므로 여기서 설정한다.

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="codm-test-")
os.environ["CODM_DB_PATH"] = os.path.join(_TMP_DIR, "fixture.db")
os.environ.pop("DATABASE_URL", None)           # 테스트는 항상 SQLite 모드
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ["ADMIN_PASSWORD"] = "test-admin-pw"  # 기본 비번("3717") 의존 제거

import pytest  # noqa: E402 (환경변수 설정 후 임포트해야 함)

# ── 시드 데이터 ────────────────────────────────────────────────────────────
# 기대값은 test_metrics.py·test_sql_compat.py의 손계산과 일치시킨다:
#   Shisui HP#1 ZCS = 1.1*100 + 8*3 + 4.1*20 - 5*10 = 166.0
#   Shisui HP#2 ZCS = 1.1*95 + 8*2 + 4.1*22 - 5*11 = 155.7
#   Shisui SND RDS  = 327.5 (test_metrics.test_rds_typical 동일 입력)

HP_MATCH_1 = [
    {"name": "Shisui",  "k": 20, "d": 10, "kd_ratio": 2.0,  "time": 100, "score": 2500, "total_damage": 3000, "capture_kill": 3},
    {"name": "Cartels", "k": 15, "d": 12, "kd_ratio": 1.25, "time": 80,  "score": 2200, "total_damage": 2500, "capture_kill": 1},
    {"name": "unravel", "k": 18, "d": 8,  "kd_ratio": 2.25, "time": 60,  "score": 2400, "total_damage": 2800, "capture_kill": 2},
    {"name": "Kingz",   "k": 12, "d": 14, "kd_ratio": 0.86, "time": 90,  "score": 2000, "total_damage": 2200, "capture_kill": 4},
    {"name": "Maozyn",  "k": 10, "d": 9,  "kd_ratio": 1.11, "time": 110, "score": 2100, "total_damage": 2000, "capture_kill": 2},
]

HP_MATCH_2 = [
    {"name": "Shisui",  "k": 22, "d": 11, "kd_ratio": 2.0,  "time": 95,  "score": 2600, "total_damage": 3200, "capture_kill": 2},
    {"name": "Cartels", "k": 14, "d": 10, "kd_ratio": 1.4,  "time": 70,  "score": 2100, "total_damage": 2400, "capture_kill": 1},
    {"name": "unravel", "k": 17, "d": 9,  "kd_ratio": 1.89, "time": 65,  "score": 2300, "total_damage": 2700, "capture_kill": 1},
    {"name": "Kingz",   "k": 13, "d": 12, "kd_ratio": 1.08, "time": 85,  "score": 2000, "total_damage": 2100, "capture_kill": 3},
    {"name": "Maozyn",  "k": 11, "d": 10, "kd_ratio": 1.1,  "time": 100, "score": 2200, "total_damage": 1900, "capture_kill": 2},
]

SND_MATCH_1 = [
    {"name": "Shisui",  "k": 20, "d": 10, "a": 5, "kd_ratio": 2.0,  "score": 2400, "adr": 1800, "first_kill": 3, "lone_wolf_win": 1},
    {"name": "Cartels", "k": 12, "d": 12, "a": 3, "kd_ratio": 1.0,  "score": 1900, "adr": 1500, "first_kill": 1, "lone_wolf_win": 0},
    {"name": "unravel", "k": 16, "d": 9,  "a": 6, "kd_ratio": 1.78, "score": 2200, "adr": 1700, "first_kill": 2, "lone_wolf_win": 1},
    {"name": "Kingz",   "k": 8,  "d": 13, "a": 8, "kd_ratio": 0.62, "score": 1700, "adr": 1300, "first_kill": 0, "lone_wolf_win": 0},
    {"name": "Maozyn",  "k": 14, "d": 11, "a": 4, "kd_ratio": 1.27, "score": 2000, "adr": 1600, "first_kill": 1, "lone_wolf_win": 0},
]

SND_MATCH_2 = [
    {"name": "Shisui",  "k": 16, "d": 12, "a": 4, "kd_ratio": 1.33, "score": 2100, "adr": 1600, "first_kill": 1, "lone_wolf_win": 0},
    {"name": "Cartels", "k": 10, "d": 13, "a": 5, "kd_ratio": 0.77, "score": 1800, "adr": 1400, "first_kill": 1, "lone_wolf_win": 1},
    {"name": "unravel", "k": 15, "d": 10, "a": 7, "kd_ratio": 1.5,  "score": 2100, "adr": 1650, "first_kill": 2, "lone_wolf_win": 1},
    {"name": "Kingz",   "k": 9,  "d": 12, "a": 9, "kd_ratio": 0.75, "score": 1750, "adr": 1350, "first_kill": 0, "lone_wolf_win": 0},
    {"name": "Maozyn",  "k": 12, "d": 12, "a": 5, "kd_ratio": 1.0,  "score": 1900, "adr": 1550, "first_kill": 1, "lone_wolf_win": 0},
]


@pytest.fixture(scope="session")
def seeded_db():
    """임시 SQLite에 스키마 + HP 2매치 + SND 1매치 시드."""
    import db
    db.init_db()

    import stats_repo
    hp1 = stats_repo.save_match("HP", HP_MATCH_1, "2026-08-01",
                                map_name="Takeoff", result="WIN",
                                team_score=250, opponent_score=207)
    hp2 = stats_repo.save_match("HP", HP_MATCH_2, "2026-08-08",
                                map_name="Takeoff", result="LOSS",
                                team_score=200, opponent_score=250)
    snd1 = stats_repo.save_match("SND", SND_MATCH_1, "2026-08-05",
                                 map_name="Firing Range", result="WIN",
                                 team_score=6, opponent_score=4)
    stats_repo.save_match("SND", SND_MATCH_2, "2026-08-07",
                          map_name="Firing Range", result="LOSS",
                          team_score=3, opponent_score=6)
    return {
        "hp_match_id": hp1["match_id"],
        "hp2_match_id": hp2["match_id"],
        "snd_match_id": snd1["match_id"],
        "dates": ["2026-08-01", "2026-08-05", "2026-08-08"],
    }


@pytest.fixture(scope="session")
def client(seeded_db):
    """GPT 호출을 목킹한 TestClient. 캐시 미스여도 외부 API 호출이 없다."""
    import analytics_insights
    for fn in ("player_profile_insight", "match_insight", "map_advice",
               "briefing_insight", "summarize_transcript"):
        setattr(analytics_insights, fn, lambda *a, **k: "[TEST] mock insight")

    import web_api
    from fastapi.testclient import TestClient
    with TestClient(web_api.app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_client(client):
    """로그인 완료(쿠키 설정)된 client."""
    r = client.post("/admin/login", json={"password": "test-admin-pw"})
    assert r.status_code == 200 and r.json().get("ok") is True
    return client
