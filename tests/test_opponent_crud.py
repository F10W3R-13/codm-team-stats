# R1 상대팀 관리 CRUD (docs/plans/opponent-remake.plan.md) —
# 팀 이름변경/삭제, 로스터 행 제거, 매치 지정 해제, 상대 alias 관리,
# 팀 중복 norm 검사(D3). 라우트는 인증 미들웨어가 보호 → admin_client 사용
# (tests/test_opponent_admin.py와 동일 패턴·쿠키 격리).
# 테스트 DB는 세션 공유 → 팀/선수명에 'rc' 접두를 붙여 고유성 유지.

import pytest
from fastapi.testclient import TestClient  # noqa: F401

import admin_write
import db


@pytest.fixture(scope="module")
def admin_client(client):
    r = client.post("/admin/login", json={"password": "test-admin-pw"})
    assert r.status_code == 200 and r.json().get("ok") is True
    yield client
    client.cookies.clear()


def _mk_team(name):
    with db.get_conn() as conn:
        return conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", (name,))


def _mk_opp_player(name):
    with db.get_conn() as conn:
        return conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", (name,))


def _mk_match():
    with db.get_conn() as conn:
        return conn.execute_returning_id(
            "INSERT INTO matches(mode, map_name, match_date, season) VALUES (?,?,?,?)",
            ("HP", "Summit", "2026-09-10", "s2"))


class TestTeamCrud:
    def test_rename_keeps_roster(self, admin_client):
        tid = _mk_team("rc RenameMe")
        pid = _mk_opp_player("rc RenamePlayer")
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_team_rosters(team_id, player_id, source) "
                "VALUES (?, ?, 'manual')"), (tid, pid))
        r = admin_client.post("/admin/opponent/team/rename",
                              json={"team_id": tid, "name": "rc Renamed!"})
        assert r.json()["ok"] is True
        with db.get_conn() as conn:
            assert conn.execute(
                "SELECT name FROM opponent_teams WHERE id=?", (tid,),
            ).fetchone()["name"] == "rc Renamed!"
            # 로스터·선수 연결은 team_id 기반이라 자동 유지
            assert conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_team_rosters WHERE team_id=?"),
                (tid,)).fetchone()["c"] == 1

    def test_rename_norm_duplicate_rejected(self, admin_client):
        _mk_team("rc Zephyr7")           # norm: rczephyr7
        tid2 = _mk_team("rc Other Team")
        r = admin_client.post("/admin/opponent/team/rename",
                              json={"team_id": tid2, "name": "rc ZEPHYR 7!!"})
        assert r.json()["ok"] is False

    def test_rename_empty_rejected(self, admin_client):
        tid = _mk_team("rc EmptyProbe")
        r = admin_client.post("/admin/opponent/team/rename",
                              json={"team_id": tid, "name": "   "})
        assert r.json()["ok"] is False

    def test_delete_preserves_players_and_nulls_matches(self, admin_client):
        tid = _mk_team("rc DelTeam")
        pid = _mk_opp_player("rc DelPlayer")
        mid = _mk_match()
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
                "VALUES (?,?,?,?,?)"), (mid, pid, "rc DelPlayer", 3, 4))
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_team_rosters(team_id, player_id, source) "
                "VALUES (?, ?, 'match')"), (tid, pid))
            conn.execute(db._adapt_sql(
                "UPDATE matches SET opponent_team_id=? WHERE id=?"), (tid, mid))
        r = admin_client.post("/admin/opponent/team/delete", json={"team_id": tid})
        assert r.json()["ok"] is True
        with db.get_conn() as conn:
            assert conn.execute(
                "SELECT id FROM opponent_teams WHERE id=?", (tid,),
            ).fetchone() is None
            # 매치 태그 해제
            assert conn.execute(db._adapt_sql(
                "SELECT opponent_team_id FROM matches WHERE id=?"),
                (mid,)).fetchone()["opponent_team_id"] is None
            # 로스터 행 제거
            assert conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_team_rosters WHERE team_id=?"),
                (tid,)).fetchone()["c"] == 0
            # 선수·스탯은 보존 (실수 복구 가능 정책)
            assert conn.execute(
                "SELECT id FROM opponent_players WHERE id=?", (pid,),
            ).fetchone() is not None
            assert conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_stats_hp WHERE match_id=?"),
                (mid,)).fetchone()["c"] == 1

    def test_add_team_norm_duplicate_rejected(self, admin_client):
        """D3: 정확 일치가 아니어도 norm이 같으면 중복 거부."""
        _mk_team("rc NormDup")
        j1 = admin_client.post("/admin/opponent/team",
                               json={"name": "rc NORM DUP!!"}).json()
        assert j1["ok"] is False
        j2 = admin_client.post("/admin/opponent/team",
                               json={"name": "rc FreshTeam"}).json()
        assert j2["ok"] is True


class TestRosterAndUnassign:
    def test_remove_roster_row(self, admin_client):
        tid = _mk_team("rc RosTeam")
        pid = _mk_opp_player("rc RosPlayer")
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_team_rosters(team_id, player_id, source) "
                "VALUES (?, ?, 'registered')"), (tid, pid))
        r = admin_client.post("/admin/opponent/roster/remove",
                              json={"team_id": tid, "player_id": pid})
        assert r.json()["ok"] is True
        with db.get_conn() as conn:
            assert conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_team_rosters "
                "WHERE team_id=? AND player_id=?"), (tid, pid)).fetchone()["c"] == 0

    def test_unassign_match_keeps_stats(self, admin_client):
        tid = _mk_team("rc UnTeam")
        pid = _mk_opp_player("rc UnPlayer")
        mid = _mk_match()
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw) "
                "VALUES (?,?,?)"), (mid, pid, "rc UnPlayer"))
            conn.execute(db._adapt_sql(
                "UPDATE matches SET opponent_team_id=? WHERE id=?"), (tid, mid))
        r = admin_client.post("/admin/opponent/match-unassign",
                              json={"match_id": mid})
        assert r.json()["ok"] is True
        with db.get_conn() as conn:
            assert conn.execute(db._adapt_sql(
                "SELECT opponent_team_id FROM matches WHERE id=?"),
                (mid,)).fetchone()["opponent_team_id"] is None
            # 스탯 행은 무변동 (재지정은 assign이 담당)
            assert conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_stats_hp "
                "WHERE match_id=? AND player_id=?"), (mid, pid)).fetchone()["c"] == 1


class TestOpponentAliasCrud:
    def test_alias_add_duplicate_unknown_remove(self, admin_client):
        pid = _mk_opp_player("rc AliasTarget")
        assert pid
        r = admin_client.post("/admin/opponent/alias",
                              json={"ign": "rcAliasProbe7", "player_name": "rc AliasTarget"})
        assert r.json()["ok"] is True
        # 이미 쓰인 IGN은 다른 선수에게 등록 불가 (UNIQUE)
        _mk_opp_player("rc AliasOther")
        r2 = admin_client.post("/admin/opponent/alias",
                               json={"ign": "rcAliasProbe7", "player_name": "rc AliasOther"})
        assert r2.json()["ok"] is False
        # 없는 상대 선수에는 등록 불가 (신규 생성은 봇/병합 흐름 전용)
        r3 = admin_client.post("/admin/opponent/alias",
                               json={"ign": "rcAliasProbe8", "player_name": "rc NoSuchOpp"})
        assert r3.json()["ok"] is False
        # 삭제
        r4 = admin_client.request("DELETE", "/admin/opponent/alias",
                                  params={"ign": "rcAliasProbe7"})
        assert r4.json()["ok"] is True
        with db.get_conn() as conn:
            assert conn.execute(db._adapt_sql(
                "SELECT COUNT(*) c FROM opponent_aliases WHERE ign=?"),
                ("rcAliasProbe7",)).fetchone()["c"] == 0

    def test_admin_data_includes_aliases(self, admin_client):
        data = admin_write.opponent_admin_data()
        assert "aliases" in data
        assert all({"ign", "player_name", "source"} <= set(a) for a in data["aliases"])


class TestR3AdminUx:
    def test_admin_data_pending_total_and_recent_matches(self, admin_client):
        import admin_write
        data = admin_write.opponent_admin_data()
        assert "pending_total" in data and isinstance(data["pending_total"], int)
        assert all("recent_matches" in t for t in data["teams"])

    def test_page_has_new_ui_hooks(self, admin_client):
        # 훅 검증용 팀 1개 보장 (세션 공유 DB라도 팀 0 방어)
        _mk_team("rc HookTeam")
        html = admin_client.get("/admin/opponents").text
        assert "rename-form" in html          # 팀 이름변경 폼
        assert "delete-team-btn" in html      # 팀 삭제 버튼
        assert "roster-remove-btn" in html    # 로스터 행 제거
        assert "unassign-form" in html        # 매치 지정 해제
        assert "alias-form" in html           # 상대 alias 추가 폼
        assert "alias-del-btn" in html        # alias 삭제 버튼
        assert "ignore-alias" in html         # D1 재매칭 체크박스
        assert "opp_confirm_merge" in html or "confirm(" in html  # 병합 confirm

    def test_source_enum_localized(self, admin_client):
        import i18n
        tid = _mk_team("rc SrcTeam")
        pid = _mk_opp_player("rc SrcPlayer")
        with db.get_conn() as conn:
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_team_rosters(team_id, player_id, source) "
                "VALUES (?, ?, 'registered')"), (tid, pid))
        html = admin_client.get("/admin/opponents").text
        assert "rc SrcPlayer" in html
        # registered 원시 enum이 아닌 번역 표기가 렌더되어야 함
        assert i18n.get("ko")["opp_source_registered"] in html
