"""토너먼트 팀·명단 시드 CLI.

사용법:
  python seed.py                    # 대화형 입력
  python seed.py teams.json         # JSON 파일에서 로드

JSON 형식:
{
  "teams": [
    {"name": "Alpha", "players": ["Ace", "Sniper", "King", "Ghost", "Wolf"]},
    ...
  ]
}
"""
import json
import sys

import db


def seed_from_dict(data: dict, path: str = None) -> None:
    db.init_db(path)
    for i, team in enumerate(data.get("teams", [])):
        tid = db.insert_team(team["name"], seed=i + 1, path=path)
        for pname in team.get("players", []):
            pid = db.insert_player(pname, tid, path=path)
            db.insert_alias(pname, pid, path=path)  # 표준명도 alias로 등록
        print(f"  ✓ {team['name']}: {len(team.get('players', []))}명 (id={tid})")
    print(f"시드 완료: 팀 {len(data.get('teams', []))}개")


def interactive():
    print("=== 토너먼트 시드 ===")
    teams_input = input("팀 수 (기본 5): ").strip() or "5"
    n = int(teams_input)
    data = {"teams": []}
    for i in range(n):
        name = input(f"\n팀 {i+1} 이름: ").strip()
        if not name:
            continue
        players_str = input(f"  {name} 선수 (쉼표로 구분): ").strip()
        players = [p.strip() for p in players_str.split(",") if p.strip()]
        data["teams"].append({"name": name, "players": players})
    return data


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            data = json.load(f)
        print(f"파일에서 로드: {sys.argv[1]}")
    else:
        data = interactive()
    seed_from_dict(data)
    teams = db.list_teams()
    print(f"\n등록된 팀: {len(teams)}개")
    for t in teams:
        ps = db.list_players(t["id"])
        print(f"  {t['name']}: {len(ps)}명 — {[p['name'] for p in ps]}")


if __name__ == "__main__":
    main()
