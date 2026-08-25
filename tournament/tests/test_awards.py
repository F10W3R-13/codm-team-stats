import os
import tempfile

import db
import awards


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.init_db(path)
    return path


def test_player_rankings_empty():
    path = _fresh_db()
    try:
        assert awards.player_rankings(path=path) == []
    finally:
        os.unlink(path)


def test_mvp_highest_avg_zcs_plus_rds():
    """MVP = avg_zcs + avg_rds 최고."""
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        p_star = db.insert_player("Star", t1, path=path)  # MVP 후보
        p_avg = db.insert_player("Avg", t1, path=path)
        mid = db.insert_match("HP", "M1", "2026-08-01", t1, t2, 250, 200,
                              "round_robin", path=path)
        # Star: K=30 D=5 OBJ=120 CK=4 → ZCS=132+32+4.1*26-25=132+32+106.6-25=245.6
        db.insert_player_stats_hp(mid, p_star, t1, kills=30, deaths=5,
                                  obj_time=120, capture_kill=4, damage=4000,
                                  path=path)
        # Avg: K=10 D=10 OBJ=50 CK=1 → ZCS=55+8+4.1*9-50=55+8+36.9-50=49.9
        db.insert_player_stats_hp(mid, p_avg, t1, kills=10, deaths=10,
                                  obj_time=50, capture_kill=1, damage=2000,
                                  path=path)
        rankings = awards.player_rankings(path=path)
        assert rankings[0]["name"] == "Star"
        assert rankings[0]["mvp_score"] > rankings[1]["mvp_score"]
    finally:
        os.unlink(path)


def test_mvps_individual_awards():
    """개인상: MVP, 최다킬, 최고 K/D, 광탈왕, 딜러."""
    path = _fresh_db()
    try:
        t1 = db.insert_team("Alpha", path=path)
        t2 = db.insert_team("Bravo", path=path)
        p_killer = db.insert_player("Killer", t1, path=path)
        p_feeder = db.insert_player("Feeder", t1, path=path)
        p_dealer = db.insert_player("Dealer", t1, path=path)
        mid = db.insert_match("HP", "M1", "2026-08-01", t1, t2, 250, 200,
                              "round_robin", path=path)
        db.insert_player_stats_hp(mid, p_killer, t1, kills=30, deaths=2,
                                  obj_time=100, capture_kill=2, damage=3000,
                                  path=path)
        db.insert_player_stats_hp(mid, p_feeder, t1, kills=5, deaths=25,
                                  obj_time=50, capture_kill=0, damage=1000,
                                  path=path)
        db.insert_player_stats_hp(mid, p_dealer, t1, kills=15, deaths=10,
                                  obj_time=80, capture_kill=1, damage=5000,
                                  path=path)
        mvps = awards.mvps(path=path)
        assert mvps["top_kills"]["name"] == "Killer"
        assert mvps["top_kd"]["name"] == "Killer"  # 30/2=15.0 최고
        assert mvps["most_deaths"]["name"] == "Feeder"
        assert mvps["top_damage"]["name"] == "Dealer"
    finally:
        os.unlink(path)
