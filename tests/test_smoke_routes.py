# 라우트 스모크 테스트 — 전 GET 라우트가 fixture DB에서 200(또는 기대 코드)을 내는지.
#
# 목적: "로컬에선 통과, 배포에서 500"류(템플릿 오류·정의 안 된 변수·쿼리 오류)를
# 잡는 최후의 안전망. 페이지 내용의 정확성은 따지지 않는다.

PUBLIC_PAGES = [
    "/",
    "/players",
    "/players/Shisui",
    "/compare",
    "/compare?a=Shisui&b=Cartels",
    "/compare?a=Shisui&b=Cartels&mode=SND",
    "/leaderboard",
    "/leaderboard?mode=SND",
    "/matches",
    "/maps",
    "/maps/Takeoff",
    "/maps/Firing%20Range?mode=SND",
    "/api/player/Shisui/timeseries",
]


def test_public_pages_200(client):
    for path in PUBLIC_PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


def test_lang_variants_render(client):
    # 3개국어 사전 키 누락으로 인한 렌더 실패 방지 (test_i18n과 상호보완)
    for lang in ("ko", "en", "es"):
        for path in ("/", "/players", "/matches", "/leaderboard"):
            r = client.get(path, params={"lang": lang})
            assert r.status_code == 200, f"{path}?lang={lang} → {r.status_code}"


def test_match_detail_200(client, seeded_db):
    for mid in (seeded_db["hp_match_id"], seeded_db["snd_match_id"]):
        r = client.get(f"/matches/{mid}")
        assert r.status_code == 200, f"/matches/{mid} → {r.status_code}: {r.text[:200]}"


def test_unknown_player_404(client):
    assert client.get("/players/NoSuchPlayer").status_code == 404
    assert client.get("/matches/999999").status_code == 404


def test_admin_redirects_without_cookie(client):
    # 비인증 → 로그인 리다이렉트(303). 500이면 middleware/redirect 버그.
    # follow_redirects=False: TestClient(httpx)가 기본적으로 리다이렉트를 따라가 200으로 위장함
    for path in ("/admin", "/admin/aliases", "/admin/players"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, f"{path} → {r.status_code}"


def test_admin_login_flow(client):
    r = client.post("/admin/login", json={"password": "wrong-password"})
    assert r.status_code == 401


def test_admin_pages_with_cookie(admin_client, seeded_db):
    paths = [
        "/admin",
        "/admin/aliases",
        "/admin/aliases?source=Merge",   # 병합 필터 — Query pattern 누락 시 422 (2026-08 실사고)
        "/admin/aliases?source=OCR%20Auto",
        "/admin/players",
        f"/admin/match/{seeded_db['hp_match_id']}",
        "/admin/day/2026-08-01",
    ]
    for path in paths:
        r = admin_client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


def test_insight_endpoints_no_gpt(client, seeded_db):
    # GPT는 conftest에서 목킹됨 — 엔드포인트 배선·캐시 경로가 깨지지 않았는지만 확인
    paths = [
        "/api/insight/player/Shisui",
        f"/api/insight/match/{seeded_db['hp_match_id']}",
        "/api/insight/map/Takeoff",
        "/api/insight/briefing",
    ]
    for path in paths:
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
