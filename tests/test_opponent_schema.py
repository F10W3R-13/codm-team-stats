# 상대팀 전적/H2H 스키마 테스트 (task 2)
# brief 원본 + db.init_db() 호출 한 줄 (get_conn은 스키마를 생성하지 않아 필요)
import db

db.init_db()


def test_opponent_tables_exist():
    with db.get_conn() as conn:
        for tbl in ("opponent_teams", "opponent_players", "opponent_aliases",
                    "opponent_team_rosters", "opponent_stats_hp", "opponent_stats_snd"):
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,)).fetchone()
            assert row, f"{tbl} 테이블 없음"


def test_matches_has_opponent_team_id():
    with db.get_conn() as conn:
        row = conn.execute("PRAGMA table_info(matches)").fetchall()
        cols = [r["name"] for r in row]
        assert "opponent_team_id" in cols


def test_opponent_stats_columns_mirror_ours():
    with db.get_conn() as conn:
        ours = [r["name"] for r in conn.execute("PRAGMA table_info(player_stats_hp)")]
        theirs = [r["name"] for r in conn.execute("PRAGMA table_info(opponent_stats_hp)")]
        assert ours == theirs  # 컬럼 구조 동일 (FK 대상만 다름)
