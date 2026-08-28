"""bot.write_to_db가 enemy_players를 save_match로 그대로 전달하는지 검증.

bot.py는 discord.py를 모듈 상단에서 임포트하지만, requirements.txt 의존이라
로컬·CI 모두 설치되어 있어 스텁 없이 직접 임포트한다 (conftest가 더미 토큰 세팅).
"""
import bot


def test_write_to_db_forwards_enemy(monkeypatch):
    captured = {}

    def fake_save_match(**kwargs):
        captured.update(kwargs)
        return {"match_id": 1, "saved": 5, "mode": "HP", "duplicate": False,
                "result": "WIN", "team_score": 250, "opponent_score": 198,
                "map": "Combine", "opponent": {"team_id": None, "saved": 5}}

    monkeypatch.setattr(bot.stats_repo, "save_match", fake_save_match)
    bot.write_to_db("HP", [{"name": "Shisui", "k": 1, "d": 1, "score": 100}],
                    "2026-08-28", map_name="Combine", result="WIN",
                    team_score=250, opponent_score=198,
                    enemy_players=[{"name": "Alpha", "k": 1, "d": 1, "score": 90}])
    assert captured["enemy_players"] == [{"name": "Alpha", "k": 1, "d": 1, "score": 90}]


def test_write_to_db_default_enemy_none(monkeypatch):
    """enemy_players 미지정 시 None으로 전달 (기존 호출부 호환)."""
    captured = {}

    def fake_save_match(**kwargs):
        captured.update(kwargs)
        return {"match_id": 1, "saved": 5, "mode": "HP", "duplicate": False}

    monkeypatch.setattr(bot.stats_repo, "save_match", fake_save_match)
    bot.write_to_db("HP", [{"name": "Shisui", "k": 1, "d": 1, "score": 100}], "2026-08-28")
    assert captured["enemy_players"] is None
