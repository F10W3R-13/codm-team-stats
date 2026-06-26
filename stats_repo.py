# 스탯 기록/조회 저장소 (Repository)
#
# 봇과 향후 웹/명령어가 공통으로 쓰는 데이터 접근 계층.
# 구글 시트에 직접 쓰던 것을 SQLite로 대체한다.
# 디스코드 봇이 한 매치 분석 결과를 이 모듈의 save_match()로 넘기면 된다.

import db


def save_match(mode: str, players: list, match_date: str, map_name: str = None,
               result: str = None, team_score: int = None, opponent_score: int = None) -> dict:
    """GPT 분석 결과 한 매치를 DB에 저장.

    mode:           "HP" 또는 "SND"
    players:        GPT 결과의 players 배열 (선수 dict 리스트)
    match_date:     ISO 날짜(YYYY-MM-DD). 디스코드 메시지 작성일.
    map_name:       맵 이름 (전체 스크린샷에서 추출, 예: "Combine")
    result:         "WIN" 또는 "LOSS"
    team_score:     우리 팀 점수
    opponent_score: 상대 팀 점수

    반환: {"match_id": int, "saved": int, "mode": str}
    """
    with db.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO matches(mode, map_name, match_date, result, team_score, opponent_score)
               VALUES (?,?,?,?,?,?)""",
            (mode, map_name, match_date, result, team_score, opponent_score),
        )
        match_id = cur.lastrowid

        if mode == "HP":
            for p in players:
                _insert_hp(conn, match_id, p)
        else:  # SND
            for p in players:
                _insert_snd(conn, match_id, p)

        # 새 매치 기록 → 인사이트 캐시 전체 무효화 (최신 데이터로 갱신 유도)
        try:
            import insight_cache
            insight_cache.invalidate_all()
        except ImportError:
            pass

        return {"match_id": match_id, "saved": len(players), "mode": mode,
                "result": result, "team_score": team_score,
                "opponent_score": opponent_score, "map": map_name}


def _insert_hp(conn, match_id, p):
    # 표준 이름(actual name)으로 player 매핑. GPT가 이미 로스터 기준 정규화해줌.
    name = p.get("name", "").strip() or "Unknown"
    pid = db.resolve_player_id(conn, name, ign_raw=p.get("ign_raw"))
    conn.execute(
        """INSERT OR REPLACE INTO player_stats_hp
           (match_id, player_id, ign_raw, kills, deaths, kd_ratio,
            obj_time, score, impact, total_damage, capture_kill)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            match_id, pid, p.get("name"),
            _to_int(p.get("k")), _to_int(p.get("d")), _to_float(p.get("kd_ratio")),
            _to_int(p.get("time")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_int(p.get("total_damage")),
            _to_int(p.get("capture_kill")),
        ),
    )


def _insert_snd(conn, match_id, p):
    name = p.get("name", "").strip() or "Unknown"
    pid = db.resolve_player_id(conn, name, ign_raw=p.get("ign_raw"))
    conn.execute(
        """INSERT OR REPLACE INTO player_stats_snd
           (match_id, player_id, ign_raw, kills, deaths, assists,
            kd_ratio, score, impact, adr, first_kill, lone_wolf_win)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            match_id, pid, p.get("name"),
            _to_int(p.get("k")), _to_int(p.get("d")), _to_int(p.get("a")),
            _to_float(p.get("kd_ratio")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_float(p.get("adr")),
            _to_int(p.get("first_kill")), _to_int(p.get("lone_wolf_win")),
        ),
    )


def _to_int(v):
    try:
        return int(float(str(v))) if str(v).strip() not in ("", "None") else None
    except (ValueError, TypeError):
        return None


def _to_float(v):
    try:
        return float(str(v)) if str(v).strip() not in ("", "None") else None
    except (ValueError, TypeError):
        return None
