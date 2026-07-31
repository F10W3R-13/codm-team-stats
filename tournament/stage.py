"""매치 stage 자동 판별: round_robin vs final.

풀리그(라운드로빈)에서는 모든 팀쌍이 정확히 1번 만난다.
결승 = 1위 vs 2위 재대결이므로 같은 팀쌍이 2번째로 만나면 'final'.
"""
import db


def determine_stage(team_a_id: int, team_b_id: int, path: str = None) -> str:
    """두 팀이 이미 1번 이상 만났으면 'final', 처음이면 'round_robin'."""
    count = db.match_count_between(team_a_id, team_b_id, path=path)
    return "final" if count >= 1 else "round_robin"
