import os
import tempfile

import db
import stage


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.init_db(path)
    return path


def test_first_meeting_is_round_robin():
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        assert stage.determine_stage(t1, t2, path=path) == "round_robin"
    finally:
        os.unlink(path)


def test_second_meeting_is_final():
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        # 첫 매치 등록
        db.insert_match("HP", "Combine", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        # 두 번째 만남 → 결승
        assert stage.determine_stage(t1, t2, path=path) == "final"
    finally:
        os.unlink(path)


def test_second_meeting_reverse_order_is_final():
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        db.insert_match("HP", "Combine", "2026-08-01", t1, t2, 250, 200,
                        "round_robin", path=path)
        # 팀 순서 바뀌어도 같은 쌍 → 결승
        assert stage.determine_stage(t2, t1, path=path) == "final"
    finally:
        os.unlink(path)
