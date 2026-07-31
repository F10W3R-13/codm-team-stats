import os
import tempfile

import db
import standings


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.init_db(path)
    return path


def _seed_teams(path, *names):
    return [db.insert_team(n, path=path) for n in names]


def test_standings_points_win2_loss0():
    """승=2점, 패=0점."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha 250-200 승
        db.insert_match("HP", "Combine", "2026-08-01", t1, t2,
                        250, 200, "round_robin", path=path)
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        bravo = next(r for r in table if r["team_id"] == t2)
        assert alpha["points"] == 2
        assert alpha["wins"] == 1
        assert bravo["points"] == 0
        assert bravo["losses"] == 1
    finally:
        os.unlink(path)


def test_standings_tiebreak_by_diff():
    """동점 시 득실차."""
    path = _fresh_db()
    try:
        t1, t2, t3 = _seed_teams(path, "Alpha", "Bravo", "Charlie")
        # Alpha 1승 (드로 250-200, diff +50)
        db.insert_match("HP", "M1", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        # Charlie 1승 (250-240, diff +10)
        db.insert_match("HP", "M2", "2026-08-01", t3, t2, 250, 240,
                        "round_robin", path=path)
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        charlie = next(r for r in table if r["team_id"] == t3)
        assert alpha["points"] == 2 and charlie["points"] == 2
        assert table[0]["team_id"] == t1  # Alpha diff +50 > Charlie +10
    finally:
        os.unlink(path)


def test_standings_excludes_final_from_round_robin():
    """결승 매치는 풀리그 순위에서 제외."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        db.insert_match("HP", "RR", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        db.insert_match("HP", "Final", "2026-08-02", t2, t1, 250, 240,
                        "final", path=path)
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        # 결승은 카운트 안 함 → Alpha는 풀리그 1승만
        assert alpha["played"] == 1
        assert alpha["wins"] == 1
    finally:
        os.unlink(path)


def test_final_match_returns_stage_final():
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        db.insert_match("HP", "RR", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        final_id = db.insert_match("HP", "Final", "2026-08-02", t2, t1,
                                   250, 240, "final", path=path)
        fm = standings.final_match(path=path)
        assert fm["match_id"] == final_id
        assert fm["winner_name"] == "Bravo"  # team_a (Bravo) 250 > 240
    finally:
        os.unlink(path)
