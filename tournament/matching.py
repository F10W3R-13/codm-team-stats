"""IGN(게임 내 이름) → DB 선수 매칭.

OCR 인식명은 클랜태그/특수문자/대소문자가 뒤섞여 있어 정규화 후 비교.
우선순위: ① 정확 매칭(alias/표준명) ② 정규화 매칭 ③ 퍼지(1글자 차이).
OCR alias 매칭 스킬(.agents/skills/ocr-alias-matching)과 동일 철학.
"""
import difflib

import _path_setup  # noqa: F401  (부모 metrics.py 경로 보정 — 일관성)


def normalize(name: str) -> str:
    """이름 정규화: 소문자화 + 클랜태그/특수문자 제거.

    [CLAN]Ace_Pro_99 → acepro99
    """
    import re
    s = name.lower().strip()
    s = re.sub(r"\[.*?\]", "", s)         # 클랜태그 [XXX]
    s = re.sub(r"[^a-z0-9]", "", s)       # 알파벳+숫자만
    return s


def fuzzy_match(ign: str, candidates: list) -> str:
    """IGN을 후보 표준명 리스트에서 가장 유사한 것에 매칭.

    우선순위: 정확 정규화 매칭 → difflib 유사도(임계값 0.8).
    매칭 없으면 None.
    """
    if not candidates:
        return None
    norm_ign = normalize(ign)
    # ① 정규화 정확 매칭
    norm_map = {normalize(c): c for c in candidates}
    if norm_ign in norm_map:
        return norm_map[norm_ign]
    # ② 퍼지 매칭 (1글자 오타 등)
    best = difflib.get_close_matches(norm_ign, list(norm_map.keys()), n=1, cutoff=0.8)
    if best:
        return norm_map[best[0]]
    return None
