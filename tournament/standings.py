"""팀 순위 계산 — 팀 대결(duel) 단위 세트 스코어 기반.

리그 구조: 5팀 풀리그, 각 팀 대결은 HP + SND + Control 3세트.
세트 다승이 많은 팀이 팀 대결 승 (Bo3).
Control이 미정인 대결은 세트 1-1 동점 → 미완료 대결.

스탠딩 기준: 팀 대결 승수 → 세트 득실차.
"""
from collections import defaultdict
import db


def _duels(path: str = None) -> dict:
    """매치들을 팀 대결(duel) 단위로 묶기.

    반환: {(min_tid, max_tid): [match, ...]}
    """
    conn = db.get_conn(path)
    try:
        matches = [dict(r) for r in conn.execute("SELECT * FROM matches").fetchall()]
    finally:
        conn.close()

    duels = defaultdict(list)
    for m in matches:
        a, b = m["team_a_id"], m["team_b_id"]
        key = (min(a, b), max(a, b))
        duels[key].append(m)
    return duels


def _duel_result(matches: list, t1: int, t2: int):
    """한 팀 대결의 세트 스코어 계산.

    각 세트(HP/SND/Control)의 승자를 판정 → t1 세트승, t2 세트승.
    같은 모드가 여러 개면 첫째만(중복 입력 정리용).
    반환: (t1_sets_won, t2_sets_won, mode_results)
    """
    seen_modes = set()
    t1_wins = 0
    t2_wins = 0
    mode_results = []  # [{mode, t1_score, t2_score, winner}]

    for m in matches:
        mode = m["mode"]
        if mode in seen_modes:
            continue  # 중복 모드 스킵 (입력 오류 정리)
        seen_modes.add(mode)

        # t1, t2 기준으로 점수 정규화
        if m["team_a_id"] == t1:
            s1 = m["team_a_score"] or 0
            s2 = m["team_b_score"] or 0
        else:
            s1 = m["team_b_score"] or 0
            s2 = m["team_a_score"] or 0

        winner = 1 if s1 > s2 else (2 if s2 > s1 else 0)
        if winner == 1:
            t1_wins += 1
        elif winner == 2:
            t2_wins += 1
        mode_results.append({
            "mode": mode, "t1_score": s1, "t2_score": s2, "winner": winner,
        })

    return t1_wins, t2_wins, mode_results


def compute(path: str = None) -> list:
    """팀 순위표 반환 (팀 대결 단위 세트 스코어 기반)."""
    conn = db.get_conn(path)
    try:
        teams = [dict(r) for r in conn.execute("SELECT * FROM teams").fetchall()]
    finally:
        conn.close()

    team_map = {t["id"]: t for t in teams}
    duels = _duels(path)

    table = {}
    for t in teams:
        table[t["id"]] = {
            "team_id": t["id"], "team_name": t["name"],
            "played": 0, "wins": 0, "losses": 0, "draws": 0,
            "sets_won": 0, "sets_lost": 0, "sets_diff": 0,
            "duels_completed": 0, "duels_pending": 0,
        }

    for (t1, t2), matches in duels.items():
        if t1 not in table or t2 not in table:
            continue
        t1_sets, t2_sets, _ = _duel_result(matches, t1, t2)

        # 세트 득실 누적
        table[t1]["sets_won"] += t1_sets
        table[t1]["sets_lost"] += t2_sets
        table[t2]["sets_won"] += t2_sets
        table[t2]["sets_lost"] += t1_sets

        # Control 세트가 있어야 3세트 완료. 현재는 HP/SND만 있으면 2세트 → 미완료 가능.
        total_sets = t1_sets + t2_sets
        if total_sets >= 3:
            # 완료된 대결 — 세트 다승으로 승패
            table[t1]["played"] += 1
            table[t2]["played"] += 1
            table[t1]["duels_completed"] += 1
            table[t2]["duels_completed"] += 1
            if t1_sets > t2_sets:
                table[t1]["wins"] += 1
                table[t2]["losses"] += 1
            elif t2_sets > t1_sets:
                table[t2]["wins"] += 1
                table[t1]["losses"] += 1
            else:
                table[t1]["draws"] += 1
                table[t2]["draws"] += 1
        else:
            # 미완료 (3세트 미만, 보통 Control 미입력)
            # 임시: 세트 다승으로 승패 가정하지만 미완료 표시
            table[t1]["played"] += 1
            table[t2]["played"] += 1
            if t1_sets > t2_sets:
                table[t1]["wins"] += 1
                table[t2]["losses"] += 1
            elif t2_sets > t1_sets:
                table[t2]["wins"] += 1
                table[t1]["losses"] += 1
            else:
                # 1-1 동점 (Control 미정) → 미완료, 승패 미반영
                table[t1]["duels_pending"] += 1
                table[t2]["duels_pending"] += 1

    for row in table.values():
        row["sets_diff"] = row["sets_won"] - row["sets_lost"]
        row["points"] = row["wins"] * 2 + row["draws"]

    return sorted(table.values(),
                  key=lambda r: (-r["points"], -r["wins"], -r["sets_diff"], r["team_name"]))


def duel_details(path: str = None) -> list:
    """모든 팀 대결의 상세 결과 (스탠딩 페이지 표시용).

    반환: [{t1_name, t2_name, t1_sets, t2_sets, mode_results, completed}]
    """
    conn = db.get_conn(path)
    try:
        teams = [dict(r) for r in conn.execute("SELECT * FROM teams").fetchall()]
    finally:
        conn.close()

    team_map = {t["id"]: t["name"] for t in teams}
    duels = _duels(path)

    results = []
    for (t1, t2), matches in sorted(duels.items()):
        t1_sets, t2_sets, mode_results = _duel_result(matches, t1, t2)
        total = t1_sets + t2_sets
        winner = (team_map[t1] if t1_sets > t2_sets else
                  team_map[t2] if t2_sets > t1_sets else None)
        results.append({
            "t1_id": t1,
            "t2_id": t2,
            "t1_name": team_map.get(t1, "?"),
            "t2_name": team_map.get(t2, "?"),
            "t1_sets": t1_sets,
            "t2_sets": t2_sets,
            "modes": mode_results,
            "completed": total >= 3,
            "winner": winner,
        })
    return results


def final_match(path: str = None):
    """결승 정보 (현재는 단일 매치 기준, 추후 Bo7 확장)."""
    # TODO: 결승 Bo7 구조 구현 시 확장
    return None
