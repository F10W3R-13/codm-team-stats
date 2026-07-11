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
            # Postgres Decimal → float (metrics 계산/JSON 직렬화 위해)
            for k, v in list(result["hp"].items()):
                if hasattr(v, "as_tuple"):
                    result["hp"][k] = float(v)
            # 기복(표준편차) 별도 계산 — 값이 작을수록 일정한 폼
            rows = conn.execute(
                "SELECT kd_ratio, kills, total_damage FROM player_stats_hp WHERE player_id=?",
                (player_id,),
            ).fetchall()
            result["hp"]["std_kd"] = _stddev([x["kd_ratio"] for x in rows if x["kd_ratio"] is not None], 2)
            result["hp"]["std_kills"] = _stddev([x["kills"] for x in rows if x["kills"] is not None], 1)
            result["hp"]["std_dmg"] = _stddev([x["total_damage"] for x in rows if x["total_damage"] is not None], 0)
            # HP 커스텀 지표(DPD/DPK/ID/AP%/ZCS)는 아래(130줄)에서 한 번만 계산.

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
            for k, v in list(result["snd"].items()):
                if hasattr(v, "as_tuple"):
                    result["snd"][k] = float(v)
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
        h["impact_delta"] = m["impact_delta"]
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
            if k not in ("name", "id") and isinstance(players[0].get(k), (int, float))]
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
    valid_snd = {"avg_kd", "avg_k", "avg_score", "avg_adr"}

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
        sql = """SELECT p.id, p.name,
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
        sql = """SELECT p.id, p.name,
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

    # Postgres는 ROUND(numeric)이 Decimal 반환 → metrics 계산을 위해 float 변환
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, "as_tuple"):  # Decimal
                r[k] = float(v)

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
    """HP 커스텀 지표 기준 리더보드. metric: dpd/dpk/impact_delta/ap_pct/zcs.

    반환: [{name, matches, value}, ...] (내림차순)
    """
    players = all_players_overview("HP")
    if metric not in {"dpd", "dpk", "impact_delta", "ap_pct", "zcs"}:
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
            dpd, dpk, impact_delta, ap_pct, zcs}, ...]  (HP)
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
            r["impact_delta"] = m["impact_delta"]
            r["ap_pct"] = m["ap_pct"]
            r["zcs"] = m["zcs"]
    return rows


def match_history(limit: int = 50, offset: int = 0, mode: str = None) -> dict:
    """매치 히스토리 (평면 페이지네이션, 레거시 호환용).

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
            f"""SELECT m.id, m.mode, m.map_name, m.match_date, m.result,
                       m.team_score, m.opponent_score,
                       (SELECT COUNT(*) FROM player_stats_hp WHERE match_id=m.id) +
                       (SELECT COUNT(*) FROM player_stats_snd WHERE match_id=m.id) as players,
                       (SELECT ROUND(AVG(kd_ratio),2) FROM player_stats_hp WHERE match_id=m.id) avg_kd_hp,
                       (SELECT ROUND(AVG(kd_ratio),2) FROM player_stats_snd WHERE match_id=m.id) avg_kd_snd,
                       (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                        FROM player_stats_hp WHERE match_id=m.id) avg_zcs
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
                    "avg_zcs": r["avg_zcs"],
                    "result": r["result"], "team_score": r["team_score"],
                    "opponent_score": r["opponent_score"],
                }
                for r in rows
            ],
            "total": total, "limit": limit, "offset": offset,
        }


def match_history_grouped(mode: str = None, date_page: int = 1,
                          dates_per_page: int = 7) -> dict:
    """매치 히스토리를 날짜 단위로 그룹화 (한 페이지 = 최근 N일).

    - match_date NULL은 "날짜 미상" 그룹으로 묶어 항상 마지막에 표시.
    - 같은 날짜의 매치들을 하나의 그룹으로 묶음.
    - 반환: {groups: [{date, matches:[...]}], total_date_pages, date_page}
    """
    where = ""
    params = []
    if mode:
        where = "WHERE mode=?"
        params.append(mode)

    with db.get_conn() as conn:
        # 1) 고유 날짜 목록 (NULL 포함). NULL은 가장 나중.
        #    Postgres 제약: SELECT DISTINCT의 ORDER BY엔 SELECT 리스트 표현식만 가능.
        #    → NULL 여부를 별도 컬럼으로 SELECT해 ORDER BY에서 참조.
        date_rows = conn.execute(
            f"""SELECT match_date, (match_date IS NULL) is_null FROM matches {where}
                GROUP BY match_date
                ORDER BY is_null, match_date DESC""",
            params,
        ).fetchall()
        all_dates = [r["match_date"] for r in date_rows]

        total_date_pages = max(1, (len(all_dates) + dates_per_page - 1) // dates_per_page)
        date_page = max(1, min(date_page, total_date_pages))
        start = (date_page - 1) * dates_per_page
        page_dates = all_dates[start:start + dates_per_page]

        if not page_dates:
            return {"groups": [], "total_date_pages": total_date_pages, "date_page": date_page}

        # 2) 이 페이지 날짜들에 속한 매치 전체 (NULL은 IS NULL)
        placeholders = ",".join(["?"] * len([d for d in page_dates if d is not None]))
        has_null = any(d is None for d in page_dates)
        # mode 필터: 첫 번째(날짜 목록) 쿼리에서 이미 필터링됐지만, 같은 날짜에 다른 모드
        # 매치가 섞여 있으면 여기서 걸러지지 않으므로 두 번째 SELECT에도 mode 조건 적용.
        mode_cond = " AND m.mode=?" if mode else ""

        sql = f"""SELECT m.id, m.mode, m.map_name, m.match_date, m.result,
                         m.team_score, m.opponent_score,
                         (SELECT COUNT(*) FROM player_stats_hp WHERE match_id=m.id) +
                         (SELECT COUNT(*) FROM player_stats_snd WHERE match_id=m.id) as players,
                         (SELECT ROUND(AVG(kd_ratio),2) FROM player_stats_hp WHERE match_id=m.id) avg_kd_hp,
                         (SELECT ROUND(AVG(kd_ratio),2) FROM player_stats_snd WHERE match_id=m.id) avg_kd_snd,
                         (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                          FROM player_stats_hp WHERE match_id=m.id) avg_zcs,
                         (m.match_date IS NULL) is_null
                  FROM matches m
                  WHERE ({('m.match_date IN (%s)' % placeholders) if placeholders else 'FALSE'}
                  {(' OR ' if placeholders and has_null else '') + ('m.match_date IS NULL' if has_null else '')})
                  {mode_cond}
                  ORDER BY is_null, m.match_date DESC, m.id DESC"""
        qp = [d for d in page_dates if d is not None] + ([mode] if mode else [])
        rows = conn.execute(db._adapt_sql(sql), qp).fetchall()

        # 날짜 단위 복기 데이터(match_day_notes) 일괄 조회 (커넥션 열려있을 때)
        non_null_dates = [d for d in page_dates if d is not None]
        day_notes_map = {}
        if non_null_dates:
            dn_ph = ",".join(["?"] * len(non_null_dates))
            dn_rows = conn.execute(
                f"SELECT match_date, coach_note, vod_url, transcript_summary "
                f"FROM match_day_notes WHERE match_date IN ({dn_ph})",
                non_null_dates,
            ).fetchall()
            day_notes_map = {r["match_date"]: dict(r) for r in dn_rows}

    # 3) 날짜별 그룹핑 (page_dates 순서 = 내림차순, NULL은 끝)
    matches = [
        {
            "id": r["id"], "mode": r["mode"], "map_name": r["map_name"],
            "match_date": r["match_date"], "players": r["players"],
            "avg_kd": r["avg_kd_hp"] if r["mode"] == "HP" else r["avg_kd_snd"],
            "avg_zcs": r["avg_zcs"],
            "result": r["result"], "team_score": r["team_score"],
            "opponent_score": r["opponent_score"],
        }
        for r in rows
    ]
    groups = []
    for d in page_dates:
        # None 그룹은 match_date IS NULL인 행만, 그 외는 날짜 일치
        if d is None:
            grp_matches = [m for m in matches if m["match_date"] is None]
        else:
            grp_matches = [m for m in matches if m["match_date"] == d]
        if grp_matches:
            dn = day_notes_map.get(d, {}) if d is not None else {}
            groups.append({
                "date": d, "matches": grp_matches,
                "coach_note": dn.get("coach_note"),
                "vod_url": dn.get("vod_url"),
                "transcript_summary": dn.get("transcript_summary"),
            })

    return {"groups": groups, "total_date_pages": total_date_pages, "date_page": date_page}


# ── 관리(Admin)용 조회/수정/삭제 ───────────────────────────────────────────

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
        # SQLite: date('now','-N days'). Postgres: CURRENT_DATE - INTERVAL (TEXT 비교를 위해 ::text 캐스팅)
        if db.USE_POSTGRES:
            date_cond = f"m.match_date >= (CURRENT_DATE - INTERVAL '{int(days)} days')::text"
        else:
            date_cond = f"m.match_date >= date('now', '-{int(days)} days')"
        r = conn.execute(
            f"""SELECT COUNT(*) matches,
                       ROUND(AVG(s.kd_ratio),2) avg_kd,
                       ROUND(AVG(s.kills),1) avg_k,
                       ROUND(AVG(s.total_damage),0) avg_dmg
                FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                WHERE {date_cond}"""
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
        sql = """SELECT LOWER(m.map_name) map_name,
                        COUNT(*) n_matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.total_damage),0) avg_dmg,
                        ROUND(AVG(MAX(0, 1.1*s.obj_time + 8*s.capture_kill + 4.1*s.kills - 5*s.deaths)),1) avg_zcs
                 FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='HP'
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
    else:
        sql = """SELECT LOWER(m.map_name) map_name,
                        COUNT(*) n_matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='SND'
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, (min_matches,)).fetchall()]
    # 맵 이름 Title Case 정규화 (n_matches → matches 별칭)
    for r in rows:
        r["matches"] = r.pop("n_matches")
        r["map_name"] = r["map_name"].strip().title()
    return rows


def map_team_stats_recent(mode: str = "HP", recent_matches: int = 10,
                          min_matches: int = 2) -> list:
    """맵별 팀 성적 — 최근 N매치 기준 (코칭 허브 밴픽보드용).

    전체 매치 풀에서 최근 N매치(match id DESC)만 추려 그 안에서 맵별 집계.
    시즌 전체용은 map_team_stats() 사용.
    반환: map_team_stats()와 동일 키 [{map_name, matches, avg_kd, avg_k, avg_dmg, avg_zcs}]
    """
    if recent_matches is None:
        return map_team_stats(mode, min_matches)
    # mode 화이트리스트 강제 — recent_ids 서브쿼리에 문자열 보간되므로 인젝션 방어.
    if mode not in ("HP", "SND"):
        raise ValueError(f"map_team_stats_recent: invalid mode={mode!r}")
    if recent_matches <= 0:
        recent_matches = 10
    # 최근 N매치 id 서브쿼리 (mode 고정) — SQLite/Postgres 공통
    recent_ids = f"SELECT id FROM matches WHERE mode='{mode}' ORDER BY id DESC LIMIT {int(recent_matches)}"
    if mode == "HP":
        sql = f"""SELECT LOWER(m.map_name) map_name,
                        COUNT(*) n_matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.total_damage),0) avg_dmg,
                        ROUND(AVG(MAX(0, 1.1*s.obj_time + 8*s.capture_kill + 4.1*s.kills - 5*s.deaths)),1) avg_zcs
                 FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='HP'
                   AND m.id IN ({recent_ids})
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
    else:
        sql = f"""SELECT LOWER(m.map_name) map_name,
                        COUNT(*) n_matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.adr),0) avg_adr
                 FROM player_stats_snd s JOIN matches m ON m.id=s.match_id
                 WHERE m.map_name IS NOT NULL AND m.map_name != '' AND m.mode='SND'
                   AND m.id IN ({recent_ids})
                 GROUP BY LOWER(m.map_name)
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(db._adapt_sql(sql), (min_matches,)).fetchall()]
    for r in rows:
        r["matches"] = r.pop("n_matches")
        r["map_name"] = r["map_name"].strip().title()
    return rows


def team_trend_by_matches(recent_matches: int = 10) -> dict:
    """팀 전체 추세 — 최근 N매치 vs 시즌 전체 (HP 기준, 매치 수 기반).

    coaching_hub용. 기존 team_trend(days)와 달리 날짜가 아닌 매치 수 기준.
    반환: {
        recent: {matches, avg_kd, avg_k, avg_dmg, avg_zcs},
        season: {matches, avg_kd, avg_k, avg_dmg, avg_zcs},
        delta_pct: {avg_kd, avg_k, avg_dmg, avg_zcs},
    }
    """
    if recent_matches is None:
        recent_matches = 10
    if recent_matches <= 0:
        recent_matches = 10
    recent_ids = f"SELECT id FROM matches WHERE mode='HP' ORDER BY id DESC LIMIT {int(recent_matches)}"
    zcs_expr = "MAX(0, 1.1*s.obj_time + 8*s.capture_kill + 4.1*s.kills - 5*s.deaths)"
    with db.get_conn() as conn:
        r = conn.execute(db._adapt_sql(f"""SELECT COUNT(*) matches,
                       ROUND(AVG(s.kd_ratio),2) avg_kd,
                       ROUND(AVG(s.kills),1) avg_k,
                       ROUND(AVG(s.total_damage),0) avg_dmg,
                       ROUND(AVG({zcs_expr}),1) avg_zcs
                FROM player_stats_hp s JOIN matches m ON m.id=s.match_id
                WHERE m.id IN ({recent_ids})""")).fetchone()
        recent = dict(r) if r else {}
        s = conn.execute(db._adapt_sql(f"""SELECT COUNT(*) matches,
                      ROUND(AVG(s.kd_ratio),2) avg_kd,
                      ROUND(AVG(s.kills),1) avg_k,
                      ROUND(AVG(s.total_damage),0) avg_dmg,
                      ROUND(AVG({zcs_expr}),1) avg_zcs
               FROM player_stats_hp s JOIN matches m ON m.id=s.match_id""")).fetchone()
        season = dict(s) if s else {}
    delta = {}
    for k in ("avg_kd", "avg_k", "avg_dmg", "avg_zcs"):
        rv = recent.get(k)
        sv = season.get(k)
        if rv is not None and sv and sv != 0:
            delta[k] = round((rv - sv) / sv * 100, 1)
        else:
            delta[k] = None
    return {"recent": recent, "season": season, "delta_pct": delta,
            "recent_matches": recent_matches}


def map_player_stats(map_name: str, mode: str = "HP", min_matches: int = 2) -> list:
    """특정 맵에서의 선수별 성적.

    반환: [{player_name, matches, avg_kd, avg_k, avg_dmg}, ...] avg_kd 내림차순
    """
    if mode == "HP":
        sql = """SELECT p.name player_name,
                        COUNT(*) matches,
                        ROUND(AVG(s.kd_ratio),2) avg_kd,
                        ROUND(AVG(s.kills),1) avg_k,
                        ROUND(AVG(s.total_damage),0) avg_dmg,
                        ROUND(AVG(s.obj_time),0) avg_obj,
                        ROUND(AVG(s.capture_kill),1) avg_capture,
                        ROUND(AVG(MAX(0, 1.1*s.obj_time + 8*s.capture_kill + 4.1*s.kills - 5*s.deaths)),1) avg_zcs
                 FROM player_stats_hp s
                 JOIN matches m ON m.id=s.match_id
                 JOIN players p ON p.id=s.player_id
                 WHERE LOWER(m.map_name)=LOWER(?) AND m.mode='HP'
                 GROUP BY p.id, p.name
                 HAVING COUNT(*) >= ?
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
                 GROUP BY p.id, p.name
                 HAVING COUNT(*) >= ?
                 ORDER BY avg_kd DESC"""
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, (map_name, min_matches)).fetchall()]
    # Postgres Decimal → float
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, "as_tuple"):
                r[k] = float(v)
    return rows


def player_map_breakdown(player_id: int, min_matches: int = 5) -> list:
    """특정 선수의 맵별 성적 — 본인 전체 평균 ZCS 대비 ±%.

    ZCS(Zone Control Score) = max(0, 1.1·OBJ + 8·캡처킬 + 4.1·K − 5·D) — HP 제1 지표.
    반환: [{map_name, matches, zcs, zcs_pct}, ...]
      zcs: 그 맵에서의 평균 ZCS
      zcs_pct: 본인 평균 대비 % (양수=강함, 음수=약함)
    HP 전용 (SND엔 ZCS 없음). min_matches 미만 맵은 신뢰도 낮아 제외.
    히트맵 색은 템플릿에서 zcs_pct 크기에 비례해 계산 — 절대 임계값/라벨 없음.
    """
    sql = """SELECT LOWER(m.map_name) map_name,
                    COUNT(*) matches,
                    ROUND(AVG(MAX(0, 1.1*s.obj_time + 8*s.capture_kill + 4.1*s.kills - 5*s.deaths)),1) zcs
             FROM player_stats_hp s
             JOIN matches m ON m.id=s.match_id
             WHERE s.player_id=? AND m.map_name IS NOT NULL AND m.map_name != ''
               AND m.mode='HP'
             GROUP BY LOWER(m.map_name)
             HAVING COUNT(*) >= ?
             ORDER BY zcs DESC"""
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(db._adapt_sql(sql), (player_id, min_matches)).fetchall()]
    # Postgres Decimal → float
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, "as_tuple"):
                r[k] = float(v)
    if not rows:
        return []
    # 본인 전체 평균 ZCS
    overall = _player_overall_zcs(player_id)
    if not overall:
        return []
    out = []
    for r in rows:
        pct = round((r["zcs"] - overall) / overall * 100, 1) if overall else 0
        out.append({
            "map_name": r["map_name"].strip().title(),
            "matches": r["matches"], "zcs": r["zcs"],
            "zcs_pct": pct,
        })
    # ±% 내림차순 (강한 맵이 위로)
    out.sort(key=lambda x: x["zcs_pct"], reverse=True)
    return out


def _player_overall_zcs(player_id: int) -> float:
    """선수의 전체 평균 ZCS (player_map_breakdown 내부용)."""
    sql = "SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1) zcs FROM player_stats_hp WHERE player_id=?"
    with db.get_conn() as conn:
        r = conn.execute(db._adapt_sql(sql), (player_id,)).fetchone()
    if r and r["zcs"] is not None:
        v = r["zcs"]
        return float(v) if hasattr(v, "as_tuple") else v
    return None


def map_win_loss(map_name: str, mode: str = "HP") -> dict:
    """특정 맵의 승패 요약.

    반환: {total, wins, losses, draw, none, win_rate}
    """
    with db.get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) c FROM matches WHERE LOWER(map_name)=LOWER(?) AND mode=?",
            (map_name, mode),
        ).fetchone()["c"]
        wins = conn.execute(
            "SELECT COUNT(*) c FROM matches WHERE LOWER(map_name)=LOWER(?) AND mode=? AND result='WIN'",
            (map_name, mode),
        ).fetchone()["c"]
        losses = conn.execute(
            "SELECT COUNT(*) c FROM matches WHERE LOWER(map_name)=LOWER(?) AND mode=? AND result='LOSS'",
            (map_name, mode),
        ).fetchone()["c"]
        draw = conn.execute(
            "SELECT COUNT(*) c FROM matches WHERE LOWER(map_name)=LOWER(?) AND mode=? AND result='DRAW'",
            (map_name, mode),
        ).fetchone()["c"]
    none_r = total - wins - losses - draw
    decided = wins + losses
    win_rate = round(wins / decided * 100, 1) if decided else None
    return {"total": total, "wins": wins, "losses": losses,
            "draw": draw, "none": none_r, "win_rate": win_rate}


def map_trend(map_name: str, mode: str = "HP", days: int = 30) -> dict:
    """특정 맵의 최근 N일 vs 시즌 전체 평균 (모든 HP 지표 포함).

    HP: K/D, ZCS, 킬, 데스, 딜, OBJ, 캡처, Impact, DPD, DPK, ID, AP% 전부.
    SND: K/D, 킬, 데스, 어시스트, ADR, Impact.
    반환: {
        recent: {matches, ...}, season: {...},
        delta_pct: {지표: ±%},
        metrics_meta: {지표: {higher_better, label_key}},  # 템플릿 표시용
    }
    """
    import metrics as _metrics

    if db.USE_POSTGRES:
        date_cond = f"m.match_date >= (CURRENT_DATE - INTERVAL '{int(days)} days')::text"
    else:
        date_cond = f"m.match_date >= date('now', '-{int(days)} days')"

    def _q(extra_where):
        wh = "WHERE LOWER(m.map_name)=LOWER(?) AND m.mode=?"
        if extra_where:
            wh += f" AND {extra_where}"
        if mode == "HP":
            return ("SELECT COUNT(*) matches, "
                    "ROUND(AVG(s.kd_ratio),2) avg_kd, ROUND(AVG(s.kills),1) avg_k, "
                    "ROUND(AVG(s.deaths),1) avg_d, ROUND(AVG(s.total_damage),0) avg_dmg, "
                    "ROUND(AVG(s.obj_time),0) avg_obj, ROUND(AVG(s.score),0) avg_score, "
                    "ROUND(AVG(s.impact),0) avg_impact, ROUND(AVG(s.capture_kill),1) avg_capture "
                    f"FROM player_stats_hp s JOIN matches m ON m.id=s.match_id {wh}")
        else:
            return ("SELECT COUNT(*) matches, "
                    "ROUND(AVG(s.kd_ratio),2) avg_kd, ROUND(AVG(s.kills),1) avg_k, "
                    "ROUND(AVG(s.deaths),1) avg_d, ROUND(AVG(s.assists),1) avg_a, "
                    "ROUND(AVG(s.adr),0) avg_adr, ROUND(AVG(s.score),0) avg_score, "
                    "ROUND(AVG(s.impact),0) avg_impact "
                    f"FROM player_stats_snd s JOIN matches m ON m.id=s.match_id {wh}")

    def _d(r):
        if not r:
            return {}
        out = dict(r)
        for k, v in list(out.items()):
            if hasattr(v, "as_tuple"):
                out[k] = float(v)
        return out

    with db.get_conn() as conn:
        recent = _d(conn.execute(_q(date_cond), (map_name, mode)).fetchone())
        season = _d(conn.execute(_q(None), (map_name, mode)).fetchone())

    # HP: 커스텀 지표(ZCS/DPD/DPK/ID/AP%)를 평균 raw 값으로부터 계산해 추가
    if mode == "HP":
        for block in (recent, season):
            if block.get("matches"):
                m = _metrics.all_hp_metrics(
                    block.get("avg_k"), block.get("avg_d"), block.get("avg_obj"),
                    block.get("avg_score"), block.get("avg_impact"),
                    block.get("avg_dmg"), block.get("avg_capture"),
                )
                block["zcs"] = m["zcs"]
                block["dpd"] = m["dpd"]
                block["dpk"] = m["dpk"]
                block["impact_delta"] = m["impact_delta"]
                block["ap_pct"] = m["ap_pct"]

    # 비교할 지표 + 메타 (높을수록 좋은가, 라벨 키)
    if mode == "HP":
        metric_defs = [
            ("avg_kd", True, "kd"),
            ("zcs", True, "zcs_label"),
            ("avg_k", True, "avg_k"),
            ("avg_d", False, "avg_d"),
            ("avg_dmg", True, "avg_total_dmg"),
            ("avg_obj", True, "avg_obj"),
            ("avg_capture", True, "avg_cap_kill"),
            ("avg_impact", True, "avg_impact"),
            ("dpd", True, "m_dpd"),
            ("dpk", False, "m_dpk"),
            ("impact_delta", True, "m_id"),
            ("ap_pct", True, "m_ap_pct"),
        ]
    else:
        metric_defs = [
            ("avg_kd", True, "kd"),
            ("avg_k", True, "avg_k"),
            ("avg_d", False, "avg_d"),
            ("avg_a", True, "avg_a"),
            ("avg_adr", True, "avg_adr"),
            ("avg_score", True, "avg_score"),
            ("avg_impact", True, "avg_impact"),
        ]

    delta = {}
    metrics_meta = {}
    for key, higher, label_key in metric_defs:
        rv, sv = recent.get(key), season.get(key)
        if rv is not None and sv and sv != 0:
            delta[key] = round((rv - sv) / sv * 100, 1)
        else:
            delta[key] = None
        metrics_meta[key] = {"higher_better": higher, "label_key": label_key}

    return {
        "recent": recent, "season": season,
        "delta_pct": delta, "metrics_meta": metrics_meta,
        "period_days": days,
    }


# ── 승패(W/L) 통계 ──────────────────────────────────────────────────────────

def win_loss_summary(mode: str = None) -> dict:
    """팀 승패 요약.

    mode: None(전체), "HP", "SND".
    반환: {
        total, wins, losses, draw, none, win_rate,
        by_mode: {"HP": {...}, "SND": {...}}  (mode=None 일 때만)
    }
    result 값: 'WIN' / 'LOSS' / 'DRAW' / NULL(미입력).
    win_rate = wins / (wins+losses) * 100 (무승부 제외).
    """
    where = "WHERE mode=?" if mode else ""
    params = (mode,) if mode else ()

    def _count(conn, w, p):
        return conn.execute(
            f"SELECT COUNT(*) c FROM matches {w}", p
        ).fetchone()["c"]

    with db.get_conn() as conn:
        total = _count(conn, where, params)
        w = _count(conn, (where + " AND result='WIN'") if where else "WHERE result='WIN'",
                   params if where else ())
        l = _count(conn, (where + " AND result='LOSS'") if where else "WHERE result='LOSS'",
                   params if where else ())
        d = _count(conn, (where + " AND result='DRAW'") if where else "WHERE result='DRAW'",
                   params if where else ())
        n = total - w - l - d
        decided = w + l
        win_rate = round(w / decided * 100, 1) if decided else None

        out = {"total": total, "wins": w, "losses": l, "draw": d,
               "none": n, "win_rate": win_rate}

        if not mode:
            # mode=None: 단일 GROUP BY 쿼리로 HP/SND 각각 집계 (재귀 호출 제거)
            by_mode = {}
            rows = conn.execute(
                "SELECT mode, result, COUNT(*) c FROM matches "
                "WHERE mode IN ('HP','SND') GROUP BY mode, result"
            ).fetchall()
            mode_counts = {}
            for r in rows:
                m = r["mode"]
                mode_counts.setdefault(m, {"total": 0, "wins": 0, "losses": 0, "draw": 0})
                mode_counts[m]["total"] += r["c"]
                if r["result"] == "WIN":
                    mode_counts[m]["wins"] += r["c"]
                elif r["result"] == "LOSS":
                    mode_counts[m]["losses"] += r["c"]
                elif r["result"] == "DRAW":
                    mode_counts[m]["draw"] += r["c"]
            for m, c in mode_counts.items():
                c["none"] = c["total"] - c["wins"] - c["losses"] - c["draw"]
                dec = c["wins"] + c["losses"]
                c["win_rate"] = round(c["wins"] / dec * 100, 1) if dec else None
                by_mode[m] = c
            out["by_mode"] = by_mode
        return out


def recent_results(limit: int = 10, mode: str = None) -> list:
    """최근 N매치 승패 흐름 (시간순: 과거→최신). 차트용.

    반환: [{id, mode, result, score_text}, ...]
    result: 'WIN' / 'LOSS' / 'DRAW' / None.
    score_text: "3-2" 형태 (스코어 없으면 None).
    """
    where = "WHERE mode=?" if mode else ""
    params = (mode,) if mode else ()
    with db.get_conn() as conn:
        rows = conn.execute(
            f"""SELECT id, mode, match_date, result, team_score, opponent_score
                FROM matches {where}
                ORDER BY id DESC LIMIT ?""",
            params + (limit,),
        ).fetchall()
    out = []
    for r in reversed(rows):  # DESC로 받아서 reverse → 과거→최신
        ts = None
        if r["team_score"] is not None and r["opponent_score"] is not None:
            ts = f"{r['team_score']}-{r['opponent_score']}"
        out.append({
            "id": r["id"], "mode": r["mode"], "match_date": r["match_date"],
            "result": r["result"], "score_text": ts,
        })
    return out


def recent_zcs_trend(limit: int = 10) -> list:
    """최근 N HP 매치의 팀 평균 ZCS 시계열 (과거→최신). 허브/대시보드 차트용.

    반환: [{id, match_date, avg_zcs}, ...]
    """
    with db.get_conn() as conn:
        rows = conn.execute(
            f"""SELECT m.id, m.match_date,
                       (SELECT ROUND(AVG(MAX(0, 1.1*obj_time + 8*capture_kill + 4.1*kills - 5*deaths)),1)
                        FROM player_stats_hp WHERE match_id=m.id) avg_zcs
                FROM matches m WHERE m.mode='HP'
                ORDER BY m.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [
        {"id": r["id"], "match_date": r["match_date"], "avg_zcs": r["avg_zcs"]}
        for r in reversed(rows)
    ]


# ── 선수 비교 ────────────────────────────────────────────────────────────────

# 비교에 쓸 지표 정의. (키, 라벨키, 높을수록 좋은가)
# HP 지표 — ZCS를 최우선으로 배치
_COMPARE_HP = [
    ("zcs", "zcs_label", True),
    ("avg_kd", "kd", True),
    ("avg_k", "avg_k", True),
    ("avg_d", "avg_d", False),
    ("avg_dmg", "avg_total_dmg", True),
    ("avg_obj", "avg_obj", True),
    ("avg_score", "avg_score", True),
    ("avg_impact", "avg_impact", True),
    ("dpd", "m_dpd", True),
    ("ap_pct", "m_ap_pct", True),
]
_COMPARE_SND = [
    ("avg_kd", "kd", True),
    ("avg_k", "avg_k", True),
    ("avg_d", "avg_d", False),
    ("avg_a", "avg_a", True),
    ("avg_adr", "avg_adr", True),
    ("avg_score", "avg_score", True),
    ("avg_impact", "avg_impact", True),
]


def compare_players(name_a: str, name_b: str, mode: str = "HP") -> dict:
    """두 선수의 모드별 평균 스탯 비교.

    반환: {
        a: {name, pid, stats}, b: {...},
        mode,
        rows: [{key, label, higher_better, a, b, winner: 'a'|'b'|'tie'|None}],
        chart: [{metric, a, b}],  # 레이더 차트용 (정규화된 값)
    }
    """
    pid_a = get_player_id(name_a)
    pid_b = get_player_id(name_b)
    if not pid_a or not pid_b:
        return None

    stats_a = player_overall_stats(pid_a)
    stats_b = player_overall_stats(pid_b)

    block_a = stats_a.get("hp" if mode == "HP" else "snd") or {}
    block_b = stats_b.get("hp" if mode == "HP" else "snd") or {}

    defs = _COMPARE_HP if mode == "HP" else _COMPARE_SND
    rows = []
    chart = []
    for key, label_key, higher in defs:
        va = block_a.get(key)
        vb = block_b.get(key)
        # Postgres Decimal → float
        if hasattr(va, "as_tuple"): va = float(va)
        if hasattr(vb, "as_tuple"): vb = float(vb)
        winner = None
        if va is not None and vb is not None:
            if va == vb:
                winner = "tie"
            elif (va > vb) == higher:
                winner = "a"
            else:
                winner = "b"
        rows.append({"key": key, "label_key": label_key,
                     "higher_better": higher, "a": va, "b": vb, "winner": winner})
        # 차트용 (원시 값 — JS에서 정규화)
        chart.append({"metric": label_key, "a": va, "b": vb})

    return {
        "a": {"name": stats_a["name"], "pid": pid_a},
        "b": {"name": stats_b["name"], "pid": pid_b},
        "mode": mode,
        "rows": rows,
        "chart": chart,
        "matches_a": block_a.get("matches", 0),
        "matches_b": block_b.get("matches", 0),
    }


# ── 팀 역할(Role) 분포 ──────────────────────────────────────────────────────

def team_role_distribution() -> list:
    """HP 기준 팀 전체 선수의 역할 분포.

    반환: [{name, role, slay_score, obj_score, avg_k, avg_obj, avg_dmg, avg_capture}, ...]
    role: "slayer" | "objective" | "balanced"
    slay_score / obj_score: classify_role 내부 비율 로직을 표시 계층에서 재현한 연속값.
      (팀평균 대비 개인평균 비율의 평균 — metrics.py 공식과 동일, 출처 고정 원칙 준수)
      (slay_score - obj_score)/(slay_score + obj_score) → -1(순obj)~+1(순slay).
    """
    import metrics
    players = all_players_overview("HP")
    team_avg = {}
    if players:
        for k_src, k_dst in (("avg_k", "avg_k"), ("avg_obj", "avg_obj"),
                             ("avg_dmg", "avg_dmg"), ("avg_ck", "avg_capture")):
            vals = [p.get(k_src) for p in players if p.get(k_src) is not None]
            team_avg[k_dst] = round(sum(vals) / len(vals), 2) if vals else 0

    def _ratio(indiv, team):
        if not indiv or not team:
            return 1.0
        return indiv / team

    out = []
    for p in players:
        # all_players_overview는 캡처킬을 avg_ck로 리턴 → classify_role에 맞게 복사
        p_norm = dict(p)
        if "avg_ck" in p_norm and "avg_capture" not in p_norm:
            p_norm["avg_capture"] = p_norm["avg_ck"]
        role = metrics.classify_role(p_norm, team_avg)
        # classify_role 내부 점수 로직 동일 재현 (metrics.py 미수정)
        slay = round((_ratio(p_norm.get("avg_k"), team_avg.get("avg_k")) +
                      _ratio(p_norm.get("avg_dmg"), team_avg.get("avg_dmg"))) / 2, 3)
        obj = round((_ratio(p_norm.get("avg_obj"), team_avg.get("avg_obj")) +
                     _ratio(p_norm.get("avg_capture"), team_avg.get("avg_capture"))) / 2, 3)
        out.append({
            "name": p["name"], "role": role,
            "slay_score": slay, "obj_score": obj,
            "spectrum_pos": metrics.role_spectrum_pos(slay, obj),
            "avg_k": p.get("avg_k"), "avg_obj": p.get("avg_obj"),
            "avg_dmg": p.get("avg_dmg"), "avg_capture": p_norm.get("avg_capture"),
        })
    return out


# ── 코칭 노트 (액션 아이템) ──────────────────────────────────────────────────

def _elapsed_matches(conn, match_id, created_at):
    """노트 이후 경과한 HP 매치 수. match_id 있으면 id 비교, 없으면 created_at 기준."""
    if match_id:
        r = conn.execute(
            "SELECT COUNT(*) AS n FROM matches WHERE id > ? AND mode='HP'", (match_id,)
        ).fetchone()
    else:
        # created_at 이후 매치 — created_at은 'YYYY-MM-DD HH:MM:SS' (datetime),
        # match_date는 'YYYY-MM-DD'라 날짜 추출 비교.
        created_day = (created_at or "")[:10]
        if created_day:
            r = conn.execute(
                "SELECT COUNT(*) AS n FROM matches "
                "WHERE match_date >= ? AND mode='HP'", (created_day,)
            ).fetchone()
        else:
            r = {"n": 0}
    return dict(r)["n"] if r else 0


def open_notes(limit: int = 20) -> list:
    """open 노트 — 오래된 순. 허브용.

    반환: [{id, content, match_id, player_id, player_name, created_at, elapsed_matches}]
    elapsed_matches = 노트 이후 경과한 HP 매치 수 (방치 압박 지표).
    """
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(db._adapt_sql(
            "SELECT n.id, n.content, n.match_id, n.player_id, n.created_at, "
            "       p.name AS player_name "
            "FROM coaching_notes n "
            "LEFT JOIN players p ON p.id = n.player_id "
            "WHERE n.status='open' "
            "ORDER BY n.created_at ASC, n.id ASC "
            "LIMIT ?"
        ), (limit,)).fetchall()]
        for r in rows:
            r["elapsed_matches"] = _elapsed_matches(
                conn, r.get("match_id"), r.get("created_at")
            )
    return rows


def notes_for_match(match_id: int) -> list:
    """특정 매치 관련 노트(open+done) 이력. 매치 상세용. 최신 순.

    반환: [{id, content, status, player_id, player_name, created_at, resolved_at}]
    """
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(db._adapt_sql(
            "SELECT n.id, n.content, n.status, n.player_id, n.created_at, n.resolved_at, "
            "       p.name AS player_name "
            "FROM coaching_notes n "
            "LEFT JOIN players p ON p.id = n.player_id "
            "WHERE n.match_id=? "
            "ORDER BY n.created_at DESC, n.id DESC"
        ), (match_id,)).fetchall()]
    return rows
