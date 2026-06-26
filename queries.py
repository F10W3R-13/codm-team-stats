# DB 집계 쿼리 계층
#
# 디스코드 명령어(/stats, /compare, /lastmatch)와 향후 웹이 공통으로 쓰는
# 데이터 조회 함수들. SQL을 한 곳에 모아둔다.

import db
import metrics


def _stddev(values: list, ndigits: int = 2):
    """표본표준편차(기복 지표). 값이 작을수록 폼이 일정. 1개 이하면 None."""
    if not values or len(values) < 2:
        return None
    n = len(values)
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)  # 표본분산(n-1)
    import math
    return round(math.sqrt(var), ndigits)


def player_exists(name: str) -> bool:
    """해당 선수가 DB에 존재하는지."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM players WHERE name = ? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        return row is not None


def get_player_id(name: str):
    """선수 이름 → id. 없으면 None."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM players WHERE name = ? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        return row["id"] if row else None


def list_players() -> list:
    """등록된 전체 선수 이름 목록."""
    with db.get_conn() as conn:
        rows = conn.execute("SELECT name FROM players ORDER BY name").fetchall()
        return [r["name"] for r in rows]


def player_overall_stats(player_id: int) -> dict:
    """선수의 HP/SND 종합 평균 스탯.

    반환: {
        "name": str,
        "hp": {matches, avg_k, avg_d, avg_kd, avg_obj, avg_score, avg_impact,
               avg_dmg, avg_capture} or None,
        "snd": {matches, avg_k, avg_d, avg_a, avg_kd, avg_score, avg_impact,
                avg_adr, avg_fk, avg_lww} or None,
    }
    """
    result = {"name": None, "hp": None, "snd": None}
    with db.get_conn() as conn:
        # 이름
        r = conn.execute("SELECT name FROM players WHERE id=?", (player_id,)).fetchone()
        if not r:
            return result
        result["name"] = r["name"]

        # HP 평균 + 표준편차(기복)
        r = conn.execute(
            """SELECT COUNT(*) matches,
                      ROUND(AVG(kills),1) avg_k,
                      ROUND(AVG(deaths),1) avg_d,
                      ROUND(AVG(kd_ratio),2) avg_kd,
                      ROUND(AVG(obj_time),0) avg_obj,
                      ROUND(AVG(score),0) avg_score,
                      ROUND(AVG(impact),0) avg_impact,
                      ROUND(AVG(total_damage),0) avg_dmg,
                      ROUND(AVG(capture_kill),1) avg_capture
               FROM player_stats_hp WHERE player_id=?""",
            (player_id,),
        ).fetchone()
        if r and r["matches"]:
            result["hp"] = dict(r)
            # 기복(표준편차) 별도 계산 — 값이 작을수록 일정한 폼
            rows = conn.execute(
                "SELECT kd_ratio, kills, total_damage FROM player_stats_hp WHERE player_id=?",
                (player_id,),
            ).fetchall()
            result["hp"]["std_kd"] = _stddev([x["kd_ratio"] for x in rows if x["kd_ratio"] is not None], 2)
            result["hp"]["std_kills"] = _stddev([x["kills"] for x in rows if x["kills"] is not None], 1)
            result["hp"]["std_dmg"] = _stddev([x["total_damage"] for x in rows if x["total_damage"] is not None], 0)

        # SND 평균 + 표준편차(기복)
        r = conn.execute(
            """SELECT COUNT(*) matches,
                      ROUND(AVG(kills),1) avg_k,
                      ROUND(AVG(deaths),1) avg_d,
                      ROUND(AVG(assists),1) avg_a,
                      ROUND(AVG(kd_ratio),2) avg_kd,
                      ROUND(AVG(score),0) avg_score,
                      ROUND(AVG(impact),0) avg_impact,
                      ROUND(AVG(adr),0) avg_adr,
                      ROUND(AVG(first_kill),2) avg_fk,
                      ROUND(AVG(lone_wolf_win),2) avg_lww
               FROM player_stats_snd WHERE player_id=?""",
            (player_id,),
        ).fetchone()
        if r and r["matches"]:
            result["snd"] = dict(r)
            rows = conn.execute(
                "SELECT kd_ratio, kills FROM player_stats_snd WHERE player_id=?",
                (player_id,),
            ).fetchall()
            result["snd"]["std_kd"] = _stddev([x["kd_ratio"] for x in rows if x["kd_ratio"] is not None], 2)
            result["snd"]["std_kills"] = _stddev([x["kills"] for x in rows if x["kills"] is not None], 1)

    # HP 커스텀 지표(DPD/DPK/ID/AP%/ZCS) 계산 추가
    if result["hp"]:
        h = result["hp"]
        m = metrics.all_hp_metrics(
            h["avg_k"], h["avg_d"], h["avg_obj"],
            h["avg_score"], h["avg_impact"],
            h["avg_dmg"], h["avg_capture"],
        )
        # 'id' 키 충돌 주의: impact_delta로 저장
        h["dpd"] = m["dpd"]
        h["dpk"] = m["dpk"]
        h["impact_delta"] = m["id"]
        h["ap_pct"] = m["ap_pct"]
        h["zcs"] = m["zcs"]

    return result


def team_averages(mode: str = "HP") -> dict:
    """팀 전체(모든 선수) 평균. 개인 대비 벤치마크용.

    반환: {avg_k, avg_d, avg_kd, ...} — all_players_overview의 평균.
    """
    players = all_players_overview(mode)
    if not players:
        return {}
    keys = [k for k in players[0].keys()
            if k not in ("name",) and isinstance(players[0].get(k), (int, float))]
    avg = {}
    for k in keys:
        vals = [p[k] for p in players if p.get(k) is not None]
        avg[k] = round(sum(vals) / len(vals), 2) if vals else None
    return avg


def leaderboard(mode: str = "HP", metric: str = "avg_kd", limit: int = 10) -> list:
    """모드별 순위표. metric: avg_kd/avg_k/avg_dmg/avg_score/avg_obj/avg_adr.

    반환: [{name, matches, <metric 값>}, ...]
    """
    valid_hp = {"avg_kd", "avg_k", "avg_dmg", "avg_score", "avg_obj"}
    valid_snd = {"avg_kd", "avg_k", "avg_dmg", "avg_score", "avg_adr"}

    if mode == "HP":
        if metric not in valid_hp:
            metric = "avg_kd"
        expr = {
            "avg_kd": "AVG(kd_ratio)",
            "avg_k": "AVG(kills)",
            "avg_dmg": "AVG(total_damage)",
            "avg_score": "AVG(score)",
            "avg_obj": "AVG(obj_time)",
        }[metric]
        sql = f"""SELECT p.name,
                         COUNT(*) matches,
                         ROUND({expr},2) value
                  FROM player_stats_hp s JOIN players p ON p.id=s.player_id
                  GROUP BY p.id ORDER BY value DESC LIMIT ?"""
    else:
        if metric not in valid_snd:
            metric = "avg_kd"
        expr = {
            "avg_kd": "AVG(kd_ratio)",
            "avg_k": "AVG(kills)",
            "avg_dmg": "AVG(score)",  # SND는 total_damage 없음 → score로 대체
            "avg_score": "AVG(score)",
            "avg_adr": "AVG(adr)",
        }[metric]
        sql = f"""SELECT p.name,
                         COUNT(*) matches,
                         ROUND({expr},2) value
                  FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                  GROUP BY p.id ORDER BY value DESC LIMIT ?"""

    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]


def last_match_summary(mode: str = None) -> dict:
    """가장 최근 매치 요약.

    mode: None(전체 최근), "HP", "SND"
    반환: {match_id, mode, map_name, match_date, players: [{name, ...스탯}]}
          또는 None
    """
    where = ""
    params = ()
    if mode:
        where = "WHERE mode=?"
        params = (mode,)

    with db.get_conn() as conn:
        m = conn.execute(
            f"""SELECT id, mode, map_name, match_date
                FROM matches {where}
                ORDER BY id DESC LIMIT 1""",
            params,
        ).fetchone()
        if not m:
            return None

        result = {
            "match_id": m["id"],
            "mode": m["mode"],
            "map_name": m["map_name"],
            "match_date": m["match_date"],
            "players": [],
        }

        if m["mode"] == "HP":
            rows = conn.execute(
                """SELECT p.name, s.kills, s.deaths, s.kd_ratio, s.obj_time,
                          s.score, s.impact, s.total_damage, s.capture_kill
                   FROM player_stats_hp s JOIN players p ON p.id=s.player_id
                   WHERE s.match_id=? ORDER BY s.kills DESC""",
                (m["id"],),
            ).fetchall()
            for r in rows:
                result["players"].append({
                    "name": r["name"], "k": r["kills"], "d": r["deaths"],
                    "kd": r["kd_ratio"], "obj": r["obj_time"], "score": r["score"],
                    "impact": r["impact"], "dmg": r["total_damage"],
                    "cap": r["capture_kill"],
                })
        else:
            rows = conn.execute(
                """SELECT p.name, s.kills, s.deaths, s.assists, s.kd_ratio,
                          s.score, s.impact, s.adr, s.first_kill, s.lone_wolf_win
                   FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                   WHERE s.match_id=? ORDER BY s.kills DESC""",
                (m["id"],),
            ).fetchall()
            for r in rows:
                result["players"].append({
                    "name": r["name"], "k": r["kills"], "d": r["deaths"],
                    "a": r["assists"], "kd": r["kd_ratio"], "score": r["score"],
                    "impact": r["impact"], "adr": r["adr"], "fk": r["first_kill"],
                    "lww": r["lone_wolf_win"],
                })

    return result


def match_by_date(date_str: str, mode: str = None) -> list:
    """특정 날짜의 매치들 요약 (같은 날 여러 매치 가능).

    반환: last_match_summary 와 같은 구조의 리스트
    """
    where = "WHERE match_date=?"
    params = (date_str,)
    if mode:
        where += " AND mode=?"
        params = (date_str, mode)

    summaries = []
    with db.get_conn() as conn:
        matches = conn.execute(
            f"""SELECT id, mode, map_name, match_date
                FROM matches {where} ORDER BY id""",
            params,
        ).fetchall()
        for m in matches:
            summary = {
                "match_id": m["id"], "mode": m["mode"],
                "map_name": m["map_name"], "match_date": m["match_date"],
                "players": [],
            }
            if m["mode"] == "HP":
                rows = conn.execute(
                    """SELECT p.name, s.kills, s.deaths, s.kd_ratio, s.score
                       FROM player_stats_hp s JOIN players p ON p.id=s.player_id
                       WHERE s.match_id=? ORDER BY s.kills DESC""",
                    (m["id"],),
                ).fetchall()
                for r in rows:
                    summary["players"].append({
                        "name": r["name"], "k": r["kills"], "d": r["deaths"],
                        "kd": r["kd_ratio"], "score": r["score"],
                    })
            else:
                rows = conn.execute(
                    """SELECT p.name, s.kills, s.deaths, s.assists, s.kd_ratio, s.score
                       FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                       WHERE s.match_id=? ORDER BY s.kills DESC""",
                    (m["id"],),
                ).fetchall()
                for r in rows:
                    summary["players"].append({
                        "name": r["name"], "k": r["kills"], "d": r["deaths"],
                        "a": r["assists"], "kd": r["kd_ratio"], "score": r["score"],
                    })
            summaries.append(summary)
    return summaries


# ── 웹 대시보드용 쿼리 ────────────────────────────────────────────────────

def overview_stats() -> dict:
    """개요 대시보드용 요약 통계."""
    with db.get_conn() as conn:
        total_matches = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
        hp_matches = conn.execute(
            "SELECT COUNT(*) c FROM matches WHERE mode='HP'"
        ).fetchone()["c"]
        snd_matches = conn.execute(
            "SELECT COUNT(*) c FROM matches WHERE mode='SND'"
        ).fetchone()["c"]
        total_players = conn.execute("SELECT COUNT(*) c FROM players").fetchone()["c"]

        # 날짜 범위
        dr = conn.execute(
            "SELECT MIN(match_date) lo, MAX(match_date) hi FROM matches WHERE match_date IS NOT NULL"
        ).fetchone()

        # 맵 분포 (대소문자 정규화)
        maps = conn.execute(
            """SELECT map_name, COUNT(*) n FROM matches
               WHERE map_name IS NOT NULL AND map_name != ''
               GROUP BY LOWER(map_name) ORDER BY n DESC LIMIT 10"""
        ).fetchall()

        # 최근 5매치
        recent = conn.execute(
            """SELECT id, mode, map_name, match_date,
                      (SELECT COUNT(*) FROM player_stats_hp WHERE match_id=m.id) +
                      (SELECT COUNT(*) FROM player_stats_snd WHERE match_id=m.id) as players
               FROM matches m ORDER BY id DESC LIMIT 5"""
        ).fetchall()

        return {
            "total_matches": total_matches,
            "hp_matches": hp_matches,
            "snd_matches": snd_matches,
            "total_players": total_players,
            "date_range": {"start": dr["lo"], "end": dr["hi"]},
            "maps": [{"name": r["map_name"], "count": r["n"]} for r in maps],
            "recent_matches": [
                {
                    "id": r["id"], "mode": r["mode"],
                    "map_name": r["map_name"], "match_date": r["match_date"],
                    "players": r["players"],
                }
                for r in recent
            ],
        }


def player_kd_trend(player_id: int, mode: str = "HP", limit: int = 30) -> list:
    """선수의 매치별 K/D 시계열 (최신 limit개, 시간순). 차트용."""
    table = "player_stats_hp" if mode == "HP" else "player_stats_snd"
    with db.get_conn() as conn:
        rows = conn.execute(
            f"""SELECT m.match_date, s.kd_ratio, s.kills, s.deaths
                FROM {table} s JOIN matches m ON m.id=s.match_id
                WHERE s.player_id=? ORDER BY m.id DESC LIMIT ?""",
            (player_id, limit),
        ).fetchall()
        # 시간순(과거→최신)으로 뒤집기
        return [
            {
                "date": r["match_date"], "kd": r["kd_ratio"],
                "k": r["kills"], "d": r["deaths"],
            }
            for r in reversed(rows)
        ]


def all_players_overview(mode: str = "HP") -> list:
    """모든 선수의 모드별 평균 스탯 (선수 페이지용). HP는 커스텀 지표 포함."""
    if mode == "HP":
        sql = """SELECT p.name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.deaths),1) avg_d,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.score),0) avg_score,
                        ROUND(AVG(s.total_damage),0) avg_dmg,
                        ROUND(AVG(s.obj_time),0) avg_obj,
                        ROUND(AVG(s.impact),0) avg_impact,
                        ROUND(AVG(s.capture_kill),1) avg_ck
                 FROM player_stats_hp s JOIN players p ON p.id=s.player_id
                 GROUP BY p.id ORDER BY avg_kd DESC"""
    else:
        sql = """SELECT p.name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.deaths),1) avg_d,
                        ROUND(AVG(s.assists),1) avg_a,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.score),0) avg_score,
                        ROUND(AVG(s.adr),0) avg_adr,
                        ROUND(AVG(s.impact),0) avg_impact
                 FROM player_stats_snd s JOIN players p ON p.id=s.player_id
                 GROUP BY p.id ORDER BY avg_kd DESC"""
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]

    # HP는 커스텀 지표(DPD/DPK/ID/AP%/ZCS)를 평균 스탯 기반으로 계산해 추가
    if mode == "HP":
        for p in rows:
            m = metrics.all_hp_metrics(
                p["avg_k"], p["avg_d"], p["avg_obj"],
                p["avg_score"], p["avg_impact"],
                p["avg_dmg"], p["avg_ck"],
            )
            p.update(m)
    return rows


def advanced_leaderboard(metric: str = "dpd", limit: int = 20) -> list:
    """HP 커스텀 지표 기준 리더보드. metric: dpd/dpk/id/ap_pct/zcs.

    반환: [{name, matches, value}, ...] (내림차순)
    """
    players = all_players_overview("HP")
    if metric not in {"dpd", "dpk", "id", "ap_pct", "zcs"}:
        metric = "dpd"
    # 값이 있는 선수만, 해당 지표 기준 정렬
    ranked = [
        {"name": p["name"], "matches": p["matches"], "value": p.get(metric)}
        for p in players
        if p.get(metric) is not None
    ]
    # DPK는 낮을수록 좋음(적은 딜로 킬) → 오름차순. 나머지는 높을수록 좋음 → 내림차순.
    reverse = (metric != "dpk")
    ranked.sort(key=lambda x: x["value"], reverse=reverse)
    return ranked[:limit]


def player_metric_timeseries(player_id: int, mode: str = "HP", limit: int = 50) -> list:
    """선수의 매치별 모든 지표(기본+커스텀) 시계열. 최신 limit개, 시간순(과거→최신).

    반환: [{date, kills, deaths, kd, obj, score, impact, dmg, cap,
            dpd, dpk, id, ap_pct, zcs}, ...]  (HP)
          [{date, kills, deaths, assists, kd, score, impact, adr,
            fk, lww}, ...]  (SND)
    """
    if mode == "HP":
        sql = """SELECT m.match_date date, s.kills, s.deaths, s.kd_ratio kd,
                        s.obj_time obj, s.score, s.impact, s.total_damage dmg,
                        s.capture_kill cap
                 FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                 WHERE s.player_id=? ORDER BY m.id DESC LIMIT ?"""
    else:
        sql = """SELECT m.match_date date, s.kills, s.deaths, s.assists,
                        s.kd_ratio kd, s.score, s.impact, s.adr,
                        s.first_kill fk, s.lone_wolf_win lww
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE s.player_id=? ORDER BY m.id DESC LIMIT ?"""

    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, (player_id, limit)).fetchall()]

    # 시간순(과거→최신)으로 뒤집기 + HP는 커스텀 지표 계산 추가
    rows.reverse()
    if mode == "HP":
        for r in rows:
            m = metrics.all_hp_metrics(
                r.get("kills"), r.get("deaths"), r.get("obj"),
                r.get("score"), r.get("impact"), r.get("dmg"), r.get("cap"),
            )
            # id 키 충돌 주의: dict의 'id' 대신 'impact_delta' 사용
            r["dpd"] = m["dpd"]
            r["dpk"] = m["dpk"]
            r["impact_delta"] = m["id"]  # 'id'는 예약 느낌이라 별명 사용
            r["ap_pct"] = m["ap_pct"]
            r["zcs"] = m["zcs"]
    return rows


def match_history(limit: int = 50, offset: int = 0, mode: str = None) -> dict:
    """매치 히스토리 (페이지네이션).

    반환: {matches: [...], total: int, limit, offset}
    """
    where = ""
    params = []
    if mode:
        where = "WHERE mode=?"
        params.append(mode)
    params.extend([limit, offset])

    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) c FROM matches {where}", params[:1] if mode else []
        ).fetchone()["c"]

        rows = conn.execute(
            f"""SELECT m.id, m.mode, m.map_name, m.match_date,
                       (SELECT COUNT(*) FROM player_stats_hp WHERE match_id=m.id) +
                       (SELECT COUNT(*) FROM player_stats_snd WHERE match_id=m.id) as players,
                       (SELECT ROUND(AVG(kd_ratio),2) FROM player_stats_hp WHERE match_id=m.id) avg_kd_hp,
                       (SELECT ROUND(AVG(kd_ratio),2) FROM player_stats_snd WHERE match_id=m.id) avg_kd_snd
                FROM matches m {where}
                ORDER BY m.id DESC LIMIT ? OFFSET ?""",
            params,
        ).fetchall()

        return {
            "matches": [
                {
                    "id": r["id"], "mode": r["mode"], "map_name": r["map_name"],
                    "match_date": r["match_date"], "players": r["players"],
                    "avg_kd": r["avg_kd_hp"] if r["mode"] == "HP" else r["avg_kd_snd"],
                }
                for r in rows
            ],
            "total": total, "limit": limit, "offset": offset,
        }


# ── 관리(Admin)용 조회/수정/삭제 ───────────────────────────────────────────

def match_raw_stats(match_id: int) -> dict:
    """매치 메타 + 선수 원시 스탯(편집용). 모든 필드를 그대로 반환.

    반환: {match: {...}, players: [{stat_id, player_name, ...모든스탯필드}]} 또는 None
    """
    with db.get_conn() as conn:
        m = conn.execute(
            "SELECT id, mode, map_name, match_date, result, team_score, opponent_score "
            "FROM matches WHERE id=?",
            (match_id,),
        ).fetchone()
        if not m:
            return None

        match = dict(m)
        mode = match["mode"]
        table = "player_stats_hp" if mode == "HP" else "player_stats_snd"

        if mode == "HP":
            rows = conn.execute(
                f"""SELECT s.id stat_id, p.name player_name, s.kills, s.deaths,
                           s.kd_ratio, s.obj_time, s.score, s.impact,
                           s.total_damage, s.capture_kill
                    FROM {table} s JOIN players p ON p.id=s.player_id
                    WHERE s.match_id=? ORDER BY s.kills DESC""",
                (match_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT s.id stat_id, p.name player_name, s.kills, s.deaths,
                           s.assists, s.kd_ratio, s.score, s.impact,
                           s.adr, s.first_kill, s.lone_wolf_win
                    FROM {table} s JOIN players p ON p.id=s.player_id
                    WHERE s.match_id=? ORDER BY s.kills DESC""",
                (match_id,),
            ).fetchall()

        match["players"] = [dict(r) for r in rows]
        return match


def update_match_meta(match_id: int, **fields) -> bool:
    """매치 메타(result, team_score, opponent_score, map_name, match_date, mode) 수정.

    허용 필드만 업데이트. 반환: 성공 여부.
    """
    allowed = {"result", "team_score", "opponent_score", "map_name", "match_date", "mode"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [match_id]
    with db.get_conn() as conn:
        cur = conn.execute(
            f"UPDATE matches SET {set_clause} WHERE id=?", params
        )
        return cur.rowcount > 0


def update_player_stat(stat_id: int, mode: str, **fields) -> bool:
    """선수 스탯 행의 특정 필드 수정.

    mode: "HP" 또는 "SND". 허용 필드만 업데이트.
    """
    if mode == "HP":
        allowed = {"kills", "deaths", "kd_ratio", "obj_time", "score",
                   "impact", "total_damage", "capture_kill"}
        table = "player_stats_hp"
    else:
        allowed = {"kills", "deaths", "assists", "kd_ratio", "score",
                   "impact", "adr", "first_kill", "lone_wolf_win"}
        table = "player_stats_snd"

    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [stat_id]
    with db.get_conn() as conn:
        cur = conn.execute(f"UPDATE {table} SET {set_clause} WHERE id=?", params)
        return cur.rowcount > 0


def delete_match(match_id: int) -> bool:
    """매치와 그 매치의 모든 스탯 행을 삭제. 반환: 성공 여부."""
    with db.get_conn() as conn:
        conn.execute("DELETE FROM player_stats_hp WHERE match_id=?", (match_id,))
        conn.execute("DELETE FROM player_stats_snd WHERE match_id=?", (match_id,))
        cur = conn.execute("DELETE FROM matches WHERE id=?", (match_id,))
        return cur.rowcount > 0


def admin_match_list(limit: int = 50, offset: int = 0, mode: str = None,
                     has_result: bool = None) -> dict:
    """관리용 매치 목록. result/score 포함, 필터링 지원.

    has_result: True면 result가 있는 매치만, False면 없는(NULL) 매치만, None이면 전체.
    반환: {matches: [...], total, limit, offset}
    """
    where_clauses = []
    params = []
    if mode:
        where_clauses.append("mode=?")
        params.append(mode)
    if has_result is True:
        where_clauses.append("result IS NOT NULL")
    elif has_result is False:
        where_clauses.append("result IS NULL")
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.extend([limit, offset])

    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) c FROM matches {where}",
            params[:len(params) - 2],
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT id, mode, map_name, match_date, result, team_score, opponent_score,
                       (SELECT COUNT(*) FROM player_stats_hp WHERE match_id=m.id) +
                       (SELECT COUNT(*) FROM player_stats_snd WHERE match_id=m.id) as players
                FROM matches m {where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            params,
        ).fetchall()
        return {
            "matches": [
                {
                    "id": r["id"], "mode": r["mode"], "map_name": r["map_name"],
                    "match_date": r["match_date"], "result": r["result"],
                    "team_score": r["team_score"], "opponent_score": r["opponent_score"],
                    "players": r["players"],
                }
                for r in rows
            ],
            "total": total, "limit": limit, "offset": offset,
        }


# ── 팀 인사이트용 통계 ────────────────────────────────────────────────────

def team_trend(days: int = 30) -> dict:
    """팀 전체 추세 — 최근 N일 vs 시즌 전체 평균 (HP 기준).

    반환: {
        recent: {matches, avg_kd, avg_k, avg_dmg},
        season: {matches, avg_kd, avg_k, avg_dmg},
        delta_pct: {kd, k, dmg},
    }
    """
    with db.get_conn() as conn:
        # 최근 N일 팀 평균
        r = conn.execute(
            f"""SELECT COUNT(*) matches,
                       ROUND(AVG(s.kd_ratio),2) avg_kd,
                       ROUND(AVG(s.kills),1) avg_k,
                       ROUND(AVG(s.total_damage),0) avg_dmg
                FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                WHERE m.match_date >= date('now', '-{int(days)} days')"""
        ).fetchone()
        recent = dict(r) if r else {}

        # 시즌 전체 팀 평균
        s = conn.execute(
            """SELECT COUNT(*) matches,
                      ROUND(AVG(s.kd_ratio),2) avg_kd,
                      ROUND(AVG(s.kills),1) avg_k,
                      ROUND(AVG(s.total_damage),0) avg_dmg
               FROM player_stats_hp s JOIN matches m ON m.id=s.match_id"""
        ).fetchone()
        season = dict(s) if s else {}

    delta = {}
    for k in ("avg_kd", "avg_k", "avg_dmg"):
        rv = recent.get(k)
        sv = season.get(k)
        if rv is not None and sv and sv != 0:
            delta[k] = round((rv - sv) / sv * 100, 1)
        else:
            delta[k] = None

    return {"recent": recent, "season": season, "delta_pct": delta, "period_days": days}


def map_team_stats(mode: str = "HP", min_matches: int = 2) -> list:
    """맵별 팀 성적 (평균 K/D, 킬, 딜, 매치 수).

    min_matches 미만 맵은 노이즈라 제외.
    반환: [{map_name, matches, avg_kd, avg_k, avg_dmg}, ...] avg_kd 내림차순
    """
    if mode == "HP":
        sql = """SELECT m.map_name map_name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.total_damage),0) avg_dmg
                 FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='HP'
                 GROUP BY LOWER(m.map_name)
                 HAVING matches >= ?
                 ORDER BY avg_kd DESC"""
    else:
        sql = """SELECT m.map_name map_name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='SND'
                 GROUP BY LOWER(m.map_name)
                 HAVING matches >= ?
                 ORDER BY avg_kd DESC"""
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, (min_matches,)).fetchall()]
    # 맵 이름 Title Case 정규화
    for r in rows:
        r["map_name"] = r["map_name"].strip().title()
    return rows


def map_player_stats(map_name: str, mode: str = "HP", min_matches: int = 2) -> list:
    """특정 맵에서의 선수별 성적.

    반환: [{player_name, matches, avg_kd, avg_k, avg_dmg}, ...] avg_kd 내림차순
    """
    if mode == "HP":
        sql = """SELECT p.name player_name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.total_damage),0) avg_dmg
                 FROM player_stats_hp s
                 JOIN matches m ON m.id=s.match_id
                 JOIN players p ON p.id=s.player_id
                 WHERE LOWER(m.map_name)=LOWER(?) AND m.mode='HP'
                 GROUP BY p.id
                 HAVING matches >= ?
                 ORDER BY avg_kd DESC"""
    else:
        sql = """SELECT p.name player_name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr
                 FROM player_stats_snd s
                 JOIN matches m ON m.id=s.match_id
                 JOIN players p ON p.id=s.player_id
                 WHERE LOWER(m.map_name)=LOWER(?) AND m.mode='SND'
                 GROUP BY p.id
                 HAVING matches >= ?
                 ORDER BY avg_kd DESC"""
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (map_name, min_matches)).fetchall()]
