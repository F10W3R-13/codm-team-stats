"""팀 순위 계산 — 풀리그(round_robin) 매치만 집계.

승점: 승=2, 패=0 (CODM HP/SND에 무승부 없음).
동점 시 타이브레이크: 득실차(score_for - score_against).
결승(final)은 별도 표시 (final_match).
"""
import db


def compute(path: str = None) -> list:
    """풀리그 순위표 반환. stage='round_robin' 매치만."""
    conn = db.get_conn(path)
    try:
        teams = [dict(r) for r in conn.execute("SELECT * FROM teams").fetchall()]
        matches = [dict(r) for r in conn.execute(
            "SELECT * FROM matches WHERE stage='round_robin'").fetchall()]
    finally:
        conn.close()

    table = {}
    for t in teams:
        table[t["id"]] = {
            "team_id": t["id"], "team_name": t["name"],
            "played": 0, "wins": 0, "losses": 0,
            "score_for": 0, "score_against": 0, "diff": 0, "points": 0,
        }

    for m in matches:
        a, b = m["team_a_id"], m["team_b_id"]
        if a not in table or b not in table:
            continue
        sa, sb = m["team_a_score"] or 0, m["team_b_score"] or 0
        table[a]["played"] += 1
        table[b]["played"] += 1
        table[a]["score_for"] += sa
        table[a]["score_against"] += sb
        table[b]["score_for"] += sb
        table[b]["score_against"] += sa
        if sa > sb:
            table[a]["wins"] += 1
            table[a]["points"] += 2
            table[b]["losses"] += 1
        elif sb > sa:
            table[b]["wins"] += 1
            table[b]["points"] += 2
            table[a]["losses"] += 1
        # 무승부(sa==sb) → CODM엔 없지만 안전망: 둘 다 1점
        elif sa == sb:
            table[a]["points"] += 1
            table[b]["points"] += 1

    for row in table.values():
        row["diff"] = row["score_for"] - row["score_against"]

    return sorted(table.values(),
                  key=lambda r: (-r["points"], -r["diff"], r["team_name"]))


def final_match(path: str = None):
    """결승(stage='final') 매치 정보. 없으면 None."""
    conn = db.get_conn(path)
    try:
        row = conn.execute(
            """SELECT m.id, m.team_a_score, m.team_b_score,
                      ta.name AS team_a_name, tb.name AS team_b_name
               FROM matches m
               JOIN teams ta ON ta.id = m.team_a_id
               JOIN teams tb ON tb.id = m.team_b_id
               WHERE m.stage='final'
               ORDER BY m.id DESC LIMIT 1""").fetchone()
        if not row:
            return None
        d = dict(row)
        sa, sb = d["team_a_score"] or 0, d["team_b_score"] or 0
        d["match_id"] = d["id"]
        d["winner_name"] = d["team_a_name"] if sa > sb else d["team_b_name"]
        return d
    finally:
        conn.close()
