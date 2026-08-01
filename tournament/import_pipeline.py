"""매치 자동 등록 오케스트레이션: 스크린샷 → 매치.

흐름: GPT 파싱 → IGN 팀 역추적 → 미리보기(preview) → 확정(confirm) → DB 저장.
stage 자동 판별: 같은 팀쌍 2번째 매치 = final.
"""
from vision import analyze_two_screens
import matching
import db
import stage


def _build_team_hint(path: str = None) -> str:
    """DB에서 팀별 명단을 읽어 GPT 힌트 텍스트 생성.

    예: "Team Fabriz (Fz.Karpe, Fz.Sica, Fz.Bang, ...), YetoTense (Madara, Itachi, ...)"
    GPT가 팀 인식과 선수 매칭에 활용.
    """
    try:
        teams = db.list_teams(path=path)
        if not teams:
            return ""
        lines = []
        for t in teams:
            players = db.list_players(t["id"], path=path)
            names = ", ".join(p["name"] for p in players)
            lines.append(f"- {t['name']}: {names}")
        return "이 대회에 참가한 팀과 선수:\n" + "\n".join(lines)
    except Exception:
        return ""  # DB 문제 시 힌트 없이 진행 (실패 안전)


def _match_team(team_igns: list, path: str):
    """5 IGN 리스트 → (team_id, [{...선수}], [unmatched_ign]).

    각 IGN을 DB에서 역추적. 전원 같은 팀이면 그 팀 ID 반환.
    일부만 매칭/서로 다른 팀이면 team_id=None (사용자 개입 필요).
    """
    players = db.list_players(path=path)
    candidates = [p["name"] for p in players]

    resolved = {}  # ign → matched standard name
    team_ids = set()
    unmatched = []
    for ign in team_igns:
        # ① DB 직접 매칭 (alias/표준명/정규화)
        result = db.resolve_player(ign, path=path)
        if result:
            pid, tid = result
            # 정확 매칭은 틀릴 리 없으므로 alias 자동 등록 (다음부턴 더 빠르게 매칭)
            db.insert_alias(ign, pid, path=path)
            resolved[ign] = {"player_id": pid, "team_id": tid, "ign": ign}
            team_ids.add(tid)
            continue
        # ② 퍼지 매칭 (임계값 0.75)
        match = matching.fuzzy_match(ign, candidates)
        if match:
            result = db.resolve_player(match, path=path)
            if result:
                pid, tid = result
                # alias 자동 등록은 안 함 (틀릴 수 있음).
                # 사용자가 미리보기에서 확인하고 저장할 때만 등록됨 (_resolve_player_id).
                resolved[ign] = {"player_id": pid, "team_id": tid, "ign": ign,
                                 "standard_name": match}
                team_ids.add(tid)
                continue
        # ③ 추측 매칭 (임계값 0.6) — 알파벳 일부만 맞아도 원본 닉네임 추측
        # alias 자동 등록은 안 함 (틀릴 가능성 높음). guessed 표시만.
        guess = matching.best_guess(ign, candidates)
        if guess:
            guess_name, ratio = guess
            result = db.resolve_player(guess_name, path=path)
            if result:
                pid, tid = result
                resolved[ign] = {"player_id": pid, "team_id": tid, "ign": ign,
                                 "standard_name": guess_name, "guessed": True}
                team_ids.add(tid)
                continue
        # ④ 매칭 전부 실패 → player_id=None으로 자리에 넣음 (미리보기에 5명 유지)
        # 사용자가 미리보기에서 이름을 올바른 선수로 고쳐 저장하면 매칭됨.
        resolved[ign] = {"player_id": None, "ign": ign, "unmatched": True}
        unmatched.append(ign)

    # 전원 같은 팀이면 team_id 확정
    team_id = next(iter(team_ids)) if len(team_ids) == 1 else None
    return team_id, list(resolved.values()), unmatched


def preview(image_bytes_1: bytes, image_bytes_2: bytes, path: str = None) -> dict:
    """GPT 파싱 + 팀 역추적 → 미리보기 (저장 전).

    반환: {mode, map, team_left_score, team_right_score,
          team_a_name, team_b_name, team_a_id, team_b_id,
          team_a: [매핑된 선수+스탯], team_b: [...], unmatched: [ign]}
    """
    # GPT에게 팀 명단 힌트 제공 → 팀 인식 정확도 향상
    team_hint = _build_team_hint(path)
    gpt = analyze_two_screens(image_bytes_1, image_bytes_2, team_hint=team_hint)
    mode = gpt.get("mode", "")
    map_name = gpt.get("map")
    left = gpt.get("team_left", [])
    right = gpt.get("team_right", [])

    team_a_id, team_a_resolved, unmatched_a = _match_team(
        [p.get("name", "") for p in left], path)
    team_b_id, team_b_resolved, unmatched_b = _match_team(
        [p.get("name", "") for p in right], path)

    # IGN → 스탯 매핑 (resolved에 스탯 병합)
    left_by_name = {p.get("name", ""): p for p in left}
    right_by_name = {p.get("name", ""): p for p in right}

    def _merge(resolved, by_name):
        out = []
        for r in resolved:
            ign = r["ign"]
            stats = by_name.get(ign, {})
            out.append({**r, **{k: v for k, v in stats.items() if k != "name"}})
        return out

    teams = {t["id"]: t["name"] for t in db.list_teams(path=path)}

    return {
        "mode": mode,
        "map": map_name,
        "team_left_score": gpt.get("team_left_score"),
        "team_right_score": gpt.get("team_right_score"),
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "team_a_name": teams.get(team_a_id) if team_a_id else None,
        "team_b_name": teams.get(team_b_id) if team_b_id else None,
        "team_a": _merge(team_a_resolved, left_by_name),
        "team_b": _merge(team_b_resolved, right_by_name),
        "unmatched": unmatched_a + unmatched_b,
        # 원본 GPT 스탯 (수동 매핑 시 사용)
        "_raw_left": left,
        "_raw_right": right,
    }


def confirm(preview_data: dict, path: str = None) -> int:
    """미리보기 확정 → 매치 INSERT + stats INSERT. match_id 반환.

    team_a_id/team_b_id가 None이면 (팀 식별 실패) raise.
    player_id가 없는 선수(수동 추가 등)는 name으로 DB 조회 후,
    못 찾으면 해당 팀에 신규 선수로 등록한다.
    """
    team_a_id = preview_data["team_a_id"]
    team_b_id = preview_data["team_b_id"]
    if not team_a_id or not team_b_id:
        raise ValueError("팀 식별 실패 — unmatched 처리 필요")

    # stage 자동 판별
    st = stage.determine_stage(team_a_id, team_b_id, path=path)

    match_id = db.insert_match(
        preview_data["mode"], preview_data.get("map"),
        preview_data.get("match_date"), team_a_id, team_b_id,
        preview_data.get("team_left_score"),
        preview_data.get("team_right_score"),
        stage=st, path=path)

    mode = preview_data["mode"]
    for p in preview_data["team_a"]:
        _insert_stat(mode, match_id, p, team_a_id, path)
    for p in preview_data["team_b"]:
        _insert_stat(mode, match_id, p, team_b_id, path)

    return match_id


def _resolve_player_id(player, team_id, path):
    """선수의 player_id 해결. 우선순위:
    ① 기존 player_id ② name/ign으로 DB 조회 ③ 신규 선수 등록.
    빈 이름이면 None (스킵).
    저장 시점이므로 사용자가 미리보기에서 확인한 이름을 alias로 등록 (안전).
    """
    pid = player.get("player_id")
    ign = (player.get("ign") or "").strip()
    name = (player.get("standard_name") or ign).strip()
    if not pid:
        if not name:
            return None
        # DB에서 이름으로 조회 (alias/표준명/정규화 매칭)
        resolved = db.resolve_player(name, path=path)
        if resolved:
            pid = resolved[0]
        else:
            # DB에 없으면 해당 팀에 신규 선수 등록
            pid = db.insert_player(name, team_id, path=path)
            db.insert_alias(name, pid, path=path)
    # 저장 시점 alias 등록 (사용자가 확인한 이름 — 추측 매칭 포함 안전).
    # IGN과 표준명이 다르면 IGN을 alias로 등록 → 다음부턴 직접 매칭.
    if ign and ign != name:
        db.insert_alias(ign, pid, path=path)
    return pid


def _insert_stat(mode, match_id, player, team_id, path):
    """모드별로 HP/SND 스탯 INSERT.

    player_id 자동 해결: 없으면 name으로 DB 조회/신규 등록.
    빈 이름 선수는 스킵.
    """
    pid = _resolve_player_id(player, team_id, path)
    if not pid:
        return  # 이름 없는 빈 행 — 스킵
    if mode == "HP":
        db.insert_player_stats_hp(
            match_id, pid, team_id,
            kills=player.get("k", 0), deaths=player.get("d", 0),
            assists=player.get("a", 0), damage=player.get("total_damage", 0),
            obj_time=player.get("time", 0), capture_kill=player.get("capture_kill", 0),
            path=path)
    elif mode == "SND":
        db.insert_player_stats_snd(
            match_id, pid, team_id,
            kills=player.get("k", 0), deaths=player.get("d", 0),
            assists=player.get("a", 0), damage=player.get("total_damage", 0),
            adr=player.get("adr", 0), first_kill=player.get("first_kill", 0),
            lone_wolf_win=player.get("lone_wolf_win", 0), path=path)
