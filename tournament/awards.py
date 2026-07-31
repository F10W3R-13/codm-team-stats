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


def _avg(vals):
    """None/빈 리스트 안전 평균."""
    nums = [v for v in vals if v is not None]
    return round(sum(nums) / len(nums), 2) if nums else 0.0


def _sum(vals):
    """None 안전 합산."""
    return sum(v or 0 for v in vals)


def hp_rankings(path: str = None) -> list:
    """HP 매치만 집계한 선수 상세 순위 (모든 HP 지표). ZCS 순."""
    conn = db.get_conn(path)
    try:
        players = [dict(r) for r in conn.execute(
            """SELECT p.id, p.name, t.name AS team_name
               FROM players p JOIN teams t ON t.id = p.team_id""").fetchall()]
        rows = [dict(r) for r in conn.execute("SELECT * FROM player_stats_hp").fetchall()]
    finally:
        conn.close()

    agg = {p["id"]: {**p, "rows": []} for p in players}
    for r in rows:
        if r["player_id"] in agg:
            agg[r["player_id"]]["rows"].append(r)

    result = []
    for a in agg.values():
        rs = a["rows"]
        if not rs:
            continue  # HP 매치 없는 선수 제외
        result.append({
            "player_id": a["id"], "name": a["name"], "team_name": a["team_name"],
            "matches": len(rs),
            "kills": _avg([r["kills"] for r in rs]),
            "deaths": _avg([r["deaths"] for r in rs]),
            "assists": _avg([r["assists"] for r in rs]),
            "damage": _avg([r["damage"] for r in rs]),
            "obj_time": _avg([r["obj_time"] for r in rs]),
            "capture_kill": _avg([r["capture_kill"] for r in rs]),
            "avg_zcs": _avg([compute_zcs(r["obj_time"] or 0, r["capture_kill"] or 0,
                                         r["kills"] or 0, r["deaths"] or 0) for r in rs]),
            "kd": round(_sum([r["kills"] for r in rs]) / max(1, _sum([r["deaths"] for r in rs])), 2),
        })
    result.sort(key=lambda r: (-r["avg_zcs"], -r["kills"], r["name"]))
    return result


def snd_rankings(path: str = None) -> list:
    """SND 매치만 집계한 선수 상세 순위 (모든 SND 지표). RDS 순."""
    conn = db.get_conn(path)
    try:
        players = [dict(r) for r in conn.execute(
            """SELECT p.id, p.name, t.name AS team_name
               FROM players p JOIN teams t ON t.id = p.team_id""").fetchall()]
        rows = [dict(r) for r in conn.execute("SELECT * FROM player_stats_snd").fetchall()]
    finally:
        conn.close()

    agg = {p["id"]: {**p, "rows": []} for p in players}
    for r in rows:
        if r["player_id"] in agg:
            agg[r["player_id"]]["rows"].append(r)

    result = []
    for a in agg.values():
        rs = a["rows"]
        if not rs:
            continue  # SND 매치 없는 선수 제외
        result.append({
            "player_id": a["id"], "name": a["name"], "team_name": a["team_name"],
            "matches": len(rs),
            "kills": _avg([r["kills"] for r in rs]),
            "deaths": _avg([r["deaths"] for r in rs]),
            "assists": _avg([r["assists"] for r in rs]),
            "damage": _avg([r["damage"] for r in rs]),
            "adr": _avg([r["adr"] for r in rs]),
            "first_kill": _avg([r["first_kill"] for r in rs]),
            "lone_wolf_win": _avg([r["lone_wolf_win"] for r in rs]),
            "avg_rds": _avg([compute_rds(r["kills"] or 0, r["assists"] or 0,
                                         r["first_kill"] or 0, r["lone_wolf_win"] or 0,
                                         r["adr"] or 0, r["deaths"] or 0) for r in rs]),
            "kd": round(_sum([r["kills"] for r in rs]) / max(1, _sum([r["deaths"] for r in rs])), 2),
        })
    result.sort(key=lambda r: (-r["avg_rds"], -r["kills"], r["name"]))
    return result
