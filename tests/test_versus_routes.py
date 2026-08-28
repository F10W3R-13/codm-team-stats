def test_versus_page_200_empty(client):
    r = client.get("/versus")
    assert r.status_code == 200


def test_versus_overview_counts(client):
    import db
    import queries
    import stats_repo
    with db.get_conn() as conn:
        # 전체 스위트에서 선행 opponent 테스트와 이름 충돌 방지 (UNIQUE 제약).
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("VersusUnited",))
    # 세션 공유 DB 오염 방지: total_damage 포함 + 시드와 무관한 고유 선수명.
    for i, res in enumerate(["WIN", "LOSS", "WIN"]):
        stats_repo.save_match(
            mode="HP", players=[{"name": "VersusTester", "k": 10, "d": 5,
                                 "score": 2000, "total_damage": 1500}],
            match_date=f"2026-08-2{i}", map_name="Summit", result=res,
            team_score=250, opponent_score=200)
        with db.get_conn() as conn:
            mid = conn.execute("SELECT MAX(id) id FROM matches").fetchone()["id"]
            conn.execute(db._adapt_sql(
                "UPDATE matches SET opponent_team_id=? WHERE id=?"), (tid, mid))
    rows = queries.versus_overview()
    team = next(t for t in rows if t["name"] == "VersusUnited")
    assert team["match_n"] == 3
    assert team["wins"] == 2
    assert team["losses"] == 1
