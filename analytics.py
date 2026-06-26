# 분석 리포트 데이터 생성
#
# 매치 리포트 / 주간 리포트 / 선수 트렌드 데이터를 DB에서 뽑아 정리한다.
# GPT 인사이트는 analytics_insights.py 에서 별도 처리.

import db
import metrics


# ── 매치 리포트 ────────────────────────────────────────────────────────────
def match_report(match_id: int) -> dict:
    """특정 매치의 분석 리포트.

    반환: {
        match_id, mode, map_name, match_date,
        players: [{name, k, d, ...}],            # 킬 내림차순
        team_totals: {kills, deaths, ...},        # 팀 합계
        mom: {name, reason},                      # Man of the Match
        best: {stat: {name, value}},              # 항목별 1위
        worst: {stat: {name, value}},             # 항목별 꼴찌
    } 또는 None
    """
    with db.get_conn() as conn:
        m = conn.execute(
            "SELECT id, mode, map_name, match_date, result, team_score, opponent_score "
            "FROM matches WHERE id=?",
            (match_id,),
        ).fetchone()
        if not m:
            return None

        result = {
            "match_id": m["id"], "mode": m["mode"],
            "map_name": m["map_name"], "match_date": m["match_date"],
            "result": m["result"], "team_score": m["team_score"],
            "opponent_score": m["opponent_score"],
            "players": [], "team_totals": {},
            "mom": None, "best": {}, "worst": {},
        }

        if m["mode"] == "HP":
            rows = conn.execute(
                """SELECT p.name, s.kills, s.deaths, s.kd_ratio, s.obj_time,
                          s.score, s.impact, s.total_damage, s.capture_kill
                   FROM player_stats_hp s JOIN players p ON p.id=s.player_id
                   WHERE s.match_id=? ORDER BY s.kills DESC""",
                (match_id,),
            ).fetchall()
            for r in rows:
                result["players"].append({
                    "name": r["name"], "k": r["kills"] or 0, "d": r["deaths"] or 0,
                    "kd": r["kd_ratio"] or 0, "obj": r["obj_time"] or 0,
                    "score": r["score"] or 0, "impact": r["impact"] or 0,
                    "dmg": r["total_damage"] or 0, "cap": r["capture_kill"] or 0,
                    "zcs": metrics.compute_zcs(r["obj_time"], r["capture_kill"],
                                               r["kills"], r["deaths"]),
                })
            result["team_totals"] = {
                "kills": sum(p["k"] for p in result["players"]),
                "deaths": sum(p["d"] for p in result["players"]),
                "score": sum(p["score"] for p in result["players"]),
                "dmg": sum(p["dmg"] for p in result["players"]),
                "obj": sum(p["obj"] for p in result["players"]),
                "zcs": round(sum(p["zcs"] for p in result["players"] if p["zcs"]) /
                             max(1, len([p for p in result["players"] if p["zcs"]])), 1),
            }
            # 항목별 1위/꼴찌 (높을수록 좋은 것)
            for stat, label in [("k", "킬"), ("kd", "K/D"), ("dmg", "딜"),
                                ("obj", "OBJ"), ("cap", "캡처킬"), ("impact", "임팩트")]:
                vals = [(p["name"], p[stat]) for p in result["players"]]
                if vals:
                    result["best"][label] = max(vals, key=lambda x: x[1])
                    result["worst"][label] = min(vals, key=lambda x: x[1])
            # MOM: 가장 높은 가중치 (K/D + 딜 + OBJ 종합 점수)
            if result["players"]:
                def score(p):
                    return (p["kd"] * 30) + (p["dmg"] / 100) + (p["obj"] / 5) + p["cap"]
                mom_p = max(result["players"], key=score)
                result["mom"] = {
                    "name": mom_p["name"],
                    "reason": f"K/D {mom_p['kd']} · {mom_p['k']}킬 · {mom_p['dmg']}딜 · OBJ {mom_p['obj']}초",
                }
        else:  # SND
            rows = conn.execute(
                """SELECT p.name, s.kills, s.deaths, s.assists, s.kd_ratio,
                          s.score, s.impact, s.adr, s.first_kill, s.lone_wolf_win
                   FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                   WHERE s.match_id=? ORDER BY s.kills DESC""",
                (match_id,),
            ).fetchall()
            for r in rows:
                result["players"].append({
                    "name": r["name"], "k": r["kills"] or 0, "d": r["deaths"] or 0,
                    "a": r["assists"] or 0, "kd": r["kd_ratio"] or 0,
                    "score": r["score"] or 0, "impact": r["impact"] or 0,
                    "adr": r["adr"] or 0, "fk": r["first_kill"] or 0,
                    "lww": r["lone_wolf_win"] or 0,
                })
            result["team_totals"] = {
                "kills": sum(p["k"] for p in result["players"]),
                "deaths": sum(p["d"] for p in result["players"]),
                "assists": sum(p["a"] for p in result["players"]),
                "fk": sum(p["fk"] for p in result["players"]),
            }
            for stat, label in [("k", "킬"), ("kd", "K/D"), ("adr", "ADR"),
                                ("fk", "퍼스트킬"), ("a", "어시스트")]:
                vals = [(p["name"], p[stat]) for p in result["players"]]
                if vals:
                    result["best"][label] = max(vals, key=lambda x: x[1])
                    result["worst"][label] = min(vals, key=lambda x: x[1])
            if result["players"]:
                def score(p):
                    return (p["kd"] * 25) + (p["adr"] / 5) + (p["fk"] * 5) + (p["a"] * 2)
                mom_p = max(result["players"], key=score)
                result["mom"] = {
                    "name": mom_p["name"],
                    "reason": f"K/D {mom_p['kd']} · {mom_p['k']}킬 · ADR {mom_p['adr']} · FK {mom_p['fk']}",
                }

    return result


# ── 주간 리포트 ────────────────────────────────────────────────────────────
def weekly_report(days: int = 7) -> dict:
    """최근 N일 트렌드 리포트 (최근 N일 평균 vs 전체 평균 비교).

    반환: {
        period: "최근 {days}일",
        matches_recent: int, matches_total: int,
        players: [{name, mode, recent_avg_kd, overall_avg_kd, delta_pct, trend}],
        team_recent: {kd, kills}, team_overall: {kd, kills},
    }
    """
    with db.get_conn() as conn:
        # 최근 N일 매치 수
        recent = conn.execute(
            f"""SELECT COUNT(*) c FROM matches
                WHERE match_date >= date('now', '-{int(days)} days')"""
        ).fetchone()["c"]
        total = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]

        result = {
            "period": f"최근 {days}일",
            "matches_recent": recent,
            "matches_total": total,
            "players": [],
        }

        for mode, table in [("HP", "player_stats_hp"), ("SND", "player_stats_snd")]:
            rows = conn.execute(
                f"""SELECT p.name,
                           ROUND(AVG(CASE WHEN m.match_date >= date('now', '-{days} days')
                                     THEN s.kd_ratio END),2) recent_kd,
                           ROUND(AVG(CASE WHEN m.match_date >= date('now', '-{days} days')
                                     THEN s.kills END),1) recent_k,
                           ROUND(AVG(s.kd_ratio),2) overall_kd,
                           ROUND(AVG(s.kills),1) overall_k,
                           SUM(CASE WHEN m.match_date >= date('now', '-{days} days')
                                THEN 1 ELSE 0 END) recent_matches,
                           COUNT(*) total_matches
                    FROM {table} s
                    JOIN matches m ON m.id = s.match_id
                    JOIN players p ON p.id = s.player_id
                    WHERE m.mode = ?
                    GROUP BY p.id
                    HAVING recent_matches > 0""",
                (mode,),
            ).fetchall()

            for r in rows:
                if r["recent_kd"] is None:
                    continue
                overall = r["overall_kd"] or 0
                recent_v = r["recent_kd"] or 0
                if overall > 0:
                    delta_pct = round((recent_v - overall) / overall * 100, 1)
                else:
                    delta_pct = 0
                trend = "📈" if delta_pct > 3 else ("📉" if delta_pct < -3 else "➡️")
                result["players"].append({
                    "name": r["name"], "mode": mode,
                    "recent_kd": recent_v, "overall_kd": overall,
                    "recent_k": r["recent_k"], "overall_k": r["overall_k"],
                    "recent_matches": r["recent_matches"],
                    "delta_pct": delta_pct, "trend": trend,
                })

        # trend 기준 정렬 (delta 내림차순)
        result["players"].sort(key=lambda x: x["delta_pct"], reverse=True)
    return result


# ── 선수 트렌드 ────────────────────────────────────────────────────────────
def player_trend(name: str, recent_n: int = 10) -> dict:
    """특정 선수의 최근 N매치 vs 전체 평균 비교 (HP 기준, 없으면 SND).

    반환: {
        name, mode, recent_matches, total_matches,
        recent: {avg_k, avg_d, avg_kd, ...}, overall: {...},
        delta: {kd_pct, k_pct, ...}, last_matches: [{date, k, d, kd}],
    } 또는 None
    """
    pid = None
    with db.get_conn() as conn:
        r = conn.execute(
            "SELECT id FROM players WHERE name=? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        if not r:
            return None
        pid = r["id"]

    # HP 먼저, 데이터 적으면 SND
    for mode, table in [("HP", "player_stats_hp"), ("SND", "player_stats_snd")]:
        with db.get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE player_id=?", (pid,)
            ).fetchone()["c"]
            if total < recent_n:
                continue

            # 전체 평균
            if mode == "HP":
                o = conn.execute(
                    f"""SELECT ROUND(AVG(kills),1) k, ROUND(AVG(deaths),1) d,
                               ROUND(AVG(kd_ratio),2) kd, ROUND(AVG(total_damage),0) dmg,
                               ROUND(AVG(score),0) score
                        FROM {table} WHERE player_id=?""",
                    (pid,),
                ).fetchone()
            else:
                o = conn.execute(
                    f"""SELECT ROUND(AVG(kills),1) k, ROUND(AVG(deaths),1) d,
                               ROUND(AVG(kd_ratio),2) kd, ROUND(AVG(adr),0) adr,
                               ROUND(AVG(score),0) score
                        FROM {table} WHERE player_id=?""",
                    (pid,),
                ).fetchone()

            # 최근 N매치 평균 (최신 순)
            if mode == "HP":
                recent_rows = conn.execute(
                    f"""SELECT m.match_date, s.kills k, s.deaths d, s.kd_ratio kd,
                               s.total_damage dmg, s.score
                        FROM {table} s JOIN matches m ON m.id=s.match_id
                        WHERE s.player_id=? ORDER BY m.id DESC LIMIT ?""",
                    (pid, recent_n),
                ).fetchall()
            else:
                recent_rows = conn.execute(
                    f"""SELECT m.match_date, s.kills k, s.deaths d, s.kd_ratio kd,
                               s.adr, s.score
                        FROM {table} s JOIN matches m ON m.id=s.match_id
                        WHERE s.player_id=? ORDER BY m.id DESC LIMIT ?""",
                    (pid, recent_n),
                ).fetchall()

            if not recent_rows:
                continue

            # 최근 평균 계산
            def avg(rows, key):
                vals = [r[key] for r in rows if r[key] is not None]
                return round(sum(vals) / len(vals), 2) if vals else 0

            recent = {
                "k": avg(recent_rows, "k"), "d": avg(recent_rows, "d"),
                "kd": avg(recent_rows, "kd"),
                "score": avg(recent_rows, "score"),
            }
            if mode == "HP":
                recent["dmg"] = avg(recent_rows, "dmg")
            else:
                recent["adr"] = avg(recent_rows, "adr")

            overall = {"k": o["k"], "d": o["d"], "kd": o["kd"], "score": o["score"]}
            if mode == "HP":
                overall["dmg"] = o["dmg"]
            else:
                overall["adr"] = o["adr"]

            delta = {}
            for key in ["kd", "k", "d"]:
                ov = overall[key] or 0
                if ov > 0:
                    delta[key + "_pct"] = round((recent[key] - ov) / ov * 100, 1)
                else:
                    delta[key + "_pct"] = 0

            last_matches = [
                {"date": r["match_date"], "k": r["k"], "d": r["d"], "kd": r["kd"]}
                for r in recent_rows
            ][::-1]  # 시간순(과거→최신)

            return {
                "name": name, "mode": mode,
                "recent_matches": len(recent_rows), "total_matches": total,
                "recent": recent, "overall": overall, "delta": delta,
                "last_matches": last_matches,
            }

    return None


def last_match_id(mode: str = None) -> int:
    """가장 최근 매치 ID."""
    with db.get_conn() as conn:
        if mode:
            r = conn.execute(
                "SELECT id FROM matches WHERE mode=? ORDER BY id DESC LIMIT 1",
                (mode,),
            ).fetchone()
        else:
            r = conn.execute(
                "SELECT id FROM matches ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return r["id"] if r else None


# ── 팀 인사이트 데이터 조립 ──────────────────────────────────────────────

def team_insights_data(days: int = 30, mode: str = "HP") -> dict:
    """팀 인사이트용 종합 데이터 조립 (GPT 인사이트 + 웹 표시용).

    반환: {
        trend: team_trend 결과,
        maps: [{map_name, matches, avg_kd, avg_k, avg_dmg, top_player, weak_player}],
    }
    """
    import queries
    trend = queries.team_trend(days)
    maps_raw = queries.map_team_stats(mode, min_matches=3)

    # 각 맵별 에이스/약점 선수 추가
    maps = []
    for m in maps_raw:
        players = queries.map_player_stats(m["map_name"], mode, min_matches=2)
        top = players[0] if players else None
        weak = players[-1] if players else None
        entry = dict(m)
        entry["top_player"] = {"name": top["player_name"], "kd": top["avg_kd"]} if top else None
        entry["weak_player"] = {"name": weak["player_name"], "kd": weak["avg_kd"]} if weak else None
        entry["players"] = players[:5]  # 상위 5명
        maps.append(entry)

    return {"trend": trend, "maps": maps, "mode": mode}


# ── 코칭 허브 데이터 조립 ──────────────────────────────────────────────────

def coaching_hub(mode: str = "HP", days: int = 30) -> dict:
    """코칭 허브(/ 홈)용 종합 데이터.

    "이번에 봐야 할 것"을 한눈에 보여주기 위한 요약:
    - 팀 트렌드(최근 vs 시즌)
    - 팀 승률 요약
    - 폼 경고: 시즌 평균 대비 최근 K/D 하락 선수
    - 맵 하이라이트: 가장 강한/약한 맵 (top 1)
    - 밴픽 힌트: 강한 맵은 픽, 약한 맵은 밴

    반환: {
        trend, win_loss, mode, days,
        form_alerts: [{name, season_kd, recent_kd, delta_pct}],
        strong_map, weak_map,
    }
    """
    import queries

    trend = queries.team_trend(days)
    win_loss = queries.win_loss_summary()
    maps = queries.map_team_stats(mode, min_matches=3)

    # 폼 경고 — 시즌 평균 vs 최근 5매치 K/D
    players = queries.all_players_overview(mode)
    form_alerts = []
    for p in players:
        pid = queries.get_player_id(p["name"])
        if not pid:
            continue
        recent = queries.player_kd_trend(pid, mode, 5)
        if len(recent) < 3:
            continue
        recent_vals = [r["kd"] for r in recent if r["kd"] is not None]
        if len(recent_vals) < 3:
            continue
        recent_kd = round(sum(recent_vals) / len(recent_vals), 2)
        season_kd = p["avg_kd"]
        if season_kd and season_kd > 0:
            delta_pct = round((recent_kd - season_kd) / season_kd * 100, 1)
            # 하락(-10% 이하)만 경고
            if delta_pct <= -10:
                form_alerts.append({
                    "name": p["name"], "season_kd": season_kd,
                    "recent_kd": recent_kd, "delta_pct": delta_pct,
                    "season_zcs": p.get("zcs"),
                })
    # 하락폭 큰 순
    form_alerts.sort(key=lambda x: x["delta_pct"])

    # 강한/약한 맵 (avg_kd 기준)
    strong_map = maps[0] if maps else None
    weak_map = maps[-1] if maps else None

    # ZCS 데이터 (HP 전용)
    team_zcs = None
    zcs_trend = []
    if mode == "HP":
        team_zcs = queries.overview_stats().get("team_zcs")
        if team_zcs is not None:
            team_zcs = float(team_zcs)
        zcs_trend = queries.recent_zcs_trend(10)
        # Postgres Decimal → float (JSON 직렬화/차트용)
        for r in zcs_trend:
            if r.get("avg_zcs") is not None:
                r["avg_zcs"] = float(r["avg_zcs"])

    return {
        "trend": trend, "win_loss": win_loss,
        "mode": mode, "days": days,
        "form_alerts": form_alerts,
        "strong_map": strong_map, "weak_map": weak_map,
        "team_zcs": team_zcs, "zcs_trend": zcs_trend,
    }
