import os
import tempfile
from unittest.mock import patch

import db
import import_pipeline


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.init_db(path)
    return path


def _mock_gpt_response():
    """GPT가 파싱한 것처럼 가짜 응답 반환."""
    return {
        "mode": "HP",
        "map": "Combine",
        "team_left_score": 250,
        "team_right_score": 198,
        "team_left": [
            {"name": "Ace", "k": 20, "d": 10, "kd_ratio": 2.0, "time": 120,
             "score": 2500, "impact": 100, "total_damage": 3000, "capture_kill": 2},
            {"name": "Sniper", "k": 15, "d": 12, "kd_ratio": 1.25, "time": 100,
             "score": 2000, "impact": 90, "total_damage": 2800, "capture_kill": 1},
            {"name": "King", "k": 18, "d": 11, "kd_ratio": 1.64, "time": 110,
             "score": 2200, "impact": 95, "total_damage": 2900, "capture_kill": 1},
            {"name": "Ghost", "k": 12, "d": 14, "kd_ratio": 0.86, "time": 90,
             "score": 1800, "impact": 80, "total_damage": 2500, "capture_kill": 0},
            {"name": "Wolf", "k": 14, "d": 13, "kd_ratio": 1.08, "time": 95,
             "score": 1900, "impact": 85, "total_damage": 2600, "capture_kill": 1},
        ],
        "team_right": [
            {"name": "Blaze", "k": 16, "d": 15, "kd_ratio": 1.07, "time": 105,
             "score": 2100, "impact": 88, "total_damage": 2700, "capture_kill": 1},
            {"name": "Storm", "k": 13, "d": 16, "kd_ratio": 0.81, "time": 85,
             "score": 1700, "impact": 75, "total_damage": 2400, "capture_kill": 0},
            {"name": "Frost", "k": 11, "d": 17, "kd_ratio": 0.65, "time": 80,
             "score": 1600, "impact": 70, "total_damage": 2300, "capture_kill": 0},
            {"name": "Thunder", "k": 17, "d": 12, "kd_ratio": 1.42, "time": 115,
             "score": 2300, "impact": 92, "total_damage": 2850, "capture_kill": 1},
            {"name": "Shadow", "k": 10, "d": 18, "kd_ratio": 0.56, "time": 75,
             "score": 1500, "impact": 68, "total_damage": 2200, "capture_kill": 0},
        ],
    }


def test_preview_identifies_teams_by_roster():
    """GPT 응답 → 5명이 같은 팀에 매핑되는지 역추적."""
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        for n in ["Ace", "Sniper", "King", "Ghost", "Wolf"]:
            db.insert_player(n, t1, path=path)
        for n in ["Blaze", "Storm", "Frost", "Thunder", "Shadow"]:
            db.insert_player(n, t2, path=path)

        with patch("import_pipeline.analyze_two_screens",
                   return_value=_mock_gpt_response()):
            preview = import_pipeline.preview(b"\x00", b"\x00", path=path)

        assert preview["mode"] == "HP"
        assert preview["team_a_name"] == "Alpha"
        assert preview["team_b_name"] == "Bravo"
        assert len(preview["team_a"]) == 5
        assert len(preview["team_b"]) == 5
        assert preview["unmatched"] == []
    finally:
        os.unlink(path)


def test_preview_collects_unmatched_igns():
    """매칭 안 된 IGN은 unmatched 리스트로."""
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        # Alpha엔 2명만 시드 → 3명은 unmatched
        for n in ["Ace", "Sniper"]:
            db.insert_player(n, t1, path=path)
        for n in ["Blaze", "Storm", "Frost", "Thunder", "Shadow"]:
            db.insert_player(n, t2, path=path)

        with patch("import_pipeline.analyze_two_screens",
                   return_value=_mock_gpt_response()):
            preview = import_pipeline.preview(b"\x00", b"\x00", path=path)

        assert len(preview["unmatched"]) == 3  # King, Ghost, Wolf
        assert "King" in preview["unmatched"]
    finally:
        os.unlink(path)


def test_confirm_inserts_match_and_stats():
    """미리보기 확정 → 매치 + 10명 스탯 INSERT."""
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        for n in ["Ace", "Sniper", "King", "Ghost", "Wolf"]:
            db.insert_player(n, t1, path=path)
        for n in ["Blaze", "Storm", "Frost", "Thunder", "Shadow"]:
            db.insert_player(n, t2, path=path)

        with patch("import_pipeline.analyze_two_screens",
                   return_value=_mock_gpt_response()):
            preview = import_pipeline.preview(b"\x00", b"\x00", path=path)
            match_id = import_pipeline.confirm(preview, path=path)

        assert match_id > 0
        import sqlite3
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        match = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        hp_count = conn.execute("SELECT COUNT(*) FROM player_stats_hp").fetchone()[0]
        conn.close()
        assert match["stage"] == "round_robin"  # 첫 만남
        assert match["team_a_score"] == 250
        assert hp_count == 10  # 양 팀 10명
    finally:
        os.unlink(path)


def test_confirm_auto_assigns_final_on_second_meeting():
    """같은 팀쌍 두 번째 매치 → 자동 final."""
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        for n in ["Ace", "Sniper", "King", "Ghost", "Wolf"]:
            db.insert_player(n, t1, path=path)
        for n in ["Blaze", "Storm", "Frost", "Thunder", "Shadow"]:
            db.insert_player(n, t2, path=path)
        # 첫 매치 수동 등록
        db.insert_match("HP", "M1", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)

        with patch("import_pipeline.analyze_two_screens",
                   return_value=_mock_gpt_response()):
            preview = import_pipeline.preview(b"\x00", b"\x00", path=path)
            match_id = import_pipeline.confirm(preview, path=path)

        import sqlite3
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        match = conn.execute("SELECT stage FROM matches WHERE id=?",
                             (match_id,)).fetchone()
        conn.close()
        assert match["stage"] == "final"
    finally:
        os.unlink(path)
