# stats_repo.save_match 재업로드(중복) 처리 테스트
#
# 시나리오:
#  1. 동일 스탯 재업로드 → 새 매치 생성 안 함 (duplicate=True, saved=0)
#  2. 부분 인식(4명) 저장 후 전체(5명) 재업로드 → 기존 매치에 병합 (saved=1)
#  3. 같은 날 같은 맵이지만 스탯이 다른 경기 → 새 매치 정상 생성
#  4. 병합 시 기존 매치의 NULL meta(result/스코어/맵) 채움
#  5. missing_result_count (허브 경고 배지용 쿼리)

import db
import queries
import stats_repo
from conftest import HP_MATCH_1


def _match_ids(mode="HP"):
    with db.get_conn() as conn:
        rows = conn.execute(
            db._adapt_sql("SELECT id FROM matches WHERE mode=?"), (mode,)
        ).fetchall()
    return {r["id"] for r in rows}


def test_exact_duplicate_skips_insert(seeded_db):
    before = _match_ids()
    r = stats_repo.save_match("HP", HP_MATCH_1, "2026-08-01",
                              map_name="Takeoff", result="WIN",
                              team_score=250, opponent_score=207)
    assert r["duplicate"] is True
    assert r["saved"] == 0
    assert r["match_id"] == seeded_db["hp_match_id"]
    assert _match_ids() == before  # 새 매치 생성 없음


def test_partial_reupload_merges_missing_player(seeded_db):
    before = _match_ids()
    # 4명만 인식된 저장 (스탯을 살짝 바꿔 진짜 새 매치로 만든다)
    partial = [dict(p) for p in HP_MATCH_1[:4]]
    for p in partial:
        p["k"] = p["k"] + 100
    r0 = stats_repo.save_match("HP", partial, "2026-08-02", map_name="Takeoff")
    assert r0["duplicate"] is False

    # 같은 경기를 5명 전체로 재업로드 → 기존 매치에 병합
    full = [dict(p) for p in partial] + [dict(HP_MATCH_1[4])]
    r1 = stats_repo.save_match("HP", full, "2026-08-02", map_name="Takeoff")
    assert r1["duplicate"] is True
    assert r1["saved"] == 1
    assert r1["match_id"] == r0["match_id"]
    assert _match_ids() == before | {r0["match_id"]}  # 병합 → 추가 매치 없음


def test_different_stats_creates_new_match(seeded_db):
    # 같은 날·같은 맵 실제 2번째 경기 (스탯이 다름) → 중복 아님
    changed = [dict(p) for p in HP_MATCH_1]
    for p in changed:
        p["k"] = p["k"] + 1
    r = stats_repo.save_match("HP", changed, "2026-08-01", map_name="Takeoff",
                              result="LOSS", team_score=180, opponent_score=250)
    assert r["duplicate"] is False
    assert r["match_id"] != seeded_db["hp_match_id"]
    assert r["saved"] == len(changed)


def test_merge_fills_null_meta(seeded_db):
    # 맵/승패 못 읽은 부분 저장 → 재업로드가 NULL meta를 채움
    partial = [dict(p) for p in HP_MATCH_1[:3]]
    for p in partial:
        p["d"] = p["d"] + 50
    r0 = stats_repo.save_match("HP", partial, "2026-08-03")  # map/result/score 전부 없음
    assert r0["duplicate"] is False

    full = partial + [dict(p) for p in HP_MATCH_1[3:]]
    r1 = stats_repo.save_match("HP", full, "2026-08-03", map_name="Takeoff",
                               result="WIN", team_score=250, opponent_score=200)
    assert r1["duplicate"] is True
    assert r1["match_id"] == r0["match_id"]

    with db.get_conn() as conn:
        m = conn.execute(
            db._adapt_sql("SELECT result, team_score, map_name FROM matches WHERE id=?"),
            (r0["match_id"],),
        ).fetchone()
    assert m["result"] == "WIN"
    assert m["team_score"] == 250
    assert m["map_name"] == "Takeoff"


def test_missing_result_count(seeded_db):
    # 상대 카운트로 검증 — 다른 테스트가 NULL-result 매치를 추가해도 순서 무관
    base = queries.missing_result_count()
    stats_repo.save_match("HP", [dict(p) for p in HP_MATCH_1], "2026-08-10",
                          map_name="Takeoff")  # result 의도적으로 생략
    assert queries.missing_result_count() == base + 1


def test_hub_missing_result_badge_rendering(client):
    """NULL-result 매치가 있으면 허브(관리자 로그인)에 경고 배지가 렌더된다."""
    client.post("/admin/login", json={"password": "test-admin-pw"})
    html = client.get("/").text
    if queries.missing_result_count() > 0:
        assert "승패 미입력 매치" in html  # 기본 lang=ko 렌더
    else:
        assert "승패 미입력 매치" not in html
