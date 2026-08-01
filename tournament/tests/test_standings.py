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


def test_standings_bo5_win_3_sets():
    """Bo5: 한 팀이 3승(과반수)하면 확정 승. 승=2점."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha 3-0 (HP, SND, CTL 전부 승)
        db.insert_match("HP", "M", "d", t1, t2, 250, 200, "round_robin", path=path)
        db.insert_match("SND", "M", "d", t1, t2, 6, 4, "round_robin", path=path)
        db.insert_match("CTL", "M", "d", t1, t2, 3, 1, "round_robin", path=path)
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        bravo = next(r for r in table if r["team_id"] == t2)
        assert alpha["wins"] == 1 and alpha["points"] == 2
        assert bravo["losses"] == 1 and bravo["points"] == 0
    finally:
        os.unlink(path)


def test_standings_bo5_incomplete_no_win():
    """Bo5: 3승 미만이면 미완료 → 승패 반영 안 함."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha 2-0 (HP, SND만, CTL 미입력) → 미완료
        db.insert_match("HP", "M", "d", t1, t2, 250, 200, "round_robin", path=path)
        db.insert_match("SND", "M", "d", t1, t2, 6, 4, "round_robin", path=path)
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        assert alpha["wins"] == 0  # 미완료 → 승 없음
        assert alpha["duels_pending"] == 1
    finally:
        os.unlink(path)


def test_standings_bo5_cycling_modes():
    """Bo5 세트 순환: HP→SND→CTL→HP→SND. 같은 모드 여러 번 정상."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha 3-2 (HP, SND, CTL 패, HP, SND)
        db.insert_match("HP", "M", "d", t1, t2, 250, 200, "round_robin", path=path)   # A 승 1-0
        db.insert_match("SND", "M", "d", t1, t2, 6, 4, "round_robin", path=path)      # A 승 2-0
        db.insert_match("CTL", "M", "d", t1, t2, 1, 3, "round_robin", path=path)      # B 승 2-1
        db.insert_match("HP", "M", "d", t1, t2, 250, 248, "round_robin", path=path)   # A 승 3-1 완료
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        assert alpha["wins"] == 1  # 3-1로 확정
        duels = standings.duel_details(path=path)
        assert duels[0]["t1_sets"] == 3 and duels[0]["t2_sets"] == 1
        assert duels[0]["completed"]
    finally:
        os.unlink(path)


def test_standings_tiebreak_by_diff():
    """동점 시 세트 득실차."""
    path = _fresh_db()
    try:
        t1, t2, t3 = _seed_teams(path, "Alpha", "Bravo", "Charlie")
        # Alpha 3-0 (완료, 세트 +3)
        for mode in ["HP", "SND", "CTL"]:
            db.insert_match(mode, "M", "d", t1, t2, 250, 200, "round_robin", path=path)
        # Charlie 3-2 (완료, 세트 +1)
        db.insert_match("HP", "M", "d", t3, t2, 250, 200, "round_robin", path=path)
        db.insert_match("SND", "M", "d", t3, t2, 6, 4, "round_robin", path=path)
        db.insert_match("CTL", "M", "d", t2, t3, 3, 1, "round_robin", path=path)  # B 승
        db.insert_match("HP", "M", "d", t3, t2, 250, 200, "round_robin", path=path)  # C 3-1
        table = standings.compute(path=path)
        alpha = next(r for r in table if r["team_id"] == t1)
        charlie = next(r for r in table if r["team_id"] == t3)
        assert alpha["points"] == 2 and charlie["points"] == 2  # 둘 다 1승
        assert alpha["sets_diff"] > charlie["sets_diff"]  # +3 > +1
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
    """Bo5: 3승(과반수)하면 완료. CTL 포함 3-0."""
    path = _fresh_db()
    try:
        t1, t2 = _seed_teams(path, "Alpha", "Bravo")
        # Alpha 3-0 (HP, SND, CTL 전부 승)
        db.insert_match("HP", "M", "d", t1, t2, 250, 200, "round_robin", path=path)
        db.insert_match("SND", "M", "d", t1, t2, 6, 4, "round_robin", path=path)
        db.insert_match("CTL", "M", "d", t1, t2, 3, 1, "round_robin", path=path)
        duels = standings.duel_details(path=path)
        d = duels[0]
        assert d["t1_sets"] == 3
        assert d["t2_sets"] == 0
        assert d["winner"] == "Alpha"
        assert d["completed"]
    finally:
        os.unlink(path)
