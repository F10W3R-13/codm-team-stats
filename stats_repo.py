# 스탯 기록/조회 저장소 (Repository)
#
# 봇과 향후 웹/명령어가 공통으로 쓰는 데이터 접근 계층.
# 구글 시트에 직접 쓰던 것을 SQLite로 대체한다.
# 디스코드 봇이 한 매치 분석 결과를 이 모듈의 save_match()로 넘기면 된다.

import logging

import db

log = logging.getLogger(__name__)


def save_match(mode: str, players: list, match_date: str, map_name: str = None,
               result: str = None, team_score: int = None, opponent_score: int = None,
               enemy_players: list = None) -> dict:
    """GPT 분석 결과 한 매치를 DB에 저장.

    mode:           "HP" 또는 "SND"
    players:        GPT 결과의 players 배열 (선수 dict 리스트)
    match_date:     ISO 날짜(YYYY-MM-DD). 디스코드 메시지 작성일.
    map_name:       맵 이름 (전체 스크린샷에서 추출, 예: "Combine")
    result:         "WIN" 또는 "LOSS"
    team_score:     우리 팀 점수
    opponent_score: 상대 팀 점수
    enemy_players:  상대팀 선수 스탯 (선택). 있으면 상대팀 테이블에 별도 저장 +
                    팀 자동 식별(matches.opponent_team_id 태그). 부분 실패 격리 —
                    여기서 실패해도 우리팀 저장은 정상 (spec §5.3).

    재업로드(같은 경기 중복) 처리:
    같은 날짜·모드·맵의 기존 매치 중 스탯이 들어오는 것의 부분집합인 매치가 있으면
    새 매치를 만들지 않고 그 매치에 병합한다 (부분 인식 4/5명 재업로드 보정).
    반환 dict에 "duplicate": True 와 실제 추가된 행수가 "saved"로 들어간다.

    반환: {"match_id": int, "saved": int, "mode": mode, "duplicate": bool,
           ..., "opponent": {"team_id": int|None, "saved": int} | None}
    """
    with db.get_conn() as conn:
        dup_match_id = _find_reupload_target(conn, mode, players, match_date, map_name)
        if dup_match_id is not None:
            match_id = dup_match_id
            before = _match_row_count(conn, mode, match_id)
            _upsert_players(conn, mode, match_id, players)
            after = _match_row_count(conn, mode, match_id)
            _fill_match_meta(conn, match_id, map_name, result, team_score, opponent_score)
            saved = after - before
            duplicate = True
        else:
            match_id = conn.execute_returning_id(
                """INSERT INTO matches(mode, map_name, match_date, result, team_score, opponent_score)
                   VALUES (?,?,?,?,?,?)""",
                (mode, map_name, match_date, result, team_score, opponent_score),
            )
            _upsert_players(conn, mode, match_id, players)
            saved = len(players)
            duplicate = False

        # 상대팀 저장 — 부분 실패 격리: 여기서 실패해도 우리팀 저장은 유효 (spec §5.3)
        # if/else 밖에서 실행 → 신규·재업로드 병합 양쪽 경로 모두 커버.
        enemy_info = None
        if enemy_players:
            try:
                enemy_info = _save_opponent_stats(conn, match_id, mode, enemy_players)
            except Exception as e:
                log.warning(f"[save_match] 상대팀 저장 실패 (우리팀 저장은 정상): {e}")
                enemy_info = {"team_id": None, "saved": 0, "error": str(e)}

        # 매치 기록/병합 → 인사이트 캐시 전체 무효화 (최신 데이터로 갱신 유도)
        try:
            import insight_cache
            insight_cache.invalidate_all()
        except ImportError:
            pass

        return {"match_id": match_id, "saved": saved, "mode": mode,
                "duplicate": duplicate,
                "result": result, "team_score": team_score,
                "opponent_score": opponent_score, "map": map_name,
                "opponent": enemy_info}


def _upsert_players(conn, mode: str, match_id: int, players: list) -> None:
    if mode == "HP":
        for p in players:
            _insert_hp(conn, match_id, p)
    else:  # SND
        for p in players:
            _insert_snd(conn, match_id, p)


def _match_row_count(conn, mode: str, match_id: int) -> int:
    tbl = "player_stats_hp" if mode == "HP" else "player_stats_snd"
    r = conn.execute(
        db._adapt_sql(f"SELECT COUNT(*) c FROM {tbl} WHERE match_id=?"),
        (match_id,),
    ).fetchone()
    return r["c"] if r else 0


def _fill_match_meta(conn, match_id: int, map_name, result, team_score, opponent_score) -> None:
    """병합 시 기존 매치의 NULL meta 필드만 채운다 (기존 값은 덮어쓰지 않음)."""
    conn.execute(
        db._adapt_sql(
            """UPDATE matches SET
                 result=COALESCE(result, ?),
                 team_score=COALESCE(team_score, ?),
                 opponent_score=COALESCE(opponent_score, ?),
                 map_name=COALESCE(map_name, ?)
               WHERE id=?"""),
        (result, team_score, opponent_score, map_name, match_id),
    )


def _find_reupload_target(conn, mode: str, players: list, match_date: str, map_name):
    """같은 경기의 재업로드 탐지 → 병합할 기존 match_id (없으면 None).

    조건: 같은 날짜·모드·맵의 기존 매치 중, 그 매치의 모든 스탯 행(kills,deaths,score
    다중집합)이 들어오는 선수 스탯의 부분집합인 매치.
    - 전체 동일 → 순수 중복 (skip)
    - 기존이 일부(4/5명 인식) → 재업로드 병합 대상 (누락 선수 추가)
    같은 날 같은 맵을 실제로 두 번 하는 경기는 선수 스탯이 달라 집합에 못 들어간다.
    """
    from collections import Counter
    incoming = Counter(
        (_to_int(p.get("k")), _to_int(p.get("d")), _to_int(p.get("score")))
        for p in players
    )
    if not any(incoming.values()):
        return None
    tbl = "player_stats_hp" if mode == "HP" else "player_stats_snd"
    # 맵 조건: 양쪽 다 알 때는 동일해야 하되, 한쪽이라도 못 읽었으면(NULL) 통과.
    # 진짜 중복 판별은 아래 스탯 부분집합 조건이 담당한다.
    cands = conn.execute(
        db._adapt_sql(
            """SELECT id FROM matches
               WHERE mode=? AND match_date=?
                 AND (map_name=? OR map_name IS NULL OR ? IS NULL)
               ORDER BY id DESC"""),
        (mode, match_date, map_name, map_name),
    ).fetchall()
    for c in cands:
        rows = conn.execute(
            db._adapt_sql(f"SELECT kills, deaths, score FROM {tbl} WHERE match_id=?"),
            (c["id"],),
        ).fetchall()
        existing = Counter((r["kills"], r["deaths"], r["score"]) for r in rows)
        if existing and existing <= incoming:
            return c["id"]
    return None


def _insert_hp(conn, match_id, p):
    # 표준 이름(actual name)으로 player 매핑. GPT가 이미 로스터 기준 정규화해줌.
    name = p.get("name", "").strip() or "Unknown"
    # ign_raw: GPT가 원본 IGN을 별도로 주면 그것을, 없으면 표준 name을 저장.
    # alias 자가학습(db.resolve_player_id)과 감사 추적에 사용.
    ign_raw = (p.get("ign_raw") or "").strip() or name
    pid = db.resolve_player_id(conn, name, ign_raw=ign_raw)
    conn.upsert(
        "player_stats_hp",
        ["match_id", "player_id", "ign_raw", "kills", "deaths", "kd_ratio",
         "obj_time", "score", "impact", "total_damage", "capture_kill"],
        (
            match_id, pid, ign_raw,
            _to_int(p.get("k")), _to_int(p.get("d")), _to_float(p.get("kd_ratio")),
            _to_int(p.get("time")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_int(p.get("total_damage")),
            _to_int(p.get("capture_kill")),
        ),
        conflict_col="match_id, player_id",
        update_cols=["ign_raw", "kills", "deaths", "kd_ratio",
                     "obj_time", "score", "impact", "total_damage", "capture_kill"],
    )


def _insert_snd(conn, match_id, p):
    name = p.get("name", "").strip() or "Unknown"
    ign_raw = (p.get("ign_raw") or "").strip() or name
    pid = db.resolve_player_id(conn, name, ign_raw=ign_raw)
    conn.upsert(
        "player_stats_snd",
        ["match_id", "player_id", "ign_raw", "kills", "deaths", "assists",
         "kd_ratio", "score", "impact", "adr", "first_kill", "lone_wolf_win"],
        (
            match_id, pid, ign_raw,
            _to_int(p.get("k")), _to_int(p.get("d")), _to_int(p.get("a")),
            _to_float(p.get("kd_ratio")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_float(p.get("adr")),
            _to_int(p.get("first_kill")), _to_int(p.get("lone_wolf_win")),
        ),
        conflict_col="match_id, player_id",
        update_cols=["ign_raw", "kills", "deaths", "assists", "kd_ratio",
                     "score", "impact", "adr", "first_kill", "lone_wolf_win"],
    )


def _save_opponent_stats(conn, match_id: int, mode: str, enemy_players: list) -> dict:
    """상대 선수 스탯 저장 + 팀 자동 식별 (spec §5).

    identify(전역 resolve + 다수결) → 팀 태그 → 팀 풀 재resolve로 저장 →
    로스터 축적(source='match'). 사전이 자라나는 지점.
    """
    names = [(p.get("name") or "").strip() for p in enemy_players]
    names = [n for n in names if n]
    if not names:
        return {"team_id": None, "saved": 0}

    team_id = db.identify_opponent_team(conn, names)
    # 1차 패스: 전원 resolve를 먼저 끝낸다 — 저장 중에 로스터를 축적하면
    # 방금 추가된 신규 선수가 다음 이름의 팀 풀 퍼지 후보로 들어가
    # 유사 무명 선수끼리 오병합된다 (예: SubNew1~SubNew2).
    resolved = []
    for p in enemy_players:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        pid = db.resolve_opponent_player_id(conn, name, team_id=team_id)
        resolved.append((pid, p))
    # 2차 패스: 스탯 저장 + 로스터 축적(source='match'). 사전이 자라나는 지점.
    saved = 0
    for pid, p in resolved:
        if mode == "HP":
            _insert_opp_hp(conn, match_id, pid, p)
        else:
            _insert_opp_snd(conn, match_id, pid, p)
        if team_id:
            conn.upsert("opponent_team_rosters",
                        ["team_id", "player_id", "source"], (team_id, pid, "match"),
                        conflict_col="team_id, player_id")
        saved += 1

    if team_id:
        conn.execute(db._adapt_sql(
            "UPDATE matches SET opponent_team_id = ? "
            "WHERE id = ? AND opponent_team_id IS NULL"), (team_id, match_id))
    return {"team_id": team_id, "saved": saved}


def _insert_opp_hp(conn, match_id, pid, p):
    conn.upsert(
        "opponent_stats_hp",
        ["match_id", "player_id", "ign_raw", "kills", "deaths", "kd_ratio",
         "obj_time", "score", "impact", "total_damage", "capture_kill"],
        (
            match_id, pid, (p.get("name") or "").strip() or "Unknown",
            _to_int(p.get("k")), _to_int(p.get("d")), _to_float(p.get("kd_ratio")),
            _to_int(p.get("time")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_int(p.get("total_damage")),
            _to_int(p.get("capture_kill")),
        ),
        conflict_col="match_id, player_id",
        update_cols=["ign_raw", "kills", "deaths", "kd_ratio",
                     "obj_time", "score", "impact", "total_damage", "capture_kill"],
    )


def _insert_opp_snd(conn, match_id, pid, p):
    conn.upsert(
        "opponent_stats_snd",
        ["match_id", "player_id", "ign_raw", "kills", "deaths", "assists",
         "kd_ratio", "score", "impact", "adr", "first_kill", "lone_wolf_win"],
        (
            match_id, pid, (p.get("name") or "").strip() or "Unknown",
            _to_int(p.get("k")), _to_int(p.get("d")), _to_int(p.get("a")),
            _to_float(p.get("kd_ratio")), _to_int(p.get("score")),
            _to_float(p.get("impact")), _to_float(p.get("adr")),
            _to_int(p.get("first_kill")), _to_int(p.get("lone_wolf_win")),
        ),
        conflict_col="match_id, player_id",
        update_cols=["ign_raw", "kills", "deaths", "assists", "kd_ratio",
                     "score", "impact", "adr", "first_kill", "lone_wolf_win"],
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
