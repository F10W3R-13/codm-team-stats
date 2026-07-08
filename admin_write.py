# 관리자 전용 DB 쓰기·admin 조회 (Admin Write / Admin Read)
#
# queries.py에서 분리 — 봇·웹이 공통으로 읽는 조회(queries)와
# 관리자만 DB를 변경하는 쓰기·편성(admin_write)을 구분.
# 이 모듈의 함수는 web_api.py의 /admin/* 라우트에서만 호출된다.
# 봇(bot.py, commands_cog.py)·analytics·prompt_context는 import 금지.
#
# 분리 이유: "봇·웹이 동시에 DB를 만질 때 위험한 함수"가 한곳에 모여
# 코드 리뷰·감사가 쉽도록.

import db


# ── 선수 관리 ──────────────────────────────────────────────────────────────

def list_players_with_ids() -> list:
    """선수 [{id, name}] 목록 — 매치 편집 선수 재매핑 드롭다운용."""
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, name FROM players ORDER BY name").fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]


def list_players_admin() -> list:
    """선수 관리 페이지용 — id, 이름, HP/SND 매치 수 포함."""
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT p.id, p.name,
                      (SELECT COUNT(*) FROM player_stats_hp WHERE player_id=p.id) hp_matches,
                      (SELECT COUNT(*) FROM player_stats_snd WHERE player_id=p.id) snd_matches
               FROM players p ORDER BY p.name"""
        ).fetchall()
        return [{"id": r["id"], "name": r["name"],
                 "hp_matches": r["hp_matches"], "snd_matches": r["snd_matches"]} for r in rows]


def delete_player(player_id: int) -> bool:
    """선수 삭제 — 캐스케이드가 없어 자식 테이블(player_stats_hp/snd, aliases)을
    먼저 삭제한 뒤 players 행 삭제. 되돌릴 수 없음.
    """
    with db.get_conn() as conn:
        conn.execute("DELETE FROM player_stats_hp WHERE player_id=?", (player_id,))
        conn.execute("DELETE FROM player_stats_snd WHERE player_id=?", (player_id,))
        conn.execute("DELETE FROM aliases WHERE player_id=?", (player_id,))
        cur = conn.execute("DELETE FROM players WHERE id=?", (player_id,))
        return cur.rowcount > 0


# ── 매치 편집 ──────────────────────────────────────────────────────────────

def match_raw_stats(match_id: int) -> dict:
    """매치 메타 + 선수 원시 스탯(편집용). 모든 필드를 그대로 반환.

    반환: {match: {...}, players: [{stat_id, player_name, ...모든스탯필드}]} 또는 None
    """
    with db.get_conn() as conn:
        m = conn.execute(
            "SELECT id, mode, map_name, match_date, result, team_score, opponent_score, "
            "coach_note, vod_url, transcript_summary "
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
                f"""SELECT s.id stat_id, s.player_id player_id, p.name player_name,
                           s.kills, s.deaths,
                           s.kd_ratio, s.obj_time, s.score, s.impact,
                           s.total_damage, s.capture_kill
                    FROM {table} s JOIN players p ON p.id=s.player_id
                    WHERE s.match_id=? ORDER BY s.kills DESC""",
                (match_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT s.id stat_id, s.player_id player_id, p.name player_name,
                           s.kills, s.deaths,
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
    주의: coach_note/vod_url/transcript_summary는 날짜 단위(match_day_notes)로 이관됨.
    """
    allowed = {"result", "team_score", "opponent_score", "map_name", "match_date", "mode"}
    # result는 None(빈값) 저장 허용 — 클리어 목적.
    nullable = {"result"}
    updates = {k: v for k, v in fields.items()
               if k in allowed and (v is not None or k in nullable)}
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
    """선수 스탯 행의 특정 필드 수정. player_id(선수 재매핑)도 허용.

    mode: "HP" 또는 "SND". 허용 필드만 업데이트.
    player_id 변경 시 UNIQUE(match_id, player_id) 충돌 가능 — 그런 경우는 False 반환.
    """
    if mode == "HP":
        allowed = {"player_id", "kills", "deaths", "kd_ratio", "obj_time", "score",
                   "impact", "total_damage", "capture_kill"}
        table = "player_stats_hp"
    else:
        allowed = {"player_id", "kills", "deaths", "assists", "kd_ratio", "score",
                   "impact", "adr", "first_kill", "lone_wolf_win"}
        table = "player_stats_snd"

    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [stat_id]
    with db.get_conn() as conn:
        try:
            cur = conn.execute(f"UPDATE {table} SET {set_clause} WHERE id=?", params)
            return cur.rowcount > 0
        except Exception:
            # UNIQUE(match_id, player_id) 충돌 등 — 같은 매치에 이미 그 선수가 있음
            return False


def add_player_to_match(match_id: int, mode: str, player_id: int, **stats) -> bool:
    """기존 매치에 선수 한 명을 새로 추가 (AI 누락 보정용).

    mode: "HP" 또는 "SND".
    player_id: players 테이블의 정확한 id (admin 드롭다운에서 선택).
    stats: 모드별 허용 필드만 사용. (update_player_stat과 동일 화이트리스트)

    반환: True=추가 성공, False=이미 (match_id, player_id) 존재하거나 실패.
    UNIQUE(match_id, player_id) 제약이 새 조합 INSERT는 허용, 중복은 차단.
    """
    if mode == "HP":
        allowed = {"kills", "deaths", "kd_ratio", "obj_time", "score",
                   "impact", "total_damage", "capture_kill"}
        table = "player_stats_hp"
    else:
        allowed = {"kills", "deaths", "assists", "kd_ratio", "score",
                   "impact", "adr", "first_kill", "lone_wolf_win"}
        table = "player_stats_snd"

    fields = {k: v for k, v in stats.items() if k in allowed and v not in (None, "")}
    if not fields:
        # 최소 빈 행이라도 INSERT는 가능 (매치에 선수 자리만 확보)
        cols_str = "match_id, player_id"
        placeholders = "?, ?"
        params = [match_id, player_id]
    else:
        cols = list(fields.keys())
        cols_str = "match_id, player_id, " + ", ".join(cols)
        placeholders = "?, ?, " + ", ".join(["?"] * len(cols))
        params = [match_id, player_id] + [fields[c] for c in cols]

    with db.get_conn() as conn:
        try:
            cur = conn.execute(
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})", params
            )
            return cur.rowcount > 0
        except Exception:
            # UNIQUE(match_id, player_id) 충돌 — 이미 그 선수가 이 매치에 있음
            return False


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


# ── 날짜 단위 복기 (match_day_notes) ───────────────────────────────────────
# VOD/코치메모/전사요약은 하루 치가 하나라 매치 단위가 아닌 날짜 단위로 저장.

def get_day_notes(match_date: str) -> dict:
    """특정 날짜의 복기 데이터. 반환: {coach_note, vod_url, transcript_summary} or None."""
    if not match_date:
        return None
    with db.get_conn() as conn:
        r = conn.execute(
            "SELECT coach_note, vod_url, transcript_summary FROM match_day_notes WHERE match_date=?",
            (match_date,),
        ).fetchone()
        return dict(r) if r else None


def update_day_meta(match_date: str, **fields) -> bool:
    """날짜 단위 복기(coach_note/vod_url/transcript_summary) 갱신 (UPSERT).

    ★ 부분 갱신 지원: 전달된 필드만 업데이트.
    빈 문자열("")은 None으로 정규화(클리어), 아예 전달되지 않은 필드는 기존값 유지.
    (이전 구현은 세 필드를 통째로 UPSERT해 빈 필드가 다른 필드를 None으로 덮어쓰는
     데이터 손실 버그가 있었음.)
    """
    if not match_date:
        return False
    allowed = {"coach_note", "vod_url", "transcript_summary"}
    # 전달된 필드만, 빈문자열→None 정규화
    vals = {k: (v if v != "" else None) for k, v in fields.items() if k in allowed}
    if not vals:
        return False
    with db.get_conn() as conn:
        # 기존값 조회 후 병합 — 전달되지 않은 필드는 기존값 유지
        existing = conn.execute(
            "SELECT coach_note, vod_url, transcript_summary FROM match_day_notes WHERE match_date=?",
            (match_date,),
        ).fetchone()
        merged = {
            "coach_note": vals.get("coach_note", existing["coach_note"] if existing else None),
            "vod_url": vals.get("vod_url", existing["vod_url"] if existing else None),
            "transcript_summary": vals.get("transcript_summary",
                                           existing["transcript_summary"] if existing else None),
        }
        conn.upsert(
            "match_day_notes",
            ["match_date", "coach_note", "vod_url", "transcript_summary"],
            (match_date, merged["coach_note"], merged["vod_url"], merged["transcript_summary"]),
            conflict_col="match_date",
            update_cols=["coach_note", "vod_url", "transcript_summary"],
        )
        return True


def matches_by_date(match_date: str) -> list:
    """특정 날짜의 매치 요약 목록 (날짜 편집 페이지용). 반환: [{id, mode, map_name, result, ...}]."""
    if not match_date:
        return []
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT id, mode, map_name, result, team_score, opponent_score,
                      (SELECT COUNT(*) FROM player_stats_hp WHERE match_id=m.id) +
                      (SELECT COUNT(*) FROM player_stats_snd WHERE match_id=m.id) as players
               FROM matches m WHERE match_date=? ORDER BY id DESC""",
            (match_date,),
        ).fetchall()
        return [dict(r) for r in rows]
