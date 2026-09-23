# 우리팀 방향 확인 플로우 + 오염 방지 회귀 테스트
#
# 커버:
#  1. stats_repo.swap_sides — 코치가 반대쪽을 ours로 확정할 때의 뒤집기
#     (배열 스왑·승패/점수 반전·GPT 정규화 이름 ign_raw 되돌리기)
#  2. bot.load_roster — 상대팀에 동명(norm)이 있는 이름은 GPT 힌트에서 제외
#  3. admin_write.delete_match — opponent_stats_*까지 삭제 (배포 FK 500 방지)
#  4. /admin/opponents 렌더 — pending 51건(>LIMIT 50) 상태에서 500 방지
#     (배포 사고: replace에 int 전달 — 1e77125과 동일 계열 다른 줄)
import admin_write
import bot
import db
import stats_repo


class TestSwapSides:
    def test_swap_arrays_and_flip_result(self):
        ours = [{"name": "Kingz", "k": 1}]
        enemy = [{"name": "uD Fabuloso", "k": 2}]
        out = stats_repo.swap_sides(ours, enemy, "WIN", 250, 198)
        assert [p["name"] for p in out["players"]] == ["uD Fabuloso"]
        assert [p["name"] for p in out["enemy_players"]] == ["Kingz"]
        assert out["result"] == "LOSS"
        assert out["team_score"] == 198
        assert out["opponent_score"] == 250

    def test_normalized_name_restored_from_ign_raw(self):
        """GPT가 상대 'Shisui'를 우리 로스터명으로 정규화해도 ign_raw가 있으면
        뒤집기 시 원본 이름으로 상대팀에 저장된다."""
        ours = [{"name": "Kingz", "ign_raw": "Shisui", "k": 5}]
        enemy = [{"name": "uD Legacy", "k": 3}]
        out = stats_repo.swap_sides(ours, enemy, "LOSS", 3, 6)
        assert out["enemy_players"][0]["name"] == "Shisui"
        assert out["enemy_players"][0]["ign_raw"] == "Shisui"

    def test_no_ign_raw_keeps_name(self):
        ours = [{"name": "Kingz", "k": 1}]  # ign_raw 없음 → 이름 그대로
        out = stats_repo.swap_sides(ours, [], None, None, None)
        assert out["enemy_players"][0]["name"] == "Kingz"
        assert out["result"] is None
        assert out["team_score"] is None

    def test_inputs_not_mutated(self):
        ours = [{"name": "Kingz", "ign_raw": "Shisui", "k": 5}]
        enemy = [{"name": "uD Legacy", "k": 3}]
        snap_ours, snap_enemy = dict(ours[0]), dict(enemy[0])
        stats_repo.swap_sides(ours, enemy, "WIN", 1, 2)
        assert ours[0] == snap_ours and enemy[0] == snap_enemy


class TestRosterHintFilter:
    def test_opponent_clash_name_excluded(self, seeded_db):
        """players에 상대와 동명(norm)인 이름이 섞여 있으면 힌트에서 제외 —
        오염 이름이 GPT에 '우리 로스터'로 주입되는 자기강화 방지."""
        with db.get_conn() as conn:
            conn.execute_returning_id(
                "INSERT INTO opponent_players(name) VALUES (?)", ("SHISUI",))
        roster = bot.load_roster()
        assert "Shisui" not in roster      # norm 일치 → 제외
        assert "Cartels" in roster         # 충돌 없음 → 유지

    def test_roster_never_empty(self, seeded_db):
        """필터 후에도 로스터는 비지 않는다 (전원 충돌 시 필터 포기)."""
        assert bot.load_roster()


class TestDeleteMatchOpponentStats:
    def test_delete_match_removes_opponent_rows(self, client):
        r = client.post("/admin/login", json={"password": "test-admin-pw"})
        assert r.json().get("ok") is True
        with db.get_conn() as conn:
            mid = conn.execute_returning_id(
                "INSERT INTO matches(mode, match_date, season) "
                "VALUES ('HP','2026-09-20','s2')")
            pid = conn.execute_returning_id(
                "INSERT INTO opponent_players(name) VALUES (?)", ("dm Opp",))
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills) "
                "VALUES (?,?,?,1)"), (mid, pid, "dm Opp"))
            # 매치에 묶인 코칭 노트 — 삭제 시 태그만 끊리고 노트는 보존
            conn.execute(db._adapt_sql(
                "INSERT INTO coaching_notes(content, match_id, status) "
                "VALUES ('dm note', ?, 'open')"), (mid,))
        assert admin_write.delete_match(mid) is True
        with db.get_conn() as conn:
            assert conn.execute(
                "SELECT COUNT(*) c FROM opponent_stats_hp WHERE match_id=?",
                (mid,)).fetchone()["c"] == 0
            note = conn.execute(
                "SELECT match_id, content FROM coaching_notes WHERE content='dm note'"
            ).fetchone()
            assert note is not None and note["match_id"] is None


class TestPendingMoreRender:
    def test_page_renders_with_51_pending(self, client):
        """pending > 50 (LIMIT) 상태에서 opp_pending_more 줄이 렌더되어도 200 —
        배포 사고: replace('{n}', int) TypeError (2026-09-23)."""
        r = client.post("/admin/login", json={"password": "test-admin-pw"})
        assert r.json().get("ok") is True
        with db.get_conn() as conn:
            pid = conn.execute_returning_id(
                "INSERT INTO opponent_players(name) VALUES (?)", ("pm Opp",))
            for i in range(51):
                mid = conn.execute_returning_id(
                    "INSERT INTO matches(mode, match_date, season) "
                    "VALUES ('HP', ?, 's2')", (f"2026-09-{(i % 28) + 1:02d}",))
                conn.execute(db._adapt_sql(
                    "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw) "
                    "VALUES (?,?,?)"), (mid, pid, f"pm{i}"))
        r = client.get("/admin/opponents")
        assert r.status_code == 200
