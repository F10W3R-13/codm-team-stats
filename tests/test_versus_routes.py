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


def test_versus_team_detail_h2h(client):
    import db
    import queries
    import stats_repo
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("H2HTeam",))
        opp_pid = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("TheirAce",))
    # 세션 공유 DB 오염 방지: 시드 "Shisui" 대신 고유명 "H2HProbe".
    # 스탯 값은 brief의 Shisui와 동일 → ZCS = 1.1*100 + 8*3 + 4.1*(20-3) - 5*10 = 153.7.
    info = stats_repo.save_match(
        mode="HP",
        players=[{"name": "H2HProbe", "k": 20, "d": 10, "kd_ratio": 2.0, "time": 100,
                  "score": 2500, "total_damage": 3000, "capture_kill": 3}],
        match_date="2026-08-28", map_name="Summit", result="WIN",
        team_score=250, opponent_score=100,
        enemy_players=[{"name": "TheirAce", "k": 8, "d": 15, "kd_ratio": 0.53,
                        "time": 90, "score": 1800, "impact": 80,
                        "total_damage": 1900, "capture_kill": 1}])
    with db.get_conn() as conn:
        conn.execute(db._adapt_sql(
            "UPDATE matches SET opponent_team_id=? WHERE id=?"), (tid, info["match_id"]))
    detail = queries.versus_team_detail(tid)
    assert detail["team"]["name"] == "H2HTeam"
    assert len(detail["matches"]) >= 1
    # 셀 검증: H2HProbe vs TheirAce — K-D diff = (20-10) - (8-15) = +17
    with db.get_conn() as conn:
        our_id = conn.execute(
            "SELECT id FROM players WHERE name='H2HProbe'").fetchone()["id"]
    cell = detail["h2h"]["cells"][(our_id, opp_pid)]
    assert cell["matches"] == 1
    assert cell["kd_diff"] == 17
    # ZCS diff: H2HProbe ZCS=153.7(conftest 손계산과 동일 입력) vs TheirAce
    # = 1.1*90 + 8*1 + 4.1*(8-1) - 5*15 = 99+8+28.7-75 = 60.7 → diff = 93.0
    assert abs(cell["metric_diff"] - (153.7 - 60.7)) < 0.01


def test_versus_team_page_200(client):
    import db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("PageTeam",))
    r = client.get(f"/versus/{tid}")
    assert r.status_code == 200


def test_versus_team_page_404(client):
    r = client.get("/versus/99999999")
    assert r.status_code == 404


# ── R4: versus 화면 강화 (docs/plans/opponent-remake.plan.md) ──────────────

def _rv4_fixture():
    """요약/로스터 검증용 팀: HP 2매치(1승1패) + 상대 rv4 Ace 스탯 2행."""
    import db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("rv4 Team",))
        pid = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("rv4 Ace",))
        conn.execute(db._adapt_sql(
            "INSERT INTO opponent_team_rosters(team_id, player_id, source) "
            "VALUES (?, ?, 'registered')"), (tid, pid))
        for res, ts, os_, k, d in [("WIN", 3, 2, 5, 2), ("LOSS", 2, 3, 3, 4)]:
            mid = conn.execute_returning_id(
                "INSERT INTO matches(mode, map_name, match_date, season, result, "
                "team_score, opponent_score, opponent_team_id) "
                "VALUES ('HP','Summit','2026-09-11','s2',?,?,?,?)",
                (res, ts, os_, tid))
            conn.execute(db._adapt_sql(
                "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
                "VALUES (?,?,?,?,?)"), (mid, pid, "rv4 Ace", k, d))
    return tid, pid


def test_versus_team_detail_summary_and_roster(client):
    import queries
    tid, pid = _rv4_fixture()
    d = queries.versus_team_detail(tid)
    s = d["summary"]
    assert s["total"] == 2 and s["wins"] == 1 and s["losses"] == 1
    assert s["win_rate"] == 50.0
    assert s["by_mode"]["HP"] == {"wins": 1, "losses": 1}
    ace = next(r for r in d["roster"] if r["name"] == "rv4 Ace")
    assert ace["games"] == 2 and ace["kills"] == 8 and ace["deaths"] == 6
    assert ace["source"] == "registered"


def test_versus_detail_null_score_renders_dash(client):
    import db
    with db.get_conn() as conn:
        tid = conn.execute_returning_id(
            "INSERT INTO opponent_teams(name) VALUES (?)", ("rv4 NullTeam",))
        pid = conn.execute_returning_id(
            "INSERT INTO opponent_players(name) VALUES (?)", ("rv4 NullAce",))
        mid = conn.execute_returning_id(
            "INSERT INTO matches(mode, map_name, match_date, season, opponent_team_id) "
            "VALUES ('HP','Summit','2026-09-12','s2',?)", (tid,))
        conn.execute(db._adapt_sql(
            "INSERT INTO opponent_stats_hp(match_id, player_id, ign_raw, kills, deaths) "
            "VALUES (?,?,?,?,?)"), (mid, pid, "rv4 NullAce", 1, 1))
    html = client.get(f"/versus/{tid}").text
    assert "None : None" not in html
    assert "—" in html
    import i18n
    assert i18n.get("ko")["versus_no_result"] in html


def test_versus_card_season_and_margin_label(client):
    import i18n
    html = client.get("/versus").text
    # 카드 링크 season 승계 + avg_margin 라벨
    assert "&season=" in html
    assert i18n.get("ko")["versus_avg_margin"] in html
