# opponent_matching.py
"""상대팀 닉네임 정규화·퍼지 매칭·팀 투표 — 순수 로직 (DB 의존 없음).

설계 원칙(spec §2): 읽기는 GPT, 분류는 DB. 이 모듈은 분류의 순수 계산부다.
프롬프트에 상대 로스터를 주입하지 않기 때문에, 표기 정규화 + 유사도로
OCR 변형을 흡수한다.
"""
import difflib
import re
import unicodedata

TEAM_VOTE_RATIO = 0.6          # 팀 다수결: 일치 인원 / 적팀 인원 ≥ 0.6 (5명 중 3명)
FUZZY_TEAM_THRESHOLD = 0.75    # 팀 로스터 풀 내 퍼지 임계값 (넉넉)
FUZZY_GLOBAL_THRESHOLD = 0.85  # 전역 풀(용병 폴백) 임계값 (엄격)


def norm_name(s: str) -> str:
    """OCR 표기 정규화: NFKC → lowercase → 영숫자만 남김."""
    s = unicodedata.normalize("NFKC", (s or "").strip())
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def similarity(a: str, b: str) -> float:
    """정규화 후 유사도 (0~1). 어느 쪽이든 빈 문자열이면 0."""
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def best_fuzzy_match(name: str, candidates: list, threshold: float):
    """candidates: [(player_id, 기존 표기), ...] 중 임계값을 넘는 최고 유사도 매칭.

    반환: (player_id, score) 또는 None. 동점이면 먼저 등장한 후보.
    """
    best = None
    for pid, cand in candidates:
        score = similarity(name, cand)
        if score >= threshold and (best is None or score > best[1]):
            best = (pid, score)
    return best


def tally_team_votes(team_ids: list, total: int):
    """팀 득표 집계. team_ids: resolve된 선수들의 소속팀 목록(중복 허용,
    선수당 소속마다 1표). total: 적팀 선수 수(분모 — 미매칭 선수도 포함).

    반환: (과반 팀 id, 득표수). 단일 최고이면서 비율 ≥ TEAM_VOTE_RATIO인
    팀이 없으면 (None, 0). 동률은 기각(모호하면 admin으로).
    """
    counts = {}
    for t in team_ids:
        if t is not None:
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        return None, 0
    best_team, best_n = max(counts.items(), key=lambda kv: kv[1])
    others_max = max((v for t, v in counts.items() if t != best_team), default=0)
    if best_n > others_max and best_n / max(total, 1) >= TEAM_VOTE_RATIO:
        return best_team, best_n
    return None, 0
