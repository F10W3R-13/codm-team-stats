# -*- coding: utf-8 -*-
"""우리팀 로스터(players) 오염 진단 — 상대 선수가 players/player_stats로 흡수됐는지.

배포 DB 읽기 전용. 실행:
  railway run --service Postgres python scripts/diag_roster_pollution.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# railway run이 주입하는 DATABASE_URL은 프라이빗이라 PUBLIC으로 덮어쓴 후 db 임포트.
if os.environ.get("DATABASE_PUBLIC_URL"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_PUBLIC_URL"]

import db  # noqa: E402
import opponent_matching  # noqa: E402


def main():
    with db.get_conn() as conn:
        our = conn.execute("SELECT id, name FROM players ORDER BY id").fetchall()
        print(f"== players(우리 로스터) {len(our)}명 ==")
        for r in our:
            print(f"  {r['id']:4d}  {r['name']}")

        print("\n== opponent_players ↔ players 이름 충돌 (norm 일치) ==")
        opp = conn.execute("SELECT id, name FROM opponent_players").fetchall()
        opp_by_norm = {opponent_matching.norm_name(r["name"]): r["name"] for r in opp}
        clashes = []
        for r in our:
            hit = opp_by_norm.get(opponent_matching.norm_name(r["name"]))
            if hit:
                clashes.append((r["name"], hit))
        for a, b in clashes:
            print(f"  우리 '{a}'  ==  상대 '{b}'")
        if not clashes:
            print("  (없음)")

        # opp alias까지 포함해 우리 players 이름이 상대로 등록된 경우
        print("\n== opponent_aliases에 우리 players 이름 등록 여부 ==")
        our_norms = {opponent_matching.norm_name(r["name"]) for r in our}
        n = 0
        for r in conn.execute("SELECT ign, opponent_player_id FROM opponent_aliases").fetchall():
            if opponent_matching.norm_name(r["ign"]) in our_norms:
                print(f"  alias '{r['ign']}' -> opponent_player {r['opponent_player_id']}")
                n += 1
        if not n:
            print("  (없음)")

        print("\n== uD 팀 로스터 ==")
        rows = conn.execute(db._adapt_sql(
            "SELECT t.id, t.name FROM opponent_teams t")).fetchall()
        for t in rows:
            ros = conn.execute(db._adapt_sql(
                "SELECT p.name FROM opponent_team_rosters r "
                "JOIN opponent_players p ON p.id=r.player_id WHERE r.team_id=?"),
                (t["id"],)).fetchall()
            print(f"  [{t['id']}] {t['name']}: {', '.join(r['name'] for r in ros)}")

        # 우리 선수별 최근 스탯 행 — 오염 의심 이름(uD 접두 등) 탐지
        print("\n== player_stats ign_raw 샘플 (이상 이름 탐지, 최근 200행) ==")
        for tbl in ("player_stats_hp", "player_stats_snd"):
            rows = conn.execute(db._adapt_sql(
                f"SELECT p.name, s.ign_raw, s.match_id FROM {tbl} s "
                f"JOIN players p ON p.id=s.player_id ORDER BY s.match_id DESC LIMIT 200")).fetchall()
            weird = [r for r in rows
                     if opponent_matching.norm_name(r["name"]) != opponent_matching.norm_name(r["ign_raw"] or "")]
            print(f"  -- {tbl}: name≠ign_raw {len(weird)}건/최근{len(rows)}건")
            for r in weird[:40]:
                print(f"     match {r['match_id']}: name='{r['name']}' ign_raw='{r['ign_raw']}'")

        # 매치당 우리팀 5명 초과/미만 이상치
        print("\n== 매치별 우리팀 행수 이상 (6행 초과, 최근 순) ==")
        for tbl in ("player_stats_hp", "player_stats_snd"):
            rows = conn.execute(db._adapt_sql(
                f"SELECT match_id, COUNT(*) AS c FROM {tbl} GROUP BY match_id "
                f"HAVING COUNT(*) > 5 ORDER BY match_id DESC LIMIT 30")).fetchall()
            print(f"  -- {tbl}: {len(rows)}개 매치")
            for r in rows:
                print(f"     match {r['match_id']}: {r['c']}행")

        print("\n== pending 규모 (opponent_team_id NULL + 상대스탯 보유 매치) ==")
        c = conn.execute(db._adapt_sql(
            "SELECT COUNT(*) c FROM matches m WHERE m.opponent_team_id IS NULL "
            "AND EXISTS (SELECT 1 FROM opponent_stats_hp h WHERE h.match_id=m.id "
            "UNION ALL SELECT 1 FROM opponent_stats_snd s WHERE s.match_id=m.id)")).fetchone()
        print(f"  {c['c']}건")


if __name__ == "__main__":
    main()
