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


def map_detail(map_name: str, mode: str = "HP", days: int = 30) -> dict:
    """단일 맵의 종합 상세 데이터 조립 (맵 상세 페이지용).

    반환: {
        map_name, mode,
        players: [map_player_stats 결과],   # ZCS 포함 (HP)
        win_loss: map_win_loss 결과,
        trend: map_trend 결과 (최근 vs 시즌),
        team_avg: {avg_kd, avg_k, avg_dmg, avg_obj, avg_capture, avg_zcs},  # 선수별 ±% 벤치마크
    }
    데이터가 없으면 None.
    """
    import queries
    players = queries.map_player_stats(map_name, mode, min_matches=1)
    if not players:
        return None

    win_loss = queries.map_win_loss(map_name, mode)
    trend = queries.map_trend(map_name, mode, days)

    # 팀 전체 평균 — 선수별 vs ±% 계산용
    team_players = queries.all_players_overview(mode)
    team_avg = {}
    if team_players:
        # HP: zcs/avg_k/avg_dmg/avg_obj/avg_ck, SND: avg_k/avg_adr
        src_keys = {
            "avg_k": "avg_k", "avg_dmg": "avg_dmg", "avg_kd": "avg_kd",
        }
        if mode == "HP":
            src_keys.update({"avg_obj": "avg_obj", "avg_capture": "avg_ck", "avg_zcs": "zcs"})
        for dst_k, src_k in src_keys.items():
            vals = [p.get(src_k) for p in team_players if p.get(src_k) is not None]
            team_avg[dst_k] = round(sum(vals) / len(vals), 2) if vals else None

    return {
        "map_name": map_name, "mode": mode,
        "players": players,
        "win_loss": win_loss,
        "trend": trend,
        "team_avg": team_avg,
        "days": days,
    }


# ── 코칭 허브 데이터 조립 ──────────────────────────────────────────────────

def banpick_board(recent_matches=None) -> dict:
    """밴픽 우선순위 리스트 — 픽 1순위 → 밴 1순위 정렬.

    수축(shrinkage) 블렌딩으로 표본 부족 왜곡 방지:
        blended = (n × recent + k × season) / (n + k),  k = 3
    팀 시즌 평균 대비 %로 정규화해 맵 간 비교.
    HP는 ZCS 제1 + K/D 타이브레이크, SND는 K/D만.
    상위 2 = PICK, 하위 2 = BAN, 중간 = neutral.

    recent_matches: None이면 시즌 전체 모드.
    반환: {"HP": {ranked, no_data}, "SND": {...}}
    """
    import queries

    SHRINK_K = 3  # 시즌 가중치 (낮을수록 최근 민감, 높을수록 안정)

    def _shrink(recent_val, season_val, n):
        if recent_val is None or season_val is None or n is None:
            return season_val if season_val is not None else recent_val
        return (n * recent_val + SHRINK_K * season_val) / (n + SHRINK_K)

    def _mode_board(mode, recent_n):
        season_maps = queries.map_team_stats(mode, min_matches=2)
        if not season_maps:
            return {"ranked": [], "no_data": []}

        # 팀 시즌 평균 (정규화 기준)
        team_season_zcs = None
        team_season_kd = None
        if mode == "HP":
            zcs_vals = [m["avg_zcs"] for m in season_maps if m.get("avg_zcs") is not None]
            team_season_zcs = sum(zcs_vals) / len(zcs_vals) if zcs_vals else None
        kd_vals = [m["avg_kd"] for m in season_maps if m.get("avg_kd") is not None]
        team_season_kd = sum(kd_vals) / len(kd_vals) if kd_vals else None

        season_by_name = {m["map_name"]: m for m in season_maps}

        # 기간 데이터 (시즌 모드면 None → 시즌값 그대로)
        if recent_n is None:
            recent_by_name = {}  # 시즌 모드: 블렌딩 불필요
        else:
            recent_maps = queries.map_team_stats_recent(mode, recent_n, min_matches=1)
            recent_by_name = {m["map_name"]: m for m in recent_maps}

        ranked = []
        for sm in season_maps:
            name = sm["map_name"]
            sv_kd = sm.get("avg_kd")
            sv_zcs = sm.get("avg_zcs") if mode == "HP" else None
            rm = recent_by_name.get(name)
            rv_kd = rm.get("avg_kd") if rm else None
            rv_zcs = rm.get("avg_zcs") if (rm and mode == "HP") else None
            n_matches = rm.get("matches") if rm else 0
            low_sample = (recent_n is not None and n_matches < 3)

            # 블렌딩
            blended_kd = _shrink(rv_kd, sv_kd, n_matches) if recent_n is not None else sv_kd
            blended_zcs = _shrink(rv_zcs, sv_zcs, n_matches) if (recent_n is not None and mode == "HP") else sv_zcs

            # 정규화 (팀 시즌 평균 대비 %)
            score = None
            score_kd = None
            if mode == "HP" and blended_zcs is not None and team_season_zcs and team_season_zcs != 0:
                score = round((blended_zcs / team_season_zcs - 1) * 100, 1)
            if blended_kd is not None and team_season_kd and team_season_kd != 0:
                score_kd = round((blended_kd / team_season_kd - 1) * 100, 1)
            if score is None:  # SND 또는 ZCS 없음 → K/D로
                score = score_kd if score_kd is not None else 0

            # 델타 (블렌딩값 − 시즌값, 화살표용)
            delta_pct = None
            if recent_n is not None and mode == "HP" and sv_zcs and sv_zcs != 0:
                delta_pct = round((blended_zcs / sv_zcs - 1) * 100, 1) if blended_zcs else None
            elif recent_n is not None and sv_kd and sv_kd != 0:
                delta_pct = round((blended_kd / sv_kd - 1) * 100, 1) if blended_kd else None

            ranked.append({
                "map_name": name,
                "score": score,
                "score_kd": score_kd,  # 타이브레이크용
                "delta_pct": delta_pct,
                "recent_kd": rv_kd if recent_n is not None else sv_kd,
                "recent_zcs": rv_zcs if (recent_n is not None and mode == "HP") else sv_zcs,
                "recent_matches": n_matches if recent_n is not None else sm.get("matches", 0),
                "season_kd": sv_kd,
                "season_zcs": sv_zcs,
                "low_sample": low_sample,
            })

        # 정렬: score 내림차순, 동점 시 score_kd 내림차순
        ranked.sort(key=lambda x: (x["score"] if x["score"] is not None else -999,
                                   x["score_kd"] if x["score_kd"] is not None else -999), reverse=True)

        # 배지 부여 (상위 2 PICK, 하위 2 BAN)
        total = len(ranked)
        for i, m in enumerate(ranked):
            if i < 2:
                m["badge"] = "pick"
            elif i >= total - 2:
                m["badge"] = "ban"
            else:
                m["badge"] = "neutral"

        return {"ranked": ranked, "no_data": []}

    return {
        "HP": _mode_board("HP", recent_matches),
        "SND": _mode_board("SND", recent_matches),
    }


def coaching_hub(mode: str = "HP", recent_matches: int = 10) -> dict:
    """코칭 허브(/ 홈)용 종합 데이터 — 액션/진단 중심.

    "다음 매치 전에 뭘 해야 하나"를 한눈에:
    - 기간 토글 전역 단일 (최근 5/10매치/시즌)
    - ZCS·K/D 요약 한 줄 + ZCS 추이 spark
    - 폼 경고: 시즌 평균 대비 최근 K/D 하락 선수 (시즌 모드엔 비활성)
    - 밴픽보드: 맵별 기간 vs 시즌 델타 + 픽/밴 추천
    - 역할 스펙트럼: slay↔obj 축 위 선수 위치

    recent_matches: None이면 "시즌 전체" 모드.
    반환: {
        mode, recent_matches,
        summary: {period_zcs, zcs_delta, period_kd, kd_delta, season_zcs, season_kd},
        zcs_trend: [...],
        form_alerts: [...],
        map_board: [{map_name, recent, season, delta_pct, rec}],
        roles: [{name, role, slay_score, obj_score, ...}],
        win_loss,
    }
    """
    import queries

    season_mode = (recent_matches is None)
    n = recent_matches if not season_mode else 10
    win_loss = queries.win_loss_summary()

    # 트렌드(매치 수 기반) — 요약 + ZCS 추이에 사용
    trend = queries.team_trend_by_matches(n)
    summary = {
        "period_zcs": trend["recent"].get("avg_zcs"),
        "season_zcs": trend["season"].get("avg_zcs"),
        "zcs_delta": trend["delta_pct"].get("avg_zcs"),
        "period_kd": trend["recent"].get("avg_kd"),
        "season_kd": trend["season"].get("avg_kd"),
        "kd_delta": trend["delta_pct"].get("avg_kd"),
        "period_matches": trend["recent"].get("matches"),
    }

    # ZCS 추이 spark (시즌 모드면 큰 수로 전체)
    zcs_trend = queries.recent_zcs_trend(n if not season_mode else 100)
    for r in zcs_trend:
        if r.get("avg_zcs") is not None:
            r["avg_zcs"] = float(r["avg_zcs"])

    # 폼 경고 — 시즌 평균 vs 최근 N매치 K/D (시즌 모드엔 무의미 → 비활성)
    form_alerts = []
    if not season_mode and n >= 3:
        players = queries.all_players_overview(mode)
        for p in players:
            pid = queries.get_player_id(p["name"])
            if not pid:
                continue
            recent = queries.player_kd_trend(pid, mode, n)
            if len(recent) < 3:
                continue
            recent_vals = [r["kd"] for r in recent if r["kd"] is not None]
            if len(recent_vals) < 3:
                continue
            recent_kd = round(sum(recent_vals) / len(recent_vals), 2)
            season_kd = p["avg_kd"]
            if season_kd and season_kd > 0:
                delta_pct = round((recent_kd - season_kd) / season_kd * 100, 1)
                if delta_pct <= -10:
                    form_alerts.append({
                        "name": p["name"], "season_kd": season_kd,
                        "recent_kd": recent_kd, "delta_pct": delta_pct,
                        "season_zcs": p.get("zcs"),
                    })
        form_alerts.sort(key=lambda x: x["delta_pct"])

    # 밴픽 우선순위 리스트 (수축 블렌딩 + 정규화 + PICK/BAN 배지)
    banpick = banpick_board(recent_matches)

    # 역할 스펙트럼 (HP 전용, 시즌 누적 기준)
    roles = queries.team_role_distribution() if mode == "HP" else []

    return {
        "mode": mode, "recent_matches": recent_matches,
        "season_mode": season_mode,
        "summary": summary, "zcs_trend": zcs_trend,
        "form_alerts": form_alerts,
        "banpick": banpick, "roles": roles,
        "win_loss": win_loss,
    }
