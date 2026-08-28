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
