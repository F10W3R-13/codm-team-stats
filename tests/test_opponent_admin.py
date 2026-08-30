# 상대팀 관리 탭 (Task 7) — /admin/opponents 페이지 + 팀 등록/로스터 POST.
# /admin/* 라우트는 인증 미들웨어가 걸려 있어 admin_client(로그인 쿠키) 사용
# (tests/test_smoke_routes.py::test_admin_pages_with_cookie 와 동일 방식).
# client가 session 스코프라 모듈 종료 시 쿠키를 지운다 — 그렇지 않으면
# 알파벳순으로 먼저 도는 이 파일이 test_smoke_routes의 비인증 리다이렉트
# 테스트를 오염시킨다 (로그인 상태 유지 → 303 기대가 200으로 깨짐).

import pytest
from fastapi.testclient import TestClient  # noqa: F401


@pytest.fixture(scope="module")
def admin_client(client):
    """이 모듈 전용 로그인 client — 모듈 종료 후 쿠키 정리 (테스트 격리)."""
    r = client.post("/admin/login", json={"password": "test-admin-pw"})
    assert r.status_code == 200 and r.json().get("ok") is True
    yield client
    client.cookies.clear()


def test_admin_opponents_page_200(admin_client):
    r = admin_client.get("/admin/opponents")
    assert r.status_code == 200


def test_add_team_and_roster(admin_client):
    r = admin_client.post("/admin/opponent/team", json={"name": "Godlike"})
    assert r.json()["ok"] is True
    r2 = admin_client.post(
        "/admin/opponent/roster",
        json={"team_id": r.json()["team_id"], "names": "Alpha\nBeta\nGamma"},
    )
    assert r2.json()["ok"] is True
    data = __import__("admin_write").opponent_admin_data()
    team = next(t for t in data["teams"] if t["name"] == "Godlike")
    assert len(team["roster"]) == 3


def test_assign_match_team_and_rematch(admin_client):
    # 팀 등록 + enemy 있는 매치 저장(팀은 미확정 — 로스터 없이 저장)
    # 주의: 테스트 DB는 세션 공유라 시드 선수(Shisui 등)를 쓰면 맵별 지표
    # 집계가 오염된다 (불완전 스탯 → SQLite max(0,NULL)=NULL). 고유 선수명 +
    # 전체 스탯 필드로 저장해 격리를 지킨다.
    import db
    import stats_repo
    import admin_write
    r = admin_client.post("/admin/opponent/team", json={"name": "Kings"})
    tid = r.json()["team_id"]
    info = stats_repo.save_match(
        mode="HP",
        players=[{"name": "AssignProbe", "k": 1, "d": 1, "kd_ratio": 1.0,
                  "time": 50, "score": 100, "total_damage": 150, "capture_kill": 0}],
        match_date="2026-08-28", map_name="Summit",
        enemy_players=[{"name": "K1ngzman", "k": 2, "d": 2, "score": 110}])
    assert info["opponent"]["team_id"] is None  # 로스터 없어 미확정

    # 로스터 등록 후 매치에 팀 지정 → ign_raw 재매칭
    admin_client.post("/admin/opponent/roster", json={"team_id": tid, "names": "Kingzman"})
    ok = admin_client.post("/admin/opponent/match-team",
                           json={"match_id": info["match_id"], "team_id": tid})
    assert ok.json()["ok"] is True
    data = admin_write.opponent_admin_data()
    # 미확정 목록에서 빠졌는지 재확인
    assert all(p["id"] != info["match_id"] for p in data["pending"])
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


def test_merge_opponent_route(admin_client):
    import db
    with db.get_conn() as conn:
        dst = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("RealName",))
        src = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("WrongSplit",))
    r = admin_client.post("/admin/opponent/merge",
                          json={"src_player_id": src, "dst_player_id": dst})
    assert r.json()["ok"] is True
    with db.get_conn() as conn:
        assert conn.execute("SELECT id FROM opponent_players WHERE id=?",
                            (src,)).fetchone() is None


def test_attention_list_only_teamless_or_suspect(admin_client):
    """병합 섹션 = 확인 필요 선수(팀 없음 or OCR 의심)만 — 등록+정상 표기는 제외."""
    import admin_write
    import db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("ProbeTeam",))
        clean_id = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("CleanProbe",))
        conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("[GarbageProbe",))
        conn.execute(db._adapt_sql(
            "INSERT INTO opponent_team_rosters(team_id, player_id, source) "
            "VALUES (?, ?, 'manual')"), (tid, clean_id))
    data = admin_write.opponent_admin_data()
    names = [p["name"] for p in data["recent_opponents"]]
    assert "CleanProbe" not in names       # 팀 있음 + 정상 표기 → 제외
    assert "[GarbageProbe" in names        # OCR 의심 → 포함
    row = next(p for p in data["recent_opponents"] if p["name"] == "[GarbageProbe")
    assert row["no_team"] is True and row["ocr_suspect"] is True
