# insight_cache fingerprint 연동 테스트
#
# 실행: pytest test_insight_cache_fingerprint.py -v
#
# 검증:
#  - fingerprint 없으면 기존 동작 유지 (하위 호환)
#  - 같은 fingerprint → 캐시 hit
#  - 다른 fingerprint → 캐시 미스 (코칭 브레인 변경 감지)
#  - fingerprint=None (한쪽만) → 지문 검사 안 함 (miss 아님)
#  - coaching_brain_loader.fingerprint() 정상 동작

import time

import insight_cache
import coaching_brain_loader as loader


def setup_function(_):
    """각 테스트 전 캐시 초기화."""
    insight_cache._cache.clear()


def test_no_fingerprint_backward_compatible():
    """fingerprint 안 넘기면 기존 동작 (TTL만)."""
    insight_cache.set("player", "alice", "ko", "인사이트1")
    assert insight_cache.get("player", "alice", "ko") == "인사이트1"


def test_same_fingerprint_cache_hit():
    """같은 지문으로 set/get → hit."""
    insight_cache.set("player", "bob", "ko", "인사이트2", fingerprint="fp_v1")
    assert insight_cache.get("player", "bob", "ko", fingerprint="fp_v1") == "인사이트2"


def test_different_fingerprint_cache_miss():
    """저장 시점 지문 ≠ 현재 지문 → miss."""
    insight_cache.set("player", "carol", "ko", "옛날 인사이트", fingerprint="fp_v1")
    # 코칭 브레인이 수정돼 지문이 바뀜
    assert insight_cache.get("player", "carol", "ko", fingerprint="fp_v2") is None


def test_miss_removes_stale_entry():
    """지문 불일치 miss 시 캐시 엔트리 제거 (다음 set가 정상 저장)."""
    insight_cache.set("player", "dave", "ko", "옛날", fingerprint="fp_v1")
    assert insight_cache.get("player", "dave", "ko", fingerprint="fp_v2") is None
    # stale 엔트리 제거됐는지 — 새 set 없이 get(None 지문)도 None이어야
    assert insight_cache.get("player", "dave", "ko") is None


def test_stored_fingerprint_none_skips_check():
    """저장 시 fingerprint 안 넘김(stored=None) → 조회 시 지문 검사 안 함."""
    insight_cache.set("player", "eve", "ko", "노프린트")  # fingerprint=None
    # 조회에서 fingerprint 넘겨도 stored가 None이면 miss 아님
    assert insight_cache.get("player", "eve", "ko", fingerprint="anything") == "노프린트"


def test_query_fingerprint_none_skips_check():
    """저장 시 지문 있어도 조회에서 fingerprint 안 넘기면 검사 안 함."""
    insight_cache.set("player", "frank", "ko", "v1지식", fingerprint="fp_v1")
    assert insight_cache.get("player", "frank", "ko") == "v1지식"


def test_ttl_still_works():
    """TTL 만료는 지문과 무관하게 동작."""
    insight_cache.set("player", "grace", "ko", "단명", ttl=0,
                      fingerprint="fp_v1")
    time.sleep(0.01)  # TTL 0 + 약간의 시간
    assert insight_cache.get("player", "grace", "ko", fingerprint="fp_v1") is None


def test_loader_fingerprint_returns_string():
    """fingerprint()가 비지 않은 문자열(또는 빈 폴더 시 '') 반환."""
    fp = loader.fingerprint()
    assert isinstance(fp, str)
    # 코칭 브레인이 있으므로 비지 않아야 함
    assert fp, "fingerprint()가 빈 문자열 — knowledge 폴더 인식 실패"


def test_loader_fingerprint_stable():
    """변경 없으면 fingerprint() 값 안정."""
    a = loader.fingerprint()
    b = loader.fingerprint()
    assert a == b
