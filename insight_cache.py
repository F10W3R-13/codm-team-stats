# 인사이트 캐싱
#
# GPT 호출 비용/지연을 줄이기 위해 결과를 메모리에 캐싱.
# 전략:
#   - TTL 기반 만료 (기본 1시간)
#   - 새 매치 기록 시 관련 캐시 무효화 (stats_repo.save_match 호출 시)
#   - 코칭 브레인 지문 연동: 저장 시점 지문 ≠ 현재 지문이면 캐시 미스
#     (코치가 코칭 브레인 수정 → 옛날 지식이 캐시에서 서비스되는 것 방지)
#   - 캐시 키 = 인사이트 종류 + 대상 ID + 언어
#
# 단순 in-memory 캐시. 단일 프로세스 가정. (다중 워커면 Redis로 교체 필요)

import time
from threading import Lock

# 기본 TTL (초) — 1시간
DEFAULT_TTL = 3600

_lock = Lock()
# {(kind, target, lang): (insight_text, expire_timestamp, fingerprint)}
# fingerprint = 저장 시점의 코칭 브레인 지문 (None이면 지문 검사 안 함)
_cache = {}


def get(kind: str, target: str, lang: str, ttl: int = DEFAULT_TTL,
        fingerprint: str = None) -> str | None:
    """캐시에서 인사이트 조회. 만료·지문 불일치·없으면 None.

    fingerprint: 현재 코칭 브레인 지문. None이면 지문 검사 생략 (기존 동작).
                 캐시에 저장된 지문과 다르면 캐시 미스 (코칭 브레인 변경 감지).
    """
    key = (kind, target, lang)
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        text, expire_at, stored_fp = entry
        # TTL 만료
        if time.time() > expire_at:
            _cache.pop(key, None)
            return None
        # 코칭 브레인 지문 불일치 (캐시는 옛날 지식 기반 → 재생성 필요)
        if fingerprint is not None and stored_fp is not None and stored_fp != fingerprint:
            _cache.pop(key, None)
            return None
        return text


def set(kind: str, target: str, lang: str, insight: str, ttl: int = DEFAULT_TTL,
        fingerprint: str = None) -> None:
    """인사이트를 캐시에 저장. fingerprint는 저장 시점 코칭 브레인 지문."""
    if not insight:
        return
    key = (kind, target, lang)
    with _lock:
        _cache[key] = (insight, time.time() + ttl, fingerprint)


def invalidate(kind: str = None, target: str = None) -> int:
    """캐시 무효화. 필터 조건에 맞는 항목 삭제.

    kind=None, target=None 이면 전체 무효화.
    반환: 삭제된 항목 수.
    """
    removed = 0
    with _lock:
        keys_to_remove = []
        for k in _cache:
            if kind is not None and k[0] != kind:
                continue
            if target is not None and k[1] != target:
                continue
            keys_to_remove.append(k)
        for k in keys_to_remove:
            _cache.pop(k, None)
            removed += 1
    return removed


def invalidate_all() -> int:
    """전체 캐시 무효화 (새 매치 기록 시 호출). 반환: 삭제된 수."""
    with _lock:
        n = len(_cache)
        _cache.clear()
        return n


def stats() -> dict:
    """캐시 상태 (디버그용)."""
    with _lock:
        return {"entries": len(_cache), "keys": [f"{k[0]}:{k[1]}:{k[2]}" for k in list(_cache.keys())[:10]]}
