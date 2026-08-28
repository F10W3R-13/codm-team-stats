# tests/test_opponent_resolve.py
# brief 원본 + db.init_db() 호출 한 줄 (get_conn은 스키마를 생성하지 않아 필요)
# + autouse 격리 fixture (conftest의 임시 DB가 세션 내 공유되어
#   _seed_roster의 UNIQUE(name) 재삽입이 터지는 것을 방지 — 상대팀 테이블만 초기화)
import pytest

import db

db.init_db()


@pytest.fixture(autouse=True)
def _fresh_opponent_tables():
    with db.get_conn() as conn:
        for tbl in ("opponent_aliases", "opponent_team_rosters",
                    "opponent_stats_hp", "opponent_stats_snd",
                    "opponent_players", "opponent_teams"):
            conn.execute(f"DELETE FROM {tbl}")
        # 병합 테스트가 남긴 player_stats 없는 고아 매치 정리 (시드 매치는 보존)
        conn.execute(
            "DELETE FROM matches WHERE id NOT IN "
            "(SELECT match_id FROM player_stats_hp UNION "
            " SELECT match_id FROM player_stats_snd)")
    yield


def _seed_roster(conn):
    """Godlike = Alpha/Beta/Gamma, Kings = Delta 등록."""
    teams = {}
    for tname in ("Godlike", "Kings"):
        teams[tname] = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", (tname,))
    pids = {}
    for pname, tname in [("Alpha", "Godlike"), ("Beta", "Godlike"), ("Gamma", "Godlike"),
                         ("Delta", "Kings")]:
        pid = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", (pname,))
        pids[pname] = pid
        conn.upsert("opponent_team_rosters", ["team_id", "player_id", "source"],
                    (teams[tname], pid, "registered"), conflict_col="team_id, player_id")
    return teams, pids


def test_resolve_exact_then_alias_learning():
    with db.get_conn() as conn:
        teams, pids = _seed_roster(conn)
        # 정확 매칭
        assert db.resolve_opponent_player_id(conn, "alpha", team_id=teams["Godlike"]) == pids["Alpha"]
        # OCR 변형이 alias로 학습됐는지
        row = conn.execute("SELECT opponent_player_id FROM opponent_aliases WHERE ign='alpha'").fetchone()
        assert row and row["opponent_player_id"] == pids["Alpha"]


def test_resolve_fuzzy_ocr_variant():
    with db.get_conn() as conn:
        teams, pids = _seed_roster(conn)
        # 팀 풀 퍼지: Alphа(Cyrillic а) → 정규화 후 "alph" ≠ "alpha", 유사도 0.888
        pid = db.resolve_opponent_player_id(conn, "Alphа", team_id=teams["Godlike"])
        assert pid == pids["Alpha"]


def test_resolve_new_player_created():
    with db.get_conn() as conn:
        teams, _ = _seed_roster(conn)
        before = conn.execute("SELECT COUNT(*) c FROM opponent_players").fetchone()["c"]
        db.resolve_opponent_player_id(conn, "BrandNewMerc", team_id=teams["Godlike"])
        after = conn.execute("SELECT COUNT(*) c FROM opponent_players").fetchone()["c"]
        assert after == before + 1  # 신규 엔트리 (admin 병합 대기)


def test_identify_team_majority():
    with db.get_conn() as conn:
        teams, _ = _seed_roster(conn)
        names = ["Alpha", "Beta", "Gamma", "UnknownSub1", "UnknownSub2"]
        assert db.identify_opponent_team(conn, names) == teams["Godlike"]


def test_identify_team_ambiguous_returns_none():
    with db.get_conn() as conn:
        teams, _ = _seed_roster(conn)
        names = ["Alpha", "Delta", "New1", "New2", "New3"]  # 1:1 동률
        assert db.identify_opponent_team(conn, names) is None


def test_merge_opponent_player_moves_stats():
    with db.get_conn() as conn:
        teams, pids = _seed_roster(conn)
        mid = conn.execute_returning_id(
            "INSERT INTO matches(mode, match_date) VALUES ('HP', '2026-08-28')")
        src = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("Renegul8808",))
        conn.execute(db._adapt_sql(
            "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
            "VALUES (?,?,?,?,?)"), (mid, src, "Renegul8808", 10, 5))
        db._learn_opponent_alias(conn, "Renegul8808", src)
        # merge_opponent_player는 자체 get_conn()을 열므로(merge_player 선례와 동일),
        # 외부 커넥션의 미커밋 쓰기 잠금을 먼저 해제한다 (SQLite 잠금 데드락 방지).
        conn.commit()
        result = db.merge_opponent_player(src, pids["Alpha"])
        assert result["ok"] is True
        row = conn.execute(db._adapt_sql(
            "SELECT player_id FROM opponent_stats_hp WHERE match_id=?"), (mid,)).fetchone()
        assert row["player_id"] == pids["Alpha"]
        # alias도 치환
        a = conn.execute("SELECT opponent_player_id FROM opponent_aliases WHERE ign='Renegul8808'").fetchone()
        assert a["opponent_player_id"] == pids["Alpha"]
        # src 선수 삭제
        gone = conn.execute("SELECT id FROM opponent_players WHERE id=?", (src,)).fetchone()
        assert gone is None
