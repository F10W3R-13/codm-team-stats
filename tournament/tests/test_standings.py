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


def test_final_match_returns_none_until_implemented():
    """결승 Bo7 구조 미구현 → final_match는 None 반환 (추후 구현 시 확장)."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        db.insert_match("HP", "RR", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        db.insert_match("HP", "Final", "2026-08-02", t2, t1,
                        250, 240, "final", path=path)
        fm = standings.final_match(path=path)
        assert fm is None  # Bo7 결승 구조 구현 전까지 None
    finally:
        os.unlink(path)


def test_duel_set_score():
    """팀 대결 세트 스코어: HP/SND 각 승자 → 세트 다승."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha HP 승 (250-200), Bravo SND 승 (5-9) → 1-1
        db.insert_match("HP", "M", "2026-08-01", t1, t2, 250, 200, "round_robin", path=path)
        db.insert_match("SND", "M", "2026-08-01", t1, t2, 5, 9, "round_robin", path=path)
        duels = standings.duel_details(path=path)
        assert len(duels) == 1
        d = duels[0]
        assert d["t1_sets"] == 1  # Alpha HP 승
        assert d["t2_sets"] == 1  # Bravo SND 승
        assert d["winner"] is None  # 1-1 동점
        assert not d["completed"]  # Control 없어서 미완료
    finally:
        os.unlink(path)


def test_duel_completed_with_control():
    """3세트(HP+SND+CTL) 있으면 완료된 대결."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha 2-1 승 (HP, CTL 승 / SND 패)
        db.insert_match("HP", "M", "d", t1, t2, 250, 200, "round_robin", path=path)
        db.insert_match("SND", "M", "d", t1, t2, 5, 9, "round_robin", path=path)
        db.insert_match("CTL", "M", "d", t1, t2, 3, 1, "round_robin", path=path)
        duels = standings.duel_details(path=path)
        d = duels[0]
        assert d["t1_sets"] == 2
        assert d["t2_sets"] == 1
        assert d["winner"] == "Alpha"
        assert d["completed"]
    finally:
        os.unlink(path)
