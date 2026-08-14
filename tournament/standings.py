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

    CODM 대회 세트 순서: HP → SND → CTL → HP → SND → CTL ... (Bo3/Bo5/Bo7).
    같은 모드가 여러 번 나오는 게 정상 (순환 구조).
    매치를 id순(=세트 순서)으로 전부 유효하게 처리 → 다승 판정.
    반환: (t1_sets_won, t2_sets_won, mode_results)
    """
    t1_wins = 0
    t2_wins = 0
    mode_results = []  # [{mode, t1_score, t2_score, winner, match_id}]

    # id순 정렬 (세트 순서 보장)
    for m in sorted(matches, key=lambda x: x["id"]):
        mode = m["mode"]

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
            "match_id": m["id"],
        })

    return t1_wins, t2_wins, mode_results


def compute(path: str = None) -> list:
    """팀 순위표 반환 (팀 대결 단위 세트 스코어 기반)."""
    conn = db.get_conn(path)
    try:
        teams = [dict(r) for r in conn.execute("SELECT * FROM teams").fetchall()]
    finally:
        conn.close()

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

        # Bo5: 한 팀이 3승(과반수) 먼저 따면 확정 완료. 아니면 진행 중.
        table[t1]["played"] += 1
        table[t2]["played"] += 1
        if t1_sets >= 3 or t2_sets >= 3:
            # 완료된 대결
            if t1_sets > t2_sets:
                table[t1]["wins"] += 1
                table[t2]["losses"] += 1
            elif t2_sets > t1_sets:
                table[t2]["wins"] += 1
                table[t1]["losses"] += 1
        else:
            # 진행 중 (3승 미만) — 임시로 다승 다인 팀을 리드로 표시하지만 승패 미반영
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
            "completed": t1_sets >= 3 or t2_sets >= 3,  # Bo5: 3승 시 확정
            "winner": winner,
        })
    return results


def final_match(path: str = None):
    """결승 정보 (현재는 단일 매치 기준, 추후 Bo7 확장)."""
    # TODO: 결승 Bo7 구조 구현 시 확장
    return None
