# 인사이트 캐싱
#
# GPT 호출 비용/지연을 줄이기 위해 결과를 메모리에 캐싱.
# 전략:
#   - TTL 기반 만료 (기본 1시간)
#   - 새 매치 기록 시 관련 캐시 무효화 (stats_repo.save_match 호출 시)
#   - 캐시 키 = 인사이트 종류 + 대상 ID + 언어
#
# 단순 in-memory 캐시. 단일 프로세스 가정. (다중 워커면 Redis로 교체 필요)

import time
from threading import Lock

# 기본 TTL (초) — 1시간
DEFAULT_TTL = 3600

_lock = Lock()
# {(kind, target, lang): (insight_text, expire_timestamp)}
_cache = {}


def get(kind: str, target: str, lang: str, ttl: int = DEFAULT_TTL) -> str | None:
    """캐시에서 인사이트 조회. 만료됐거나 없으면 None."""
    key = (kind, target, lang)
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        text, expire_at = entry
        if time.time() > expire_at:
            _cache.pop(key, None)
            return None
        return text


def set(kind: str, target: str, lang: str, insight: str, ttl: int = DEFAULT_TTL) -> None:
    """인사이트를 캐시에 저장."""
    if not insight:
        return
    key = (kind, target, lang)
    with _lock:
        _cache[key] = (insight, time.time() + ttl)


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
