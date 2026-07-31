"""IGN(게임 내 이름) → DB 선수 매칭.

OCR 인식명은 클랜태그/특수문자/대소문자가 뒤섞여 있어 정규화 후 비교.
우선순위: ① 정확 매칭(alias/표준명) ② 정규화 매칭 ③ 퍼지(클랜태그 제거 후 비교).
OCR alias 매칭 스킬(.agents/skills/ocr-alias-matching)과 동일 철학.
"""
import difflib
import re

import _path_setup  # noqa: F401  (부모 metrics.py 경로 보정 — 일관성)


def normalize(name: str) -> str:
    """이름 정규화: 소문자화 + 클랜태그/특수문자 제거 + 끝 숫자접미사 제거.

    [CLAN]Ace_Pro_99 → acepro99
    Fz.Karpe → karpe
    V1 Ichi → ichi
    Hashirama6974 → hashirama
    """
    s = name.lower().strip()
    s = re.sub(r"\[.*?\]", "", s)         # 클랜태그 [XXX]
    s = re.sub(r"[^a-z0-9가-힣]", "", s)  # 알파벳+숫자+한글만 (특수문자/점/공백 제거)
    s = re.sub(r"\d+$", "", s)            # 끝 숫자 접미사 (6974 등 — 플레이어 식별번호)
    return s


def _strip_clan_prefix(name: str) -> str:
    """클랜태그 접두사(Fz./V1 /CLRS.)를 제거한 핵심 이름 추출.

    Fz.Karpe → Karpe, V1 Ichi → Ichi, CLRS.LL → LL, -MaDara- → MaDara
    GPT가 'Fz.slca'로 읽어도 핵심 'slca'만 남겨 'Sica'와 비교 가능.
    """
    s = re.sub(r"\[.*?\]", "", name).strip()
    # 점/공백/하이픈으로 구분된 첫 토큰이 클랜태그면 제거
    # Fz.Karpe → Karpe, V1 Ichi → Ichi, CLRS.LL → LL
    # 단 핵심 이름 자체에 점이 있으면 보존
    parts = re.split(r"[.\s]+", s, maxsplit=1)
    if len(parts) == 2 and len(parts[0]) <= 6:
        # 첫 토큰이 6자 이하면 클랜태그로 간주 (V1, Fz, CLRS, 4uNi 등)
        return parts[1]
    return s.lstrip("-").strip()


def fuzzy_match(ign: str, candidates: list) -> str:
    """IGN을 후보 표준명 리스트에서 가장 유사한 것에 매칭.

    우선순위: ① 정확 정규화 매칭 → ② 클랜태그 제거 후 매칭 → ③ difflib 유사도.
    매칭 없으면 None.
    """
    if not candidates:
        return None
    norm_ign = normalize(ign)
    # ① 정규화 정확 매칭
    norm_map = {normalize(c): c for c in candidates}
    if norm_ign in norm_map:
        return norm_map[norm_ign]
    # ② 클랜태그 제거 후 매칭 (Fz.slca → slca → Sica와 비교)
    stripped = normalize(_strip_clan_prefix(ign))
    if stripped and stripped in norm_map:
        return norm_map[stripped]
    # ③ 퍼지 매칭 (OCR 오타: slca↔sica, l↔i 교체 등)
    # 임계값 0.75로 낮춰 1-2글자 오타까지 포용 (slca vs sica = 0.75)
    targets = list(norm_map.keys())
    best = difflib.get_close_matches(stripped, targets, n=1, cutoff=0.75)
    if not best:
        best = difflib.get_close_matches(norm_ign, targets, n=1, cutoff=0.75)
    if best:
        return norm_map[best[0]]
    return None


def best_guess(ign: str, candidates: list, min_ratio: float = 0.6):
    """fuzzy_match가 실패했을 때 가장 유사한 후보를 '추측'으로 반환.

    임계값(0.5) 이상의 유사도를 가진 가장 가까운 후보와 그 비율을 반환.
    알파벳이 일부만 맞아도(예: 오타, 부분 인식) 원본 닉네임을 추측해 매칭.
    반환: (후보 표준명, 유사도) 또는 None (0.5 미만이면 아예 단념).
    """
    if not candidates:
        return None
    stripped = normalize(_strip_clan_prefix(ign))
    norm_ign = normalize(ign)
    norm_map = {normalize(c): c for c in candidates}
    targets = list(norm_map.keys())
    # stripped와 norm_ign 둘 다에서 가장 높은 유사도
    ratios = difflib.SequenceMatcher(None, stripped, "").quick_ratio()  # warmup
    best_t, best_r = None, 0.0
    for t in targets:
        r1 = difflib.SequenceMatcher(None, stripped, t).ratio()
        r2 = difflib.SequenceMatcher(None, norm_ign, t).ratio()
        r = max(r1, r2)
        if r > best_r:
            best_r, best_t = r, t
    if best_t and best_r >= min_ratio:
        return (norm_map[best_t], round(best_r, 2))
    return None
