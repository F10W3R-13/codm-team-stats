# R2 매칭 품질 (docs/plans/opponent-remake.plan.md) —
# D1: 잘못 학습된 alias를 ignore_alias 재매칭으로 교정(purge→재학습 rebound)
# OCR 의심 이름: 스탯은 저장하되 로스터 자동 축적 제외.
# 팀/선수명에 'rm' 접두 — 세션 공유 DB 고유성 유지 (test_opponent_admin 주석 참조).

import pytest
from fastapi.testclient import TestClient  # noqa: F401

import db
import stats_repo


@pytest.fixture(scope="module")
def admin_client(client):
    r = client.post("/admin/login", json={"password": "test-admin-pw"})
    assert r.status_code == 200 and r.json().get("ok") is True
    yield client
    client.cookies.clear()


def _mk_opp(name):
    with db.get_conn() as conn:
        return conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", (name,))


def _mk_alias(ign, pid):
    with db.get_conn() as conn:
        conn.execute(db._adapt_sql(
            "INSERT INTO opponent_aliases(ign, opponent_player_id, source) "
            "VALUES (?,?,'Auto')"), (ign, pid))


def _mk_match():
    with db.get_conn() as conn:
        return conn.execute_returning_id(
            "INSERT INTO matches(mode, map_name, match_date, season) VALUES (?,?,?,?)",
            ("HP", "Summit", "2026-09-10", "s2"))


def _opp_pid(match_id, ign_raw):
    with db.get_conn() as conn:
        row = conn.execute(db._adapt_sql(
            "SELECT player_id FROM opponent_stats_hp WHERE match_id=? AND ign_raw=?"),
            (match_id, ign_raw)).fetchone()
    return row["player_id"] if row else None


_OUR_PLAYER = [{"name": "rmOurProbe", "k": 1, "d": 1, "kd_ratio": 1.0,
                "time": 50, "score": 100, "total_damage": 150, "capture_kill": 0}]


class TestD1IgnoreAlias:
    def test_wrong_alias_fixed_by_ignore_alias(self, admin_client):
        # 팀 + 로스터 rmAlpha
        tid = admin_client.post("/admin/opponent/team",
                                json={"name": "rm IgTeam"}).json()["team_id"]
        admin_client.post("/admin/opponent/roster",
                          json={"team_id": tid, "names": "rmAlpha"})
        # 과거 잘못 학습된 alias: rmAipha → rmWrong
        wrong_id = _mk_opp("rmWrong")
        _mk_alias("rmAipha", wrong_id)
        # 매치: rmAipha 스탯이 wrong에 귀속된 상태
        mid = _mk_match()
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
                "VALUES (?,?,?,?,?)"), (mid, wrong_id, "rmAipha", 2, 3))

        # 기본 assign: alias 우선이라 여전히 wrong (현행 동작 — D1 문서화)
        r1 = admin_client.post("/admin/opponent/match-team",
                               json={"match_id": mid, "team_id": tid})
        assert r1.json()["ok"] is True
        assert _opp_pid(mid, "rmAipha") == wrong_id

        # ignore_alias 재매칭 → rmAlpha로 교정 + alias 재학습(rebound)
        r2 = admin_client.post("/admin/opponent/match-team",
                               json={"match_id": mid, "team_id": tid,
                                     "ignore_alias": True})
        assert r2.json()["ok"] is True
        with db.get_conn() as conn:
            alpha = conn.execute(db._adapt_sql(
                "SELECT id FROM opponent_players WHERE name = ?"),
                ("rmAlpha",)).fetchone()
            relearned = conn.execute(db._adapt_sql(
                "SELECT opponent_player_id FROM opponent_aliases WHERE ign = ?"),
                ("rmAipha",)).fetchone()
        assert _opp_pid(mid, "rmAipha") == alpha["id"]
        assert relearned is not None and relearned["opponent_player_id"] == alpha["id"]


class TestOcrSuspectRosterSkip:
    def test_suspect_stats_saved_but_roster_skipped(self, admin_client):
        tid = admin_client.post("/admin/opponent/team",
                                json={"name": "rm SusTeam"}).json()["team_id"]
        admin_client.post("/admin/opponent/roster",
                          json={"team_id": tid, "names": "rmGhost\nrmBeta"})
        info = stats_repo.save_match(
            mode="HP", players=_OUR_PLAYER,
            match_date="2026-09-10", map_name="Summit",
            enemy_players=[
                {"name": "rmGhost", "k": 1, "d": 1, "score": 100},
                {"name": "rmBeta", "k": 1, "d": 1, "score": 100},
                {"name": "[386yLR", "k": 1, "d": 1, "score": 100},
            ])
        # 정상 2명 다수결(2/3 ≥ 0.6)로 팀 자동 태그
        assert info["opponent"]["team_id"] == tid
        mid = info["match_id"]
        with db.get_conn() as conn:
            n_stats = conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_stats_hp WHERE match_id=?"),
                (mid,)).fetchone()["c"]
            suspect = conn.execute(db._adapt_sql(
                "SELECT id FROM opponent_players WHERE name = ?"),
                ("[386yLR",)).fetchone()
            roster_n = conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_team_rosters "
                "WHERE team_id=? AND player_id=?"),
                (tid, suspect["id"])).fetchone()["c"]
        # 스탯은 3명 전부 저장…
        assert n_stats == 3
        # …지만 OCR 의심 이름은 로스터에 축적하지 않는다
        assert roster_n == 0

    def test_is_ocr_suspect_predicate(self):
        import opponent_matching
        assert opponent_matching.is_ocr_suspect("[386yLR") is True
        assert opponent_matching.is_ocr_suspect("rmGhost") is False
        assert opponent_matching.is_ocr_suspect("") is True
        assert opponent_matching.is_ocr_suspect("EXCL 4") is True


class TestGlobalNameConflict:
    def test_assign_name_exists_globally_not_in_roster(self, admin_client):
        """배포 500 수정: 팀 로스터에 없지만 전역에 존재하는 이름(예: 무소속/타팀 Jim)은
        신규 INSERT가 아니라 기존 선수로 귀속되어야 한다 (opponent_players_name_key)."""
        jim_id = _mk_opp("rm2Jim")  # 전역엔 있음, 팀 로스터엔 없음
        tid = admin_client.post("/admin/opponent/team",
                                json={"name": "rm2 Team"}).json()["team_id"]
        admin_client.post("/admin/opponent/roster",
                          json={"team_id": tid, "names": "rm2Alpha"})
        mid = _mk_match()
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
                "VALUES (?,?,?,?,?)"), (mid, jim_id, "rm2Jim", 1, 2))
        r = admin_client.post("/admin/opponent/match-team",
                              json={"match_id": mid, "team_id": tid})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert _opp_pid(mid, "rm2Jim") == jim_id
