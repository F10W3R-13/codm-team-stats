"""선수 순위 + MVP/개인상 산출.

MVP = (자기 HP 매치들의 ZCS 평균) + (자기 SND 매치들의 RDS 평균).
평균이라 HP 매치 많아도 유리하지 않음 (모드 불균형 보정).
ZCS/RDS 공식은 부모 metrics.py에서 import (출처 고정).
"""
import _path_setup  # noqa: F401
from metrics import compute_zcs, compute_rds

import db


def player_rankings(path: str = None) -> list:
    """전체 선수 순위 (mvp_score = avg_zcs + avg_rds 내림차순)."""
    conn = db.get_conn(path)
    try:
        players = [dict(r) for r in conn.execute(
            """SELECT p.id, p.name, t.name AS team_name
               FROM players p JOIN teams t ON t.id = p.team_id
               ORDER BY p.name""").fetchall()]
        hp_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM player_stats_hp").fetchall()]
        snd_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM player_stats_snd").fetchall()]
    finally:
        conn.close()

    # 선수별 스탯 누적
    agg = {p["id"]: {**p, "hp_zcs": [], "snd_rds": [],
                     "kills": 0, "deaths": 0, "damage": 0}
           for p in players}
    for r in hp_rows:
        if r["player_id"] not in agg:
            continue
        zcs = compute_zcs(r["obj_time"] or 0, r["capture_kill"] or 0,
                          r["kills"] or 0, r["deaths"] or 0)
        if zcs is not None:
            agg[r["player_id"]]["hp_zcs"].append(zcs)
        agg[r["player_id"]]["kills"] += r["kills"] or 0
        agg[r["player_id"]]["deaths"] += r["deaths"] or 0
        agg[r["player_id"]]["damage"] += r["damage"] or 0
    for r in snd_rows:
        if r["player_id"] not in agg:
            continue
        rds = compute_rds(r["kills"] or 0, r["assists"] or 0,
                          r["first_kill"] or 0, r["lone_wolf_win"] or 0,
                          r["adr"] or 0, r["deaths"] or 0)
        if rds is not None:
            agg[r["player_id"]]["snd_rds"].append(rds)
        agg[r["player_id"]]["kills"] += r["kills"] or 0
        agg[r["player_id"]]["deaths"] += r["deaths"] or 0
        agg[r["player_id"]]["damage"] += r["damage"] or 0

    result = []
    for a in agg.values():
        avg_zcs = round(sum(a["hp_zcs"]) / len(a["hp_zcs"]), 2) if a["hp_zcs"] else 0.0
        avg_rds = round(sum(a["snd_rds"]) / len(a["snd_rds"]), 2) if a["snd_rds"] else 0.0
        kd = round(a["kills"] / a["deaths"], 2) if a["deaths"] else float(a["kills"])
        result.append({
            "player_id": a["id"], "name": a["name"], "team_name": a["team_name"],
            "hp_matches": len(a["hp_zcs"]), "snd_matches": len(a["snd_rds"]),
            "avg_zcs": avg_zcs, "avg_rds": avg_rds,
            "total_kills": a["kills"], "total_deaths": a["deaths"],
            "kd": kd, "total_damage": a["damage"],
            "mvp_score": round(avg_zcs + avg_rds, 2),
        })

    result.sort(key=lambda r: (-r["mvp_score"], -r["total_kills"], r["name"]))
    return result


def mvps(path: str = None) -> dict:
    """개인상 5종. 매치 기록 없으면 각 None."""
    rankings = player_rankings(path)
    if not rankings:
        return {"mvp": None, "top_kills": None, "top_kd": None,
                "most_deaths": None, "top_damage": None}

    return {
        "mvp": rankings[0],
        "top_kills": max(rankings, key=lambda r: r["total_kills"]),
        "top_kd": max(rankings, key=lambda r: r["kd"]),
        "most_deaths": max(rankings, key=lambda r: r["total_deaths"]),
        "top_damage": max(rankings, key=lambda r: r["total_damage"]),
    }
